import random
import time
import re
import pandas as pd
import json
import os
import signal, atexit
from playwright.sync_api import (
    sync_playwright,
    Page,
    Error as PWError,
    TimeoutError as PWTimeoutError,
)
from urllib.parse import urljoin
from base64 import b64decode
from io import BytesIO
from PIL import Image
from pathlib import Path

class AvitoParse:
    def __init__(self, input_file: str, max_num_firm: int):
        self.input_file = Path(input_file)  # Имя Excel/CSV-файла с ссылками на объявления
        self.max_num_firm = max_num_firm
        
        self.phones_map = {}  # Инициализация словаря для результатов
        self.pending_queue = []  # Инициализация списка для отложенных
        
        self.CONCURRENCY = 3   # Количество одновременно открытых вкладок браузера (2–3 оптимально)
        self.OUT_DIR = Path("avito_phones_playwright")  # Рабочая директория парсера
        self.OUT_DIR.mkdir(exist_ok=True)    # mkdir - создание папки, если её нет
        self.IMG_DIR = (self.OUT_DIR / "phones")  # Сюда будут сохраняться PNG с номерами
        self.IMG_DIR.mkdir(exist_ok=True)
        self.DEBUG_DIR = self.OUT_DIR / "debug"   # Сюда складываем скриншоты и html проблемных объявлений
        self.DEBUG_DIR.mkdir(exist_ok=True)
        
        self.OUT_JSON = (self.OUT_DIR / "phones" / "phones_map.json")          # Основной результат: {url: data:image... или тег __SKIP_*__}
        self.PENDING_JSON = (self.OUT_DIR / "phones" / "pending_review.json")  # Ссылки «на модерации» и с лимитом контактов (в разработке на будущее)
        self.SAVE_DATA_URL = (True)                                       # True = сохраняем data:image в JSON; False = сохраняем PNG в IMG_DIR
        self.HEADLESS = False                                             # False = браузер виден (можно логиниться руками)
        
        # ПОВЕДЕНИЕ (МЕДЛЕННЕЕ И ЕСТЕСТВЕНЕЕ)
        self.PAGE_DELAY_BETWEEN_BATCHES = (2.4, 5.2, )    # Пауза между партиями ссылок (раньше была (2.0, 4.0))
        self.NAV_STAGGER_BETWEEN_TABS = (0.45, 1.35, )    # Пауза перед открытием КАЖДОЙ вкладки (чтобы не стартовали все разом)
        self.POST_NAV_IDLE = (0.45, 1.05,)                # Небольшая «заминка» после загрузки страницы перед действиями
        self.BATCH_CONCURRENCY_JITTER = (True)            # Иногда работаем 2 вкладками вместо 3 для естественности
        self.CLOSE_STAGGER_BETWEEN_TABS = (0.25, 0.75, )  # Вкладки закрываем с небольшой случайной паузой

        # ВХОДНОЙ ФАЙЛ С ССЫЛКАМИ
        self.INPUT_SHEET = None  # Имя листа в Excel; None = использовать все листы
        self.URL_COLUMN = None   # Имя колонки со ссылками; None = искать ссылки во всех колонках

        # БАЗОВЫЕ ТАЙМАУТЫ
        self.CLICK_DELAY = 3       # Базовая задержка в секундах перед ожиданием появления номера телефона
        self.NAV_TIMEOUT = 70_000  # Таймаут загрузки страницы, мс (70 секунд)

        # ЧЕЛОВЕЧНОСТЬ / АНТИБАН-ПОВЕДЕНИЕ
        self.HUMAN = {
            "pre_page_warmup_scrolls": (1, 3, ),      # Сколько раз «прогрелись» скроллом после открытия страницы
            "scroll_step_px": (250, 900),             # Диапазон шага скролла в пикселях
            "scroll_pause_s": (0.18, 0.75),           # Пауза между скроллами
            "hover_pause_s": (0.14, 0.42),            # Пауза при наведении на элементы
            "pre_click_pause_s": (0.10, 0.28),        # Короткая пауза перед кликом
            "post_click_pause_s": (0.12, 0.32),       # Пауза сразу после клика
            "mouse_wiggle_px": (4, 12),               # Амплитуда «подёргивания» мыши
            "mouse_wiggle_steps": (2, 5),             # Сколько шагов «подёргиваний» мыши
            "between_actions_pause": (0.10, 0.30, ),  # Пауза между действиями (скролл, клик, наведение)
            "click_delay_jitter": (
                self.CLICK_DELAY * 0.9,
                self.CLICK_DELAY * 1.25
            ),  # Случайная задержка после клика по телефону (min и max)
        }   
        
            
    def human_sleep(self, a: float, b: float):
        '''
        Приостанавливает выполнение на случайное количество секунд в диапазоне [a, b].
        Используется для имитации человеческих пауз и предотвращения блокировок!
        '''
        time.sleep(random.uniform(a, b))

    def human_scroll_jitter(self, page: Page, count: int | None = None):
        '''
        Имитирует человеческий скроллинг страницы.
        Выполняет случайное количество скроллов со случайным шагом и направлением.
        page: Playwright Page объект
        count: Количество скроллов
        '''
        if count is None:
            count = random.randint(*self.HUMAN["pre_page_warmup_scrolls"]) # Случайное количество скролов
        try:
            height = page.evaluate("() => document.body.scrollHeight") or 3000
            for _ in range(count):
                step = random.randint(*self.HUMAN["scroll_step_px"])
                direction = 1 if random.random() > 0.25 else -1
                y = max(0, min(height, page.evaluate("() => window.scrollY") + step * direction))
                page.evaluate("y => window.scrollTo({top: y, behavior: 'smooth'})", y)  # Плавный скролл через JavaScript
                self.human_sleep(*self.HUMAN["scroll_pause_s"])
        except Exception:
            pass


    def human_wiggle_mouse(self, page: Page, x: float, y: float):
        '''
        Имитирует мелкие случайные движения мыши вокруг указанных координат.
        Добавляет реалистичности наведению мыши.
        '''
        steps = random.randint(*self.HUMAN["mouse_wiggle_steps"])  # Шаги подергиваний
        amp = random.randint(*self.HUMAN["mouse_wiggle_px"])  # Амплитуда подергиваний
        for _ in range(steps):
            dx = random.randint(-amp, amp)  # Смещения x и y
            dy = random.randint(-amp, amp)
            try:
                page.mouse.move(x + dx, y + dy)
            except Exception:
                pass
            self.human_sleep(*self.HUMAN["between_actions_pause"])  # Пауза между движениями


    def human_hover(self, page: Page, el):
        '''
        Имитирует человеческое наведение мыши на элемент.
        Вычисляет центр элемента, добавляет случайное смещение и вибрацию мыши.
        el: Элемент для наведения
        '''
        try:
            box = el.bounding_box()  # Получение координат и размеров элемента
            if not box:
                return
            cx = box["x"] + box["width"] * random.uniform(0.35, 0.65)  # Координаты x, y в пределах элемента
            cy = box["y"] + box["height"] * random.uniform(0.35, 0.65)
            page.mouse.move(cx, cy)
            self.human_wiggle_mouse(page, cx, cy)
            self.human_sleep(*self.HUMAN["hover_pause_s"])
        except Exception:
            pass
      
    def safe_get_content(self, page: Page) -> str:
        '''
        Безопасно получает HTML-содержимое страницы с одной попыткой повторения.
        Return: HTML-код страницы или пустая строка при ошибке
        '''
        for _ in range(2):
            try:
                return page.content().lower()
            except PWError:  # Обработка ошибок Playwright
                time.sleep(1)
        return ""
    
    def get_avito_id_from_url(self, url: str) -> str:
        '''
        Извлекает ID объявления из URL Avito.
        Arg: url объявления Avito
        Return: ID объявления или timestamp если ID не найден
        '''
        m = re.search(r"(\d{7,})", url)
        return m.group(1) if m else str(int(time.time()))
    
    def is_limit_contacts_modal(self, page: Page) -> bool:
        '''
        Проверяет наличие модального окна о лимите контактов.
        Return: True если обнаружено сообщение о лимите контактов
        '''
        html = self.safe_get_content(page).lower()
        if "закончился лимит" in html and "просмотр контактов" in html:
            return True
        try:
            loc = page.locator("text=Купить контакты").first
            if loc.is_visible():
                return True
        except Exception:
            pass
        return False
    
    def is_captcha_or_block(self, page: Page) -> bool:
        """Быстрая проверка на блокировку"""
        try:
            url = (page.url or "").lower()
        except PWError:
            url = ""
        html = (self.safe_get_content(page)).lower()
        return (
            "captcha" in url or 
            "firewall" in url or
            "доступ с вашего ip-адреса временно ограничен" in html
        )
    
    def classify_ad_status(self, page: Page) -> str:
        '''
        Определяет статус объявления по содержимому страницы.
        Return: Строка с статусом: 'ok' | 'no_calls' | 'on_review' | 'unavailable' | 'blocked' | 'limit'
        '''
        # КЛАССИФИКАЦИЯ СТРАНИЦЫ ОБЪЯВЛЕНИЯ
        self.NO_CALLS_MARKERS = [
            "без звонков",
            "пользователь предпочитает сообщения",
        ]
        self.MODERATION_MARKERS = [
            "оно ещё на проверке",
            "объявление на проверке",
            "объявление ещё на проверке",
        ]
        self.UNAVAILABLE_MARKERS = [
            "объявление не посмотреть",
            "объявление снято с продажи",
            "объявление удалено",
            "объявление закрыто",
            "объявление больше не доступно",
        ]
        
        if self.is_captcha_or_block(page):
            return "blocked"

        html = self.safe_get_content(page)

        # Проверка лимита контактов
        if self.is_limit_contacts_modal(page):
            return "limit"
        
        # Проверка модерации, доступности, режима "без звонков"
        MARKERS = [self.NO_CALLS_MARKERS, self.MODERATION_MARKERS, self.UNAVAILABLE_MARKERS]
        text_makers = ["on_review", "unavailable", "no_calls"]
        for i in range(3):
            if any(m in html for m in MARKERS[i]):
                return text_makers[i]

        try:
            if page.locator("text=Без звонков").first.is_visible():
                return "no_calls"
        except Exception:
            pass

        return "ok"  # Возвращаем 'ok', если проблем не обнаружено
    
    def load_progress(self, path: Path) -> dict[str, str]:
        '''
        Загружает прогресс парсинга из JSON файла.
        Return: Словарь с прогрессом или пустой словарь при ошибке
        '''
        if path.exists():  # Проверка существования файла
            try:
                return json.loads(path.read_text(encoding="utf-8"))  # Загрузка JSON данных
            except Exception as e:
                print(f"Не удалось прочитать существующий прогресс: {e}")
        return {}


    def load_pending(self, path: Path) -> list[str]:
        '''
        Загружает список отложенных ссылок из JSON файла.
        Return: Список URL или пустой список при ошибке
        '''
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return [u for u in data if isinstance(u, str)]
            except Exception:
                pass
        return []


    def save_pending(self, path: Path, urls: list[str]):
        '''
        Сохраняет список отложенных ссылок в JSON файл.
        '''
        urls = list(dict.fromkeys(urls))  # Уникальные, порядок сохраняем
        self.atomic_write_json(path, urls)
    
    def read_urls_from_excel_or_csv(self, sheet=None, url_column=None) -> list[str]:
        '''
        Читает URL объявлений из Excel или CSV файла.
        Args:
            sheet: Имя листа Excel (None для всех листов)
            url_column: Имя колонки с URL (None для поиска во всех колонках)
        Return: Список уникальных URL
        '''
        if not self.input_file.exists():
            raise FileNotFoundError(f"Файл не найден: {self.input_file}")
        
        url_re = re.compile(r'https?://(?:www\.)?avito\.ru/[^\s"]+')
        urls: list[str] = []

        if self.input_file.suffix.lower() in {".xlsx", ".xls"}:
            xls = pd.ExcelFile(self.input_file)  # Создание объекта Excel
            sheets = [sheet] if sheet is not None else xls.sheet_names  # Определение листов для обработки
            for sh in sheets:
                df = xls.parse(sh, dtype=str)  # Чтение листа как DataFrame
                if url_column and url_column in df.columns:
                    col = df[url_column].dropna().astype(str)  # Получение колонки и удаление пустых значений
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
        '''
        Атомарно записывает данные в JSON файл с использованием временного файла.
        Arg: data: Данные для записи
        '''
        tmp = path.with_suffix(path.suffix + f".tmp_{int(time.time()*1000)}_{random.randint(1000,9999)}")  # Создание уникального имени временного файла
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
    
    def try_click(self, page: Page, el) -> bool:
        '''
        Пытается кликнуть на элемент различными способами.
        Return: True если клик выполнен успешно
        '''
        self.human_hover(page, el)
        self.human_sleep(*self.HUMAN["pre_click_pause_s"])
        try:
            el.click()
            self.human_sleep(*self.HUMAN["post_click_pause_s"])
            return True
        except Exception:
            try:  # Попытка альтернативного клика через JavaScript
                box = el.bounding_box() or {}
                if box:
                    page.mouse.move(box.get("x", 0) + 6, box.get("y", 0) + 6)  # Перемещение мыши к элементу со смещением
                    self.human_sleep(*self.HUMAN["pre_click_pause_s"])
                page.evaluate("(e)=>e.click()", el)  # Клик через JS
                self.human_sleep(*self.HUMAN["post_click_pause_s"])
                return True
            except Exception:
                return False
    
    def click_show_phone_on_ad(self, page: Page) -> bool:
        '''
        Пытается найти и кликнуть на кнопку "Показать телефон" в объявлении.
        Return: True если кнопка найдена и клик выполнен
        '''
        self.human_scroll_jitter(page)

        for anchor in [
            "[data-marker='seller-info']",
            "[data-marker='item-sidebar']",
            "section:has(button[data-marker*='phone'])",
            "section:has(button:has-text('Показать'))",
            ]:
            try:
                anchor_element = page.query_selector(anchor)  # Поиск якорного элемента
                if anchor_element:
                    anchor_element.scroll_into_view_if_needed()  # Прокрутка к элементу, если элемент найден
                    self.human_sleep(*self.HUMAN["scroll_pause_s"])
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
                el = page.query_selector(sel)
                if el and el.is_visible() and el.is_enabled():
                    if self.try_click(page, el):
                        print("Нажали 'Показать телефон'.")
                        # Ждем номер телефона
                        try:
                            page.wait_for_selector("img[data-marker='phone-image']", timeout=4000)
                        except Exception:
                            pass
                        # Проверяем, появилась ли модалка авторизации
                        if page.query_selector("[data-marker='login-form']"):
                            print("Обнаружена модалка авторизации после клика")
                            return False
                        return True
            except Exception:
                continue

        print("Кнопка 'Показать телефон' не найдена.")
        return False
    
    def extract_phone_data_uri_on_ad(self, page: Page) -> str | None:
        '''
        Извлекает data:image URI с изображением телефона со страницы. 
        Return: data:image URI или None если изображение не найдено
        '''
        try:  # Попытка поиска изображения телефона
            img = page.query_selector("img[data-marker='phone-image']")  # Поиск изображения по data-maker
        except PWError:
            img = None

        if not img or not img.is_visible():
            print("Картинка с номером не найдена.")
            return None

        # Получаем src атрибут
        try:
            src = img.get_attribute("src") or ""
        except Exception:
            img = None
        if not src.startswith("data:image"):
            print(f"src не data:image, а: {src[:60]}...")
            return None
        return src
    
    def save_phone_png_from_data_uri(self, data_uri: str, file_stem: str) -> str | None:
        '''
        Сохраняет изображение телефона из data:image URL в PNG файл.
        Args:
            data_uri: Строка data:image с изображением
            file_stem: Имя файла без расширения
        Return: Путь к сохраненному файлу или None при ошибке
        '''
        try:
            _, b64_data = data_uri.split(",", 1)  # Разделение data:image URI и получение base64 данных
            raw = b64decode(b64_data)             # Декодирование base64 в бинарные данные
            image = Image.open(BytesIO(raw)).convert("RGB")  # Создание изображения из бинарных данных
            file_name = f"{file_stem}.png"
            out_path = self.IMG_DIR / file_name  # Путь к файлу
            image.save(out_path)
            print(f"PNG сохранён: {out_path}")
            return str(out_path)
        except Exception as e:
            print(f"Ошибка при сохранении PNG: {e}")
            return None
    
    def process_urls_with_pool(self, context, urls: list[str], on_result, pending_queue: list[str]):
        '''
        Обрабатывает список URL с использованием пула страниц.
        Args:
            context: Контекст браузера Playwright
            urls: Список URL для обработки
            on_result: Функция обратного вызова для сохранения результатов
            pending_queue: Список для добавления отложенных URL
        '''
        if not urls:
            return

        # Пул создаём максимального размера; часть вкладок можем не использовать
        pages = [context.new_page() for _ in range(self.CONCURRENCY)]
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
                    self.human_sleep(*self.NAV_STAGGER_BETWEEN_TABS)
                    try:
                        p.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
                    except PWTimeoutError:
                        print(f"Таймаут: {url}")
                        continue

                    # Лёгкая «заминка» после навигации + пара скроллов
                    self.human_sleep(*self.POST_NAV_IDLE)
                    self.human_scroll_jitter(p, count=random.randint(1, 2))
                  
                # Статус + модалки + попытка клика
                for url, p in batch:
                    self.human_sleep(*self.HUMAN["between_actions_pause"])
                    
                    st = self.classify_ad_status(p)
                    
                    # Обработка всех статусных кейсов
                    if st == "blocked":
                        print(f"Капча/блок: {url}")
                        continue
                    if st == "limit":
                        print(f"Лимит контактов: {url}")
                        on_result(url, "__SKIP_LIMIT__")
                        pending_queue.append(url)
                        continue
                    if st == "unavailable":
                        print(f"Недоступно/закрыто: {url}")
                        on_result(url, "__SKIP_UNAVAILABLE__")
                        continue
                    if st == "no_calls":
                        print(f"Без звонков: {url}")
                        on_result(url, "__SKIP_NO_CALLS__")
                        continue
                    if st == "on_review":
                        print(f"На проверке: {url}")
                        on_result(url, "__SKIP_ON_REVIEW__")
                        pending_queue.append(url)
                        continue
                                
                    # Пытаемся кликнуть на кнопку телефона
                    if not self.click_show_phone_on_ad(p):
                        print(f"Не удалось кликнуть на {url}")
                        self.dump_debug(p, url)
                        continue  # Переходим к следующему URL 
                    
                # Ждём картинку телефона
                self.human_sleep(*self.HUMAN["click_delay_jitter"])
                for url, p in batch:
                    self.human_sleep(*self.HUMAN["between_actions_pause"])
                    if self.is_captcha_or_block(p):  # Проверка модалок и блокировок
                        continue  # Пропуск объявления 
                    data_uri = self.extract_phone_data_uri_on_ad(p)
                    if not data_uri:
                        continue
                    if self.SAVE_DATA_URL:
                        value = data_uri
                    else:
                        avito_id = self.get_avito_id_from_url(url)
                        out_path = self.save_phone_png_from_data_uri(data_uri, avito_id)
                        if not out_path:  # Проверка успешности сохранения
                            continue
                        value = out_path   # Использование пути к файлу
                    on_result(url, value)  # Сохранение результата
                    print(f"{url} -> {'[data:image...]' if self.SAVE_DATA_URL else value}")

                self.human_sleep(*self.PAGE_DELAY_BETWEEN_BATCHES)  # Пауза между партиями
        finally:
            for p in pages:
                try:
                    self.human_sleep(*self.CLOSE_STAGGER_BETWEEN_TABS)
                    p.close()  # Закрытие страницы
                except Exception:
                    pass
      
    def flush_progress(self):
            '''
            Внутренняя функция для сохранения прогресса.
            Вызывается при завершении программы.
            '''
            try:
                self.atomic_write_json(self.OUT_JSON, self.phones_map)    # Сохранение основного прогресса
                self.save_pending(self.PENDING_JSON, self.pending_queue)  # Сохранение отложенных ссылок
            except Exception as e:
                print(f"Ошибка записи прогресса: {e}")
      
    def on_result(self, url: str, value: str | None):
        '''
        Функция обратного вызова для сохранения результатов.
        Args:
            url: URL объявления
            value: data:image..., путь к PNG или __SKIP_*__
        '''
        if value is None:
            return
        self.phones_map[url] = value
        self.atomic_write_json(self.OUT_JSON, self.phones_map) # Сохранение прогресса
      
    def dump_debug(self, page: Page, url: str):
        '''
        Сохраняет скриншот и HTML проблемной страницы для отладки.
        '''
        try:
            ad_id = self.get_avito_id_from_url(url)     # Получение ID объявления из URL
            png_path = self.DEBUG_DIR / f"{ad_id}.png"  # Пути
            # html_path = self.DEBUG_DIR / f"{ad_id}.html"
            page.screenshot(path=str(png_path), full_page=True)  # Создание скриншота всей страницы
            # html = self.safe_get_content(page)  # Получение HTML содержимого
            # html_path.write_text(html, encoding="utf-8")
            print(f"Debug сохранён: {png_path.name}")  # Со скриншотом {png_path.name}, {html_path.name}
        except Exception as e:
            print(f"Не удалось сохранить debug: {e}")
        
    def get_random_user_agent(self):
        """Скрываем автоматизацию с помощью захода с разных систем"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        ]
        return random.choice(user_agents)
      
    def parse_main(self):  
        """Парсинг сайта"""
        
        urls = self.read_urls_from_excel_or_csv(self.INPUT_SHEET, self.URL_COLUMN)
        urls = urls[:self.max_num_firm]

        self.phones_map: dict[str, str] = self.load_progress(self.OUT_JSON)
        already_done = set(self.phones_map.keys())
        urls = [u for u in urls if u not in already_done]

        # При старте — сначала очередь pending
        self.pending_queue = self.load_pending(self.PENDING_JSON)

        print(f"Новых ссылок к обработке: {len(urls)}; отложенных: {len(self.pending_queue)}")
        if not urls and not self.pending_queue:
            print(f"Нечего делать. Прогресс в {self.OUT_JSON}: {len(self.phones_map)} записей.")
            return
        
        atexit.register(self.flush_progress)  # Регистрация функции при завершении программы
        for sig in ("SIGINT", "SIGTERM"):
            try:
                signal.signal(getattr(signal, sig), lambda *a: (self.flush_progress(), exit(1))) # Установка обработчика сигнала
            except Exception:
                pass
        
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=False)  # headless=True - без графического итерфейса
                vp_w = random.randint(1200, 1400)
                vp_h = random.randint(760, 900)
                self.context = browser.new_context(
                    viewport={"width": vp_w, "height": vp_h},
                    user_agent=self.get_random_user_agent(),
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                )
                # Ручной логин на первой ссылке (если есть что открывать)
                seed_url = self.pending_queue[0] if self.pending_queue else (urls[0] if urls else None)
                if seed_url:
                    page = self.context.new_page() # Создание новой страницы
                    try:
                        page.goto(seed_url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
                    except PWTimeoutError:
                        pass
                    print("\nВаши действия:")  # Инструкция пользователю
                    print(" • Если есть капча — решите;")
                    print(" • Залогиньтесь в Авито;")
                    print(" • Оставьте открытую страницу объявления.")
                    input("Готово? Нажмите Enter в консоли.\n")
                    if self.is_captcha_or_block(page):
                        print("Всё ещё капча/блок — выходим.")
                        browser.close()
                        self.flush_progress()
                        return
                    try:
                        page.close()
                    except Exception:
                        pass
            except Exception as e:
                print(f"Произошла ошибка: {e}")

        # Обработка отложенных ссылок (сняв уже обработанные)
        self.pending_queue = [u for u in self.pending_queue if u not in already_done]
        try:
            self.process_urls_with_pool(
                self.context, self.pending_queue, self.on_result, self.pending_queue
            )  # Обработка с добавлением новых отложенных в конец
        except KeyboardInterrupt:
            print("Остановлено пользователем (на pending).")
            self.flush_progress()  # Сохранение прогресса

        # Основной список из Excel
        try:
            self.process_urls_with_pool(self.context, urls, self.on_result, self.pending_queue)
        except KeyboardInterrupt:
            print("Остановлено пользователем (на основных ссылках).")
            self.flush_progress()

        browser.close()
        self.flush_progress()
        print(
            f"\nГотово. В {self.OUT_JSON} сейчас {len(self.phones_map)} записей. "
            f"Отложенных осталось: {len(self.load_pending(self.PENDING_JSON))}"
        )
                
                            
def main():
    parser = AvitoParse(input_file="Корп питание avito_593927_23.12.2025_16.05.xlsx", max_num_firm=50)
    parser.parse_main()


if __name__ == "__main__":
    main()