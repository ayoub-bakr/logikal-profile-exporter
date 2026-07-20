import os
import psutil
from pywinauto import Application
from src.config import AppConfig
from src.errors import LogikalNotRunningError

class LogikalAppManager:
    def __init__(self, config: AppConfig, selectors: dict):
        self.config = config
        self.selectors = selectors
        self.app = None
        self.main_window = None

    def connect_or_launch(self) -> Application:
        """الاتصال بـ Logikal إذا كان مفتوحاً، أو تشغيله تلقائياً في حال انغلاقه."""
        sel = self.selectors["main_window"]
        
        # محاولة البحث عن عملية قيد التشغيل أولاً
        logikal_running = False
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and 'logikal' in proc.info['name'].lower():
                logikal_running = True
                break

        if logikal_running:
            self.app = Application(backend=self.config.backend).connect(
                title_re=sel["title_re"], timeout=self.config.dialog_timeout_seconds
            )
        else:
            if not os.path.exists(self.config.logikal_executable):
                raise LogikalNotRunningError(f"Logikal executable path invalid: {self.config.logikal_executable}")
            self.app = Application(backend=self.config.backend).start(self.config.logikal_executable)

        self.main_window = self.app.window(title_re=sel["title_re"])
        self.main_window.wait("visible enabled ready", timeout=self.config.dialog_timeout_seconds)
        return self.app

    def get_cad_window(self):
        sel = self.selectors["cad_window"]
        cad_win = self.app.window(title_re=sel["title_re"])
        cad_win.wait("visible", timeout=self.config.dialog_timeout_seconds)
        return cad_win