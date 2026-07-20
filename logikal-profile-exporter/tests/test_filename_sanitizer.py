from pathlib import Path

import pytest

from src.utils import sanitize_filename, build_dxf_path, unique_path_with_suffix


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("123456", "123456"),
        ("  123456  ", "123456"),
        ("Mullion 50/125", "Mullion_50125"),
        ('bad<>:"/\\|?*name', "badname"),
        ("...leading.dots...", "leading.dots"),
        ("", "ARTICLE"),
        ("   ", "ARTICLE"),
        ("CON", "_CON"),
        ("com1", "_com1"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_build_dxf_path(tmp_path):
    path = build_dxf_path(tmp_path, "123456")
    assert path == tmp_path / "123456.dxf"


def test_unique_path_with_suffix_no_collision(tmp_path):
    path = tmp_path / "123456.dxf"
    assert unique_path_with_suffix(path) == path


def test_unique_path_with_suffix_collision(tmp_path):
    path = tmp_path / "123456.dxf"
    path.write_bytes(b"existing")

    result = unique_path_with_suffix(path)
    assert result == tmp_path / "123456-2.dxf"

    (tmp_path / "123456-2.dxf").write_bytes(b"existing2")
    result2 = unique_path_with_suffix(path)
    assert result2 == tmp_path / "123456-3.dxf"


def test_filenames_stay_deterministic_across_calls():
    assert sanitize_filename("123456") == sanitize_filename("123456")
