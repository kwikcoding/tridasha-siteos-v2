"""Read SiteOS v1 data — the Google Sheets as downloaded (.xlsx, one tab per sheet) or the v1 /api/export JSON —
into {tab name: [ {header: value}, … ]}. No Django imports, so it is unit-tested on its own."""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import date, datetime

from apps.materials import importer

MAX_BYTES = 25 * 1024 * 1024

# v1 tab names (after "Live – ") that v2 knows how to use
KNOWN = ["Sites", "Inventory", "Stock Balance", "Receipts & Issues", "Materials Register", "Take-off Detail", "Indents",
         "Bills", "Labour", "Daily Reports", "Tasks", "Quality & Safety", "Equipment"]
SKIP = {"Sync"}


def tab_name(title: str) -> tuple[str, bool]:
    """'Live – Sites' → ('Sites', True); 'Materials Register' → ('Materials Register', False)."""
    t = str(title or "").strip()
    m = re.match(r"^live\s*[–—-]\s*(.+)$", t, re.I)
    return (m.group(1).strip(), True) if m else (t, False)


def _cell(v):
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == datetime.min.time() else v.isoformat(sep=" ", timespec="minutes")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        return v.strip()
    return v


def _rows_to_dicts(header, rows):
    head = [str(h).strip() if h not in (None, "") else f"col{ix + 1}" for ix, h in enumerate(header)]
    out = []
    for r in rows:
        r = [_cell(v) for v in (r or [])]
        if not any(v not in (None, "") for v in r):
            continue
        out.append({head[ix]: (r[ix] if ix < len(r) else None) for ix in range(len(head))})
    return out


def _header_index(rows):
    """The header is the first row with at least two filled cells (title rows above it are skipped)."""
    for ix, r in enumerate(rows[:25]):
        if sum(1 for v in (r or []) if v not in (None, "")) >= 2:
            return ix
    return None


def read_file(filename: str, content: bytes) -> dict[str, dict]:
    """→ {tab: {"live": bool, "rows": [dict], "file": name}}"""
    if len(content) > MAX_BYTES:
        raise importer.ImportError_(f"{filename} is larger than 25 MB.")
    name = (filename or "").lower()
    tabs: dict[str, dict] = {}

    def put(title, header, rows, raw_rows=None):
        tab, live = tab_name(title)
        if tab in SKIP or not header:
            return
        entry = {"live": live, "rows": _rows_to_dicts(header, rows), "file": filename, "raw": raw_rows}
        # the "Live –" tab written by v1 wins over a hand-kept tab of the same name
        if tab not in tabs or (live and not tabs[tab]["live"]):
            tabs[tab] = entry

    if name.endswith(".json"):
        try:
            data = json.loads(content.decode("utf-8-sig"))
        except Exception:
            raise importer.ImportError_(f"{filename} isn’t valid JSON.")
        for t in data.get("tabs", []):
            put(t.get("title"), t.get("header") or [], t.get("rows") or [])
        return tabs
    if name.endswith((".xlsx", ".xlsm")):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            raise importer.ImportError_(f"Couldn’t open {filename} — download the Google Sheet again as .xlsx.")
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            hix = _header_index(rows)
            if hix is None:
                continue
            put(ws.title, rows[hix], rows[hix + 1:], raw_rows=rows)
        return tabs
    raise importer.ImportError_(f"{filename}: upload the Google Sheets as .xlsx (File → Download → Microsoft Excel), or the v1 export .json.")


def merge(files: list[tuple[str, bytes]]) -> dict[str, dict]:
    """Several files → one set of tabs. A tab present in more than one file (v1 wrote some tabs to two sheets)
    is merged; identical rows collapse later by their key."""
    out: dict[str, dict] = {}
    for fname, content in files:
        for tab, entry in read_file(fname, content).items():
            if tab not in out:
                out[tab] = entry
            elif entry["live"] and not out[tab]["live"]:
                out[tab] = entry
            elif entry["live"] == out[tab]["live"] and entry["file"] != out[tab]["file"]:
                if _same_rows(entry["rows"], out[tab]["rows"]):
                    continue          # v1 wrote this tab to two sheets — same rows, keep one copy
                out[tab] = {**out[tab], "rows": out[tab]["rows"] + entry["rows"], "file": out[tab]["file"] + ", " + entry["file"]}
    return out


def row_keys(rows: list[dict]) -> list[str]:
    """Stable key per row; identical rows get #2, #3 … so true duplicates survive but re-imports don't double."""
    seen: dict[str, int] = {}
    keys = []
    for r in rows:
        base = hashlib.sha1(json.dumps(r, sort_keys=True, default=str).encode()).hexdigest()[:40]
        n = seen.get(base, 0) + 1
        seen[base] = n
        keys.append(base if n == 1 else f"{base[:36]}#{n}")
    return keys


def _same_rows(a: list[dict], b: list[dict]) -> bool:
    enc = lambda rows: sorted(json.dumps(r, sort_keys=True, default=str) for r in rows)
    return enc(a) == enc(b)


def g(row: dict, *names, default=None):
    """Get a value by any of several header spellings (case/spacing-insensitive)."""
    norm = {importer.norm(k): v for k, v in row.items()}
    for n in names:
        v = norm.get(importer.norm(n))
        if v not in (None, ""):
            return v
    return default
