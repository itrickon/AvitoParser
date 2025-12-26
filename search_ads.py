from playwright.sync_api import sync_playwright
import time

class SearchAvitoAds:
    def __init__(self, sity, keyword, max_num_ads=10):
        self.sity = sity
        self.keyword = keyword
        self.max_num_ads = max_num_ads
        self.ads = []

    def _get_links(self):
        link_selector = '[data-marker="item-title"][href]'
        found_links = self.page.query_selector_all(link_selector)
        links = [f'https://www.avito.ru/{link.get_attribute("href")}' for link in found_links]
        return links

    def _go_to_next_page(self):
        """Переход на следующую страницу"""
        try:
            # Ищем кнопку "Вперёд" или пагинацию
            next_button = self.page.query_selector('[aria-label="Следующая страница"]')
            if next_button and next_button.is_visible():
                next_button.click()
                time.sleep(2)  # Ждем загрузки страницы
                return True
            return False
        except Exception as e:
            print(f"Ошибка при переходе на следующую страницу: {e}")
            return False

    def parse_main(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            self.context = browser.new_context()
            self.page = self.context.new_page()
            
            # Формируем URL с городом
            self.page.goto(f"https://www.avito.ru/{self.sity}?cd=1&q={self.keyword}", wait_until="domcontentloaded")
            
            # Собираем ссылки с нескольких страниц
            while len(self.ads) < self.max_num_ads:

                # Получаем ссылки с текущей страницы
                page_links = self._get_links()
                
                # Добавляем новые ссылки, избегая дубликатов
                for link in page_links:
                    if link not in self.ads and len(self.ads) < self.max_num_ads:
                        self.ads.append(link)
                        time.sleep(0.2)
                
                print(f"Всего собрано ссылок: {len(self.ads)} из {self.max_num_ads}")

                # Проверяем, нужно ли собирать еще
                if len(self.ads) >= self.max_num_ads:
                    print(f"Достигнуто необходимое количество ссылок: {self.max_num_ads}")
                    break
                
                # Пытаемся перейти на следующую страницу
                if not self._go_to_next_page():
                    print("Больше нет страниц для парсинга")
                    break
                
                time.sleep(1)  # Небольшая задержка между страницами
            
            # Выводим результат
            print(f"\nИтог: собрано {len(self.ads)} ссылок:")
            for i, ad in enumerate(self.ads, 1):
                print(f"{i}. {ad}")
            
            browser.close()


def main():
    parser = SearchAvitoAds(sity="tambov", keyword="Авто Мойка", max_num_ads=200)
    parser.parse_main()


if __name__ == "__main__":
    main()