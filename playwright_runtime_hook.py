import os
import sys
from pathlib import Path


def fix_playwright_for_pyinstaller():
    """
    Исправление для работы Playwright с PyInstaller
    """
    # Устанавливаем переменную окружения для playwright
    if getattr(sys, "frozen", False):
        # Если программа запущена как EXE
        base_path = sys._MEIPASS
        # Путь к браузерам playwright внутри распакованных ресурсов
        playwright_dir = Path(base_path) / "ms-playwright"

        if playwright_dir.exists():
            # Устанавливаем переменную окружения
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(playwright_dir)
            os.environ["PLAYWRIGHT_HOME"] = str(playwright_dir)

            # Также добавляем путь в sys.path для импорта
            sys.path.append(str(playwright_dir))

        # Для Windows также может потребоваться установить путь к драйверам
        os.environ["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = str(
            playwright_dir / "chromium-*/chrome-win/chrome.exe"
        )


# Вызываем функцию при импорте
fix_playwright_for_pyinstaller()
