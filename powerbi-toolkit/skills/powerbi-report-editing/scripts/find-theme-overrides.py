#!/usr/bin/env python3
"""List per-visual formatting that fights or duplicates the report's theme.

Formatting is owned by the theme. Anything hard-set on a visual is a local
exception to it, and there are two kinds:

  OVERRIDE   the visual sets a DIFFERENT value than the theme -> the theme is
             being overridden. This is the one that matters: the visual stops
             following the theme, so a later theme change silently skips it and
             the page drifts out of the design system.
  REDUNDANT  the visual sets exactly the theme's value -> dead weight; it does
             nothing today and freezes the old look the moment the theme changes.

    python3 <skill>/scripts/find-theme-overrides.py <report-dir-or-repo> [--detail]

Prints a summary by property (what to fix, and how widespread) and, with
--detail, every occurrence. It never edits anything.

Not every override is a mistake -- a deliberate accent or a data-driven color is
legitimate. The script lists candidates; the project's layout file (section 7)
and the task decide which survive.

Deliberately conservative -- it skips what it cannot compare safely:
state/data-bound selectors, and `title.text`, which carries the visual's name in
the Selection pane and must never be stripped.

Skips dead copies of the report tree -- .claude/worktrees, node_modules, .git,
__pycache__, .venv -- so an old git worktree under the repo does not get
scanned alongside the real tree. If the same *.Report basename still turns up
in more than one surviving location, a WARNING lists all of them so you don't
edit the wrong copy.

Exit 0 = nothing found, 1 = candidates found (backlog, never blocking),
2 = no *.Report directory under the root at all.
"""
import argparse
import glob
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

SKIP_PROPS = {("title", "text"), ("title", "titleText"), ("subTitle", "text")}


def literal(node):
    """PBIR value -> plain Python, or a sentinel when it is not a literal."""
    if isinstance(node, dict):
        if "expr" in node and isinstance(node["expr"], dict):
            lit = node["expr"].get("Literal")
            if isinstance(lit, dict) and "Value" in lit:
                return _parse(lit["Value"])
            return NotImplemented
        if "solid" in node:
            inner = node["solid"].get("color")
            return literal(inner) if isinstance(inner, dict) else inner
        return NotImplemented
    return node


def _parse(raw):
    if not isinstance(raw, str):
        return raw
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)[DLM]?", raw)
    if m:
        v = float(m.group(1))
        return int(v) if v.is_integer() else v
    return raw


def theme_value(theme, vtype, card, prop):
    styles = theme.get("visualStyles", {})
    for key in (vtype, "*"):
        cards = (styles.get(key) or {}).get("*") or {}
        arr = cards.get(card)
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and prop in arr[0]:
            val = arr[0][prop]
            if isinstance(val, dict) and "solid" in val:
                return val["solid"].get("color")
            return val
    return NotImplemented


def find_theme(report_dir):
    hits = glob.glob(os.path.join(report_dir, "StaticResources/RegisteredResources/*.json"))
    for h in hits:
        try:
            d = json.load(io.open(h, encoding="utf-8"))
        except Exception:
            continue
        if "visualStyles" in d:
            return h, d
    return None, None


def scan_report(report_dir, findings):
    theme_path, theme = find_theme(report_dir)
    name = os.path.basename(report_dir)
    if not theme:
        print(f"-- {name}: no registered theme with visualStyles, skipped")
        return
    print(f"== {name}  (theme: {os.path.basename(theme_path)})")
    for f in sorted(glob.glob(os.path.join(report_dir, "definition/pages/*/visuals/*/visual.json"))):
        v = (json.load(io.open(f, encoding="utf-8")) or {}).get("visual") or {}
        vtype = v.get("visualType")
        if not vtype:
            continue
        for holder in ("objects", "visualContainerObjects"):
            for card, arr in (v.get(holder) or {}).items():
                for item in arr:
                    sel = item.get("selector")
                    if sel and sel.get("id") != "default":
                        continue  # state- or data-bound, not comparable
                    for prop, raw in (item.get("properties") or {}).items():
                        if (card, prop) in SKIP_PROPS:
                            continue
                        mine = literal(raw)
                        if mine is NotImplemented:
                            continue
                        theirs = theme_value(theme, vtype, card, prop)
                        if theirs is NotImplemented:
                            continue
                        kind = "REDUNDANT" if mine == theirs else "OVERRIDE"
                        findings.append({
                            "kind": kind, "report": name, "visualType": vtype,
                            "card": card, "prop": prop, "mine": mine, "theme": theirs,
                            "page": f.split(os.sep)[-4], "visual": f.split(os.sep)[-2],
                        })


def build_parser():
    ap = argparse.ArgumentParser(
        prog="find-theme-overrides.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "List per-visual formatting that fights or duplicates the report's\n"
            "theme. Formatting is owned by the theme, so anything hard-set on a\n"
            "visual is a local exception to it, and there are two kinds:\n"
            "  OVERRIDE   the visual sets a DIFFERENT value than the theme. The\n"
            "             visual stops following the theme, so a later theme change\n"
            "             silently skips it and the page drifts out of the system.\n"
            "  REDUNDANT  the visual sets exactly the theme's value: dead weight\n"
            "             that freezes the old look the moment the theme changes.\n\n"
            "Deliberately conservative -- it skips what it cannot compare safely:\n"
            "state- and data-bound selectors, and title.text, which carries the\n"
            "visual's Selection-pane name and must never be stripped. Not every\n"
            "override is a mistake; this lists candidates, and the project's layout\n"
            "file decides which survive. It reads only; nothing is written."),
        epilog=(
            "exit codes:\n"
            "  0  no visual sets a property the theme already governs\n"
            "  1  overrides or redundant properties found -- backlog, never blocking\n"
            "     (doctor.py lists them under 'Backlog (not blocking)')\n"
            "  2  no *.Report directory under <root> (wrong directory?)\n\n"
            "Respects .powerbi-scan-ignore and skips worktrees, node_modules, .git,\n"
            "__pycache__ and .venv."))
    ap.add_argument("root", nargs="?", default=".",
                    help="a *.Report directory, or a repo root holding several "
                         "(default: the current directory)")
    ap.add_argument("--detail", action="store_true",
                    help="also print every single occurrence, not just the "
                         "per-property summary")
    return ap


def main(argv=None):
    parsed = build_parser().parse_args(argv)
    detail = parsed.detail
    root = os.path.abspath(parsed.root)
    _common.load_ignore(root)

    reports = ([root] if root.endswith(".Report") else _common.report_dirs(root))
    reports = [r for r in reports if not _common.is_excluded(r)]
    if not reports:
        print(f"no *.Report directory under {root}")
        return 2

    _common.warn_duplicate_reports(reports)

    findings = []
    for r in reports:
        scan_report(r, findings)

    for kind, label in (("OVERRIDE", "OVERRIDES the theme"), ("REDUNDANT", "duplicates the theme")):
        rows = [f for f in findings if f["kind"] == kind]
        print(f"\n=== {len(rows)} propert(ies) that {label}")
        if not rows:
            continue
        groups = {}
        for f in rows:
            key = (f["visualType"], f["card"], f["prop"])
            g = groups.setdefault(key, {"n": 0, "values": set(), "theme": f["theme"]})
            g["n"] += 1
            g["values"].add(repr(f["mine"]))
        for (vtype, card, prop), g in sorted(groups.items(), key=lambda kv: -kv[1]["n"]):
            vals = ", ".join(sorted(g["values"])[:3])
            more = "" if len(g["values"]) <= 3 else f" +{len(g['values']) - 3} more"
            if kind == "OVERRIDE":
                print(f"  {g['n']:>4}x  {vtype}.{card}.{prop}  = {vals}{more}   theme: {g['theme']!r}")
            else:
                print(f"  {g['n']:>4}x  {vtype}.{card}.{prop}  = {vals}{more}")
        if detail:
            for f in rows:
                print(f"        {f['report']}/pages/{f['page']}/…/{f['visual'][:8]}"
                      f"  {f['card']}.{f['prop']} = {f['mine']!r}")

    print("\nNothing was modified. In a refactor: drop REDUNDANT ones outright, and take")
    print("OVERRIDE ones back to the theme unless the value is a deliberate exception")
    print("(record those in the layout file, section 10). Screenshot the page afterwards.")
    # 1 is backlog, not breakage -- doctor.py lists this check as a note. Before
    # this it always returned 0, so doctor could never surface these at all.
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
