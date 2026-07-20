import json
import os
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel

class ProgressState(BaseModel):
    manufacturer: str
    system: str
    last_article: str = ""
    exported_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    updated_at: str = ""

class StateStore:
    def __init__(self, directory: Path):
        self.file_path = directory / "progress.json"
        self.state = ProgressState(manufacturer="", system="")

    def load(self, manufacturer: str, system: str) -> ProgressState:
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.state = ProgressState(**data)
                    if self.state.manufacturer == manufacturer and self.state.system == system:
                        return self.state
            except Exception:
                pass # في حال تلف ملف الـ JSON يتم تصفيره تلقائياً لسلامة التشغيل
        
        self.state = ProgressState(
            manufacturer=manufacturer,
            system=system,
            updated_at=datetime.now().isoformat()
        )
        self.save()
        return self.state

    def update(self, last_article: str, status: str):
        self.state.last_article = last_article
        if status == "Exported":
            self.state.exported_count += 1
        elif status == "Skipped":
            self.state.skipped_count += 1
        elif status == "Failed":
            self.state.failed_count += 1
        
        self.state.updated_at = datetime.now().isoformat()
        self.save()

    def save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.state.model_dump(), f, indent=2, ensure_ascii=False)