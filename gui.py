import os
import sv_ttk
import tkinter as tk
import json
import pandas as pd
from tkinter import *
from tkinter import ttk, messagebox, filedialog
    
class MainApplication(ttk.Frame):
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
 
    def interface_style(self):
        sv_ttk.set_theme("light")
           
    def create_widgets(self):
        """Создание всех виджетов интерфейса"""
        self.top_level_menu()
        self.create_parser_controls()
        
    def top_level_menu(self):
        """Верхнее меню"""
        menubar = tk.Menu(self.parent)
        self.parent.config(menu=menubar)

        parse_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Парсинг", menu=parse_menu)
        parse_menu.add_command(label="Открыть...", accelerator="Ctrl+O", command=self.btn_open)
        self.parent.bind("<Control-o>", lambda _: self.btn_open())  # Горячие клавиши
        parse_menu.add_separator()

        parse_menu.add_command(label="Начать поиск объявлений")
        parse_menu.add_command(label="Начать поиск объявлений по URL")
        parse_menu.add_command(label="Начать поиск телефонов")
        parse_menu.add_command(label="Начать декодирование изображений")
        parse_menu.add_separator()
        parse_menu.add_command(label="Выход", command=self.btn_exit)

        export_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Экспорт", menu=export_menu)
        export_menu.add_command(label="Экспорт телефонов...")
        export_menu.add_command(label="Экспорт изображений...")
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="Руководство пользователя")
        help_menu.add_command(label="Горячие клавиши")
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
                                          command="#", width=22)
        self.generate_url_btn.grid(row=1, column=1, padx=5, pady=0, sticky=tk.W)
        
        row += 1
        
        # 5. Кнопки управления
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, sticky=tk.W, padx=20, pady=4)
        button_frame.config(height=40)
        
        ttk.Button(button_frame, text="Начать парсиг", 
                  command='#', width=20).pack(side=tk.LEFT, padx=5)
        
        self.btn_continue_parse = ttk.Button(button_frame, text="Продолжить парсинг", 
                                     command='#', width=20)
        self.btn_continue_parse.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="Остановить парсинг", 
                  command='#', width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Очистить лог", 
                  command='#', width=20).pack(side=tk.LEFT, padx=5)
        
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
                foreground="gray", wraplength=300).grid(row=0, column=2, padx=10, pady=0, sticky=tk.W)
        
        # Checkbutton для включения фильтра по ключевому слову
        self.enable_keyword_var = tk.BooleanVar(value=True)
        self.enabled_checkbutton = ttk.Checkbutton(self.phone_frame, text="Включить декодирование изображений",
                                                variable=self.enable_keyword_var, command="self.toggle_keyword_filter")
        self.enabled_checkbutton.grid(row=1, column=1, padx=5, pady=0, sticky=tk.W)
        
        
    def create_decode_params(self):
        """Создание элементов для парсера телефонов"""
        self.decode_frame = ttk.Frame(self.params_frame)
        self.decode_frame.place(x=0, y=0, relwidth=1, relheight=1)
        
        # Загрузить Excel файл
        ttk.Label(self.decode_frame, text="Выбрать файл:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=5)
        
        self.json_file_btn = ttk.Button(self.decode_frame, text="Файл для декодирования фото", 
                                        command=self.btn_open_decocde, width=28)
        self.json_file_btn.grid(row=0, column=1, padx=5, pady=0, sticky=tk.W)
        
        # Путь к файлу (необязательно, но полезно)
        self.excel_file_path = tk.StringVar()
        ttk.Label(self.decode_frame, textvariable=self.excel_file_path, 
                foreground="gray", wraplength=300).grid(row=0, column=2, padx=10, pady=0, sticky=tk.W)
        
        # Пустое пространство для выравнивания
        empty_space = ttk.Frame(self.url_frame, height=30)
        empty_space.grid(row=1, column=0, columnspan=2, pady=0)
        
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
     
    def load_telemetry_data(self, file_path):
        """Загружаю и обрабатываю файл с телеметрией UAV"""
        try:
            # Определяем расширение файла
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(file_path, na_values=["--.--", "nan", "NaN", "", "---"])
            elif file_ext == '.json':
                df = pd.read_json(file_path)
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {file_ext}")
            
            # Обработка данных (общая для всех форматов)
            if "Timestamp" in df.columns:
                df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
            
            return df

        except Exception as e:
            print(f"Ошибка загрузки данных: {e}")
            raise
            
    def btn_open(self):
        """Обработчик кнопки 'Открыть'"""
        file_path = filedialog.askopenfilename(
            title="Выберите файл телеметрии",
            filetypes=[("Excel", "*.xlsx"), ("All files", "*.*")],
        )
        if file_path:
            # self.status_var.set(f"Загрузка файла: {file_path}...")
            self.update_idletasks()  # Обновляю статус-бар
            try:
                self.df = self.load_telemetry_data(file_path)
                # self.status_var.set(f"Успех! Загружено: {len(self.df)} записей")
                # self.enable_export_menus()
                # self.create_tabs()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{str(e)}")
                # self.status_var.set("Ошибка загрузки файла")
                
    def btn_open_decocde(self):
        """Обработчик кнопки 'Открыть'"""
        file_path = filedialog.askopenfilename(
            title="Выберите файл телеметрии",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            # self.status_var.set(f"Загрузка файла: {file_path}...")
            self.update_idletasks()  # Обновляю статус-бар
            try:
                self.df = self.load_telemetry_data(file_path)
                # self.status_var.set(f"Успех! Загружено: {len(self.df)} записей")
                # self.enable_export_menus()
                # self.create_tabs()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{str(e)}")
                # self.status_var.set("Ошибка загрузки файла")
 
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
        "    Версия 0.0.2\n\n",
        "  Режимы работы:\n",
        "    1. Парсер по ключу - поиск организаций по ключевому слову и городу\n",
        "    2. Парсер по URL - парсинг конкретной страницы поиска Avito\n\n",
        "  Возможности:\n",
        "    • Поддержка светлой и темной темы\n\n",
        "  Используемые технологии:\n",
        "    • Python 3.11+\n",
        "    • Playwright для веб-скрапинга\n",
        "    • tkinter для графического интерфейса\n",
        "    • sv_ttk для современных стилей\n",
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
 
    def btn_exit(self):
        """Выход из приложения"""
        """if self.is_parsing:
            if not messagebox.askyesno("Предупреждение", 
                                      "Парсинг выполняется. Вы уверены, что хотите выйти?"):
                return"""
        
        if messagebox.askyesno("Выход", "Вы уверены, что хотите выйти?"):
            # if self.is_parsing:
            #     self.stop_parsing()
            self.parent.quit()
        
def main():
    """Точка входа в приложение"""
    root = tk.Tk()
    app = MainApplication(root)
    root.mainloop()


if __name__ == "__main__":
    main()