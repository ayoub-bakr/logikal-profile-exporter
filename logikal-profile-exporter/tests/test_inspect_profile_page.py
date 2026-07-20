import json
from pathlib import Path
import unittest

from scripts.inspect_profile_page import (
    control_snapshot,
    enforce_source_safety,
    exact_article_match,
    find_prohibited_calls,
    preserve_display_order,
    safe_read,
    score_candidate_control,
    to_json_safe,
)


class RaisingInfo:
    name = "2256"
    value = "2256"
    control_type = "ListItem"
    class_name = "OwnerDrawItem"
    automation_id = "item-0"
    handle = 101
    rectangle = None
    framework_id = "Win32"
    runtime_id = (1, 2, 3)
    process_id = 42
    has_keyboard_focus = False

    @property
    def offscreen(self):
        raise RuntimeError("offscreen is unsupported")


class FakeControl:
    element_info = RaisingInfo()
    handle = 101

    def window_text(self):
        return "2256"

    def class_name(self):
        return "OwnerDrawItem"

    def rectangle(self):
        raise RuntimeError("rectangle is unsupported")

    def is_visible(self):
        return True

    def is_enabled(self):
        return True

    def is_selected(self):
        return True

    def legacy_properties(self):
        raise RuntimeError("legacy accessibility is unsupported")


class InspectorHelperTests(unittest.TestCase):
    def test_exact_article_matching(self):
        self.assertTrue(exact_article_match(" 2256 ", "2256"))
        self.assertTrue(exact_article_match("K111", "K111"))
        self.assertFalse(exact_article_match("Article K111", "K111"))

    def test_k111_does_not_match_k1110(self):
        self.assertFalse(exact_article_match("K1110", "K111"))

    def test_preserves_displayed_order_and_duplicates(self):
        rows = ["2256", "K111", "K29", "K111"]
        self.assertEqual(preserve_display_order(rows), rows)

    def test_candidate_list_scoring(self):
        grid_score = score_candidate_control(
            {
                "control_type": "DataGrid",
                "class_name": "ProfileGrid",
                "descendant_texts": ["2256", "K111", "K29"],
            }
        )
        pane_score = score_candidate_control(
            {
                "control_type": "Pane",
                "class_name": "",
                "descendant_texts": [],
            }
        )
        self.assertGreater(grid_score, pane_score)
        self.assertGreaterEqual(grid_score, 100)

    def test_safe_property_extraction(self):
        errors = []
        result = safe_read(
            "unsupported", lambda: (_ for _ in ()).throw(RuntimeError("no value")), errors
        )
        self.assertIsNone(result)
        self.assertEqual(len(errors), 1)
        self.assertIn("unsupported", errors[0])

    def test_unsupported_control_properties_do_not_abort_snapshot(self):
        errors = []
        snapshot = control_snapshot(FakeControl(), "win32", "root/item", errors)
        self.assertEqual(snapshot["direct_text"], "2256")
        self.assertEqual(snapshot["control_type"], "ListItem")
        self.assertTrue(snapshot["selected"])
        self.assertGreaterEqual(len(errors), 3)

    def test_json_serialization(self):
        value = {
            "path": Path("artifacts") / "result",
            "runtime_id": (1, 2, 3),
            "bytes": b"K111",
        }
        safe = to_json_safe(value)
        encoded = json.dumps(safe)
        self.assertIn("artifacts", encoded)
        self.assertEqual(safe["runtime_id"], [1, 2, 3])
        self.assertEqual(safe["bytes"], "K111")

    def test_prohibited_call_safety_guard(self):
        source = "control.click()\nset_focus()\npattern.Invoke()\n"
        findings = find_prohibited_calls(source)
        self.assertEqual(
            [finding["call"] for finding in findings], ["click", "set_focus", "Invoke"]
        )

    def test_guard_ignores_comments_and_strings(self):
        source = '# control.click()\nmessage = "window.select()"\nprint(message)\n'
        self.assertEqual(find_prohibited_calls(source), [])

    def test_inspector_source_passes_safety_guard(self):
        script = Path(__file__).parents[1] / "scripts" / "inspect_profile_page.py"
        safe, findings = enforce_source_safety(script)
        self.assertTrue(safe, findings)


if __name__ == "__main__":
    unittest.main()
