import os
import sys
from pathlib import Path
from pywinauto import Application
import win32process
import win32gui
from rich.console import Console
from rich.panel import Panel

console = Console()

def get_logikal_pid():
    """البحث عن رقم العملية (PID) لبرنامج Logikal CAD الفعلي مع استبعاد الأدوات الأخرى"""
    def enum_windows_callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            title_lower = title.lower()
            
            # الكلمات المستبعدة تماماً
            exclusions = ["chrome", "edge", "visual studio code", "vscode", "py_discovery", "ui_discovery"]
            
            if "logikal" in title_lower:
                # التحقق من أن العنوان لا يحتوي على أي من الكلمات المستبعدة
                if not any(exc in title_lower for exc in exclusions):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    extra.append((pid, title))
                
    windows = []
    win32gui.EnumWindows(enum_windows_callback, windows)
    return windows[0] if windows else (None, None)

def discover_logikal_ui():
    console.print(Panel.fit("[bold green]Logikal UI Discovery & Inspection Tool[/bold green]"))
    
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    output_file = artifacts_dir / "logikal_controls_tree.txt"

    console.print("[yellow]🔄 Scanning for active Logikal window processes...[/yellow]")
    
    pid, win_title = get_logikal_pid()
    
    if not pid:
        console.print("[red]❌ Error: Could not find any running window with 'Logikal' in the title.[/red]")
        console.print("[bold yellow]\n💡 Fixes to try right now:[/bold yellow]")
        console.print("1. [bold]Open Logikal CAD[/bold] and make sure it's not minimized to the system tray.")
        console.print("2. Look at the exact title of your Logikal window and type it down for me.")
        return

    console.print(f"[green]✔ Found target window:[/green] [cyan]'{win_title}'[/cyan] (PID: {pid})")
    console.print("[yellow]🔄 Connecting via UIA backend...[/yellow]")
    
    try:
        # الاتصال مباشرة برقم العملية الذي عثرنا عليه
        app = Application(backend="uia").connect(process=pid, timeout=10)
        main_win = app.window(title=win_title)
        
        console.print("[yellow]⏳ Extracting UI control tree...[/yellow]")
        
        original_stdout = sys.stdout
        with open(output_file, "w", encoding="utf-8") as f:
            sys.stdout = f
            main_win.print_control_identifiers()
            
        sys.stdout = original_stdout
        
        console.print(Panel(
            f"[bold green]✔ Discovery Completed Successfully![/bold green]\n\n"
            f"[bold]Output File:[/bold] {output_file.resolve()}\n",
            title="Success"
        ))

    except Exception as e:
        sys.stdout = sys.stderr
        console.print(f"[red]❌ Discovery Failure: {str(e)}[/red]")
        console.print("\n[yellow]🔄 Trying Win32 fallback backend...[/yellow]")
        try:
            app = Application(backend="win32").connect(process=pid, timeout=5)
            main_win = app.window(title=win_title)
            with open(output_file, "w", encoding="utf-8") as f:
                sys.stdout = f
                main_win.print_control_identifiers()
            sys.stdout = original_stdout
            console.print("[green]✔ Success using Win32 backend fallback![/green]")
        except Exception as fallback_e:
            console.print(f"[red]❌ Fallback also failed: {str(fallback_e)}[/red]")

if __name__ == "__main__":
    discover_logikal_ui()