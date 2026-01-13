import tkinter as tk
from tkinter import ttk, messagebox


class MainApplication(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self.parent.title("AvitoParser")
        self.parent.geometry("1000x700")
        
        self.create_widgets()    
           
    def create_widgets(self):
        """Создание всех виджетов интерфейса"""
        self.top_level_menu()
        
    def top_level_menu(self):
        """Верхнее меню"""
        menubar = tk.Menu(self.parent)
        self.parent.config(menu=menubar)

        parse_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Парсинг", menu=parse_menu)
        parse_menu.add_command(label="Запустить парсинг")
        parse_menu.add_separator()
        parse_menu.add_command(label="Выход")

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="Руководство пользователя")
        help_menu.add_command(label="Горячие клавиши")
        help_menu.add_separator()
        help_menu.add_command(label="О программе")
        
        
        
def main():
    """Точка входа в приложение"""
    root = tk.Tk()
    app = MainApplication(root)
    root.mainloop()


if __name__ == "__main__":
    main()