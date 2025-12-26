from playwright.sync_api import sync_playwright
import time
from openpyxl import Workbook
import os
from datetime import datetime

class SearchAvitoAds:
    def __init__(self, sity, keyword, max_num_ads=10):
        self.sity = sity
        self.keyword = keyword
        self.max_num_ads = max_num_ads
        self.ads = []
        self.data_saving = "avito_parse_results/avito_ads.xlsx"
        self.start_row = 2
        
        # Удаляем старый файл, если нужно
        if os.path.exists(self.data_saving):
            os.remove(self.data_saving)

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

    def _create_xlsx(self):
        """Создание XLSX файла с заголовками"""
        # Создаем папку, если ее нет
        os.makedirs("avito_parse_results", exist_ok=True)
        
        # Создаем новую рабочую книгу
        self.wb = Workbook()
        self.ws = self.wb.active
        self.ws.title = "Avito Ads"
        
        # Добавляем заголовки
        headers = ["ID", "Ссылка на объявление", "Дата парсинга"]
        for col, header in enumerate(headers, start=1):
            self.ws.cell(row=1, column=col, value=header)
        
        # Сохраняем файл
        self.wb.save(self.data_saving)
        print(f"Создан файл: {self.data_saving}")

    def _save_to_xlsx(self):
        """Сохранение данных в XLSX файл"""
        # Если файл не существует, создаем его
        if not os.path.exists(self.data_saving):
            self._create_xlsx()
        
        # Открываем существующий файл
        from openpyxl import load_workbook
        wb = load_workbook(self.data_saving)
        ws = wb.active
        
        # Определяем с какой строки начинать запись (последняя заполненная строка + 1)
        start_row = ws.max_row + 1 if ws.max_row > 1 else 2
        
        # Записываем данные
        for i, ad in enumerate(self.ads, start=start_row):
            ws.cell(row=i, column=1, value=i-1)  # ID (начинаем с 1)
            ws.cell(row=i, column=2, value=ad)   # Ссылка
            ws.cell(row=i, column=3, value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))  # Дата парсинга
        
        # Сохраняем файл
        wb.save(self.data_saving)
        print(f"Данные сохранены в файл: {self.data_saving}")

    def parse_main(self):
        # Создаем XLSX файл перед началом парсинга
        self._create_xlsx()
        
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            self.context = browser.new_context()
            self.page = self.context.new_page()
            
            # Формируем URL с городом
            self.page.goto(f"https://www.avito.ru/{self.sity}?cd=1&q={self.keyword}", wait_until="domcontentloaded")
            time.sleep(3)  # Ждем полной загрузки
            
            # Собираем ссылки с нескольких страниц
            while len(self.ads) < self.max_num_ads:
                # Получаем ссылки с текущей страницы
                page_links = self._get_links()
                
                # Добавляем новые ссылки, избегая дубликатов
                new_links_added = 0
                for link in page_links:
                    if link not in self.ads and len(self.ads) < self.max_num_ads:
                        self.ads.append(link)
                        new_links_added += 1
                        time.sleep(0.1)  # Небольшая задержка
                
                print(f"Добавлено новых ссылок: {new_links_added}")
                print(f"Всего собрано ссылок: {len(self.ads)} из {self.max_num_ads}")
                
                # Проверяем, нужно ли собирать еще
                if len(self.ads) >= self.max_num_ads:
                    print(f"Достигнуто необходимое количество ссылок: {self.max_num_ads}")
                    break
                
                # Пытаемся перейти на следующую страницу
                if not self._go_to_next_page():
                    print("Больше нет страниц для парсинга")
                    break
                
                time.sleep(2)  # Задержка между страницами
            
            # Финальное сохранение всех данных
            self._save_to_xlsx()
            
            # Выводим результат

            print(f"Данные сохранены в файле: {self.data_saving}")
            print(f"Количество строк в файле: {len(self.ads)}")
            
            browser.close()


def main():
    parser = SearchAvitoAds(sity="tambov", keyword="Авто Мойка", max_num_ads=1200)
    parser.parse_main()


if __name__ == "__main__":
    main()