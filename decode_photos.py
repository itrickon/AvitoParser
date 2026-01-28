import json, re, base64
from io import BytesIO
from pathlib import Path
import pandas as pd

from PIL import Image
import pytesseract

# Если нужно, укажите путь к tesseract, например:
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
INPUT_JSON = Path("avito_phones_playwright/phones/phones_map.json")
OUTPUT_EXCEL = Path("phones_output.xlsx")


def to_avito_url(key: str) -> str:
    '''
    Преобразует ключи вида:
      - "/moskva/kvartiry/....?context=..." -> "https://www.avito.ru/moskva/kvartiry/..."
      - "https://www.avito.ru/....?context=..." -> "https://www.avito.ru/..."
      - оставляет прочие http-ссылки без изменений, но обрезает query.
    '''
    if key.startswith("http://") or key.startswith("https://"):
        base = key
    elif key.startswith("/"):
        base = "https://www.avito.ru" + key
    else:
        # Если вдруг пришло что-то иное — просто вернём как есть
        base = key
    # Убираем query-параметры типа ?context=...
    base = base.split("?", 1)[0]
    return base


def decode_img_phones(data: dict) -> list:
    '''
    Возвращает список кортежей [(ссылка, телефон), ...]
    '''
    results = []
    phone_pattern = re.compile(
        r'(?:\+7|7|8)?[\s\-()]*(\d{3})[\s\-()]*(\d{3})[\s\-()]*(\d{2})[\s\-()]*(\d{2})'
    )

    def normalize_phone(match):
        g = match.groups()
        return "+7" + "".join(g)

    for raw_url, data_url in data.items():
        # Нормализуем ссылку в формат https://www.avito.ru/... (без ?context=...)
        url = to_avito_url(raw_url)

        # Пропускаем специальные значения
        if data_url in ["__SKIP_NO_CALLS__", "__SKIP_UNAVAILABLE__", "__SKIP_ON_REVIEW__", "__SKIP_ON_REVIEW__"]:
            print(f"[skip] {url} - специальное значение: {data_url}")
            continue
        
        # Пропускаем пустые данные
        if not data_url or data_url.strip() == "":
            print(f"[skip] {url} - пустые данные")
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
            continue

        # OCR (рус+англ, чтобы видеть +7 / текст)
        try:
            text = pytesseract.image_to_string(img, lang="rus+eng")
        except Exception as e:
            print(f"[error] {url} - ошибка OCR: {e}")
            continue

        # Ищем телефоны
        phones = {normalize_phone(m) for m in phone_pattern.finditer(text)}

        if phones:
            # Если несколько — берём первый
            phone = next(iter(phones))
            results.append((url, phone))
            print(f"[found] {url} -> {phone}")
        else:
            print(f"[no phone] {url} - телефон не найден в изображении")
            # Если телефон не найден, всё равно сохраняем ссылку с пустым номером
            results.append((url, ""))
    
    return results


def save_to_excel(data: list, filename: Path):
    '''
    Сохраняет только записи с найденными телефонами
    '''
    # Фильтруем записи без телефонов
    filtered_data = [(url, phone) for url, phone in data if phone]
    
    df = pd.DataFrame(filtered_data, columns=['Ссылка', 'Телефон'])
    
    if len(df) == 0:
        print("Нет данных для сохранения!")
        return
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Телефоны')
        
        # Автонастройка ширины столбцов
        worksheet = writer.sheets['Телефоны']
        for column in df:
            column_width = max(df[column].astype(str).map(len).max(), len(column)) + 2
            col_idx = df.columns.get_loc(column) + 1
            worksheet.column_dimensions[chr(64 + col_idx)].width = min(column_width, 50)
    
    print(f"\nФайл сохранён: {filename.resolve()}")
    print(f"Всего записей: {len(df)}")
    print(f"Из них с номерами: {df['Телефон'].notna().sum()}")


if __name__ == "__main__":
    if not INPUT_JSON.exists():
        raise FileNotFoundError(f"Файл не найден: {INPUT_JSON.resolve()}")

    with INPUT_JSON.open("r", encoding="utf-8") as f:
        src = json.load(f)
        if not isinstance(src, dict):
            raise ValueError("Ожидался JSON-объект {url: data_uri}")

    # Получаем данные в виде списка кортежей
    result = decode_img_phones(src)
    
    # Сохраняем в Excel
    save_to_excel(result, OUTPUT_EXCEL)
    
    print(f"\nГотово! Файл сохранён как: {OUTPUT_EXCEL}")