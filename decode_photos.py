import json
import re
import base64
from io import BytesIO
from pathlib import Path
import pandas as pd
from PIL import Image
import pytesseract

class AvitoOCRProcessor:
    def __init__(self, input_json: str, output_excel: str, tesseract_path: str = None):
        """
        Инициализация OCR процессора.
        
        Args:
            input_json: Путь к JSON файлу с data:image URI
            output_excel: Путь для сохранения Excel файла
            tesseract_path: Путь к tesseract.exe (опционально)
        """
        self.INPUT_JSON = Path(input_json)
        self.OUTPUT_EXCEL = Path(output_excel)
        self.stop_flag = False  # Флаг для остановки процесса
        
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        # Регулярное выражение для телефонов
        self.phone_pattern = re.compile(
            r'(?:\+7|7|8)?[\s\-()]*(\d{3})[\s\-()]*(\d{3})[\s\-()]*(\d{2})[\s\-()]*(\d{2})'
        )
        
        # Специальные значения для пропуска
        self.skip_values = {
            "__SKIP_UNAVAILABLE__",
            "__SKIP_LIMIT__",
            "__SKIP_NO_CALLS__",  
            "__SKIP_ON_REVIEW__"
        }

    def set_stop_flag(self, stop: bool = True):
        """Устанавливает флаг остановки"""
        self.stop_flag = stop

    def to_avito_url(self, key: str) -> str:
        """
        Преобразует ключи в нормализованный URL Avito.
        key: Сырой URL из JSON  
        Returns: Нормализованный URL без query параметров
        """
        if key.startswith("http://") or key.startswith("https://"):
            base = key
        elif key.startswith("/"):
            base = "https://www.avito.ru" + key
        else:
            base = key
        
        return base.split("?", 1)[0]

    def decode_img_phones(self, data: dict, update_callback=None) -> list:
        """
        Обрабатывает данные и извлекает телефоны из изображений.
        data: Словарь {url: data_uri} из JSON
        update_callback: Функция для обновления прогресса
        Returns: Список кортежей [(ссылка, телефон), ...]
        """
        results = []
        total_items = len(data)
        processed = 0
        
        for raw_url, data_url in data.items():
            # Проверяем флаг остановки
            if self.stop_flag:
                print("Декодирование остановлено пользователем")
                return results
            
            processed += 1
            
            # Нормализуем ссылку
            url = self.to_avito_url(raw_url)

            # Обновляем прогресс
            if update_callback:
                progress_msg = f"Обработка {processed}/{total_items}: {url[:50]}..."
                update_callback(progress_msg)

            # Пропускаем специальные значения
            if data_url in self.skip_values:
                print(f"[skip] {url} - специальное значение: {data_url}")
                continue
            
            # Пропускаем пустые данные
            if not data_url or data_url.strip() == "":
                print(f"[skip] {url} - пустые данные")
                results.append((url, ""))
                continue

            # Извлекаем base64
            if "," in data_url:
                _, b64_data = data_url.split(",", 1)
            else:
                b64_data = data_url

            # Декодируем в картинку
            try:
                img_bytes = base64.b64decode(b64_data + '=' * (4 - len(b64_data) % 4))
                img = Image.open(BytesIO(img_bytes))
            except Exception as e:
                print(f"[error] {url} - ошибка декодирования изображения: {e}")
                results.append((url, ""))
                continue

            # OCR (рус+англ, чтобы видеть +7 / текст)
            try:
                text = pytesseract.image_to_string(img, lang="rus+eng")
            except Exception as e:
                print(f"[error] {url} - ошибка OCR: {e}")
                results.append((url, ""))
                continue

            # Ищем телефоны
            phones = {"+7" + "".join(m.groups()) for m in self.phone_pattern.finditer(text)}

            if phones:
                # Если несколько — берём первый
                phone = next(iter(phones))
                results.append((url, phone))
                print(f"[found] {url} -> {phone}")
            else:
                print(f"[no phone] {url} - телефон не найден в изображении")
                results.append((url, ""))
        
        return results

    def save_to_excel(self, data: list, update_callback=None):
        """
        Сохраняет результаты в Excel файл.
        data: Список кортежей [(ссылка, телефон), ...]
        """
        # Фильтруем записи без телефонов
        filtered_data = [(url, phone) for url, phone in data if phone]
        
        df = pd.DataFrame(filtered_data, columns=['Ссылка', 'Телефон'])
        
        if len(df) == 0:
            print("Нет данных для сохранения!")
            return
        
        with pd.ExcelWriter(self.OUTPUT_EXCEL, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Телефоны')
            
            # Автонастройка ширины столбцов
            worksheet = writer.sheets['Телефоны']
            for column in df:
                column_width = max(df[column].astype(str).map(len).max(), len(column)) + 2
                col_idx = df.columns.get_loc(column) + 1
                worksheet.column_dimensions[chr(64 + col_idx)].width = min(column_width, 50)
        list_cllback = [f"\nФайл сохранён: {self.OUTPUT_EXCEL.resolve()}", 
                       f"Всего записей с номерами: {df['Телефон'].notna().sum()}"]
        
        for i in list_cllback:
            print(i)
        if update_callback:
            for i in list_cllback:
                list_cllback_mrg = i
                update_callback(list_cllback_mrg)

    def parse_main(self, update_callback=None):
        """
        Основной метод обработки.
        """
        if not self.INPUT_JSON.exists():
            raise FileNotFoundError(f"Файл не найден: {self.INPUT_JSON.resolve()}")

        with self.INPUT_JSON.open("r", encoding="utf-8") as f:
            src = json.load(f)
            if not isinstance(src, dict):
                raise ValueError("Ожидался JSON-объект {url: data_uri}")

        # Получаем данные
        result = self.decode_img_phones(src, update_callback)
        
        # Проверяем, была ли остановка
        if self.stop_flag:
            print("Декодирование было остановлено")
            return False
        
        # Сохраняем в Excel
        self.save_to_excel(result, update_callback)
        
        print(f"\nГотово! Файл сохранён как: {self.OUTPUT_EXCEL}")
        return True

def main():
    """
    Основная функция запуска.
    """
    # Укажите путь к tesseract если нужно
    TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    
    processor = AvitoOCRProcessor(
        input_json="avito_phones_playwright/phones/phones_map.json",
        output_excel="phones_output.xlsx",
        tesseract_path=TESSERACT_PATH
    )
    
    processor.parse_main()


if __name__ == "__main__":
    main()