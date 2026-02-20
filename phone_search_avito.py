import random
import time
import re
import pandas as pd
import json
import os
import signal, atexit
import asyncio
from playwright.async_api import (
    async_playwright,
    Page as AsyncPage,
    Error as PWError,
    TimeoutError as PWTimeoutError,
)
from urllib.parse import urljoin
from base64 import b64decode
from io import BytesIO
from PIL import Image
from pathlib import Path


class AvitoParse:
    def __init__(self, input_file: str, max_num_firm: int, gui_works: bool):
        self.input_file = Path(input_file)  # Имя Excel/CSV-файла с ссылками на объявления
        self.max_num_firm = max_num_firm

        self.gui_works = gui_works
        self.enter_event = asyncio.Event() if gui_works else None
        self.use_gui_input = gui_works

        self.phones_map = {}  # Инициализация словаря для результатов
        self.pending_queue = []  # Инициализация списка для отложенных

        self.CONCURRENCY = 3  # Количество одновременно открытых вкладок браузера (2–3 оптимально)

        self.OUT_DIR = Path("avito_phones_playwright")  # Рабочая директория парсера
        self.OUT_DIR.mkdir(exist_ok=True)  # mkdir - создание папки, если её нет
        self.IMG_DIR = self.OUT_DIR / "phones"  # Сюда будут сохраняться PNG с номерами
        self.IMG_DIR.mkdir(exist_ok=True)
        self.DEBUG_DIR = (self.OUT_DIR / "debug")  # Сюда складываем скриншоты и html проблемных объявлений
        self.DEBUG_DIR.mkdir(exist_ok=True)

        self.OUT_JSON = (
            self.OUT_DIR / "phones" / "phones_map.json"
        )  # Основной результат: {url: data:image... или тег __SKIP_*__}
        self.PENDING_JSON = (
            self.OUT_DIR / "phones" / "pending_review.json"
        )  # Ссылки «на модерации» и с лимитом контактов (в разработке на будущее)
        self.SAVE_DATA_URL = True  # True = сохраняем data:image в JSON; False = сохраняем PNG в IMG_DIR

        self.HEADLESS = False  # False = браузер виден (можно логиниться руками)

        # ПОВЕДЕНИЕ (МЕДЛЕННЕЕ И ЕСТЕСТВЕНЕЕ)
        self.PAGE_DELAY_BETWEEN_BATCHES = (1.2, 2.4)  # Пауза между партиями ссылок (раньше была (2.0, 4.0))
        self.NAV_STAGGER_BETWEEN_TABS = (0.45, 1.0)  # Пауза перед открытием КАЖДОЙ вкладки (чтобы не стартовали все разом)
        self.POST_NAV_IDLE = (0.35, 0.7)  # Небольшая «заминка» после загрузки страницы перед действиями
        self.BATCH_CONCURRENCY_JITTER = True  # Иногда работаем 2 вкладками вместо 3 для естественности

        self.CLOSE_STAGGER_BETWEEN_TABS = (0.25, 0.55)  # Вкладки закрываем с небольшой случайной паузой

        # ВХОДНОЙ ФАЙЛ С ССЫЛКАМИ
        self.INPUT_SHEET = None  # Имя листа в Excel; None = использовать все листы
        self.URL_COLUMN = None  # Имя колонки со ссылками; None = искать ссылки во всех колонках


        # БАЗОВЫЕ ТАЙМАУТЫ
        self.CLICK_DELAY = 1.5  # Базовая задержка в секундах перед ожиданием появления номера телефона

        self.NAV_TIMEOUT = 35_000  # Таймаут загрузки страницы, мс (35 секунд)

        # ЧЕЛОВЕЧНОСТЬ / АНТИБАН-ПОВЕДЕНИЕ
        self.HUMAN = {
            "pre_page_warmup_scrolls": (1, 3),  # Сколько раз «прогрелись» скроллом после открытия страницы
            "scroll_step_px": (250, 900),  # Диапазон шага скролла в пикселях
            "scroll_pause_s": (0.32, 0.75),  # Пауза между скроллами
            "hover_pause_s": (0.34, 0.64),  # Пауза при наведении на элементы
            "pre_click_pause_s": (0.20, 0.38),  # Короткая пауза перед кликом
            "post_click_pause_s": (0.22, 0.46),  # Пауза сразу после клика
            "mouse_wiggle_px": (4, 12),  # Амплитуда «подёргивания» мыши
            "mouse_wiggle_steps": (2, 5),  # Сколько шагов «подёргиваний» мыши
            "between_actions_pause": (0.30, 0.45),  # Пауза между действиями (скролл, клик, наведение)
            "click_delay_jitter": (
                self.CLICK_DELAY * 0.9,
                self.CLICK_DELAY * 1.45,
            ),  # Случайная задержка после клика по телефону (min и max)
        }

    async def press_and_rel(self):
        """Ожидает нажатия Enter из GUI или консоли"""
        if self.gui_works:
            # Ждем, пока GUI пошлет событие
            print("Ожидаю нажатия Enter из GUI...")
            await self.wait_for_gui_enter()
        else:
            # Старый способ - ждем из консоли
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, input, "Готов? Нажми Enter в консоли: ")

    async def wait_for_gui_enter(self):
        """Асинхронно ждет события от GUI"""
        while not self.enter_event.is_set():
            await asyncio.sleep(0.1)
        self.enter_event.clear()  # Сбрасываем для следующего использования

    def trigger_enter_from_gui(self):
        """Вызывается из GUI для имитации нажатия Enter"""
        if self.gui_works and hasattr(self, "enter_event"):
            self.enter_event.set()

    async def human_sleep(self, a: float, b: float):
        """
        Приостанавливает выполнение на случайное количество секунд в диапазоне [a, b].
        Используется для имитации человеческих пауз и предотвращения блокировок!
        """
        await asyncio.sleep(random.uniform(a, b))

    async def human_scroll_jitter(self, page: AsyncPage, count: int | None = None):
        """
        Имитирует человеческий скроллинг страницы.
        Выполняет случайное количество скроллов со случайным шагом и направлением.
        page: Playwright Page объект
        count: Количество скроллов
        """
        if count is None:
            count = random.randint(*self.HUMAN["pre_page_warmup_scrolls"])  # Случайное количество скролов
        try:
            height = await page.evaluate("() => document.body.scrollHeight") or 3000
            for _ in range(count):
                step = random.randint(*self.HUMAN["scroll_step_px"])
                direction = 1 if random.random() > 0.25 else -1
                y = max(0, min(
                        height,
                        await page.evaluate("() => window.scrollY") + step * direction,
                    ),
                )
                await page.evaluate("y => window.scrollTo({top: y, behavior: 'smooth'})", y)  # Плавный скролл через JavaScript
                await self.human_sleep(*self.HUMAN["scroll_pause_s"])
        except Exception:
            pass

    async def human_wiggle_mouse(self, page: AsyncPage, x: float, y: float):
        """
        Имитирует мелкие случайные движения мыши вокруг указанных координат.
        Добавляет реалистичности наведению мыши.
        """
        steps = random.randint(*self.HUMAN["mouse_wiggle_steps"])  # Шаги подергиваний
        amp = random.randint(*self.HUMAN["mouse_wiggle_px"])  # Амплитуда подергиваний
        for _ in range(steps):
            dx = random.randint(-amp, amp)  # Смещения x и y
            dy = random.randint(-amp, amp)
            try:
                await page.mouse.move(x + dx, y + dy)
            except Exception:
                pass
            await self.human_sleep(*self.HUMAN["between_actions_pause"])  # Пауза между движениями

    async def human_hover(self, page: AsyncPage, el):
        """
        Имитирует человеческое наведение мыши на элемент.
        Вычисляет центр элемента, добавляет случайное смещение и вибрацию мыши.
        el: Элемент для наведения
        """
        try:
            box = await el.bounding_box()  # Получение координат и размеров элемента
            if not box:
                return
            cx = box["x"] + box["width"] * random.uniform(0.35, 0.65)  # Координаты x, y в пределах элемента
            cy = box["y"] + box["height"] * random.uniform(0.35, 0.65)
            await page.mouse.move(cx, cy)
            await self.human_wiggle_mouse(page, cx, cy)
            await self.human_sleep(*self.HUMAN["hover_pause_s"])
        except Exception:
            pass

    async def safe_get_content(self, page: AsyncPage) -> str:
        """
        Безопасно получает HTML-содержимое страницы с одной попыткой повторения.
        Return: HTML-код страницы или пустая строка при ошибке
        """
        for _ in range(2):
            try:
                return (await page.content()).lower()
            except PWError:  # Обработка ошибок Playwright
                await asyncio.sleep(1)
        return ""

    def get_avito_id_from_url(self, url: str) -> str:
        """
        Извлекает ID объявления из URL Avito.
        Arg: url объявления Avito
        Return: ID объявления или timestamp если ID не найден
        """
        m = re.search(r"(\d{7,})", url)
        return m.group(1) if m else str(int(time.time()))

    async def is_limit_contacts_modal(self, page: AsyncPage) -> bool:
        """
        Проверяет наличие модального окна о лимите контактов.
        Return: True если обнаружено сообщение о лимите контактов
        """
        html = await self.safe_get_content(page)
        if "закончился лимит" in html and "просмотр контактов" in html:
            return True
        try:
            loc = page.locator("text=Купить контакт").first
            if await loc.is_visible():
                return True
        except Exception:
            pass
        return False

    async def is_captcha_or_block(self, page: AsyncPage) -> bool:
        """Быстрая проверка на блокировку"""
        try:
            url = (page.url or "").lower()
        except PWError:
            url = ""
        html = await self.safe_get_content(page)
        return (
            "captcha" in url
            or "firewall" in url
            or "доступ с вашего ip-адреса временно ограничен" in html
        )

    async def classify_ad_status(self, page: AsyncPage) -> str:
        """
        Определяет статус объявления по содержимому страницы.
        Return: Строка с статусом: 'ok' | 'no_calls' | 'on_review' | 'unavailable' | 'blocked' | 'limit'
        """
        # КЛАССИФИКАЦИЯ СТРАНИЦЫ ОБЪЯВЛЕНИЯ
        self.NO_CALLS_MARKERS = [
            "без звонков",
            "пользователь предпочитает сообщения",
        ]
        self.MODERATION_MARKERS = [
            "оно ещё на проверке",
            "объявление на проверке",
            "объявление ещё на проверке",
            "сайт временно недоступен",
        ]
        self.UNAVAILABLE_MARKERS = [
            "объявление не посмотреть",
            "объявление снято с продажи",
            "объявление снято с публикации",
            "объявление удалено",
            "объявление закрыто",
            "объявление истекло",
            "объявление больше не доступно",
            "пользователь его удалил",
            "оно заблокировано после проверки",
            "о квартире",
        ]

        if await self.is_captcha_or_block(page):
            return "blocked"

        html = await self.safe_get_content(page)

        # Если не удалось получить контент, пробуем еще раз с задержкой
        if not html or len(html) < 100:  # Если HTML слишком короткий или пустой
            await self.human_sleep(0.4, 0.8)
            html = await self.safe_get_content(page)

        # Проверка лимита контактов
        if await self.is_limit_contacts_modal(page):
            return "limit"

        try:
            if await page.locator("text=Сайт временно недоступен").first.is_visible():
                page.reload()
        except Exception:
            pass

        # Проверка модерации, доступности, режима "без звонков"
        MARKERS = [
            self.NO_CALLS_MARKERS,
            self.MODERATION_MARKERS,
            self.UNAVAILABLE_MARKERS,
        ]
        text_makers = ["no_calls", "on_review", "unavailable"]
        for i in range(len(MARKERS)):
            if any(m in html for m in MARKERS[i]):
                return text_makers[i]

        try:
            if await page.locator("text=Без звонков").first.is_visible():
                return "no_calls"
        except Exception:
            pass

        return "ok"  # Возвращаем 'ok', если проблем не обнаружено

    def load_progress(self, path: Path) -> dict[str, str]:
        """
        Загружает прогресс парсинга из JSON файла.
        Return: Словарь с прогрессом или пустой словарь при ошибке
        """
        if path.exists():  # Проверка существования файла
            try:
                return json.loads(path.read_text(encoding="utf-8"))  # Загрузка JSON данных
            except Exception as e:
                print(f"Не удалось прочитать существующий прогресс: {e}")
        return {}

    def load_pending(self, path: Path) -> list[str]:
        """
        Загружает список отложенных ссылок из JSON файла.
        Return: Список URL или пустой список при ошибке
        """
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return [u for u in data if isinstance(u, str)]
            except Exception:
                pass
        return []

    def save_pending(self, path: Path, urls: list[str]):
        """
        Сохраняет список отложенных ссылок в JSON файл.
        """
        urls = list(dict.fromkeys(urls))  # Уникальные, порядок сохраняем
        self.atomic_write_json(path, urls)

    def read_urls_from_excel_or_csv(self, sheet=None, url_column=None) -> list[str]:
        """
        Читает URL объявлений из Excel или CSV файла.
        Args:
            sheet: Имя листа Excel (None для всех листов)
            url_column: Имя колонки с URL (None для поиска во всех колонках)
        Return: Список уникальных URL
        """
        if not self.input_file.exists():
            raise FileNotFoundError(f"Файл не найден: {self.input_file}")

        url_re = re.compile(r'https?://(?:www\.)?avito\.ru/[^\s"]+')
        urls: list[str] = []

        if self.input_file.suffix.lower() in {".xlsx", ".xls"}:
            xls = pd.ExcelFile(self.input_file)  # Создание объекта Excel
            sheets = (
                [sheet] if sheet is not None else xls.sheet_names
            )  # Определение листов для обработки
            for sh in sheets:
                df = xls.parse(sh, dtype=str)  # Чтение листа как DataFrame
                if url_column and url_column in df.columns:
                    col = (
                        df[url_column].dropna().astype(str)
                    )  # Получение колонки и удаление пустых значений
                    urls.extend(col.tolist())  # Добавление значений в список URL
                else:  # Если колонка не указана
                    for col in df.columns:
                        s = df[col].dropna().astype(str)  # Получение колонки как строки
                        for val in s:
                            urls.extend(url_re.findall(val))  # Поиск URL в значении
        elif self.input_file.suffix.lower() in {".csv", ".txt"}:
            df = pd.read_csv(self.input_file, dtype=str, sep=None, engine="python")
            if url_column and url_column in df.columns:
                col = df[url_column].dropna().astype(str)
                urls.extend(col.tolist())
            else:
                for col in df.columns:
                    s = df[col].dropna().astype(str)
                    for val in s:
                        urls.extend(url_re.findall(val))
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {self.input_file.suffix}")

        cleaned = []
        seen = set()  # Инициализация множества для отслеживания уникальных URL
        for u in urls:
            u = u.strip()
            if not u.startswith("http"):
                u = urljoin("https://www.avito.ru", u)
            u = u.split("#", 1)[0]  # Удаление якорей
            u = u.split("?", 1)[0]  # Удаление параметров запроса
            if u not in seen:  # Проверка уникальности URL
                seen.add(u)
                cleaned.append(u)

        print(f"Прочитано {len(cleaned)} URL из файла: {self.input_file.name}")
        return cleaned

    def atomic_write_json(self, path: Path, data):
        """
        Атомарно записывает данные в JSON файл с использованием временного файла.
        Arg: data: Данные для записи
        """
        tmp = path.with_suffix(
            path.suffix + f".tmp_{int(time.time()*1000)}_{random.randint(1000,9999)}"
        )  # Создание уникального имени временного файла
        payload = json.dumps(data, ensure_ascii=False, indent=2)  # Преобразование данных в JSON строку
        tmp.write_text(payload, encoding="utf-8")
        attempts, delay = 10, 0.1  # Настройки попыток замены файла
        for _ in range(attempts):  # Цикл попыток замены файла
            try:
                os.replace(tmp, path)  # Атомарная замена файла
                return  # Выход при успехе
            except Exception:
                time.sleep(delay)
                delay = min(delay * 1.7, 1.0)
        try:
            path.write_text(payload, encoding="utf-8")
        except Exception as e:
            print(f"Критическая ошибка записи прогресса: {e}")

    async def try_click(self, page: AsyncPage, el) -> bool:
        """
        Пытается кликнуть на элемент различными способами.
        Return: True если клик выполнен успешно
        """
        await self.human_hover(page, el)
        await self.human_sleep(*self.HUMAN["pre_click_pause_s"])
        try:
            await el.click()
            await self.human_sleep(*self.HUMAN["post_click_pause_s"])
            return True
        except Exception:
            try:  # Попытка альтернативного клика через JavaScript
                box = await el.bounding_box() or {}
                if box:
                    await page.mouse.move(
                        box.get("x", 0) + 6, box.get("y", 0) + 6
                    )  # Перемещение мыши к элементу со смещением
                    await self.human_sleep(*self.HUMAN["pre_click_pause_s"])
                await page.evaluate("(e)=>e.click()", el)  # Клик через JS
                await self.human_sleep(*self.HUMAN["post_click_pause_s"])
                return True
            except Exception:
                return False

    async def click_show_phone_on_ad(self, page: AsyncPage, update_callback=None) -> bool:
        """
        Пытается найти и кликнуть на кнопку "Показать телефон" в объявлении.
        Return: True если кнопка найдена и клик выполнен
        """
        await self.human_scroll_jitter(page)

        # Дополнительная проверка после скролла
        if await self.is_captcha_or_block(page):
            print("Обнаружена капча или блокировка после скролла")
            if update_callback:
                update_callback("Обнаружена капча или блокировка")
            return False

        for anchor in [
            "[data-marker='seller-info']",
            "[data-marker='item-sidebar']",
            "section:has(button[data-marker*='phone'])",
            "section:has(button:has-text('Показать'))",
        ]:
            try:
                anchor_element = await page.query_selector(anchor)  # Поиск якорного элемента
                if anchor_element:
                    await anchor_element.scroll_into_view_if_needed()  # Прокрутка к элементу, если элемент найден
                    await self.human_sleep(*self.HUMAN["scroll_pause_s"])
                    break
            except Exception:
                pass

        selector_groups = [  # data-marker селекторы
            "button[data-marker='item-phone-button']",
            "button[data-marker*='item-phone-button/card']",
            "button[data-marker*='phone-button']",
            "button[data-marker='phone-button/number']",
            "button:has-text('Показать телефон')",
        ]

        for sel in selector_groups:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible() and await el.is_enabled():
                    if await self.try_click(page, el):
                        print("Нажали 'Показать телефон'")
                        if update_callback:
                            update_callback("Нажали 'Показать телефон'")
                        # Ждем номер телефона
                        try:
                            await page.wait_for_selector("img[data-marker='phone-popup/phone-image']", timeout=3000)
                        except Exception:
                            pass

                        # Проверяем, появилась ли модалка авторизации
                        if await page.query_selector("[data-marker='login-form']"):
                            print("Обнаружена модалка авторизации после клика")
                            return False
                        return True
            except Exception:
                continue

        print("Кнопка 'Показать телефон' не найдена.")
        return False

    async def extract_phone_data_uri_on_ad(self, page: AsyncPage) -> str | None:
        """
        Извлекает data:image URI с изображением телефона со страницы.
        Return: data:image URI или None если изображение не найдено
        """
        try:  # Попытка поиска изображения телефона
            img = await page.query_selector("img[data-marker='phone-popup/phone-image']")  # Поиск изображения по data-maker
        except PWError:
            img = None

        if not img or not await img.is_visible():
            print("Картинка с номером не найдена.")
            return None

        # Получаем src атрибут
        try:
            src = await img.get_attribute("src") or ""
        except Exception:
            img = None
        if not src.startswith("data:image"):
            print(f"src не data:image, а: {src[:60]}...")
            return None
        return src

    def save_phone_png_from_data_uri(self, data_uri: str, file_stem: str) -> str | None:
        """
        Сохраняет изображение телефона из data:image URL в PNG файл.
        Args:
            data_uri: Строка data:image с изображением
            file_stem: Имя файла без расширения
        Return: Путь к сохраненному файлу или None при ошибке
        """
        try:
            _, b64_data = data_uri.split(",", 1)  # Разделение data:image URI и получение base64 данных
            raw = b64decode(b64_data)  # Декодирование base64 в бинарные данные
            image = Image.open(BytesIO(raw)).convert("RGB")  # Создание изображения из бинарных данных
            file_name = f"{file_stem}.png"
            out_path = self.IMG_DIR / file_name  # Путь к файлу
            image.save(out_path)
            print(f"PNG сохранён: {out_path}")
            return str(out_path)
        except Exception as e:
            print(f"Ошибка при сохранении PNG: {e}")
            return None

    async def process_urls_with_pool(self, context, urls: list[str], pending_queue: list[str], update_callback=None):
        """
        Обрабатывает список URL с использованием пула страниц.
        Args:
            context: Контекст браузера Playwright
            urls: Список URL для обработки
            pending_queue: Список для добавления отложенных URL
        """
        if not urls:
            return

        # Пул создаём максимального размера; часть вкладок можем не использовать
        pages = [await context.new_page() for _ in range(self.CONCURRENCY)]
        try:
            it = iter(urls)  # Итератор по URL
            while True:
                # Иногда делаем партию меньше максимума, чтобы поведение было менее ровным
                batch_size = (
                    random.randint(max(1, self.CONCURRENCY - 1), self.CONCURRENCY)
                    if self.BATCH_CONCURRENCY_JITTER
                    else self.CONCURRENCY
                )
                batch_pages = pages[:batch_size]

                batch = []  # Инициализация списка для текущей партии
                for p in batch_pages:  # Цикл по страницам партии
                    try:
                        url = next(it)
                    except StopIteration:
                        return
                    batch.append((url, p))

                    # Не открываем все вкладки синхронно — ставим паузу перед каждым goto
                    await self.human_sleep(*self.NAV_STAGGER_BETWEEN_TABS)
                    try:
                        await p.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
                    except PWTimeoutError:
                        print(f"Таймаут: {url}")
                        continue

                    # Лёгкая «заминка» после навигации + пара скроллов(скрыто)
                    await self.human_sleep(*self.POST_NAV_IDLE)
                    # await self.human_scroll_jitter(p, count=random.randint(1, 2))

                # Статус + модалки + попытка клика
                for url, p in batch:
                    # await self.human_sleep(*self.HUMAN["between_actions_pause"])

                    st = await self.classify_ad_status(p)

                    # Обработка всех статусных кейсов
                    if st == "blocked":
                        print(f"Капча/блок: {url}")
                        continue
                    if st == "limit":
                        print(f"Лимит контактов: {url}")
                        await self.on_result(url, "__SKIP_LIMIT__")
                        pending_queue.append(url)
                        continue
                    if st == "unavailable":
                        print(f"Недоступно/закрыто: {url}")
                        await self.on_result(url, "__SKIP_UNAVAILABLE__")
                        continue
                    if st == "no_calls":
                        print(f"Без звонков: {url}")
                        await self.on_result(url, "__SKIP_NO_CALLS__")
                        continue
                    if st == "on_review":
                        print(f"На проверке: {url}")
                        await self.on_result(url, "__SKIP_ON_REVIEW__")
                        pending_queue.append(url)
                        continue

                    # Пытаемся кликнуть на кнопку телефона
                    if not await self.click_show_phone_on_ad(p, update_callback):
                        print(f"Не удалось кликнуть на {url}")
                        if update_callback:
                            update_callback(f"Не удалось кликнуть на {url}")
                        await self.dump_debug(p, url)
                        continue  # Переходим к следующему URL

                # Ждём картинку телефона
                await self.human_sleep(*self.HUMAN["click_delay_jitter"])
                for url, p in batch:
                    await self.human_sleep(*self.HUMAN["between_actions_pause"])
                    if await self.is_captcha_or_block(p):  # Проверка модалок и блокировок
                        continue  # Пропуск объявления
                    data_uri = await self.extract_phone_data_uri_on_ad(p)
                    if not data_uri:
                        continue
                    if self.SAVE_DATA_URL:
                        value = data_uri
                    else:
                        avito_id = self.get_avito_id_from_url(url)
                        out_path = self.save_phone_png_from_data_uri(data_uri, avito_id)
                        if not out_path:  # Проверка успешности сохранения
                            continue
                        value = out_path  # Использование пути к файлу
                    await self.on_result(url, value)  # Сохранение результата
                    print(f"{url} -> {'[data:image...]' if self.SAVE_DATA_URL else value}")
                    if update_callback:
                        update_callback(f"{url} -> {'[data:image...]' if self.SAVE_DATA_URL else value}")

                await self.human_sleep(*self.PAGE_DELAY_BETWEEN_BATCHES)  # Пауза между партиями
        finally:
            for p in pages:
                try:
                    await self.human_sleep(*self.CLOSE_STAGGER_BETWEEN_TABS)
                    await p.close()  # Закрытие страницы
                except Exception:
                    pass

    def flush_progress(self):
        """
        Внутренняя функция для сохранения прогресса.
        Вызывается при завершении программы.
        """
        try:
            self.atomic_write_json(self.OUT_JSON, self.phones_map)  # Сохранение основного прогресса
            self.save_pending(self.PENDING_JSON, self.pending_queue)  # Сохранение отложенных ссылок
        except Exception as e:
            print(f"Ошибка записи прогресса: {e}")

    async def on_result(self, url: str, value: str | None):
        """
        Функция обратного вызова для сохранения результатов.
        Args:
            url: URL объявления
            value: data:image..., путь к PNG или __SKIP_*__
        """
        if value is None:
            return
        self.phones_map[url] = value
        self.atomic_write_json(self.OUT_JSON, self.phones_map)  # Сохранение прогресса

    async def dump_debug(self, page: AsyncPage, url: str):
        """
        Сохраняет скриншот и HTML проблемной страницы для отладки.
        """
        try:
            ad_id = self.get_avito_id_from_url(url)  # Получение ID объявления из URL
            png_path = self.DEBUG_DIR / f"{ad_id}.png"  # Пути
            # html_path = self.DEBUG_DIR / f"{ad_id}.html"
            await page.screenshot(path=str(png_path), full_page=True)  # Создание скриншота всей страницы
            # html = await self.safe_get_content(page)  # Получение HTML содержимого
            # html_path.write_text(html, encoding="utf-8")
            print(f"Debug сохранён: {png_path.name}")  # Со скриншотом {png_path.name}, {html_path.name}
        except Exception as e:
            print(f"Не удалось сохранить debug: {e}")

    def get_random_user_agent(self):
        """Скрываем автоматизацию с помощью захода с разных систем"""
        user_agents = user_agents = [
            # Windows Chrome - разные версии
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.85 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_7_10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        ]
        return random.choice(user_agents)

    async def parse_main(self, update_callback=None):
        """Парсинг сайта"""

        urls = self.read_urls_from_excel_or_csv(self.INPUT_SHEET, self.URL_COLUMN)
        urls = urls[: self.max_num_firm]

        self.phones_map: dict[str, str] = self.load_progress(self.OUT_JSON)
        already_done = set(self.phones_map.keys())
        urls = [u for u in urls if u not in already_done]

        # При старте — сначала очередь pending
        self.pending_queue = self.load_pending(self.PENDING_JSON)

        print(f"Новых ссылок к обработке: {len(urls)}; отложенных: {len(self.pending_queue)}")
        if update_callback:
            update_callback(f"Новых ссылок к обработке: {len(urls)}; отложенных: {len(self.pending_queue)}")
        if not urls and not self.pending_queue:
            print(f"Нечего делать. Прогресс в {self.OUT_JSON}: {len(self.phones_map)} записей.")
            return

        atexit.register(self.flush_progress)  # Регистрация функции при завершении программы
        for sig in ("SIGINT", "SIGTERM"):
            try:
                signal.signal(getattr(signal, sig), lambda *a: (self.flush_progress(), exit(1)))  # Установка обработчика сигнала
            except Exception:
                pass
            
        print("\n" + "=" * 50)
        print("EDUCATIONAL USE ONLY - NO WARRANTY PROVIDED")
        print("This parser may violate Terms of Service.")
        print("Use only for learning web scraping techniques.")
        print("Author not responsible for any legal consequences.")
        print("=" * 50 + "\n")
        
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-web-security",
                    "--disable-site-isolation-trials",
                ],
            )  # headless=True - без графического итерфейса
            try:
                vp_w = random.randint(1200, 1400)
                vp_h = random.randint(760, 900)
                context = await browser.new_context(
                    viewport={"width": vp_w, "height": vp_h},
                    user_agent=self.get_random_user_agent(),
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                    extra_http_headers={"Cache-Control": "no-cache"},
                )

                # Ручной логин на первой ссылке (если есть что открывать)
                seed_url = (self.pending_queue[0] if self.pending_queue
                            else (urls[0] if urls else None))

                if seed_url:
                    # Проверяем и исправляем URL на www-версию
                    seed_url = self.ensure_www_url(seed_url)

                    page = await context.new_page()  # Создание новой страницы

                    await asyncio.sleep(random.uniform(0.4, 0.8))
                    try:
                        await asyncio.sleep(random.uniform(0.5, 0.8))

                        # Потом на объявление
                        await page.goto(seed_url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
                    except PWTimeoutError:
                        try:
                            await page.goto(seed_url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
                        except PWTimeoutError:
                            print(f"Таймаут при загрузке {seed_url}")

                    await self.human_sleep(0.4, 0.7)
                    if await self.is_captcha_or_block(page):
                        print("Обнаружена капча/блокировка на первой странице.")
                        print("Реши капчу вручную или проверь VPN/прокси.")
                        input("После решения нажми Enter...")

                    print("\nТвои действия:")  # Инструкция пользователю
                    print(" • если есть капча — реши;")
                    print(" • залогинься в Авито;")
                    print(" • оставь открытую страницу объявления.")

                    # Здесь ждем подтверждения входа
                    if self.gui_works:
                        if update_callback:
                            update_callback("Ожидание подтверждения входа... Нажмите 'Вход выполнен'")
                        await self.press_and_rel()  # Ждем нажатия кнопки в GUI
                    else:
                        # Старый способ для консоли
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, input, "Готов? Нажми Enter в консоли: ")

                    # Проверяем после подтверждения
                    if await self.is_captcha_or_block(page):
                        print("Всё ещё капча/блок — выходим.")
                        await browser.close()
                        self.flush_progress()
                        return

                    try:
                        await page.close()
                    except Exception:
                        pass

                # Обработка отложенных ссылок (сняв уже обработанные)
                self.pending_queue = [u for u in self.pending_queue if u not in already_done]
                try:
                    await self.process_urls_with_pool(
                        context, self.pending_queue, self.pending_queue, update_callback
                    )  # Обработка с добавлением новых отложенных в конец
                except KeyboardInterrupt:
                    print("Остановлено пользователем (на pending).")
                    self.flush_progress()  # Сохранение прогресса

                # Основной список из Excel
                try:
                    await self.process_urls_with_pool(context, urls, self.pending_queue, update_callback)
                except KeyboardInterrupt:
                    print("Остановлено пользователем (на основных ссылках).")
                    self.flush_progress()

            finally:
                await browser.close()
                self.browser = None

        self.flush_progress()
        print(
            f"\nГотово. В {self.OUT_JSON} сейчас {len(self.phones_map)} записей. "
            f"Отложенных осталось: {len(self.load_pending(self.PENDING_JSON))}"
        )

    def ensure_www_url(self, url: str) -> str:
        """
        Преобразует m.avito.ru в www.avito.ru в URL
        """
        # Регулярное выражение для поиска m.avito.ru
        pattern = r"^(https?://)m\.(avito\.ru/.+)$"
        match = re.match(pattern, url)

        if match:
            # Если найдена m.avito.ru, заменяем на www.avito.ru
            new_url = f"{match.group(1)}www.{match.group(2)}"
            print(f"Исправлен URL: {url} -> {new_url}")
            return new_url

        return url


async def main():
    parser = AvitoParse(
        input_file="avito_parse_results/avito_ads.xlsx",
        max_num_firm=5,
        gui_works=False,
    )
    await parser.parse_main()


if __name__ == "__main__":
    asyncio.run(main())
