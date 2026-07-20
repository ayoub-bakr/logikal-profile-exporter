import time
from pywinauto import Application
from rich.console import Console

console = Console()

def navigate_to_project_centre():
    console.print("[yellow]🔄 Connecting to LogiKal 11 Window...[/yellow]")
    
    # الاتصال بالنافذة باستخدام العنوان الدقيق المكتشف
    app = Application(backend="uia").connect(title="LogiKal 11.2.11.67 Home", timeout=10)
    main_win = app.window(title="LogiKal 11.2.11.67 Home")
    
    console.print("[green]✔ Connected. Location: Home Screen.[/green]")
    
    # تحديد زر الـ Project Centre والضغط عليه
    project_centre_btn = main_win.child_window(title="Project Centre", control_type="Button")
    
    console.print("[yellow]🖱 Clicking on 'Project Centre' button...[/yellow]")
    project_centre_btn.click_input() # click_input تحاكي حركة الماوس الحقيقية وهي الأكثر أماناً
    
    console.print("[yellow]⏳ Waiting for Project Centre UI to load...[/yellow]")
    time.path_effects = time.sleep(3) # وقت مستقطع للتأكد من تحميل الواجهة الجديدة
    
    # حفظ الهيكل الجديد لمعرفة أين تقع المشاريع والـ Profiles
    console.print("[yellow]📝 Documenting new UI layout into 'artifacts/project_centre_tree.txt'...[/yellow]")
    
    import sys
    from pathlib import Path
    Path("artifacts").mkdir(exist_ok=True)
    
    with open("artifacts/project_centre_tree.txt", "w", encoding="utf-8") as f:
        sys.stdout = f
        # نربط الاتصال بالنافذة الجديدة (قد يتغير عنوانها عند الانتقال لمركز المشاريع)
        # لذا يفضل إيجاد النافذة الفعالة حالياً من التطبيق
        active_win = app.top_window()
        active_win.print_control_identifiers()
        
    sys.stdout = sys.__stdout__
    console.print("[bold green]✔ Done! Check 'artifacts/project_centre_tree.txt' to build our exporter script.[/bold green]")

if __name__ == "__main__":
    navigate_to_project_centre()