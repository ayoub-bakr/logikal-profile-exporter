"""LogikalExporter facade + the per-article export cycle and series
runner, matching the interface and control flow from the spec
(section 8, "منطق الأتمتة").
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import AppConfig
from .dialogs import DialogHandler
from .drawing_exporter import DrawingExporter
from .errors import ExportFailedError, LogikalAutomationError
from .logikal_app import LogikalApp
from .manifest import Manifest
from .profile_browser import ProfileBrowser
from .state_store import StateStore
from .utils import build_dxf_path, wait_for_file_size_stable
from .validators import validate_dxf, is_valid_existing_dxf

logger = logging.getLogger("logikal_exporter")


class LogikalExporter:
    """Unified internal run interface, mirroring the spec's
    class LogikalExporter pseudocode 1:1 so the design doc and the
    implementation stay easy to cross-reference."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.selectors = json.loads(config.selectors_path.read_text(encoding="utf-8"))
        self.logikal_app = LogikalApp(config, self.selectors)
        self.profile_browser = ProfileBrowser(
            self.logikal_app, self.selectors, config.dialog_timeout_seconds
        )
        self.drawing_exporter = DrawingExporter(
            self.logikal_app, self.profile_browser, self.selectors, config
        )
        self.dialogs = DialogHandler(self.logikal_app, self.selectors, config.dialog_timeout_seconds)

    def connect(self) -> None:
        self.logikal_app.connect()

    def open_add_profile(self) -> None:
        self.profile_browser.open_add_profile()

    def select_manufacturer(self, name: str) -> None:
        self.profile_browser.select_manufacturer(name)

    def select_system(self, name: str) -> None:
        self.profile_browser.select_system(name)

    def list_articles(self) -> list[str]:
        articles = self.profile_browser.list_articles()
        if articles:
            return articles
        # Priority-2 fallback: keyboard navigation.
        limit = self.config.article_limit
        return [num for _, num in self.profile_browser.iter_articles_by_keyboard(limit)]

    def add_profile(self, article_number: str) -> None:
        self.drawing_exporter.add_profile_to_drawing(article_number)

    def export_current_drawing(self, output_path: str) -> None:
        self.drawing_exporter.wait_for_drawing_ready()
        self.drawing_exporter.export_current_drawing(output_path)

    def clear_drawing(self) -> None:
        self.drawing_exporter.clear_drawing_if_needed()

    def recover_to_known_state(self) -> None:
        self.drawing_exporter.recover_to_known_state()


class ExportRunner:
    """Owns config, manifest, state store, and drives the per-article
    loop + full-series run described in workflow section 4 and
    automation section 8 of the spec."""

    def __init__(self, config: AppConfig, exporter: LogikalExporter | None = None):
        self.config = config
        self.exporter = exporter or LogikalExporter(config)

        export_dir = config.export_dir
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "screenshots").mkdir(exist_ok=True)

        self.export_dir = export_dir
        self.manifest = Manifest(export_dir / "export_manifest.csv")
        self.state_store = StateStore(export_dir / "progress.json")
        self.error_log_path = export_dir / "export_errors.log"

    # ------------------------------------------------------------------

    def _log_error(self, article: str, exc: Exception, attempt: int) -> None:
        import traceback

        self.export_dir.mkdir(parents=True, exist_ok=True)
        with open(self.error_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- article={article} attempt={attempt} ---\n")
            f.write(f"active_window: {self._safe_active_window_title()}\n")
            f.write(traceback.format_exc())

    def _safe_active_window_title(self) -> str:
        try:
            return self.exporter.logikal_app.main_window.window_text()
        except Exception:
            return "<unknown>"

    def _save_error_snapshot(self, article: str) -> None:
        try:
            from PIL import ImageGrab  # optional dependency, screenshot only

            path = self.export_dir / "screenshots" / f"{article}_error.png"
            ImageGrab.grab().save(path)
        except Exception:
            logger.debug("Screenshot capture skipped/unavailable for article %s", article)

    # ------------------------------------------------------------------

    def build_output_path(self, article: str) -> Path:
        return build_dxf_path(self.export_dir, article)

    def export_article(self, article: str, state) -> str:
        """One article, start to finish, with retries. Returns the
        final status string: 'Exported' | 'Skipped' | 'Failed'.
        Mirrors the export_article() pseudocode in the spec exactly.
        """
        output_path = self.build_output_path(article)

        if self.config.skip_valid_existing_files and is_valid_existing_dxf(
            output_path,
            article,
            self.config.min_dxf_size_bytes,
            self.config.validate_with_ezdxf,
        ):
            self.manifest.record_status(
                article, self.config.manufacturer, self.config.system,
                status="Skipped", file=output_path.name,
            )
            self.state_store.record(state, article, "Skipped")
            return "Skipped"

        last_error = ""
        for attempt in range(1, self.config.max_retries + 1):
            try:
                self.exporter.add_profile(article)
                self.exporter.export_current_drawing(str(output_path))

                if not wait_for_file_size_stable(
                    output_path, timeout=self.config.file_timeout_seconds
                ):
                    raise ExportFailedError(article, "timed out waiting for stable file size")

                ok, reason = validate_dxf(
                    output_path, article,
                    self.config.min_dxf_size_bytes,
                    self.config.validate_with_ezdxf,
                )
                if not ok:
                    raise ExportFailedError(article, f"validation failed: {reason}")

                self.manifest.record_status(
                    article, self.config.manufacturer, self.config.system,
                    status="Exported", file=output_path.name, attempts=attempt,
                )
                self.state_store.record(state, article, "Exported")
                return "Exported"

            except (LogikalAutomationError, ExportFailedError) as exc:
                last_error = str(exc)
                logger.warning("Article %s attempt %d/%d failed: %s",
                                article, attempt, self.config.max_retries, last_error)
                self._log_error(article, exc, attempt)

                if attempt < self.config.max_retries:
                    self.exporter.recover_to_known_state()
                    continue

            except Exception as exc:  # unexpected error - still don't kill the series
                last_error = str(exc)
                logger.exception("Unexpected error on article %s attempt %d", article, attempt)
                self._log_error(article, exc, attempt)
                if attempt < self.config.max_retries:
                    self.exporter.recover_to_known_state()
                    continue

            finally:
                self.exporter.clear_drawing()

        # All retries exhausted.
        self._save_error_snapshot(article)
        self.manifest.record_status(
            article, self.config.manufacturer, self.config.system,
            status="Failed", attempts=self.config.max_retries, error=last_error,
        )
        self.state_store.record(state, article, "Failed")
        return "Failed"

    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Full series run: connect, navigate, resume-aware loop over
        all articles, final summary. Returns the summary dict that
        app.py prints/logs."""
        state = self.state_store.load(self.config.manufacturer, self.config.system)
        already_done = self.manifest.completed_articles()

        self.exporter.connect()
        if self.config.connect_only:
            logger.info("connect_only=True: connection verified, skipping navigation/export.")
            return {"connected": True}

        self.exporter.open_add_profile()
        self.exporter.select_manufacturer(self.config.manufacturer)
        self.exporter.select_system(self.config.system)

        articles = self.exporter.list_articles()
        if self.config.article_limit:
            articles = articles[: self.config.article_limit]

        results = {"Exported": 0, "Skipped": 0, "Failed": 0}
        for article in articles:
            if article in already_done:
                # Manifest already has a terminal result for this
                # article from a prior run - re-validating the file on
                # disk (inside export_article) still happens, so a
                # manifest row that lied about a since-deleted file
                # will correctly re-export rather than silently skip.
                pass
            status = self.export_article(article, state)
            results[status] = results.get(status, 0) + 1

        summary = {
            "manufacturer": self.config.manufacturer,
            "system": self.config.system,
            "total": len(articles),
            "exported": results["Exported"],
            "skipped": results["Skipped"],
            "failed": results["Failed"],
            "output": str(self.export_dir),
        }
        return summary
