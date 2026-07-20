import time
from pywinauto import Application, WindowSpecification
from rich import print

class DialogHandler:
    def __init__(self, selectors: dict, timeout: int):
        self.selectors = selectors
        self.timeout = timeout

    def handle_overwrite_popup(self, app: Application):
        """التحقق من ظهور نافذة 'هل تريد استبدال الملف؟' والموافقة عليها."""
        sel = self.selectors["overwrite_dialog"]
        try:
            # محاولة البحث عن نافذة الاستبدال بفترة انتظار قصيرة جداً لعدم تعطيل الحلقة
            overwrite_win = app.window(title=sel["title"])
            if overwrite_win.exists(timeout=2):
                print("[yellow]⚠️ Overwrite prompt detected! Confirming replace...[/yellow]")
                overwrite_win.child_window(auto_id=sel["yes_button_id"], control_type="Button").click()
        except Exception:
            pass # لم تظهر النافذة، المتابعة بشكل طبيعي

    def close_unexpected_popups(self, main_window: WindowSpecification):
        """إغلاق النوافذ التحذيرية أو أخطاء التراخيص المنبثقة لإعادة البرنامج لحالة مستقرة."""
        try:
            for child in main_window.children():
                if child.element_info.control_type == "Window" and child.is_visible():
                    print(f"[red]⚠️ Unexpected popup identified: '{child.window_text()}'. Closing it.[/red]")
                    child.close()
        except Exception:
            pass