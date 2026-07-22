"""
سكربت تشخيصي: يفترض أنك بالفعل واقف على شاشة LogiKal المطلوبة (لا حاجة
لأي تنقل بالقوائم). يقوم بتفريغ شجرة عناصر التحكم بالكامل لهذه النافذة
إلى ملف نصي، حتى تقدر تبحث فيه عن قيمة مثل "K40" وتشوف بالضبط داخل أي
عنصر تحكم موجودة، وما هي العناصر الأب/الابن حولها.

الاستخدام:
    python inspect_current_window.py

بعدها افتح الملف الناتج control_dump.txt وابحث (Ctrl+F) عن رقم البروفايل
الظاهر حالياً على الشاشة (مثلاً "K40")، وابعتلي السطر الذي وجدته فيه مع
الأسطر المحيطة به (خصوصاً الأسطر الأعلى منه التي تمثل الآباء).
"""

import contextlib
from pywinauto import Application
from rich.console import Console

console = Console()

OUTPUT_FILE = "control_dump.txt"


def main():
    console.print("[cyan]🔌 الاتصال بنافذة LogiKal الحالية...[/cyan]")
    app = Application(backend="uia").connect(title_re=".*LogiKal.*", timeout=10)
    main_win = app.top_window()
    main_win.set_focus()

    console.print(f"[cyan]📝 تفريغ شجرة عناصر التحكم إلى {OUTPUT_FILE} ...[/cyan]")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        with contextlib.redirect_stdout(f):
            main_win.print_control_identifiers(depth=None)

    console.print(f"[bold green]✔ تم الحفظ في {OUTPUT_FILE}[/bold green]")
    console.print("[yellow]افتح الملف وابحث (Ctrl+F) عن رقم البروفايل الظاهر على الشاشة حالياً.[/yellow]")


if __name__ == "__main__":
    main()