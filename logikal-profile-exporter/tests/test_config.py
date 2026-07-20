import json

import pytest

from src.config import load_config
from src.errors import ConfigError

VALID = {
    "logikal_executable": "C:\\Program Files\\Orgadata\\Logikal\\Logikal.exe",
    "manufacturer": "Schueco",
    "system": "FWS 50 SG",
    "export_root": "D:\\LogikalExports",
    "language": "en",
    "backend": "uia",
}


def write_config(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_valid_config(tmp_path):
    path = write_config(tmp_path, VALID)
    config = load_config(path)
    assert config.manufacturer == "Schueco"
    assert config.system == "FWS 50 SG"
    assert config.max_retries == 3  # default
    assert config.system_dir_name == "FWS_50_SG"


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does_not_exist.json")


def test_invalid_json_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_blank_manufacturer_rejected(tmp_path):
    data = dict(VALID, manufacturer="   ")
    path = write_config(tmp_path, data)
    with pytest.raises(ConfigError):
        load_config(path)


def test_invalid_backend_rejected(tmp_path):
    data = dict(VALID, backend="totally_wrong")
    path = write_config(tmp_path, data)
    with pytest.raises(ConfigError):
        load_config(path)


def test_unknown_language_rejected(tmp_path):
    data = dict(VALID, language="xx")
    path = write_config(tmp_path, data)
    with pytest.raises(ConfigError):
        load_config(path)


def test_negative_retries_rejected(tmp_path):
    data = dict(VALID, max_retries=0)
    path = write_config(tmp_path, data)
    with pytest.raises(ConfigError):
        load_config(path)


def test_export_dir_composition(tmp_path):
    path = write_config(tmp_path, VALID)
    config = load_config(path)
    assert config.export_dir.name == "FWS_50_SG"
    assert config.export_dir.parent.name == "Schueco"
