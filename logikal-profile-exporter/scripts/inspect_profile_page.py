"""Read-only inspection of an already-open LogiKal Profile Data page.

This utility reads process, window, control, accessibility, selection, and
pattern metadata. It must never perform an action against a UI control.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import traceback
from typing import Any, Callable, Iterable


KNOWN_ARTICLES = ("2256", "K111", "K29", "K34", "K39")
EXACT_REPORT_ARTICLES = ("2256", "K111", "K29")
PROHIBITED_CALL_NAMES = (
    "click",
    "click_input",
    "double_click_input",
    "type_keys",
    "send_keys",
    "set_focus",
    "select",
    "invoke",
    "scroll",
    "scroll_into_view",
    "move_window",
    "close",
    "minimize",
    "maximize",
    "restore",
    "right_click_input",
    "set_edit_text",
    "set_text",
    "check",
    "uncheck",
    "toggle",
    "expand",
    "collapse",
    "menu_select",
)
READ_ONLY_METHOD_NAMES = {
    "children",
    "class_name",
    "get_selection",
    "is_enabled",
    "is_selected",
    "is_visible",
    "legacy_properties",
    "rectangle",
    "window_text",
}
PROCESS_NAME_EXCLUSIONS = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "code.exe",
    "devenv.exe",
    "python.exe",
    "pythonw.exe",
}
PATTERN_ATTRIBUTES = {
    "selection": "iface_selection",
    "selection_item": "iface_selection_item",
    "scroll": "iface_scroll",
    "scroll_item": "iface_scroll_item",
    "grid": "iface_grid",
    "table": "iface_table",
    "invoke": "iface_invoke",
    "virtualized_item": "iface_virtualized_item",
}
LIST_HINTS = (
    "list",
    "listbox",
    "datagrid",
    "data grid",
    "table",
    "tree",
    "pane",
    "syslistview32",
    "grid",
    "owner-draw",
    "ownerdraw",
)
ITEM_CONTROL_TYPES = {
    "dataitem",
    "listitem",
    "treeitem",
    "custom",
    "text",
    "edit",
}
ARTICLE_TOKEN_RE = re.compile(
    r"^(?:[A-Za-z]+\d+|\d+)(?:[-./][A-Za-z0-9]+)*$"
)


def find_prohibited_calls(source: str) -> list[dict[str, Any]]:
    """Return prohibited executable calls, ignoring comments and strings."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [{"call": "<syntax-error>", "line": exc.lineno or 0}]

    prohibited = {name.casefold() for name in PROHIBITED_CALL_NAMES}
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
        elif isinstance(node.func, ast.Name):
            name = node.func.id
        else:
            continue
        if name.casefold() in prohibited:
            findings.append({"call": name, "line": node.lineno})
    return findings


def enforce_source_safety(script_path: Path) -> tuple[bool, list[dict[str, Any]]]:
    try:
        source = script_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, [{"call": "<source-read-error>", "line": 0, "error": str(exc)}]
    findings = find_prohibited_calls(source)
    return not findings, findings


def safe_read(
    label: str,
    getter: Callable[[], Any],
    errors: list[str] | None = None,
    default: Any = None,
) -> Any:
    """Read one property without allowing an unsupported property to abort."""
    try:
        return getter()
    except Exception as exc:
        if errors is not None:
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
        return default


def to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_safe(item) for item in value]
    if isinstance(value, set):
        return [to_json_safe(item) for item in sorted(value, key=str)]
    if all(hasattr(value, attr) for attr in ("left", "top", "right", "bottom")):
        return {
            "left": safe_read("rectangle.left", lambda: value.left),
            "top": safe_read("rectangle.top", lambda: value.top),
            "right": safe_read("rectangle.right", lambda: value.right),
            "bottom": safe_read("rectangle.bottom", lambda: value.bottom),
        }
    return str(value)


def preserve_display_order(items: Iterable[Any]) -> list[Any]:
    """Materialize UI items in their supplied order without deduplication."""
    return [item for item in items]


def exact_article_match(text: Any, article: str) -> bool:
    return isinstance(text, str) and text.strip() == article


def article_like_value(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    normalized = text.strip()
    if ARTICLE_TOKEN_RE.fullmatch(normalized):
        return normalized
    return None


def exact_articles_in_texts(
    texts: Iterable[Any], targets: Iterable[str] = KNOWN_ARTICLES
) -> list[str]:
    matches: list[str] = []
    for target in targets:
        if any(exact_article_match(text, target) for text in texts):
            matches.append(target)
    return matches


def score_candidate_control(metadata: dict[str, Any]) -> int:
    """Score list-like controls and controls containing known exact articles."""
    control_type = str(metadata.get("control_type") or "").casefold()
    class_name = str(metadata.get("class_name") or "").casefold()
    combined = f"{control_type} {class_name}"
    score = 0

    if "datagrid" in combined or "data grid" in combined:
        score += 60
    elif "syslistview32" in combined:
        score += 55
    elif "list" in combined or "table" in combined or "tree" in combined:
        score += 45
    elif "grid" in combined:
        score += 40
    elif "pane" in combined or "owner-draw" in combined or "ownerdraw" in combined:
        score += 5

    descendant_texts = metadata.get("descendant_texts") or []
    exact_matches = exact_articles_in_texts(descendant_texts)
    score += len(exact_matches) * 25
    if len(exact_matches) >= 2:
        score += 20
    return score


def looks_like_logikal_executable(name: str | None, executable: str | None) -> bool:
    candidates = []
    if name:
        candidates.append(Path(name).name.casefold())
    if executable:
        candidates.append(Path(executable).name.casefold())
    if any(candidate in PROCESS_NAME_EXCLUSIONS for candidate in candidates):
        return False
    for candidate in candidates:
        stem = Path(candidate).stem
        normalized = re.sub(r"[^a-z0-9]", "", stem)
        if re.fullmatch(r"logikal(?:x?64|x?86|\d[0-9a-z]*)?", normalized):
            return True
    return False


def _element_info(control: Any, errors: list[str], label: str) -> Any:
    return safe_read(f"{label}.element_info", lambda: control.element_info, errors)


def _info_value(
    info: Any, attribute: str, errors: list[str], label: str, default: Any = None
) -> Any:
    if info is None:
        return default
    return safe_read(
        f"{label}.element_info.{attribute}",
        lambda: getattr(info, attribute),
        errors,
        default,
    )


def _call_optional_method(
    control: Any,
    method_name: str,
    errors: list[str],
    label: str,
    default: Any = None,
) -> Any:
    if method_name not in READ_ONLY_METHOD_NAMES:
        raise RuntimeError(f"Method {method_name!r} is not in the read-only allowlist")
    method = safe_read(
        f"{label}.{method_name}", lambda: getattr(control, method_name), errors
    )
    if not callable(method):
        return default
    return safe_read(f"{label}.{method_name}()", method, errors, default)


def _rectangle_dict(rectangle: Any) -> dict[str, Any] | None:
    if rectangle is None:
        return None
    return {
        "left": safe_read("rectangle.left", lambda: rectangle.left),
        "top": safe_read("rectangle.top", lambda: rectangle.top),
        "right": safe_read("rectangle.right", lambda: rectangle.right),
        "bottom": safe_read("rectangle.bottom", lambda: rectangle.bottom),
    }


def _legacy_properties(control: Any, errors: list[str], label: str) -> dict[str, Any]:
    legacy = _call_optional_method(control, "legacy_properties", errors, label, {})
    return legacy if isinstance(legacy, dict) else {}


def _pattern_available(
    control: Any, pattern_name: str, backend: str, errors: list[str], label: str
) -> bool | str:
    if backend != "uia":
        return "unknown"
    attribute = PATTERN_ATTRIBUTES[pattern_name]
    try:
        pattern = getattr(control, attribute)
        return pattern is not None
    except Exception as exc:
        error_name = type(exc).__name__.casefold()
        error_text = str(exc).casefold()
        if "pattern" in error_name or "pattern" in error_text or "interface" in error_text:
            return False
        errors.append(f"{label}.{attribute}: {type(exc).__name__}: {exc}")
        return "unknown"


def _pattern_map(
    control: Any, backend: str, errors: list[str], label: str
) -> dict[str, bool | str]:
    return {
        name: _pattern_available(control, name, backend, errors, label)
        for name in PATTERN_ATTRIBUTES
    }


def _read_selection_state(
    control: Any,
    backend: str,
    legacy: dict[str, Any],
    errors: list[str],
    label: str,
) -> tuple[bool | str, str]:
    result = _call_optional_method(control, "is_selected", errors, label, None)
    if isinstance(result, bool):
        return result, "is_selected"

    if backend == "uia":
        pattern = safe_read(
            f"{label}.iface_selection_item",
            lambda: getattr(control, "iface_selection_item"),
            errors,
        )
        if pattern is not None:
            current = safe_read(
                f"{label}.SelectionItem.CurrentIsSelected",
                lambda: pattern.CurrentIsSelected,
                errors,
            )
            if isinstance(current, bool):
                return current, "SelectionItemPattern.CurrentIsSelected"

    state = legacy.get("State", legacy.get("state"))
    if isinstance(state, int):
        return bool(state & 0x2), "legacy State selected bit"
    if isinstance(state, str) and "selected" in state.casefold():
        return True, "legacy State text"
    return "unknown", "unavailable"


def _read_scroll_properties(
    control: Any, backend: str, errors: list[str], label: str
) -> dict[str, Any]:
    if backend != "uia":
        return {"available": "unknown"}
    available = _pattern_available(control, "scroll", backend, errors, label)
    result: dict[str, Any] = {"available": available}
    if available is not True:
        return result

    pattern = safe_read(
        f"{label}.iface_scroll", lambda: getattr(control, "iface_scroll"), errors
    )
    if pattern is None:
        return result
    for attribute in (
        "CurrentHorizontallyScrollable",
        "CurrentVerticallyScrollable",
        "CurrentHorizontalScrollPercent",
        "CurrentVerticalScrollPercent",
        "CurrentHorizontalViewSize",
        "CurrentVerticalViewSize",
    ):
        result[attribute] = safe_read(
            f"{label}.ScrollPattern.{attribute}",
            lambda attribute=attribute: getattr(pattern, attribute),
            errors,
        )
    return result


def control_snapshot(
    control: Any, backend: str, path: str, errors: list[str]
) -> dict[str, Any]:
    """Extract control properties independently and without changing state."""
    info = _element_info(control, errors, path)
    direct_text = _call_optional_method(control, "window_text", errors, path, "")
    class_name = _call_optional_method(control, "class_name", errors, path, None)
    if not class_name:
        class_name = _info_value(info, "class_name", errors, path, "")
    rectangle = _call_optional_method(control, "rectangle", errors, path, None)
    if rectangle is None:
        rectangle = _info_value(info, "rectangle", errors, path, None)
    legacy = _legacy_properties(control, errors, path)
    patterns = _pattern_map(control, backend, errors, path)
    selected, selected_method = _read_selection_state(
        control, backend, legacy, errors, path
    )

    snapshot = {
        "path": path,
        "backend": backend,
        "direct_text": direct_text or "",
        "name": _info_value(info, "name", errors, path, "") or legacy.get("Name", ""),
        "value": _info_value(info, "value", errors, path, "") or legacy.get("Value", ""),
        "control_type": _info_value(info, "control_type", errors, path, ""),
        "class_name": class_name or "",
        "automation_id": _info_value(info, "automation_id", errors, path, ""),
        "handle": safe_read(f"{path}.handle", lambda: control.handle, errors),
        "rectangle": _rectangle_dict(rectangle),
        "visible": _call_optional_method(control, "is_visible", errors, path, None),
        "enabled": _call_optional_method(control, "is_enabled", errors, path, None),
        "offscreen": _info_value(info, "offscreen", errors, path, None),
        "framework_id": _info_value(info, "framework_id", errors, path, ""),
        "runtime_id": to_json_safe(_info_value(info, "runtime_id", errors, path, None)),
        "process_id": _info_value(info, "process_id", errors, path, None),
        "has_keyboard_focus": _info_value(
            info, "has_keyboard_focus", errors, path, None
        ),
        "legacy_name": legacy.get("Name", legacy.get("name", "")),
        "legacy_value": legacy.get("Value", legacy.get("value", "")),
        "legacy_role": to_json_safe(legacy.get("Role", legacy.get("role"))),
        "legacy_state": to_json_safe(legacy.get("State", legacy.get("state"))),
        "selected": selected,
        "selected_method": selected_method,
        "patterns": patterns,
        "scroll_properties": _read_scroll_properties(control, backend, errors, path),
    }
    if snapshot["handle"] is None:
        snapshot["handle"] = _info_value(info, "handle", errors, path, None)
    return to_json_safe(snapshot)


def _snapshot_texts(snapshot: dict[str, Any]) -> list[str]:
    values = []
    for key in ("direct_text", "name", "value", "legacy_name", "legacy_value"):
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def _control_label(snapshot: dict[str, Any], fallback: str) -> str:
    text = snapshot.get("direct_text") or snapshot.get("name") or "<unnamed>"
    control_type = snapshot.get("control_type") or "Unknown"
    automation_id = snapshot.get("automation_id") or "-"
    return f"{text} [{control_type} id={automation_id} #{fallback}]"


def _format_tree_line(snapshot: dict[str, Any], depth: int) -> str:
    fields = [
        f"text={snapshot.get('direct_text')!r}",
        f"name={snapshot.get('name')!r}",
        f"type={snapshot.get('control_type')!r}",
        f"class={snapshot.get('class_name')!r}",
        f"auto_id={snapshot.get('automation_id')!r}",
        f"handle={snapshot.get('handle')!r}",
        f"rect={snapshot.get('rectangle')!r}",
        f"visible={snapshot.get('visible')!r}",
        f"enabled={snapshot.get('enabled')!r}",
        f"offscreen={snapshot.get('offscreen')!r}",
        f"framework={snapshot.get('framework_id')!r}",
        f"runtime_id={snapshot.get('runtime_id')!r}",
        f"legacy_name={snapshot.get('legacy_name')!r}",
        f"legacy_value={snapshot.get('legacy_value')!r}",
        f"legacy_role={snapshot.get('legacy_role')!r}",
    ]
    return f"{'  ' * depth}{' | '.join(fields)}"


def _walk_control_tree(
    roots: list[Any], backend: str, errors: list[str], max_controls: int = 30000
) -> tuple[list[dict[str, Any]], list[str]]:
    nodes: list[dict[str, Any]] = []
    tree_lines: list[str] = []

    def visit(
        control: Any,
        depth: int,
        parent_id: int | None,
        ancestors: list[int],
        parent_path: str,
    ) -> None:
        if len(nodes) >= max_controls:
            errors.append(f"{backend}: control limit {max_controls} reached")
            return

        node_id = len(nodes)
        temporary_path = f"{parent_path}/control-{node_id}" if parent_path else f"control-{node_id}"
        snapshot = control_snapshot(control, backend, temporary_path, errors)
        label = _control_label(snapshot, str(node_id))
        path = f"{parent_path}/{label}" if parent_path else label
        snapshot["path"] = path
        node = {
            "node_id": node_id,
            "parent_id": parent_id,
            "ancestor_ids": preserve_display_order(ancestors),
            "depth": depth,
            "control": control,
            "snapshot": snapshot,
        }
        nodes.append(node)
        tree_lines.append(_format_tree_line(snapshot, depth))

        children = _call_optional_method(control, "children", errors, path, [])
        if not isinstance(children, (list, tuple)):
            return
        for child in preserve_display_order(children):
            visit(child, depth + 1, node_id, ancestors + [node_id], path)

    for root in preserve_display_order(roots):
        visit(root, 0, None, [], "")
    return nodes, tree_lines


def _selected_item_records(
    control: Any, backend: str, path: str, errors: list[str]
) -> list[dict[str, Any]]:
    selection = _call_optional_method(control, "get_selection", errors, path, [])
    if selection is None:
        return []
    if not isinstance(selection, (list, tuple)):
        selection = [selection]
    records = []
    for index, selected in enumerate(preserve_display_order(selection)):
        records.append(
            control_snapshot(selected, backend, f"{path}/selected-{index}", errors)
        )
    return records


def _item_record(
    node: dict[str, Any],
    visible_index: int,
    descendant_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    snapshot = node["snapshot"]
    cell_texts: list[str] = []
    for descendant in descendant_nodes:
        if node["node_id"] not in descendant["ancestor_ids"]:
            continue
        for text in _snapshot_texts(descendant["snapshot"]):
            cell_texts.append(text)
    patterns = snapshot.get("patterns") or {}
    return {
        "visible_index": visible_index,
        "path": snapshot.get("path"),
        "direct_text": snapshot.get("direct_text"),
        "descendant_cell_texts": cell_texts,
        "name": snapshot.get("name"),
        "value": snapshot.get("value"),
        "control_type": snapshot.get("control_type"),
        "class_name": snapshot.get("class_name"),
        "automation_id": snapshot.get("automation_id"),
        "handle": snapshot.get("handle"),
        "rectangle": snapshot.get("rectangle"),
        "selected": snapshot.get("selected"),
        "selected_method": snapshot.get("selected_method"),
        "offscreen": snapshot.get("offscreen"),
        "runtime_id": snapshot.get("runtime_id"),
        "legacy_accessible_text": {
            "name": snapshot.get("legacy_name"),
            "value": snapshot.get("legacy_value"),
            "role": snapshot.get("legacy_role"),
            "state": snapshot.get("legacy_state"),
        },
        "selection_item_pattern_available": patterns.get("selection_item", "unknown"),
        "scroll_item_pattern_available": patterns.get("scroll_item", "unknown"),
        "invoke_pattern_available": patterns.get("invoke", "unknown"),
        "has_keyboard_focus": snapshot.get("has_keyboard_focus"),
    }


def _candidate_records(
    nodes: list[dict[str, Any]], backend: str, errors: list[str]
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for node in nodes:
        snapshot = node["snapshot"]
        combined = (
            f"{snapshot.get('control_type') or ''} {snapshot.get('class_name') or ''}"
        ).casefold()
        if not any(hint in combined for hint in LIST_HINTS):
            continue

        descendants = [
            item for item in nodes if node["node_id"] in item["ancestor_ids"]
        ]
        direct_children = [
            item for item in nodes if item["parent_id"] == node["node_id"]
        ]
        descendant_texts: list[str] = []
        for descendant in descendants:
            descendant_texts.extend(_snapshot_texts(descendant["snapshot"]))

        score_metadata = {
            "control_type": snapshot.get("control_type"),
            "class_name": snapshot.get("class_name"),
            "descendant_texts": descendant_texts,
        }
        score = score_candidate_control(score_metadata)

        item_nodes = []
        for child in direct_children:
            child_type = str(child["snapshot"].get("control_type") or "").casefold()
            if child_type in ITEM_CONTROL_TYPES or _snapshot_texts(child["snapshot"]):
                item_nodes.append(child)
        if not item_nodes:
            for descendant in descendants:
                descendant_type = str(
                    descendant["snapshot"].get("control_type") or ""
                ).casefold()
                texts = _snapshot_texts(descendant["snapshot"])
                if descendant_type in ITEM_CONTROL_TYPES or exact_articles_in_texts(texts):
                    item_nodes.append(descendant)

        items = [
            _item_record(item, index, descendants)
            for index, item in enumerate(preserve_display_order(item_nodes))
        ]
        selected_items = _selected_item_records(
            node["control"], backend, str(snapshot.get("path")), errors
        )
        patterns = snapshot.get("patterns") or {}
        virtualized: bool | str = patterns.get("virtualized_item", "unknown")
        if virtualized is not True:
            item_virtualization = [
                item["snapshot"].get("patterns", {}).get("virtualized_item", "unknown")
                for item in descendants
            ]
            if True in item_virtualization:
                virtualized = True
            elif backend == "uia" and item_virtualization:
                virtualized = False

        candidates.append(
            {
                "backend": backend,
                "score": score,
                "path": snapshot.get("path"),
                "title": snapshot.get("direct_text") or snapshot.get("name"),
                "automation_id": snapshot.get("automation_id"),
                "class_name": snapshot.get("class_name"),
                "control_type": snapshot.get("control_type"),
                "handle": snapshot.get("handle"),
                "rectangle": snapshot.get("rectangle"),
                "direct_child_count": len(direct_children),
                "descendant_count": len(descendants),
                "exact_known_articles": exact_articles_in_texts(descendant_texts),
                "selected_items": selected_items,
                "scroll_properties": snapshot.get("scroll_properties"),
                "virtualized": virtualized,
                "patterns": patterns,
                "items": items,
            }
        )
    return candidates


def _candidate_text(candidates: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, candidate in enumerate(candidates):
        lines.extend(
            [
                f"CANDIDATE {index}",
                f"backend={candidate.get('backend')}",
                f"score={candidate.get('score')}",
                f"path={candidate.get('path')}",
                f"title={candidate.get('title')!r}",
                f"automation_id={candidate.get('automation_id')!r}",
                f"class_name={candidate.get('class_name')!r}",
                f"control_type={candidate.get('control_type')!r}",
                f"handle={candidate.get('handle')!r}",
                f"rectangle={candidate.get('rectangle')!r}",
                f"direct_child_count={candidate.get('direct_child_count')}",
                f"descendant_count={candidate.get('descendant_count')}",
                f"exact_known_articles={candidate.get('exact_known_articles')!r}",
                f"selected_items={candidate.get('selected_items')!r}",
                f"scroll_properties={candidate.get('scroll_properties')!r}",
                f"virtualized={candidate.get('virtualized')!r}",
                f"patterns={candidate.get('patterns')!r}",
                "ITEMS:",
            ]
        )
        for item in candidate.get("items", []):
            lines.append(json.dumps(to_json_safe(item), ensure_ascii=False, sort_keys=True))
        lines.append("")
    return "\n".join(lines)


def _exact_occurrences(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result = {article: [] for article in EXACT_REPORT_ARTICLES}
    for node in nodes:
        snapshot = node["snapshot"]
        texts = _snapshot_texts(snapshot)
        for article in EXACT_REPORT_ARTICLES:
            if not any(exact_article_match(text, article) for text in texts):
                continue
            result[article].append(
                {
                    "exact_text": article,
                    "path": snapshot.get("path"),
                    "control_type": snapshot.get("control_type"),
                    "class_name": snapshot.get("class_name"),
                    "automation_id": snapshot.get("automation_id"),
                    "handle": snapshot.get("handle"),
                    "rectangle": snapshot.get("rectangle"),
                    "selected": snapshot.get("selected"),
                    "offscreen": snapshot.get("offscreen"),
                    "runtime_id": snapshot.get("runtime_id"),
                }
            )
    return result


def _selected_article(candidate: dict[str, Any] | None) -> tuple[str, str, str]:
    if not candidate:
        return "UNKNOWN", "no candidate profile list", "UNKNOWN"

    for selected in candidate.get("selected_items", []):
        for text in _snapshot_texts(selected):
            article = article_like_value(text)
            if article:
                return article, "container.get_selection()", "UNKNOWN"

    for item in candidate.get("items", []):
        if item.get("selected") is not True:
            continue
        for key in ("direct_text", "name", "value"):
            article = article_like_value(item.get(key))
            if article:
                return (
                    article,
                    str(item.get("selected_method") or "selected item property"),
                    "UNKNOWN",
                )
        for text in item.get("descendant_cell_texts", []):
            article = article_like_value(text)
            if article:
                return (
                    article,
                    str(item.get("selected_method") or "selected descendant"),
                    "UNKNOWN",
                )

    focused_article = "UNKNOWN"
    for item in candidate.get("items", []):
        if item.get("has_keyboard_focus") is not True:
            continue
        for key in ("direct_text", "name", "value"):
            article = article_like_value(item.get(key))
            if article:
                focused_article = article
                break
        if focused_article != "UNKNOWN":
            break
    return "UNKNOWN", "selection metadata unavailable or non-article", focused_article


def _profile_page_found(nodes: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> bool:
    for node in nodes:
        for text in _snapshot_texts(node["snapshot"]):
            if "profile data" in text.casefold():
                return True
    return any(len(candidate.get("exact_known_articles", [])) >= 2 for candidate in candidates)


def _inspect_backend(pid: int, backend: str, errors: list[str]) -> dict[str, Any]:
    from pywinauto import Application, Desktop

    backend_errors: list[str] = []
    app = Application(backend=backend).connect(process=pid, timeout=10)
    del app
    windows = Desktop(backend=backend).windows(
        process=pid, top_level_only=True, visible_only=False
    )
    visible_windows = []
    for window in preserve_display_order(windows):
        visible = _call_optional_method(
            window, "is_visible", backend_errors, f"{backend}.top-level", None
        )
        if visible is not False:
            visible_windows.append(window)
    roots = visible_windows or preserve_display_order(windows)
    nodes, tree_lines = _walk_control_tree(roots, backend, backend_errors)
    candidates = _candidate_records(nodes, backend, backend_errors)
    occurrences = _exact_occurrences(nodes)
    errors.extend(f"{backend.upper()}: {error}" for error in backend_errors)
    return {
        "backend": backend,
        "attached": True,
        "nodes": nodes,
        "tree_lines": tree_lines,
        "candidates": candidates,
        "occurrences": occurrences,
        "profile_page_found": _profile_page_found(nodes, candidates),
    }


def _native_windows(pid: int, errors: list[str]) -> list[dict[str, Any]]:
    try:
        import win32gui
        import win32process
    except Exception as exc:
        errors.append(f"PROCESS WINDOWS: pywin32 import failed: {type(exc).__name__}: {exc}")
        return []

    windows: list[dict[str, Any]] = []

    def collect(handle: int, _: Any) -> None:
        _, window_pid = win32process.GetWindowThreadProcessId(handle)
        if window_pid != pid:
            return
        windows.append(
            {
                "title": safe_read(
                    f"window {handle} title", lambda: win32gui.GetWindowText(handle), errors, ""
                ),
                "handle": handle,
                "class_name": safe_read(
                    f"window {handle} class", lambda: win32gui.GetClassName(handle), errors, ""
                ),
                "rectangle": to_json_safe(
                    safe_read(
                        f"window {handle} rectangle",
                        lambda: win32gui.GetWindowRect(handle),
                        errors,
                    )
                ),
                "visible": safe_read(
                    f"window {handle} visible",
                    lambda: bool(win32gui.IsWindowVisible(handle)),
                    errors,
                ),
                "enabled": safe_read(
                    f"window {handle} enabled",
                    lambda: bool(win32gui.IsWindowEnabled(handle)),
                    errors,
                ),
                "process_id": window_pid,
            }
        )

    win32gui.EnumWindows(collect, None)
    return windows


def _process_info(pid: int, errors: list[str]) -> dict[str, Any] | None:
    try:
        import psutil

        process = psutil.Process(pid)
        name = safe_read(f"process {pid} name", process.name, errors, "")
        executable = safe_read(f"process {pid} executable", process.exe, errors, "")
        return {
            "pid": pid,
            "name": name,
            "executable": executable,
            "windows": _native_windows(pid, errors),
        }
    except Exception as exc:
        errors.append(f"PROCESS {pid}: {type(exc).__name__}: {exc}")
        return None


def _find_logikal_processes(errors: list[str]) -> list[dict[str, Any]]:
    import psutil

    candidates: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            info = process.info
            if not looks_like_logikal_executable(info.get("name"), info.get("exe")):
                continue
            candidates.append(
                {
                    "pid": info["pid"],
                    "name": info.get("name") or "",
                    "executable": info.get("exe") or "",
                    "windows": _native_windows(info["pid"], errors),
                }
            )
        except Exception as exc:
            errors.append(
                f"PROCESS ENUMERATION {getattr(process, 'pid', '?')}: "
                f"{type(exc).__name__}: {exc}"
            )
    candidates.sort(key=lambda candidate: candidate["pid"])
    return candidates


def _format_processes(processes: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for process in processes:
        lines.extend(
            [
                f"PID={process.get('pid')}",
                f"EXECUTABLE_NAME={process.get('name')}",
                f"EXECUTABLE_PATH={process.get('executable')}",
            ]
        )
        windows = process.get("windows") or []
        if not windows:
            lines.append("WINDOW=<none exposed>")
        for index, window in enumerate(windows):
            lines.extend(
                [
                    f"WINDOW_INDEX={index}",
                    f"TOP_LEVEL_WINDOW_TITLE={window.get('title')}",
                    f"WINDOW_HANDLE={window.get('handle')}",
                    f"CLASS_NAME={window.get('class_name')}",
                    f"RECTANGLE={window.get('rectangle')}",
                    f"VISIBLE={window.get('visible')}",
                    f"ENABLED={window.get('enabled')}",
                ]
            )
        lines.append("")
    return "\n".join(lines)


def _format_backend_top_level_windows(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for result in results:
        backend = str(result.get("backend") or "")
        lines.append(f"BACKEND_TOP_LEVEL_WINDOWS={backend}")
        roots = [node for node in result.get("nodes", []) if node.get("depth") == 0]
        for index, node in enumerate(roots):
            snapshot = node["snapshot"]
            lines.extend(
                [
                    f"WINDOW_INDEX={index}",
                    f"TITLE={snapshot.get('direct_text') or snapshot.get('name')}",
                    f"CONTROL_TYPE={snapshot.get('control_type')}",
                    f"CLASS_NAME={snapshot.get('class_name')}",
                    f"AUTOMATION_ID={snapshot.get('automation_id')}",
                    f"NATIVE_HANDLE={snapshot.get('handle')}",
                    f"RECTANGLE={snapshot.get('rectangle')}",
                    f"VISIBLE={snapshot.get('visible')}",
                    f"ENABLED={snapshot.get('enabled')}",
                    f"PROCESS_ID={snapshot.get('process_id')}",
                    f"RUNTIME_ID={snapshot.get('runtime_id')}",
                ]
            )
        lines.append("")
    return "\n".join(lines)


def _strip_internal_nodes(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [to_json_safe(node["snapshot"]) for node in result.get("nodes", [])]


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, content: Any) -> None:
    path.write_text(
        json.dumps(to_json_safe(content), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _best_candidate(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for result in results:
        candidates.extend(result.get("candidates", []))
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda candidate: (
            int(candidate.get("score") or 0),
            1 if candidate.get("backend") == "uia" else 0,
        ),
    )


def _summary(
    pid: int,
    process: dict[str, Any],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate = _best_candidate(results)
    selected_article, selected_method, focused_article = _selected_article(candidate)
    title = ""
    for window in process.get("windows", []):
        if window.get("visible") and window.get("title"):
            title = str(window["title"])
            break
    if not title and process.get("windows"):
        title = str(process["windows"][0].get("title") or "")

    exact = {article: False for article in EXACT_REPORT_ARTICLES}
    for result in results:
        occurrences = result.get("occurrences", {})
        for article in EXACT_REPORT_ARTICLES:
            if occurrences.get(article):
                exact[article] = True

    patterns = candidate.get("patterns", {}) if candidate else {}
    summary = {
        "LOGIKAL_PID": pid,
        "TOP_LEVEL_WINDOW_TITLE": title,
        "PROFILE_PAGE_FOUND": any(result.get("profile_page_found") for result in results),
        "PROFILE_LIST_FOUND": candidate is not None and int(candidate.get("score") or 0) >= 45,
        "PROFILE_LIST_BACKEND": candidate.get("backend", "") if candidate else "",
        "PROFILE_LIST_CONTROL_TYPE": candidate.get("control_type", "") if candidate else "",
        "PROFILE_LIST_CLASS_NAME": candidate.get("class_name", "") if candidate else "",
        "PROFILE_LIST_AUTOMATION_ID": candidate.get("automation_id", "") if candidate else "",
        "PROFILE_LIST_HANDLE": candidate.get("handle") if candidate else None,
        "PROFILE_LIST_ITEM_COUNT_EXPOSED": len(candidate.get("items", [])) if candidate else 0,
        "CURRENT_SELECTED_ARTICLE": selected_article,
        "CURRENT_SELECTED_ARTICLE_METHOD": selected_method,
        "FOCUSED_ARTICLE_CANDIDATE": focused_article,
        "EXACT_2256_FOUND": exact["2256"],
        "EXACT_K111_FOUND": exact["K111"],
        "EXACT_K29_FOUND": exact["K29"],
        "SELECTION_PATTERN_AVAILABLE": patterns.get("selection", "unknown"),
        "SCROLL_PATTERN_AVAILABLE": patterns.get("scroll", "unknown"),
        "GRID_PATTERN_AVAILABLE": patterns.get("grid", "unknown"),
        "TABLE_PATTERN_AVAILABLE": patterns.get("table", "unknown"),
        "INVOKE_PATTERN_AVAILABLE": patterns.get("invoke", "unknown"),
        "VIRTUALIZED": candidate.get("virtualized", "unknown") if candidate else "unknown",
    }
    return summary


def _machine_summary_text(summary: dict[str, Any]) -> str:
    lines = []
    for key, value in summary.items():
        if key in {"CURRENT_SELECTED_ARTICLE_METHOD", "BACKEND_FAILURES", "ARTIFACT_DIRECTORY"}:
            continue
        if isinstance(value, bool):
            rendered = str(value).lower()
        elif value is None:
            rendered = ""
        else:
            rendered = str(value)
        lines.append(f"{key}={rendered}")
    lines.append(
        f"CURRENT_SELECTED_ARTICLE_DISCOVERY={summary.get('CURRENT_SELECTED_ARTICLE_METHOD')}"
    )
    return "\n".join(lines)


def _exact_occurrence_text(results: list[dict[str, Any]]) -> str:
    lines = ["EXACT ARTICLE OCCURRENCES"]
    for result in results:
        lines.append(f"BACKEND={result.get('backend')}")
        for article in EXACT_REPORT_ARTICLES:
            occurrences = result.get("occurrences", {}).get(article, [])
            lines.append(f"ARTICLE={article} OCCURRENCES={len(occurrences)}")
            for occurrence in occurrences:
                lines.append(json.dumps(occurrence, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


def _create_artifact_directory(root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = root / f"profile_page_inspection_{timestamp}"
    output.mkdir(parents=True, exist_ok=False)
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only inspection of an open LogiKal Profile Data page"
    )
    parser.add_argument(
        "--pid",
        type=int,
        help="PID of a process whose executable name/path identifies it as LogiKal",
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts"),
        help="Artifact parent directory (default: artifacts)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    safe, findings = enforce_source_safety(Path(__file__))
    if not safe:
        print("SAFETY GUARD REFUSED EXECUTION", file=sys.stderr)
        print(json.dumps(findings, indent=2), file=sys.stderr)
        return 10

    args = parse_args(argv)
    errors: list[str] = []
    try:
        candidates = _find_logikal_processes(errors)
    except Exception as exc:
        print(
            f"Could not enumerate LogiKal executable processes: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 3

    print(_format_processes(candidates) or "No LogiKal executable process was found.")

    if args.pid is None:
        if len(candidates) > 1:
            print("Multiple LogiKal processes found. Run again with --pid <PID>.")
            return 0
        if not candidates:
            print("No confirmed LogiKal executable process is available for inspection.")
            return 0
        process = candidates[0]
    else:
        process = _process_info(args.pid, errors)
        if process is None:
            print(f"Cannot read process PID {args.pid}.", file=sys.stderr)
            return 3
        if not looks_like_logikal_executable(
            str(process.get("name") or ""), str(process.get("executable") or "")
        ):
            print(
                f"PID {args.pid} was rejected because its executable is not identifiable as LogiKal.",
                file=sys.stderr,
            )
            return 3

    pid = int(process["pid"])
    try:
        output_dir = _create_artifact_directory(args.artifacts_root)
    except Exception as exc:
        print(
            f"Cannot create artifact directory under {args.artifacts_root}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 4

    results: list[dict[str, Any]] = []
    backend_failures: dict[str, str] = {}
    for backend in ("uia", "win32"):
        try:
            result = _inspect_backend(pid, backend, errors)
            results.append(result)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            backend_failures[backend] = message
            errors.append(f"{backend.upper()} INSPECTION FAILURE: {message}")
            errors.append(traceback.format_exc())

    all_candidates: list[dict[str, Any]] = []
    for result in results:
        all_candidates.extend(result.get("candidates", []))
    summary = _summary(pid, process, results)
    summary["BACKEND_FAILURES"] = backend_failures
    summary["ARTIFACT_DIRECTORY"] = str(output_dir.resolve())

    process_text = _format_processes(candidates)
    if process not in candidates:
        process_text = f"{process_text}\n{_format_processes([process])}".strip()
    process_text = (
        f"{process_text}\n\n{_format_backend_top_level_windows(results)}"
    ).strip()
    candidate_text = _candidate_text(all_candidates)
    occurrence_text = _exact_occurrence_text(results)

    try:
        _write_text(output_dir / "process_windows.txt", process_text)
        for backend in ("uia", "win32"):
            result = next(
                (item for item in results if item.get("backend") == backend), None
            )
            if result is not None:
                content = "\n".join(result["tree_lines"])
            else:
                content = (
                    f"{backend.upper()}_INSPECTION_FAILED: "
                    f"{backend_failures.get(backend, 'unknown failure')}\n"
                )
            _write_text(output_dir / f"{backend}_control_tree.txt", content)
        _write_text(
            output_dir / "candidate_profile_lists.txt",
            f"{candidate_text}\n\n{occurrence_text}\n",
        )
        _write_json(output_dir / "profile_items.json", all_candidates)
        _write_json(output_dir / "summary.json", summary)
        _write_text(output_dir / "errors.txt", "\n".join(errors))
    except Exception as exc:
        print(
            f"Cannot write required artifacts in {output_dir}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 4

    print(_machine_summary_text(summary))
    print(f"ARTIFACT_DIRECTORY={output_dir.resolve()}")

    if not results:
        print("Neither UIA nor Win32 could attach to the confirmed LogiKal PID.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
