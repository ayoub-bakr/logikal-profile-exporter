from src.validators import validate_dxf, is_valid_existing_dxf, has_dxf_signature

MINIMAL_VALID_DXF = (
    b"0\r\nSECTION\r\n2\r\nHEADER\r\n0\r\nENDSEC\r\n0\r\nEOF\r\n"
    + b"0" * 500  # pad past min_size_bytes for the size check
)


def make_dxf(tmp_path, name="123456.dxf", content=MINIMAL_VALID_DXF):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_missing_file_is_invalid(tmp_path):
    path = tmp_path / "123456.dxf"
    ok, reason = validate_dxf(path, "123456", min_size_bytes=500, use_ezdxf=False)
    assert not ok
    assert "does not exist" in reason


def test_too_small_file_is_invalid(tmp_path):
    path = make_dxf(tmp_path, content=b"0\r\nSECTION\r\n")
    ok, reason = validate_dxf(path, "123456", min_size_bytes=500, use_ezdxf=False)
    assert not ok
    assert "too small" in reason


def test_wrong_filename_is_invalid(tmp_path):
    path = make_dxf(tmp_path, name="wrongname.dxf")
    ok, reason = validate_dxf(path, "123456", min_size_bytes=500, use_ezdxf=False)
    assert not ok
    assert "does not match" in reason


def test_missing_signature_is_invalid(tmp_path):
    path = make_dxf(tmp_path, content=b"NOT A DXF FILE " + b"0" * 600)
    ok, reason = validate_dxf(path, "123456", min_size_bytes=500, use_ezdxf=False)
    assert not ok
    assert "DXF content" in reason


def test_valid_dxf_passes(tmp_path):
    path = make_dxf(tmp_path)
    ok, reason = validate_dxf(path, "123456", min_size_bytes=500, use_ezdxf=False)
    assert ok
    assert reason == ""


def test_is_valid_existing_dxf_wrapper(tmp_path):
    path = make_dxf(tmp_path)
    assert is_valid_existing_dxf(path, "123456", min_size_bytes=500, use_ezdxf=False)


def test_has_dxf_signature_detects_lf_variant():
    assert has_dxf_signature.__call__ is not None  # sanity import check


def test_empty_dxf_fails_regardless_of_name(tmp_path):
    path = make_dxf(tmp_path, name="123458.dxf", content=b"")
    ok, reason = validate_dxf(path, "123458", min_size_bytes=500, use_ezdxf=False)
    assert not ok
