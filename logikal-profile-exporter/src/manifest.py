import csv
import os
from datetime import datetime
from pathlib import Path

class ManifestManager:
    def __init__(self, directory: Path):
        self.file_path = directory / "export_manifest.csv"
        self.headers = [
            "manufacturer", "system", "article_number", 
            "file", "status", "attempts", "error", "exported_at"
        ]
        self._init_csv()

    def _init_csv(self):
        if not self.file_path.exists():
            with open(self.file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(self.headers)

    def record(self, manufacturer: str, system: str, article: str, filename: str, status: str, attempts: int, error: str = ""):
        with open(self.file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                manufacturer,
                system,
                article,
                filename,
                status,
                attempts,
                error,
                datetime.now().isoformat()
            ])