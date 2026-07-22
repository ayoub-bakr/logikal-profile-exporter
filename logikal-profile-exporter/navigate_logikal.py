import time
import subprocess
import re
import pyperclip  # pip install pyperclip
from pywinauto import Application, Desktop
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

def _looks_like_profile_number(text):
    """يحدد إن كان النص يشبه رقم بروفايل (K802, 2256, K781X2...) وليس نص
    وصفي لقائمة منسدلة أخرى (مثل 'Mullion/Transom' أو 'Without' أو 'Ohne')."""
    text = (text or "").strip()
    if not text:
        return False
    if " " in text or "/" in text:
        return False
    if len(text) > 12:
        return False
    if not re.search(r"\d", text):
        return False
    return True

def get_win32_form_window():
    """يتصل بنافذة LogiKal عبر win32 backend (وليس uia) لأن هذا التطبيق مبني
    بـ Delphi (VCL) ولا يعرض نص عناصره عبر UI Automation إطلاقاً. النافذة
    الحقيقية التي تحوي كل الحقول هي النموذج (Tfm*) وليست TApplication."""
    desktop = Desktop(backend="win32")
    matches = desktop.windows(title_re=".*LogiKal.*")
    if not matches:
        return None
    chosen = next(
        (w for w in matches if w.friendly_class_name().startswith("Tfm")),
        matches[0],
    )
    return chosen

def _find_profile_number_edits_win32(win32_win, max_nodes=3000):
    """يبحث (مع حماية من التكرار اللانهائي) عن كل عناصر Edit داخل النافذة
    عبر win32 backend، ويرجع (top, النص) لكل واحد منها."""
    results = []
    visited = set()

    def walk(ctrl):
        if len(visited) >= max_nodes:
            return
        try:
            handle = ctrl.handle
        except Exception:
            handle = None
        if handle is not None:
            if handle in visited:
                return
            visited.add(handle)

        try:
            cls = ctrl.friendly_class_name()
        except Exception:
            cls = ""

        if cls == "Edit":
            try:
                txt = ctrl.window_text().strip()
            except Exception:
                txt = ""
            try:
                top = ctrl.rectangle().top
            except Exception:
                top = 0
            results.append((top, txt))

        try:
            children = ctrl.children()
        except Exception:
            children = []
        for c in children:
            walk(c)

    walk(win32_win)
    return results

def extract_current_profile_number(win32_win):
    """يستخرج رقم البروفايل الحالي عبر win32 backend (WM_GETTEXT)، لأن UI
    Automation لا يستطيع رؤية نص عناصر هذا التطبيق (Delphi/VCL) إطلاقاً.
    نجمع كل عناصر Edit، نُبقي فقط ما يشبه رقم بروفايل فعلياً (بدون مسافات،
    يحتوي رقماً، قصير — هذا يستبعد تلقائياً 'AluK 45DS' و'leer' وغيرها)،
    ثم نختار الأعلى موضعاً على الشاشة لأن حقل رقم البروفايل يقع في الشريط
    العلوي أعلى من كل الحقول الفنية الأخرى."""
    if win32_win is None:
        return "Unknown"

    edits = _find_profile_number_edits_win32(win32_win)
    candidates = [(top, txt) for top, txt in edits if _looks_like_profile_number(txt)]

    if candidates:
        candidates.sort(key=lambda pair: pair[0])  # الأعلى (top) أولاً
        return candidates[0][1]

    return "Unknown"

def click_into_profile_list_and_go_first(main_win):
    """ينقر داخل قائمة البروفايلات في اللوحة اليسرى، ثم يذهب لأول عنصر فيها
    (Home/Ctrl+Home) حتى يمكن التنقل بين البروفايلات بعد ذلك بمفاتيح الأسهم فقط."""
    rect = main_win.rectangle()
    click_x = int(rect.width() * 0.05)   # داخل عمود "Profile" في أقصى اليسار
    click_y = int(rect.height() * 0.10)  # قرب أعلى القائمة

    console.print("[yellow]🖱 نقر داخل قائمة البروفايلات في اللوحة اليسرى...[/yellow]")
    main_win.click_input(coords=(click_x, click_y))
    time.sleep(0.3)

    # الذهاب لأول عنصر في القائمة
    send_keys("^{HOME}")
    time.sleep(0.3)

def export_current_profile(main_win, profile_number):
    """ينفذ خطوات التصدير (Export Drawing -> DXF -> OK) للبروفايل المحدد حالياً."""
    console.print(f"[bold cyan]📋 رقم المقطع المستهدف: {profile_number}[/bold cyan]")

    # النقر بالزر الأيمن على رسمة CAD بأسفل اليسار
    rect = main_win.rectangle()
    rel_x = int(rect.width() * 0.08)   # 8% من اليسار
    rel_y = int(rect.height() * 0.88)  # 88% أسفل الشاشة

    console.print(f"[yellow]🖱 2. النقر بالزر الأيمن على رسمة CAD بأسفل اليسار...[/yellow]")
    main_win.right_click_input(coords=(rel_x, rel_y))
    time.sleep(1)

    console.print("[yellow]📤 3. اختيار Export (نزول 4 خطوات)...[/yellow]")
    send_keys("{DOWN 3}{ENTER}")
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

def run_full_export_pipeline():
    console.print("[bold cyan]🚀 بدء مسار الأتمتة المباشر والسريع...[/bold cyan]")
    
    app = ensure_logikal_running()
    main_win = app.top_window()
    main_win.set_focus()
    time.sleep(1)

    # ---------------------------------------------------------
    # 1. التنقل: System Database -> System Input -> Profile Data
    # ---------------------------------------------------------
    # console.print("[yellow]📂 1. فتح System Database -> System Input -> Profile Data...[/yellow]")
    # try:
    #     send_keys("%s")
    #     time.sleep(0.5)

    #     send_keys("{DOWN 2}")
    #     time.sleep(0.3)

    #     send_keys("{RIGHT}")
    #     time.sleep(0.3)

    #     send_keys("{DOWN 3}")
    #     time.sleep(0.3)

    #     send_keys("{ENTER}")
    #     console.print("[green]✔ تم اختيار Profile Data بنجاح![/green]")
    # except Exception as e:
    #     console.print(f"[bold red]❌ تعذر فتح القائمة: {str(e)}[/bold red]")

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
    # 3. المرور على كل بروفايل في اللوحة اليسرى وتصديره
    # ---------------------------------------------------------
    try:
        click_into_profile_list_and_go_first(main_win)

        # نافذة win32 منفصلة تُستخدم فقط لقراءة رقم البروفايل (WM_GETTEXT)،
        # لأن UI Automation لا يرى نص عناصر هذا التطبيق إطلاقاً
        win32_win = get_win32_form_window()
        if win32_win is None:
            console.print("[bold red]❌ تعذر الاتصال بالنافذة عبر win32 backend لقراءة رقم البروفايل.[/bold red]")

        max_profiles = 500  # سقف أمان لمنع أي حلقة لا نهائية
        previous_profile_number = None

        for idx in range(1, max_profiles + 1):
            try:
                console.print(f"\n[bold]---[/bold] [{idx}] [bold]---[/bold]")

                profile_number = extract_current_profile_number(win32_win)
                print(f"=============================> {profile_number}")
                # إن تكرر نفس الرقم مرتين متتاليتين، فهذا يعني أننا وصلنا لآخر
                # عنصر في القائمة ولم يعد السهم لأسفل ينقلنا لعنصر جديد
                if profile_number != "Unknown" and profile_number == previous_profile_number:
                    console.print("[bold cyan]✅ تم الوصول لنهاية القائمة.[/bold cyan]")
                    break

                previous_profile_number = profile_number
                export_current_profile(main_win, profile_number)

                main_win.set_focus()
                time.sleep(0.3)

                # الانتقال للبروفايل التالي بالسهم لأسفل
                send_keys("{DOWN}")
                time.sleep(0.7)

            except Exception as row_err:
                console.print(f"[bold yellow]⏭️ تخطي هذا البروفايل بسبب خطأ: {str(row_err)}[/bold yellow]")
                send_keys("{DOWN}")
                time.sleep(0.7)
                continue

    except Exception as e:
        console.print(f"[bold red]❌ حدث خطأ: {str(e)}[/bold red]")

if __name__ == "__main__":
    run_full_export_pipeline()

