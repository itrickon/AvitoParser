import asyncio
import threading

class AsyncParserRunner:
    def __init__(self, parser_instance, update_callback=None, completion_callback=None):
        self.parser_instance = parser_instance
        self.update_callback = update_callback
        self.completion_callback = completion_callback
        self.loop = None
        self.task = None

    def start(self):
        """Запуск парсинга в отдельном потоке с корректной обработкой asyncio"""
        thread = threading.Thread(target=self._run_in_thread, daemon=True)
        thread.start()
        
        return thread

    def _run_in_thread(self):
        """Запуск asyncio в отдельном потоке"""
        try:
            # Создаем новый event loop для этого потока
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Запускаем парсинг
            self.loop.run_until_complete(self._parse())
        except Exception as e:
            if self.update_callback:
                self.update_callback(f"Ошибка: {str(e)}")
        finally:
            if self.loop and not self.loop.is_closed():
                self.loop.close()

    async def _parse(self):
        """Основная функция парсинга"""
        try:
            if self.update_callback:
                self.update_callback("Начало парсинга...")

            await self.parser_instance.parse_main(update_callback=self.update_callback)

            if self.completion_callback:
                self.completion_callback(flag=True)
        except Exception as e:
            if self.update_callback:
                self.update_callback(f"Ошибка при парсинге: {str(e)}")
            if self.completion_callback:
                self.completion_callback(flag=False)
            raise