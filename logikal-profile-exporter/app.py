import sys
import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.config import load_config, load_selectors
from src.logikal_app import LogikalAppManager
from src.profile_browser import ProfileBrowser
from src.drawing_exporter import DrawingExporter
from src.state_store import StateStore
from src.manifest import ManifestManager
from src.validators import DXFValidator
from src.dialogs import DialogHandler

console = Console()

def main():
    console.print(Panel.fit("[bold blue]Logikal Profile Export Automation Pipeline[/bold blue]", subtitle="v1.0.0"))
    
    # 1. إعداد وتحميل البنية والـ Configs
    try:
        config = load_config("config.json")
        selectors = load_selectors(config.language)
    except Exception as e:
        console.print(f"[red]❌ Critical Setup Failure: {str(e)}[/red]")
        sys.exit(1)

    export_dir = config.get_export_path()
    profiles_dir = export_dir / "Profiles"
    profiles_dir.mkdir(exist_ok=True)

    # 2. استدعاء مدراء تخزين الحالة والمخرجات
    state_store = StateStore(export_dir)
    current_state = state_store.load(config.manufacturer, config.system)
    manifest = ManifestManager(export_dir)
    dialog_handler = DialogHandler(selectors, config.dialog_timeout_seconds)

    console.print(f"[green]✔[/green] Target Directory setup: [yellow]{profiles_dir}[/yellow]")
    console.print(f"[green]✔[/green] Resuming state. Current statistics: Exported={current_state.exported_count}, Failed={current_state.failed_count}")

    # 3. تشغيل أو ربط محرك الـ UI للتطبيق
    app_manager = LogikalAppManager(config, selectors)
    try:
        with console.status("[bold green]Connecting to Logikal Instance...[/bold green]"):
            app = app_manager.connect_or_launch()
            cad_win = app_manager.get_cad_window()
    except Exception as e:
        console.print(f"[red]❌ Failure establishing UI automation bridge: {str(e)}[/red]")
        sys.exit(1)

    # 4. تصفح وفهرسة قائمة العناصر
    browser = ProfileBrowser(app, config, selectors)
    exporter = DrawingExporter(app, config, selectors, dialog_handler)
    
    browser.open_add_profile_dialog(cad_win)
    browser.select_target_system()
    articles = browser.fetch_articles_list()

    console.print(f"[green]✔[/green] Identified [bold cyan]{len(articles)}[/bold cyan] profile references within target architecture.")

    # 5. بدء الـ Automation Pipeline Loop الموثوق
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress_bar:
        
        main_task = progress_bar.add_task("[blue]Processing Profiles...[/blue]", total=len(articles))

        for article in articles:
            progress_bar.update(main_task, description=f"[yellow]Processing Article: {article}[/yellow]")
            output_file = profiles_dir / f"{article}.dxf"
            
            # سيناريو تخطي الملفات المصدرة مسبقاً وسليمة بنية الـ CAD
            if config.skip_valid_existing_files and output_file.exists():
                try:
                    if DXFValidator.validate(output_file, deep_check=config.validate_with_ezdxf):
                        state_store.update(article, "Skipped")
                        manifest.record(config.manufacturer, config.system, article, output_file.name, "Skipped", 0)
                        progress_bar.advance(main_task)
                        continue
                except Exception:
                    pass # في حالة كان الملف تالف يتم تجاوز التخطى لإعادة التصدير وتصحيحه

            attempts = 0
            success = False
            error_msg = ""

            while attempts < config.max_retries and not success:
                attempts += 1
                try:
                    # ضمان سلامة النوافذ والـ State قبل بدء الضغط والأوامر
                    dialog_handler.close_unexpected_popups(app_manager.main_window)
                    
                    exporter.clear_cad_viewport()
                    browser.open_add_profile_dialog(cad_win)
                    
                    exporter.add_article_to_drawing(article)
                    exporter.export_to_dxf(output_file)
                    
                    # التحقق من استقرار واستجابة الملف الهندسي المخرج
                    if DXFValidator.wait_for_file_stability(output_file, config.file_timeout_seconds):
                        DXFValidator.validate(output_file, deep_check=config.validate_with_ezdxf)
                        success = True
                        error_msg = ""
                    else:
                        raise TimeoutError("DXF pipeline generated file but timed out waiting for OS handle release.")
                        
                except Exception as ex:
                    error_msg = str(ex)
                    # التقاط لقطة شاشة للخطأ للرجوع الفني عند الحاجة لحل المشاكل الـ UI
                    screenshot_path = export_dir / f"screenshots"
                    screenshot_path.mkdir(exist_ok=True)
                    try:
                        app_manager.main_window.capture_as_image().save(screenshot_path / f"error_{article}_attr_{attempts}.png")
                    except Exception:
                        pass
                    time.sleep(1) # تهدئة واجهة الرسوميات قبل إعادة المحاولة

            if success:
                state_store.update(article, "Exported")
                manifest.record(config.manufacturer, config.system, article, output_file.name, "Exported", attempts)
            else:
                state_store.update(article, "Failed")
                manifest.record(config.manufacturer, config.system, article, output_file.name, "Failed", attempts, error_msg)

            progress_bar.advance(main_task)

    # 6. طباعة ملخص التشغيل والتقرير النهائي للقائد المشرف
    exporter.clear_cad_viewport()
    final_state = state_store.load(config.manufacturer, config.system)
    
    summary_text = (
        f"\n[bold green]Execution Cycle Complete![/bold green]\n\n"
        f"Manufacturer : {final_state.manufacturer}\n"
        f"System       : {final_state.system}\n"
        f"Total Checked: {len(articles)}\n"
        f"Exported     : {final_state.exported_count}\n"
        f"Skipped      : {final_state.skipped_count}\n"
        f"Failed       : {final_state.failed_count}\n"
        f"Outputs Saved: {export_dir}"
    )
    console.print(Panel(summary_text, title="Final Performance Audit Report"))

if __name__ == "__main__":
    main()