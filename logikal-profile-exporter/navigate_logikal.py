import time
import subprocess
import pyperclip  # pip install pyperclip
from pywinauto import Application
from pywinauto.keyboard import send_keys
from rich.console import Console

console = Console()

LOGIKAL_EXE_PATH = r"C:\Program Files\LogiKal\LogiKal.exe"

def ensure_logikal_running():
    console.print("[yellow]🔄 التحقق من حالة برنامج LogiKal...[/yellow]")
    try:
        app = Application(backend="uia").connect(title_re=".*LogiKal.*", timeout=5)
        return app
    except Exception:
        subprocess.Popen(LOGIKAL_EXE_PATH)
        time.sleep(10)
        return Application(backend="uia").connect(title_re=".*LogiKal.*", timeout=20)

def run_full_export_pipeline():
    console.print("[bold cyan]🚀 بدء مسار الأتمتة المباشر والسريع...[/bold cyan]")
    
    app = ensure_logikal_running()
    main_win = app.top_window()
    main_win.set_focus()
    time.sleep(1)

    # ---------------------------------------------------------
    # 1. التنقل: System Database -> System Input -> Profile Data
    # ---------------------------------------------------------
    console.print("[yellow]📂 1. فتح System Database -> System Input -> Profile Data...[/yellow]")
    try:
        send_keys("%s")
        time.sleep(0.5)

        send_keys("{DOWN 2}")
        time.sleep(0.3)

        send_keys("{RIGHT}")
        time.sleep(0.3)

        send_keys("{DOWN 3}")
        time.sleep(0.3)

        send_keys("{ENTER}")
        console.print("[green]✔ تم اختيار Profile Data بنجاح![/green]")
    except Exception as e:
        console.print(f"[bold red]❌ تعذر فتح القائمة: {str(e)}[/bold red]")

    # ---------------------------------------------------------
    # 2. التعامل مع نافذة Supplier
    # ---------------------------------------------------------
    console.print("[yellow]⏳ انتظار تحميل النافذة...[/yellow]")
    time.sleep(3)

    try:
        supplier_win = main_win.child_window(title="Supplier", control_type="Window")
        supplier_win.set_focus()
        ok_button = supplier_win.child_window(title="OK", control_type="Button")
        ok_button.click_input()
        console.print("[green]✔ تم تأكيد Supplier والضغط على OK.[/green]")
        time.sleep(3)
    except Exception:
        console.print("[yellow]ℹ لم تظهر نافذة Supplier (ربما الشاشة مفتوحة بالفعل).[/yellow]")

    # ---------------------------------------------------------
    # 3. جلب رقم المقطع والتصدير من الرسمة السفلى
    # ---------------------------------------------------------
    try:
        profile_number = "2256"
        try:
            top_box = main_win.child_window(auto_id="Edit", control_type="Edit")
            val = top_box.window_text().strip()
            if val:
                profile_number = val.split()[-1]
        except Exception:
            pass
        
        console.print(f"[bold cyan]📋 رقم المقطع المستهدف: {profile_number}[/bold cyan]")

        # النقر بالزر الأيمن على رسمة CAD بأسفل اليسار
        rect = main_win.rectangle()
        rel_x = int(rect.width() * 0.08)   # 8% من اليسار
        rel_y = int(rect.height() * 0.88)  # 88% أسفل الشاشة

        console.print(f"[yellow]🖱 2. النقر بالزر الأيمن على رسمة CAD بأسفل اليسار...[/yellow]")
        main_win.right_click_input(coords=(rel_x, rel_y))
        time.sleep(1)

        console.print("[yellow]📤 3. اختيار Export (نزول 4 خطوات)...[/yellow]")
        send_keys("{DOWN 4}{ENTER}")
        time.sleep(2)

        # ---------------------------------------------------------
        # 4. التفاعل المباشر عبر send_keys مع نافذة Export Drawing
        # ---------------------------------------------------------
        console.print("[yellow]🔍 4. تعبئة البيانات في نافذة 'Export Drawing'...[/yellow]")
        
        # نسخ رقم المقطع للحافظة
        pyperclip.copy(profile_number)

        # أ. الانتقال لحقل File Name بـ Alt+N ولصق رقم المقطع
        console.print(f"[yellow]✍️ 5. كتابة اسم الملف: {profile_number}...[/yellow]")
        send_keys("%n")
        time.sleep(0.4)
        send_keys("^a{BACKSPACE}")
        time.sleep(0.2)
        send_keys("^v")
        time.sleep(0.5)

        # ب. الانتقال لـ File Type واختيار DXF
        console.print("[yellow]🔄 6. تحويل نوع الملف إلى DXF...[/yellow]")
        send_keys("%t")
        time.sleep(0.4)
        send_keys("d")  # الضغط على 'd' للانتقال لـ DXF
        time.sleep(0.5)

        # ج. الضغط على Export (Alt+E)
        console.print("[yellow]💾 7. الضغط على زر Export...[/yellow]")
        send_keys("%e")
        time.sleep(2)

        # ---------------------------------------------------------
        # 5. الضغط على OK فقط لإتمام العملية
        # ---------------------------------------------------------
        console.print("[yellow]🔘 8. الضغط على زر OK...[/yellow]")
        try:
            # محاولة النقر المباشر على زر OK الخاص بالنافذة الرئيسة/الفرعية
            ok_final_btn = main_win.child_window(title="OK", control_type="Button")
            ok_final_btn.click_input()
        except Exception:
            # استخدام زر Enter كبديل مستقر للضغط على OK المظلل
            send_keys("{ENTER}")

        console.print(f"[bold green]🎉 تم كتابة الرقم '{profile_number}' واختيار DXF ثم الضغط على OK بنجاح![/bold green]")

    except Exception as e:
        console.print(f"[bold red]❌ حدث خطأ: {str(e)}[/bold red]")

if __name__ == "__main__":
    run_full_export_pipeline()