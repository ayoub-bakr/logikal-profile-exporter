import os
import time
from pathlib import Path
import ezdxf
from src.errors import InvalidDXFFileError

class DXFValidator:
    @staticmethod
    def wait_for_file_stability(file_path: Path, timeout: int = 10) -> bool:
        """الانتظار حتى يستقر حجم الملف ويتوقف نظام التشغيل عن حظره (Locking)."""
        start_time = time.time()
        last_size = -1
        while time.time() - start_time < timeout:
            if file_path.exists():
                current_size = file_path.stat().st_size
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
            time.sleep(0.5)
        return False

    @staticmethod
    def validate(file_path: Path, deep_check: bool = True) -> bool:
        """التحقق من صحة وبنية ملف الـ DXF المصدر."""
        if not file_path.exists():
            return False
        
        # 1. التحقق الأساسي من الحجم (أكبر من 500 بايت)
        if file_path.stat().st_size < 500:
            raise InvalidDXFFileError(f"File {file_path.name} is too small or blank.")

        if not deep_check:
            return True

        # 2. الفحص العميق لبنية ملف الـ CAD
        try:
            doc = ezdxf.readfile(str(file_path))
            # التحقق من أن الملف يحتوي على كيانات رسومية (Modelspace contains elements)
            if len(doc.modelspace()) == 0:
                raise InvalidDXFFileError(f"DXF structural error: Modelspace of {file_path.name} is completely empty.")
            return True
        except ezdxf.DXFStructureError as e:
            raise InvalidDXFFileError(f"Corrupted DXF structure for {file_path.name}: {str(e)}")
        except Exception as e:
            raise InvalidDXFFileError(f"Unexpected file error during DXF inspection: {str(e)}")