#!/usr/bin/env python3
"""Catch the PBIR authoring mistakes that `validate` does not report.

Run from the repo root that holds the *.Report directories, BEFORE committing
any hand-generated visual.json. Exits non-zero when something is wrong.

    python3 <skill>/scripts/check-visual-projections.py [root]

Skips dead copies of the report tree -- .claude/worktrees, node_modules, .git,
__pycache__, .venv -- so an old git worktree under the repo does not get
double-counted alongside the real tree. If the same *.Report basename still
turns up in more than one surviving location, a WARNING lists all of them so
you don't edit the wrong copy.

Checks:
  1. `active` inside a `Values` well on a non-slicer visual. Desktop propagates
     the key and defaults later-added fields to false, so those columns silently
     drop out of the visual's query -- the field shows in the Data pane but the
     column is missing in the report, and it stays missing after publishing.
     `active` belongs only to hierarchy wells (Rows/Columns/Category/Series)
     and to a slicer's single field.
  2. Data visual without `drillFilterOtherVisuals` -- clicking it will not
     cross-filter the rest of the page.
  3. Visual with no name -- Desktop's Selection pane lists visuals by their title
     text and falls back to the visual type, so an unnamed card reads as "Card".
     Set visualContainerObjects.title.properties.text (with show:false when the
     title should not be displayed). Groups use visualGroup.displayName.
     Wording/language of names is a project convention -- see section 6 of the
     project's layout file.
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

# Wells where `active` is legitimate, surveyed across five production report repos:
# pivotTable Rows/Columns, chart Category/Series, treemap Group. Measure wells
# (Values, Data, Y, Tooltips, ...) never carry it on a non-slicer visual.
HIERARCHY_WELLS = {"Rows", "Columns", "Category", "Series", "Group", "Details", "Axis"}


def _is_slicer(vtype):
    """Slicers legitimately mark their single field active -- and they put it in
    the Values well. Covers `slicer` and `advancedSlicerVisual`."""
    return "slicer" in vtype.lower()


def build_parser():
    ap = argparse.ArgumentParser(
        prog="check-visual-projections.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Catch the PBIR authoring mistakes that `powerbi-report-author\n"
            "validate` does not report. Reads every visual.json under <root> and\n"
            "flags three things:\n"
            "  ERROR  `active` on a measure well of a non-slicer visual -- Desktop\n"
            "         then defaults later-added fields to false and the column\n"
            "         silently drops out of the visual's query.\n"
            "  WARN   a data visual with no drillFilterOtherVisuals -- clicking it\n"
            "         will not cross-filter the rest of the page.\n"
            "  NAME   a visual with no title text -- it reads as its bare type in\n"
            "         Desktop's Selection pane (name-visuals.py can fill these in).\n"
            "It reads only; nothing is written."),
        epilog=(
            "exit codes:\n"
            "  0  no errors (WARN/NAME findings may still be listed -- they are backlog)\n"
            "  1  at least one ERROR: an `active` key that will drop a column\n"
            "  2  no visual.json found under <root> (wrong directory?)\n\n"
            "Respects .powerbi-scan-ignore and skips worktrees, node_modules, .git,\n"
            "__pycache__ and .venv."))
    ap.add_argument("root", nargs="?", default=".",
                    help="repo root holding the *.Report directories "
                         "(default: the current directory)")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = args.root
    _common.load_ignore(root)
    # reports may sit at the repo root or in subfolders (reports/, archive/, .power_bi/ ...)
    files = _common.visual_json_files(root)
    if not files:
        print(f"no visual.json found under {root!r} -- wrong directory?")
        return 2

    report_dirs = sorted({d for d in (_common.report_dir_of(f) for f in files) if d})
    _common.warn_duplicate_reports(report_dirs)

    active_errs, drill_warns, name_warns = [], [], []
    for f in files:
        try:
            doc = json.load(io.open(f, encoding="utf-8"))
            visual = doc.get("visual", {})
        except json.JSONDecodeError as exc:
            active_errs.append(f"{f}: malformed JSON ({exc})")
            continue
        if not visual:
            group = doc.get("visualGroup")
            if group and group.get("displayName", "").strip().lower().startswith("group "):
                name_warns.append(f"{f}: group still named {group['displayName']!r}")
            continue
        vtype = visual.get("visualType", "?")
        if not _common.title_text(visual):
            name_warns.append(f"{f}: no name -- shows as {vtype!r} in the Selection pane")
        query = visual.get("query", {}).get("queryState") or {}
        if not query:
            continue  # not a data visual
        if not _is_slicer(vtype):
            for well, cfg in query.items():
                if well in HIERARCHY_WELLS:
                    continue
                for i, proj in enumerate(cfg.get("projections", [])):
                    if "active" in proj:
                        active_errs.append(f"{f}: well {well!r} projection #{i} has 'active' ({vtype})")
        if "drillFilterOtherVisuals" not in visual:
            drill_warns.append(f"{f}: no drillFilterOtherVisuals ({vtype})")

    for e in active_errs:
        print(f"ERROR  {e}")
    for w in drill_warns:
        print(f"WARN   {w}")
    for w in name_warns:
        print(f"NAME   {w}")
    print(
        f"\n{len(files)} visuals checked -- {len(active_errs)} errors, "
        f"{len(drill_warns)} missing drillFilterOtherVisuals, {len(name_warns)} unnamed"
    )
    return 1 if active_errs else 0


if __name__ == "__main__":
    sys.exit(main())
