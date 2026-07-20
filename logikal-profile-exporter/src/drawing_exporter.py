import time
from pathlib import Path
from pywinauto import Application
from src.config import AppConfig
from src.dialogs import DialogHandler

class DrawingExporter:
    def __init__(self, app: Application, config: AppConfig, selectors: dict, dialog_handler: DialogHandler):
        self.app = app
        self.config = config
        self.selectors = selectors
        self.dialog_handler = dialog_handler

    def add_article_to_drawing(self, article_id: str):
        sel = self.selectors["add_profile_dialog"]
        dialog = self.app.window(title=sel["title"])
        
        # اختيار العنصر المحدد بالضغط المباشر أو الـ Keyboard Type-in
        grid = dialog.child_window(auto_id=sel["article_list_id"], control_type="DataGrid")
        grid.type_keys(article_id + "{ENTER}")
        
        # الضغط على OK لإدراجه في الكاد
        dialog.child_window(auto_id=sel["ok_button_id"], control_type="Button").click()
        time.sleep(2) # انتظار انتهاء التسييل والرسم داخل الـ Viewport

    def export_to_dxf(self, output_path: Path):
        sel = self.selectors["export_dialog"]
        cad_win = self.app.window(title_re=self.selectors["cad_window"]["title_re"])
        
        # فتح نافذة التصدير عبر الشورت كت التابع للوجيكال (مثال: Ctrl+E)
        cad_win.type_keys("^e")
        
        export_dialog = self.app.window(title=sel["title"])
        export_dialog.wait("visible enabled", timeout=self.config.dialog_timeout_seconds)

        # تحديد صيغة الملف DXF من الكومبو بوكس
        export_dialog.child_window(auto_id=sel["file_type_combo_id"], control_type="ComboBox").select("DXF (*.dxf)")
        
        # إدخال المسار الكامل مع الاسم المقترح
        edit_field = export_dialog.child_window(auto_id=sel["file_name_edit_id"], control_type="Edit")
        edit_field.set_text(str(output_path.resolve()))
        
        # تنفيذ عملية التصدير
        export_dialog.child_window(auto_id=sel["save_button_id"], control_type="Button").click()
        
        # معالجة احتمالية ظهور نافذة Overwrite تأكيدية
        self.dialog_handler.handle_overwrite_popup(self.app)

    def clear_cad_viewport(self):
        """تنظيف لوحة الرسم من العنصر الحالي لتهيئة السطح للـ Profile التالي."""
        cad_win = self.app.window(title_re=self.selectors["cad_window"]["title_re"])
        cad_win.type_keys("^a{DELETE}") # تحديد الكل ثم مسح
        time.sleep(0.5)