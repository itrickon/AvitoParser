import os
import re
import time
import sv_ttk
import shutil
import asyncio
import datetime
import threading
import pandas as pd
import tkinter as tk
from urllib.parse import unquote
from googletrans import Translator
from phone_search import AvitoParse
from search_ads import SearchAvitoAds
from async_runner import AsyncParserRunner
from decode_photos import AvitoOCRProcessor
from tkinter import ttk, messagebox, filedialog, IntVar, Toplevel, Text
    
class AvitoParser(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self.parent.title("AvitoParser")
        self.parent.geometry("950x700")
        
        try:
            self.parent.iconbitmap("static/Avito_logo.ico")
        except Exception as e:
            print(f"Cannot load icon: {e}")
        
        self.interface_style()
        self.pack(fill=tk.BOTH, expand=True)
        
        self.create_widgets()  
        self.toggle_parser_mode()  
        
        self.check_button_enabled = IntVar()
        self.is_parsing = False
        self.bool_decode_input = True
        self.phone_excel_path = None  # Путь к Excel файлу для парсера телефонов
        self.decode_json_path = None  # Путь к JSON файлу для декодирования
        self.is_decoding = False
 
        self.input_json="avito_phones_playwright/phones/phones_map.json"
        self.output_excel="phones_output.xlsx"
        self.tesseract_path=r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        self.clear_bugs = 'avito_phones_playwright/debug'
        self.source_file_path = "avito_parse_results/avito_ads.xlsx"
 
    def interface_style(self):
        sv_ttk.set_theme("light")
           
    def create_widgets(self):
        """Создание всех виджетов интерфейса"""
        self.top_level_menu()
        self.create_parser_controls()
        self.create_status_bar()
        
    def top_level_menu(self):
        """Верхнее меню"""
        menubar = tk.Menu(self.parent)
        self.parent.config(menu=menubar)

        parse_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Парсинг", menu=parse_menu)
        parse_menu.add_command(label="Открыть Excel файл...", accelerator="Ctrl+O", command=self.btn_open)
        parse_menu.add_command(label="Открыть JSON файл...", accelerator="Ctrl+P", command=self.btn_open_decode)
        self.parent.bind("<Control-o>", lambda _: self.btn_open())  # Горячие клавиши
        self.parent.bind("<Control-p>", lambda _: self.btn_open_decode())
        self.parent.bind("<Control-s>", lambda _: self.stop_parsing())
        self.parent.bind("<Control-l>", lambda _: self.clear_log())
        self.parent.bind("<Control-q>", lambda _: self.btn_exit())
        parse_menu.add_separator()
        parse_menu.add_command(label="Выход", command=self.btn_exit)

        export_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Экспорт", menu=export_menu)
        export_menu.add_command(label="Экспорт объявлений...", command=self.copy_ads_file_to_path)
        export_menu.add_command(label="Экспорт готового файла...", command=self.copy_ready_file_to_path)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="Руководство пользователя")
        help_menu.add_command(label="Горячие клавиши", command=self.hotkeys_info)
        help_menu.add_command(label="Очистить папку 'debug'", command=self.clean_directory_except_py)
        help_menu.add_separator()
        help_menu.add_command(label="О программе", command=self.btn_about)
        
    def create_parser_controls(self):
        """Создание элементов управления для парсера"""
        # Основной фрейм с grid для точного контроля
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Конфигурация grid - основной контейнер
        main_frame.grid_columnconfigure(0, weight=1)
        
        # Счетчик строк для grid
        row = 0
        
        # 1. Фрейм для выбора режима парсинга
        mode_frame = ttk.LabelFrame(main_frame, text="Поиск", padding=10)
        mode_frame.grid(row=row, column=0, sticky=tk.EW, padx=10, pady=(0, 5))
        mode_frame.config(height=70)
        
        self.parser_mode_key = tk.StringVar(value="keyword")
        
        ttk.Radiobutton(mode_frame, text="Поиск объявлений", 
                       variable=self.parser_mode_key, 
                       value="keyword",
                       command=self.toggle_parser_mode).grid(row=0, column=0, sticky=tk.W, padx=15, pady=0)
        
        ttk.Radiobutton(mode_frame, text="Поиск объявлений по URL", 
                       variable=self.parser_mode_key, 
                       value="url",
                       command=self.toggle_parser_mode).grid(row=0, column=1, sticky=tk.W, padx=15, pady=0)
        
        ttk.Radiobutton(mode_frame, text="Поиск телефонов", 
                       variable=self.parser_mode_key, 
                       value="phone",
                       command=self.toggle_parser_mode).grid(row=0, column=2, sticky=tk.W, padx=15, pady=0)
        
        ttk.Radiobutton(mode_frame, text="Декодирование изображений", 
                       variable=self.parser_mode_key, 
                       value="decode",
                       command=self.toggle_parser_mode).grid(row=0, column=3, sticky=tk.W, padx=15, pady=0)
        
        row += 1
        
        # 2. Фрейм для темы парсера
        theme_frame = ttk.LabelFrame(main_frame, text="Тема парсера", padding=10)
        theme_frame.grid(row=row, column=0, sticky=tk.EW, padx=10, pady=(0, 5))
        theme_frame.config(height=70)
        
        self.parser_mode_t = tk.StringVar(value="tlight")
        
        ttk.Radiobutton(theme_frame, text="Светлая тема",
                       variable=self.parser_mode_t,
                       value="tlight",
                       command=self.theme_parser_mode).grid(row=0, column=0, sticky=tk.W, padx=15, pady=0)
        
        ttk.Radiobutton(theme_frame, text="Темная тема",
                       variable=self.parser_mode_t,
                       value="tdark",
                       command=self.theme_parser_mode).grid(row=0, column=1, sticky=tk.W, padx=15, pady=0)
        
        row += 1
        
        # 3. Фрейм для параметров парсинга
        self.params_frame = ttk.LabelFrame(main_frame, text="Параметры парсинга", padding=8)
        self.params_frame.grid(row=row, column=0, sticky=tk.EW, padx=10, pady=(0, 5))
        self.params_frame.config(height=90)
        
        self.create_keyword_params()
        self.create_url_params()
        self.create_phone_params()
        self.create_decode_params()
        
        row += 1
        
        # 4. Дополнительные параметры
        common_frame = ttk.LabelFrame(main_frame, text="Дополнительные параметры", padding=10)
        common_frame.grid(row=row, column=0, sticky=tk.EW, padx=10, pady=(0, 5))
        common_frame.config(height=90)
        
        # Содержимое common_frame
        ttk.Label(common_frame, text="Количество фирм:").grid(row=0, column=0, sticky=tk.W, pady=0)
        self.firm_count_var = tk.IntVar(value=50)
        self.firm_count_spinbox = ttk.Spinbox(common_frame, from_=1, to=10000, 
                                              textvariable=self.firm_count_var, width=15)
        self.firm_count_spinbox.grid(row=0, column=1, padx=5, pady=0, sticky=tk.W)
        
        self.text_url_btn = ttk.Label(common_frame, text="Парсинг по URL:", width=15)
        self.text_url_btn.grid(row=1, column=0, sticky=tk.W, pady=0)
        
        self.generate_url_btn = ttk.Button(common_frame, text="Сгенерировать URL", 
                                          command=self.generate_url, width=22)
        self.generate_url_btn.grid(row=1, column=1, padx=5, pady=0, sticky=tk.W)
        
        row += 1
        
        # 5. Кнопки управления
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, sticky=tk.W, padx=20, pady=4)
        button_frame.config(height=40)
        
        ttk.Button(button_frame, text="Начать парсинг", 
                    command=self.start_new_parsing, width=20).pack(side=tk.LEFT, padx=5)
        
        self.btn_continue_parse = ttk.Button(button_frame, text="Продолжить парсинг", 
                    command=self.run_parsing, width=20)
        self.btn_continue_parse.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="Остановить парсинг", 
                    command=self.stop_parsing, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Очистить лог", 
                    command=self.clear_log, width=20).pack(side=tk.LEFT, padx=5)
        
        row += 1
        
        # Лог выполнения
        log_frame = ttk.LabelFrame(main_frame, text="Лог выполнения", padding=10)
        log_frame.grid(row=row, column=0, sticky=tk.NSEW, padx=10, pady=0)
        
        # Настраиваем вес строки для растягивания лога
        main_frame.grid_rowconfigure(row, weight=1)
        
        # Создаем текстовое поле для логов
        self.log_text = tk.Text(log_frame, height=20, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Добавляем раскраску вывода текста в "Лог выполнения"
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("ERROR", foreground="red")
        self.log_text.tag_config("WARNING", foreground="#cf7c00")
        self.log_text.tag_config("SUCCESS", foreground="#00a800")
        
        # Добавляем скроллбар
        scrollbar = ttk.Scrollbar(self.log_text)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.log_text.yview)
    
    def theme_parser_mode(self):
        """Переключение между темой парсера"""
        current_geometry = self.parent.geometry()  # Сохраняем текущие размеры окна
        
        if self.parser_mode_t.get() == "tlight":
            sv_ttk.set_theme("light")
            self.log_text.tag_config("INFO", foreground="black")
            self.log_text.tag_config("WARNING", foreground="#cf7c00")
            self.log_text.tag_config("SUCCESS", foreground="#00a800")
        else:
            sv_ttk.set_theme("dark")
            self.log_text.tag_config("INFO", foreground="white")
            self.log_text.tag_config("WARNING", foreground="#ffc766")
            self.log_text.tag_config("SUCCESS", foreground="#00e600")
            
        # Принудительно обновляем интерфейс
        self.parent.update_idletasks()
        
        # Восстанавливаем размеры окна
        self.parent.geometry(current_geometry)
    
    async def translate_text(self, city):
        """Переводим город на английский для удобства"""
        self.translator = Translator()
        a = await self.translator.translate(city, src="ru", dest="en")
        a = '-'.join(a.text.split())
        return a.lower()
           
    def generate_url(self):
        """Генерация URL на основе ключевого слова и города"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        keyword = self.keyword_var_keyword.get().strip()
        city = loop.run_until_complete(self.translate_text(self.city_var_keyword.get().strip()))
        
        if not keyword or not city:
            messagebox.showwarning("Предупреждение", "Введите ключевое слово и город!")
            return

        """try:
            city_code = heavy_dicts.city_mapping[self.city_var.get().strip()]
        except:
            city_code = city"""
            
        generated_url = f"https://www.avito.ru/{city}?q={keyword}" # При try except выше city это city_code
        
        self.url_var.set(generated_url)
        
        # Предлагаем переключиться на режим по URL
        if messagebox.askyesno("URL сгенерирован", 
                              f"URL успешно сгенерирован:\n{generated_url}\n\n"
                              f"Хотите переключиться на парсер по URL?"):
            self.parser_mode_key.set("url")
            self.toggle_parser_mode()
        self.status_var.set("URL сгенерирован")
            
    def create_keyword_params(self):
        """Создание элементов для парсера по ключу"""
        self.keyword_frame = ttk.Frame(self.params_frame)
        self.keyword_frame.place(x=0, y=0, relwidth=1, relheight=1)
        
        # Ключевое слово
        ttk.Label(self.keyword_frame, text="Ключевое слово:").grid(row=0, column=0, sticky=tk.W, pady=0)
        self.keyword_var_keyword = tk.StringVar(value="Мойка")
        self.keyword_entry_keyword = ttk.Entry(self.keyword_frame, textvariable=self.keyword_var_keyword, width=25)
        self.keyword_entry_keyword.grid(row=0, column=1, padx=5, pady=0, sticky=tk.W)
        
        # Город
        ttk.Label(self.keyword_frame, text="Город:").grid(row=1, column=0, sticky=tk.W, pady=0)
        self.city_var_keyword = tk.StringVar(value="Челябинск")
        self.city_entry_keyword = ttk.Entry(self.keyword_frame, textvariable=self.city_var_keyword, width=25)
        self.city_entry_keyword.grid(row=1, column=1, padx=5, pady=0, sticky=tk.W)
        
    def create_url_params(self):
        """Создание элементов для парсера по URL"""
        self.url_frame = ttk.Frame(self.params_frame)
        self.url_frame.place(x=0, y=0, relwidth=1, relheight=1)
        
        # URL для парсинга
        ttk.Label(self.url_frame, text="URL страницы 2ГИС:").grid(row=0, column=0, sticky=tk.W, pady=0)
        self.url_var = tk.StringVar(value="https://www.avito.ru/lipetsk?q=Шубы")
        self.url_entry = ttk.Entry(self.url_frame, textvariable=self.url_var, width=50)
        self.url_entry.grid(row=0, column=1, padx=5, pady=0, sticky=tk.W)
        
        # Пустое пространство для выравнивания
        empty_space = ttk.Frame(self.url_frame, height=30)
        empty_space.grid(row=1, column=0, columnspan=2, pady=0)
        
    def create_phone_params(self):
        """Создание элементов для парсера телефонов"""
        self.phone_frame = ttk.Frame(self.params_frame)
        self.phone_frame.place(x=0, y=0, relwidth=1, relheight=1)
        
        # Загрузить Excel файл
        ttk.Label(self.phone_frame, text="Выбрать файл:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=5)
        
        self.excel_file_btn = ttk.Button(self.phone_frame, text="Excel файл после поиска объявлений", 
                                        command=self.btn_open, width=32)
        self.excel_file_btn.grid(row=0, column=1, padx=5, pady=0, sticky=tk.W)
        
        # Путь к файлу (необязательно, но полезно)
        self.excel_file_path = tk.StringVar()
        ttk.Label(self.phone_frame, textvariable=self.excel_file_path, 
                foreground="gray", wraplength=300).grid(row=0, column=2, padx=(60, 0), pady=0, sticky=tk.W)
        
        # Checkbutton для включения фильтра по ключевому слову
        self.enable_keyword_var = tk.BooleanVar(value=True)
        self.enabled_checkbutton = ttk.Checkbutton(self.phone_frame, text="Включить декодирование изображений",
                                                variable=self.enable_keyword_var, command=self.decode_photo_boolean)
        self.enabled_checkbutton.grid(row=1, column=1, padx=5, pady=0, sticky=tk.W)
        
        self.continue_btn = ttk.Button(self.phone_frame, text="Вход выполнен", 
                                        command=self.on_continue_clicked, width=22)
        self.continue_btn.grid(row=1, column=2, padx=(60, 0), pady=0, sticky=tk.W)
        
    def create_decode_params(self):
        """Создание элементов для парсера телефонов"""
        self.decode_frame = ttk.Frame(self.params_frame)
        self.decode_frame.place(x=0, y=0, relwidth=1, relheight=1)
        
        # Загрузить Excel файл
        ttk.Label(self.decode_frame, text="Выбрать файл:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=5)
        
        self.json_file_btn = ttk.Button(self.decode_frame, text="Файл для декодирования фото", 
                                        command=self.btn_open_decode, width=32)
        self.json_file_btn.grid(row=0, column=1, padx=10, pady=0, sticky=tk.W)
        
        # Путь к файлу (необязательно, но полезно)
        self.json_file_path = tk.StringVar()
        ttk.Label(self.decode_frame, textvariable=self.json_file_path, 
                foreground="gray", wraplength=300).grid(row=0, column=2, padx=10, pady=0, sticky=tk.W)

        # Поясняющий текст вместо пустого фрейма
        info_label = ttk.Label(
            self.decode_frame, 
            text="Если файл в другом месте или не после «Поиск телефонов», нажать «Выбрать файл». Иначе — «Начать парсинг».",
            foreground="gray",
            font=("Arial", 9)
        )
        info_label.grid(row=1, column=1, columnspan=3, pady=(5, 10), sticky=tk.W)
        
    def toggle_parser_mode(self):
        """Переключение между режимами парсинга"""
        if self.parser_mode_key.get() == "keyword":
            # Показываем параметры для парсера по ключу
            self.url_frame.place_forget()
            self.phone_frame.place_forget()
            self.decode_frame.place_forget()
            self.keyword_frame.place(x=0, y=0, relwidth=1, relheight=1)
            self.generate_url_btn.config(state=tk.NORMAL)
            self.btn_continue_parse.config(state=tk.DISABLED)
            self.firm_count_spinbox.config(state=tk.NORMAL)
        if self.parser_mode_key.get() == "url":
            # Показываем параметры для парсера по URL
            self.keyword_frame.place_forget()
            self.phone_frame.place_forget()
            self.decode_frame.place_forget()
            self.url_frame.place(x=0, y=0, relwidth=1, relheight=1)
            self.generate_url_btn.config(state=tk.DISABLED)
            self.btn_continue_parse.config(state=tk.DISABLED)
            self.firm_count_spinbox.config(state=tk.NORMAL)
        if self.parser_mode_key.get() == "phone":
            # Показываем параметры для парсера по URL
            self.keyword_frame.place_forget()
            self.url_frame.place_forget()
            self.decode_frame.place_forget()
            self.phone_frame.place(x=0, y=0, relwidth=1, relheight=1)
            self.generate_url_btn.config(state=tk.DISABLED)
            self.btn_continue_parse.config(state=tk.NORMAL)
            self.firm_count_spinbox.config(state=tk.NORMAL)
        if self.parser_mode_key.get() == "decode":
            # Показываем параметры для парсера по URL
            self.keyword_frame.place_forget()
            self.url_frame.place_forget()
            self.phone_frame.place_forget()
            self.decode_frame.place(x=0, y=0, relwidth=1, relheight=1)
            self.generate_url_btn.config(state=tk.DISABLED)
            self.btn_continue_parse.config(state=tk.DISABLED)
            self.firm_count_spinbox.config(state=tk.DISABLED)
    
    def run_async_parsing(self, parser_instance):
        """Запуск асинхронного парсинга в отдельном потоке"""
        try:
            # Создаем и запускаем runner
            runner = AsyncParserRunner(
                parser_instance, 
                update_callback=self.update_gui_from_thread,
                completion_callback=self.on_parsing_complete
            )
            self.parser_thread = runner.start()
            
        except Exception as e:
            self.update_gui_from_thread(f"Ошибка запуска: {str(e)}")
            self.is_parsing = False
    
    def start_new_parsing(self):
        # Проверяем существование файла
        if os.path.exists(self.input_json):
            # Удаляем файл
            os.remove(self.input_json)
            with open(self.input_json, 'w'):
                pass  # Просто создаем пустой файл
        self.run_parsing()
    
    def run_parsing(self):
        """Запуск парсинга в зависимости от выбранного режима"""
        if self.is_parsing:
            messagebox.showwarning("Предупреждение", "Парсинг уже выполняется!")
            return
        self.is_parsing = True
        if self.parser_mode_key.get() == "keyword":
            self.run_keyword_parsing()
        if self.parser_mode_key.get() == "url":
            self.run_url_parsing()
        if self.parser_mode_key.get() == "phone":
            self.run_phone_parsing()
        if self.parser_mode_key.get() == "decode":
            self.run_decoding()
    
    def run_keyword_parsing(self):
        """Запуск парсинга по ключу"""
        keyword = self.keyword_var_keyword.get()
        city = self.city_var_keyword.get()
        firm_count = self.firm_count_var.get()
        
        if not keyword or not city:
            messagebox.showwarning("Предупреждение", "Заполните все поля!")
            return
        
        right_city = re.sub(r'[^а-яА-Яa-zA-Z\s]', '', city).strip()
        self.log_message(f"Начало парсинга по ключу: '{keyword}' в {right_city}, количество: {firm_count}")
        self.status_var.set(f"Парсинг по ключу: {keyword} в {city}")
        
        self.is_parsing = True
        self.parser_instance = SearchAvitoAds(city, keyword, firm_count)
        self.parser_thread = threading.Thread(
            target=self.run_async_parsing,
            args=(self.parser_instance,),
            daemon=True
        )
        self.parser_thread.start()
    
    def run_url_parsing(self):
        """Запуск парсинга по URL - извлекаем город и ключ из URL"""
        url = self.url_var.get()
        firm_count = self.firm_count_var.get()
        
        if not url:
            messagebox.showwarning("Предупреждение", "Введите URL для парсинга!")
            return
            
        # Проверяем, что это URL Avito
        if not url.startswith(('https://www.avito.ru/', 'http://www.avito.ru/')):
            messagebox.showwarning("Предупреждение", "Введите корректный URL Avito!")
            return
        
        try:
            # Извлекаем город и ключевое слово из URL
            pattern = r'https?://www\.avito\.ru/([^/?]+)(?:\?q=([^&]+))?'
            match = re.search(pattern, url)
            
            if match:
                city_code = match.group(1)
                keyword = match.group(2)
                
                keyword = unquote(keyword)
                
                self.log_message(f"Извлечено из URL: город='{city_code}', ключ='{keyword}'")
                self.status_var.set(f"Парсинг по URL: {city_code} - {keyword}")
                
                # Проверяем, что есть ключевое слово
                if not keyword:
                    messagebox.showwarning("Ошибка", 
                        "В URL отсутствует поисковый запрос (параметр q=)\n"
                        "Пример: https://www.avito.ru/moskva?q=Доставка")
                    return
                
                self.is_parsing = True
                self.parser_instance = SearchAvitoAds(city_code, keyword, firm_count)
                print('Запуск')
                runner = AsyncParserRunner(
                    self.parser_instance,
                    update_callback=self.update_gui_from_thread,
                    completion_callback=self.on_parsing_complete
                )
                runner.start()
                
            else:
                messagebox.showwarning("Ошибка", 
                    "Не удалось извлечь данные из URL. Проверьте формат:\n"
                    "Пример: https://www.avito.ru/lipetsk?q=Шубы\n"
                    "Или: https://www.avito.ru/moskva?q=Доставка")
                    
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка парсинга по URL: {str(e)}")

    def run_phone_parsing(self):
        """Запуск парсинга телефонов из Excel файла"""
        # Проверяем, что файл выбран
        if not self.phone_excel_path or not os.path.exists(self.phone_excel_path):
            self.is_parsing = False
            self.log_message(f"Внимание! Сначала выберите Excel файл!")
            self.status_var.set(f"Выберите Excel файл!")
            return
        
        if not hasattr(self, 'df') or self.df is None:
            messagebox.showwarning("Предупреждение", "Файл не загружен! Выберите файл еще раз.")
            return
        
        # Проверяем наличие необходимой колонки
        if 'Ссылка на объявление' not in self.df.columns:
            messagebox.showerror("Ошибка", 
                "В файле должна быть колонка 'Ссылка на объявление' с ссылками на объявления!")
            return
        
        firm_count = self.firm_count_var.get()
        
        try:
            # Получаем список URL для парсинга телефонов
            urls = self.df['Ссылка на объявление'].dropna().tolist()
            
            # Получаем только имя файла для парсера
            file_name = os.path.basename(self.phone_excel_path)
            self.log_message(f"Начало парсинга телефонов из файла: {file_name}")
            self.log_message(f"Количество URL для обработки: {len(urls)}")
            self.status_var.set(f"Парсинг телефонов: {len(urls)} объявлений")
            
            self.is_parsing = True

            # Создаем экземпляр парсера телефонов
            self.parser_instance = AvitoParse(
                input_file=self.phone_excel_path,
                max_num_firm=firm_count,
                gui_works=True  # Указываем, что работает с GUI
            )
            
            # Запускаем парсер асинхронно
            self.runner = AsyncParserRunner(
                self.parser_instance,
                update_callback=self.update_gui_from_thread,
                completion_callback=self.on_parsing_complete,
            )
            self.parser_thread = self.runner.start()
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка запуска парсера телефонов: {str(e)}")
            self.log_message(f"Ошибка запуска парсера телефонов: {str(e)}")
            self.is_parsing = False
    
    def run_decoding(self):
        """Запуск декодирования изображений"""
        
        self.log_message("Запуск автоматического декодирования изображений...")
        self.status_var.set("Декодирование изображений...")
        
        # Устанавливаем флаг декодирования
        self.is_decoding = True
        
        # Создаем экземпляр декодера
        try:
            self.ocr_processor = AvitoOCRProcessor(
                self.input_json,
                self.output_excel,
                self.tesseract_path
            )
            
            # Запускаем декодирование в отдельном потоке
            self.decoding_thread = threading.Thread(
                target=self.run_decoding_process,
                daemon=True
            )
            self.decoding_thread.start()
            
        except Exception as e:
            self.log_message(f"Ошибка запуска декодирования: {str(e)}")
            self.is_decoding = False
            
    def run_decoding_process(self):
        """Запуск процесса декодирования в отдельном потоке"""
        try:
            # Запускаем декодирование с callback для обновления прогресса
            success = self.ocr_processor.parse_main(update_callback=self.update_gui_from_thread)
            
            # После завершения проверяем, была ли остановка
            def check_and_update():
                if hasattr(self, 'ocr_processor') and hasattr(self.ocr_processor, 'stop_flag') and self.ocr_processor.stop_flag:
                    # Если была остановка пользователем
                    self.status_var.set("Декодирование остановлено")
                    self.log_message("Декодирование остановлено пользователем")
                    self.is_decoding = False
                elif success:
                    # Если успешно завершилось
                    self.on_decoding_complete(True)
                else:
                    # Если завершилось с ошибкой
                    self.on_decoding_complete(False)
            
            self.after(0, check_and_update)
                
        except Exception as e:
            self.update_gui_from_thread(f"Ошибка декодирования: {str(e)}")
            self.on_decoding_complete(False)
                
    def on_decoding_complete(self, success=True):
        """Вызывается при завершении декодирования"""
        def update():
            # Проверяем, что декодирование все еще активно
            if self.is_decoding:
                self.is_decoding = False
                self.is_parsing = False
                if success:
                    self.status_var.set("Декодирование успешно завершено!")
                    self.log_message("Декодирование успешно завершено!")
        
        self.after(0, update)
    
    def btn_open_decode(self):
        """Обработчик кнопки 'Открыть JSON файл' для декодирования"""
        file_path = filedialog.askopenfilename(
            title="Выберите JSON файл для декодирования",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            # Сохраняем путь для декодирования
            self.decode_json_path = file_path
                        # Отображаем имя файла в интерфейсе
            file_name = os.path.basename(file_path)
            if len(file_name) > 22:
                # Обрезаем первые 20 символов, добавляем "...", затем пробел и расширение
                file_basename = file_name[:17] + "... " + file_name[file_name.rfind('.'):]
            else:
                file_basename = file_name
            self.json_file_path.set(f"Выбран: {file_basename}")
            
            self.update_idletasks()
            try:
                self.df = self.load_data(file_path)
                self.status_var.set(f"Успех! Загружено: {len(self.df)} изображений")
                
                # Автоматически переключаем на режим декодирования
                self.parser_mode_key.set("decode")
                self.toggle_parser_mode()
                
                self.log_message(f"JSON файл успешно загружен!")
                self.log_message(f"Количество потенциальных изображений: {len(self.df)}")
                self.log_message(f"Режим переключен на декодирование изображений.")
                self.status_var.set(f"Количество изображений в JSON: {len(self.df)}")
                    
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить JSON файл:\n{str(e)}")
                self.status_var.set("Ошибка загрузки файла")

    def decode_photo_boolean(self):
        """Включение/отключение декодирования изображений"""
        if self.enable_keyword_var.get():
            self.bool_decode_input = True
            self.log_message("Декодирование изображений: ВКЛЮЧЕНО")
        else:
            self.bool_decode_input = False
            self.log_message("Декодирование изображений: ВЫКЛЮЧЕНО")
    
    def on_parsing_complete(self, flag=True):
        """Вызывается при завершении парсинга (успешном или с ошибкой)"""
        def update():
            self.is_parsing = False
            if flag:
                self.status_var.set("Парсинг успешно завершен")
                self.log_message("Парсинг успешно завершен")
                if self.parser_mode_key.get() == "phone" and self.bool_decode_input:
                    # Запускаем декодирование
                    self.run_decoding()
            else:
                self.status_var.set("Парсинг остановлен")
                self.log_message("Парсинг остановлен")
        
        # Выполняем в основном потоке GUI
        self.after(0, update)
        
    def stop_parsing(self):
        """Остановка парсинга - просто закрываем Chrome"""
        if not self.is_parsing:
            self.log_message("Ничего не выполняется!")
            return
        
        self.is_parsing = False
        
        # Просто закрываем Chrome через taskkill
        import subprocess
        import os
        
        try:
            if os.name == 'nt':  # Windows
                # Команда для закрытия Chrome
                result = subprocess.run(
                    ['taskkill', '/F', '/IM', 'chrome.exe', '/T'],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    self.log_message("Chrome успешно закрыт")
                else:
                    self.log_message(f"Chrome закрыт (код: {result.returncode})")
                    
            else:  # Linux/Mac
                subprocess.run(['pkill', 'chrome'], capture_output=True)
                self.log_message("Chrome закрыт")
                
        except Exception as e:
            self.log_message(f"При закрытии Chrome: {str(e)}")
        
        self.status_var.set("Парсинг остановлен")
        self.log_message("Парсинг остановлен пользователем")
    
    def copy_ads_file_to_path(self):
        self.file_to_path(self.source_file_path)
        
    def copy_ready_file_to_path(self):
        self.file_to_path(self.output_excel)
        
    def file_to_path(self, file_path):
        """Копирование конкретного файла в выбранную папку"""
        if not os.path.exists(file_path):
            self.log_message("Ошибка экспорта объявлений! Исходный файл не найден.")
            self.status_var.set("Исходный файл не найден.")
            return
        
        target_folder = filedialog.askdirectory(
            title="Выберите папку для копирования файла"
        )
        
        if not target_folder:
            return
        
        try:
            filename = os.path.basename(file_path)
            target_path = os.path.join(target_folder, filename)
            
            # Проверка на существование
            if os.path.exists(target_path):
                overwrite = messagebox.askyesno(
                    "Подтверждение",
                    f"Файл '{filename}' уже существует. Заменить?"
                )
                if not overwrite:
                    return
            
            shutil.copy2(file_path, target_path)
            
            self.log_message(f"Успех! Файл '{filename}' успешно скопирован в:\n{target_folder}")
            self.status_var.set(f"Файл '{filename}' успешно скопирован!")
            
        except Exception as e:
            self.log_message(f"Ошибка! Не удалось скопировать файл:\n{str(e)}")
            self.status_var.set("Не удалось скопировать файл.")
        
    def create_status_bar(self):
        """Создание строки состояния"""
        self.status_var = tk.StringVar()
        self.status_var.set("Готов к работе")
        self.status_bar = ttk.Label(self, textvariable=self.status_var, 
                                   relief=tk.SUNKEN, padding=(10, 5))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def load_data(self, file_path):
        """Загружаю и обрабатываю файл .xlsx или .json"""
        try:
            # Определяем расширение файла
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext in ['.xlsx', '.xls']:
                # Загрузка Excel файла
                df = pd.read_excel(file_path, na_values=["--.--", "nan", "NaN", "", "---"])
                
                return df
                
            elif file_ext == '.json':
                import json
                
                # Читаем JSON файл
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Проверяем структуру данных
                if isinstance(data, dict):
                    # Если это словарь с URL как ключи и base64 как значения
                    # Преобразуем в DataFrame
                    back_skip = ["__SKIP_UNAVAILABLE__", "__SKIP_LIMIT__", "__SKIP_NO_CALLS__", "__SKIP_ON_REVIEW__"]
                    records = []
                    for url, img_data in data.items():
                        if img_data not in back_skip:
                            records.append({
                                'URL': url,
                                'Image_Data': img_data
                            })
                    
                    df = pd.DataFrame(records)
                    print(f"Загружено {len(df)} изображений из JSON")
                    
                elif isinstance(data, list):
                    # Если это список объектов
                    df = pd.DataFrame(data)
                else:
                    raise ValueError(f"Неожиданный формат JSON данных")
                return df
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {file_ext}")

        except Exception as e:
            print(f"Ошибка загрузки данных: {e}")
            raise
            
    def btn_open(self):
        """Обработчик кнопки 'Excel файл после поиска обновлений'"""
        file_path = filedialog.askopenfilename(
            title="Выберите Excel файл с ссылками на объявления",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if file_path:
            # Сохраняем путь для парсера телефонов
            self.phone_excel_path = file_path
            
            # Отображаем имя файла в интерфейсе
            file_name = os.path.basename(file_path)
            if len(file_name) > 22:
                # Обрезаем первые 20 символов, добавляем "...", затем пробел и расширение
                file_basename = file_name[:17] + "... " + file_name[file_name.rfind('.'):]
            else:
                file_basename = file_name
            self.excel_file_path.set(f"Выбран: {file_basename}")

            self.update_idletasks()
            try:
                # Загружаем для проверки
                self.df = self.load_data(file_path)
                
                # Проверяем наличие необходимой колонки
                if 'Ссылка на объявление' not in self.df.columns:
                    messagebox.showwarning("Предупреждение", 
                        "В файле должна быть колонка 'Ссылка на объявление'!")
                    self.phone_excel_path = None
                else:
                    self.log_message(f"Excel файл успешно загружен!")
                    self.log_message(f"Количество объявлений: {len(self.df)}")
                    self.log_message(f"Теперь можете запустить парсинг телефонов.")
                    self.status_var.set(f"Количество объявлений в Excel: {len(self.df)}")
            
                    
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{str(e)}")
                self.status_var.set("Ошибка загрузки файла")
                self.phone_excel_path = None

    def clean_directory_except_py(self):
        """
        Удаляет все файлы в указанной директории, кроме .py файлов
        directory_path (str): Путь к директории для очистки
        """
        len_file_bugs = len(os.listdir(self.clear_bugs))
        for filename in os.listdir(self.clear_bugs):
            file_path = os.path.join(self.clear_bugs, filename)
            
            # Проверяем, что это файл (а не папка) и не .py файл
            if os.path.isfile(file_path) and not filename.endswith('.py'):
                os.remove(file_path)
                print(f"Удален файл: {filename}")
        self.log_message(f"Список багов в количестве {len_file_bugs} штук успешно удален")
        self.status_var.set(f"Список багов удален!")
      
    def on_continue_clicked(self):
        """Обработчик нажатия кнопки 'Вход выполнен'"""
        try:
            if hasattr(self, 'parser_instance') and self.parser_instance:
                # Отправляем подтверждение в парсер
                self.parser_instance.trigger_enter_from_gui()
                self.log_message("Подтверждение входа отправлено парсеру")
                self.status_var.set("Парсинг продолжается...")
            else:
                self.log_message("Ошибка: парсер не инициализирован")
        except Exception as e:
            self.log_message(f"Ошибка отправки подтверждения: {str(e)}")
        
    def hotkeys_info(self):
        """Обработчик кнопки 'Горячие клавиши'"""
        # Создаем собственное окно вместо messagebox
        top = Toplevel()
        top.title("Горячие клавиши")
        
        # Создаем Frame для размещения текстового виджета и скроллбара
        frame = tk.Frame(top)
        frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Создаем текстовое поле
        text_widget = Text(frame, wrap=tk.WORD, width=60, height=12, 
                        font=("Arial", 10))
        
        
        top.resizable(False, False)
        
        # Добавляем остальной текст
        cities = [
        "       Горячие клавиши приложения:\n",
        "   Основные операции:\n",
        "     • Ctrl + O   - Открыть Excel файл...\n",
        "     • Ctrl + P   - Открыть JSON файл...\n",
        "     • Ctrl + S   - Остановить парсинг\n",
        "     • Ctrl + L    - Очистить лог\n",
        "     • Ctrl + Q   - Выйти из приложения\n",
        "   Дополнительные:\n",
        "     • Ctrl + G - Сгенерировать URL (в режиме по ключу)\n",
        "     • F1         - Руководство пользователя\n",
        "     • Enter     - Запустить парсинг (когда курсор в поле ввода)\n",
        "   Сочетания клавиш работают в любом месте приложения.\n",
        ]
        
        for city_text in cities:
            text_widget.insert(tk.END, city_text)
        
        text_widget.configure(state='disabled')  # Только для чтения
        
        # Кнопка закрытия
        button = tk.Button(top, text="Закрыть", command=top.destroy)
        
        text_widget.pack()
        button.pack(pady=10)
        
        # Центрируем окно
        top.update_idletasks()
        width = top.winfo_width()
        height = top.winfo_height()
        x = (top.winfo_screenwidth() // 2) - (width // 2)
        y = (top.winfo_screenheight() // 2) - (height // 2)
        top.geometry(f'{width}x{height}+{x}+{y}')

    def btn_about(self):
        """Обработчик кнопки 'О программе'"""
        # Создаем собственное окно вместо messagebox
        top = Toplevel()
        top.title("Одноименные города")
        
        # Создаем Frame для размещения текстового виджета и скроллбара
        frame = tk.Frame(top)
        frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Создаем текстовое поле
        text_widget = Text(frame, wrap=tk.WORD, width=67, height=25, 
                        font=("Arial", 10))
        
        top.resizable(False, False)
        
        # Добавляем остальной текст
        about_text = [
        "       Avito Parser\n\n",
        "  Данный инструмент предназначен для сбора открытой информации в образовательных и исследовательских целях.\n\n",
        "    Версия 0.3.4\n\n",
        "  Режимы работы:\n",
        "    1. Парсер по ключу - поиск организаций по ключевому слову и городу\n",
        "    2. Парсер по URL - парсинг конкретной страницы поиска Avito\n\n",
        "  Возможности:\n",
        "    • Поддержка светлой и темной темы\n\n",
        "  Используемые технологии:\n",
        "    • Python 3.11+\n",
        "    • Playwright для веб-скрапинга\n",
        "    • tkinter для графического интерфейса\n",
        "    • sv_ttk для современных стилей\n\n",
        "    https://github.com/itrickon/AvitoParser",
        ]
        
        for city_text in about_text:
            text_widget.insert(tk.END, city_text)
        
        text_widget.configure(state='disabled')  # Только для чтения
        
        # Кнопка закрытия
        button = tk.Button(top, text="Закрыть", command=top.destroy)
        
        text_widget.pack()
        button.pack(pady=10)
        
        # Центрируем окно
        top.update_idletasks()
        width = top.winfo_width()
        height = top.winfo_height()
        x = (top.winfo_screenwidth() // 2) - (width // 2)
        y = (top.winfo_screenheight() // 2) - (height // 2)
        top.geometry(f'{width}x{height}+{x}+{y}')
 
    def log_message(self, message):
        """Добавление сообщения в лог с цветами"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Определяем уровень
        msg_lower = message.lower()
        error_words = ["ошибка", "error", "closed", "exception", "failed", "прервано"]
        warning_words = ["предупреждение", "warning", "внимание", "остановлен"]
        success_words = ["успешно", "success", "завершен", "готово", "успешн"]
        
        if any(word in msg_lower for word in error_words):
            level = "ERROR"
        elif any(word in msg_lower for word in warning_words):
            level = "WARNING"
        elif any(word in msg_lower for word in success_words):
            level = "SUCCESS"
        else:
            level = "INFO"
        
        formatted_message = f"[{timestamp}] [{level}] {message}\n"
        
        # Вставляем с тегом
        self.log_text.insert(tk.END, formatted_message, (level,))
        self.log_text.see(tk.END)

    def clear_log(self):
        """Очистка лога"""
        self.log_text.delete(1.0, tk.END)
        self.log_message("Лог очищен")
        self.status_var.set("Лог очищен")
 
    def update_gui_from_thread(self, message):
        """Обновление GUI из потока"""
        def update():
            self.log_message(message)
            self.status_var.set(message[:50] + "..." if len(message) > 50 else message)
            
        self.after(0, update)
 
    def btn_exit(self):
        """Выход из приложения"""
        if self.is_parsing:
            if not messagebox.askyesno("Предупреждение", 
                                      "Парсинг выполняется. Вы уверены, что хотите выйти?"):
                return
        
        if messagebox.askyesno("Выход", "Вы уверены, что хотите выйти?"):
            if self.is_parsing:
                self.stop_parsing()
            self.parent.quit()
        
def main():
    """Точка входа в приложение"""
    root = tk.Tk()
    app = AvitoParser(root)
    root.mainloop()


if __name__ == "__main__":
    main()