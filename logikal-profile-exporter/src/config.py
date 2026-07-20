import json
import os
from pathlib import Path
from pydantic import BaseModel, Field, FilePath, DirectoryPath
from typing import Literal

class AppConfig(BaseModel):
    logikal_executable: str = Field(..., description="مسار ملف تشغيل لوجيكال")
    manufacturer: str
    system: str
    export_root: str
    language: Literal["en", "de"] = "en"
    backend: Literal["uia", "win32"] = "uia"
    max_retries: int = 3
    dialog_timeout_seconds: int = 20
    file_timeout_seconds: int = 45
    skip_valid_existing_files: bool = True
    validate_with_ezdxf: bool = True

    def get_export_path(self) -> Path:
        path = Path(self.export_root) / self.manufacturer / self.system.replace(" ", "_")
        path.mkdir(parents=True, exist_ok=True)
        return path

def load_config(config_path: str = "config.json") -> AppConfig:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return AppConfig(**data)

def load_selectors(language: str = "en") -> dict:
    selectors_path = Path("selectors") / f"{language}.json"
    if not selectors_path.exists():
        raise FileNotFoundError(f"Selectors definition file missing: {selectors_path}")
    with open(selectors_path, "r", encoding="utf-8") as f:
        return json.load(f)