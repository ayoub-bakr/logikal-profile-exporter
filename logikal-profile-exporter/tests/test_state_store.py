import json

from src.state_store import StateStore, ProgressState


def test_load_returns_fresh_state_when_missing(tmp_path):
    store = StateStore(tmp_path / "progress.json")
    state = store.load("Schueco", "FWS 50 SG")
    assert state.manufacturer == "Schueco"
    assert state.exported_count == 0
    assert state.last_article is None


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "progress.json"
    store = StateStore(path)
    state = ProgressState(manufacturer="Schueco", system="FWS 50 SG")
    store.save(state)

    reloaded = store.load("Schueco", "FWS 50 SG")
    assert reloaded.manufacturer == "Schueco"
    assert path.exists()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert "updated_at" in data


def test_record_updates_counters(tmp_path):
    store = StateStore(tmp_path / "progress.json")
    state = store.load("Schueco", "FWS 50 SG")

    store.record(state, "123456", "Exported")
    store.record(state, "123457", "Skipped")
    store.record(state, "123458", "Failed")

    assert state.exported_count == 1
    assert state.skipped_count == 1
    assert state.failed_count == 1
    assert state.last_article == "123458"


def test_corrupt_progress_file_falls_back_gracefully(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("{not valid json at all", encoding="utf-8")
    store = StateStore(path)
    state = store.load("Schueco", "FWS 50 SG")
    assert state.exported_count == 0


def test_save_is_atomic_no_leftover_tmp_files(tmp_path):
    path = tmp_path / "progress.json"
    store = StateStore(path)
    store.save(ProgressState(manufacturer="Schueco", system="FWS 50 SG"))

    leftovers = list(tmp_path.glob(".progress_*"))
    assert leftovers == []
