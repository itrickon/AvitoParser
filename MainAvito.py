import random
import time
from playwright.sync_api import (
    sync_playwright,
    Page,
)

class AvitoParse:
    def __init__(self, input_file: str, max_num_firm: int):
        self.input_file = input_file
        self.max_num_firm = max_num_firm
        
        self.CLICK_DELAY = 3       # Базовая задержка в секундах перед ожиданием появления номера телефона
        
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
            "randomize_selectors": True,  # Флаг случайного изменения порядка селекторов
        }      
            
    def human_sleep(a: float, b: float):
        '''
        Приостанавливает выполнение на случайное количество секунд в диапазоне [a, b].
        Используется для имитации человеческих пауз и предотвращения блокировок!
        '''
        time.sleep(random.uniform(a, b))


    def human_pause_jitter(self):
        '''
        Короткая пауза между действиями на основе настройки HUMAN["between_actions_pause"].
        Добавляет естественности поведению скрипта.
        '''
        self.human_sleep(*self.HUMAN["between_actions_pause"])


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
            self.human_pause_jitter()  # Пауза между движениями


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
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=False)  # headless=True - без графического итерфейса
                self.context = browser.new_context(
                    user_agent=self.get_random_user_agent(),
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                )  # По типу вкладок инкогнито
                self.page = (self.context.new_page())  # Новая страница, создается в контексте
                self.page.goto(f"https://www.avito.ru/", wait_until="domcontentloaded",)
                time.sleep(10)
            except Exception as e:
                print(f"Произошла ошибка: {e}")
def main():
    parser = AvitoParse(input_file="АВТОСАЛОН 05.12.xlsx", max_num_firm=50)
    parser.parse_main()


if __name__ == "__main__":
    main()
