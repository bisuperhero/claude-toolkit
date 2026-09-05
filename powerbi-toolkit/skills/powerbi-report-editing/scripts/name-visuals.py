#!/usr/bin/env python3
"""Give every visual a name that reads in Desktop's Selection pane.

Desktop lists visuals by their title text and falls back to the visual type, so
an unnamed card shows as "Card" and tells a reader nothing. This derives a name
from the visual's type and the fields it actually shows, and writes it into
visualContainerObjects.title.properties.text (with show:false when the visual
has no visible title, which is what a Selection-pane rename produces).

    python3 name-visuals.py <repo-root> [--apply] [--lang en|cs]

Dry run by default. Never renames a visual that already has a title text.

Safety: the file is never re-serialized. The title block is inserted into the
existing text, so every other byte -- including float literals like
78.553615960099748, which Python would shorten on a round-trip -- is left exactly
as Desktop wrote it. Line endings are preserved.

Respects .powerbi-scan-ignore.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

TYPES = {
    "cs": {
        "tableEx": "tabulka", "pivotTable": "matice", "cardVisual": "KPI karty",
        "card": "karta", "multiRowCard": "karta", "kpi": "KPI",
        "slicer": "slicer", "advancedSlicerVisual": "slicer",
        "clusteredColumnChart": "sloupcový graf", "columnChart": "sloupcový graf",
        "stackedColumnChart": "skládaný sloupcový graf",
        "hundredPercentStackedColumnChart": "100% sloupcový graf",
        "clusteredBarChart": "pruhový graf", "barChart": "pruhový graf",
        "hundredPercentStackedBarChart": "100% pruhový graf",
        "lineChart": "spojnicový graf", "areaChart": "plošný graf",
        "stackedAreaChart": "plošný graf",
        "lineClusteredColumnComboChart": "kombinovaný graf",
        "lineStackedColumnComboChart": "kombinovaný graf",
        "donutChart": "prstencový graf", "pieChart": "koláčový graf",
        "treemap": "stromová mapa", "funnel": "trychtýř", "scatterChart": "bodový graf",
        "waterfallChart": "vodopádový graf", "ribbonChart": "stuhový graf",
        "gauge": "měřidlo", "shapeMap": "mapa", "map": "mapa", "azureMap": "mapa",
        "textbox": "textové pole", "shape": "tvar", "image": "obrázek",
        "actionButton": "tlačítko", "basicShape": "tvar",
    },
    # Same key set as "cs" -- label() falls back to the Czech map, so a key that
    # is missing here silently produces a Czech name under --lang en.
    "en": {
        "tableEx": "table", "pivotTable": "matrix", "cardVisual": "KPI cards",
        "card": "card", "multiRowCard": "card", "kpi": "KPI",
        "slicer": "slicer", "advancedSlicerVisual": "slicer",
        "clusteredColumnChart": "column chart", "columnChart": "column chart",
        "stackedColumnChart": "stacked column chart",
        "hundredPercentStackedColumnChart": "100% stacked column chart",
        "clusteredBarChart": "bar chart", "barChart": "bar chart",
        "hundredPercentStackedBarChart": "100% stacked bar chart",
        "lineChart": "line chart", "areaChart": "area chart",
        "stackedAreaChart": "area chart",
        "lineClusteredColumnComboChart": "combo chart",
        "lineStackedColumnComboChart": "combo chart",
        "donutChart": "donut chart", "pieChart": "pie chart",
        "treemap": "treemap", "funnel": "funnel", "scatterChart": "scatter chart",
        "waterfallChart": "waterfall chart", "ribbonChart": "ribbon chart",
        "gauge": "gauge", "shapeMap": "map", "map": "map", "azureMap": "map",
        "textbox": "text box", "shape": "shape", "image": "image",
        "actionButton": "button", "basicShape": "shape",
    },
}
BY = {"cs": "podle", "en": "by"}
SLICER = {"cs": "Slicer", "en": "Slicer"}


def label(vtype, lang):
    return TYPES[lang].get(vtype) or TYPES["cs"].get(vtype) or vtype


def field_names(visual):
    """Readable field names per well."""
    out = {}
    for well, cfg in (visual.get("query", {}).get("queryState") or {}).items():
        names = []
        for proj in cfg.get("projections", []):
            n = proj.get("nativeQueryRef") or proj.get("displayName") or proj.get("queryRef", "")
            n = n.split(".")[-1].strip()
            if n and n not in names:
                names.append(n)
        if names:
            out[well] = names
    return out


title_text = _common.title_text


def text_content(visual):
    """The words a textbox or button actually shows -- a far better name than
    "Text box"."""
    for card in (visual.get("objects") or {}).get("general") or []:
        if not isinstance(card, dict):
            continue
        for para in ((card.get("properties") or {}).get("paragraphs") or []):
            if not isinstance(para, dict):
                continue
            runs = [r.get("value") for r in (para.get("textRuns") or [])
                    if isinstance(r, dict) and isinstance(r.get("value"), str)]
            text = re.sub(r"\s+", " ", " ".join(runs)).strip()
            if text:
                # first non-empty paragraph only -- the heading, not heading+subtitle
                return text[:45].rstrip()
    return None


def derive(visual, lang):
    vtype = visual.get("visualType", "")
    lab = label(vtype, lang)
    if vtype in ("textbox", "shape", "actionButton", "basicShape", "image"):
        t = text_content(visual)
        if t:
            return f"{t} — {lab}"
    wells = field_names(visual)
    if "slicer" in vtype.lower():
        f = (wells.get("Values") or wells.get("Data") or [""])[0]
        return f"{SLICER[lang]}: {f}" if f else SLICER[lang]
    dims = wells.get("Category") or wells.get("Rows") or wells.get("Group") or []
    vals = wells.get("Values") or wells.get("Y") or wells.get("Data") or []
    if vals and dims:
        head = ", ".join(vals[:2])
        return f"{head} {BY[lang]} {dims[0]} — {lab}"
    if vals:
        return f"{', '.join(vals[:3])} — {lab}"
    if dims:
        return f"{', '.join(dims[:2])} — {lab}"
    return lab.capitalize()


def title_block(name, indent):
    """The title card as text, indented to sit inside `visual`."""
    esc = name.replace("\\", "\\\\").replace('"', '\\"')
    i = " " * indent
    return (
        f'{i}"visualContainerObjects": {{\n'
        f'{i}  "title": [\n'
        f'{i}    {{\n'
        f'{i}      "properties": {{\n'
        f'{i}        "text": {{\n'
        f'{i}          "expr": {{\n'
        f'{i}            "Literal": {{\n'
        f'{i}              "Value": "\'{esc}\'"\n'
        f'{i}            }}\n'
        f'{i}          }}\n'
        f'{i}        }},\n'
        f'{i}        "show": {{\n'
        f'{i}          "expr": {{\n'
        f'{i}            "Literal": {{\n'
        f'{i}              "Value": "false"\n'
        f'{i}            }}\n'
        f'{i}          }}\n'
        f'{i}        }}\n'
        f'{i}      }}\n'
        f'{i}    }}\n'
        f'{i}  ]\n'
        f'{i}}},\n'
    )


FLOAT = re.compile(r'-?\d+\.\d+(?:[eE][+-]?\d+)?')


def mask_floats(text):
    """Swap every float literal for a unique string placeholder.

    Desktop writes floats with more digits than Python's shortest repr
    (78.553615960099748 -> 78.55361596009975), so a plain JSON round-trip would
    silently rewrite them across the whole file. Masking them keeps the document
    byte-identical apart from the edit we actually intend."""
    out, mapping, i, n, in_str, esc = [], {}, 0, len(text), False, False
    buf = []
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        m = FLOAT.match(text, i)
        if m:
            key = f"@@F{len(mapping)}@@"
            mapping[key] = m.group(0)
            out.append(f'"{key}"')
            i = m.end()
            continue
        out.append(ch)
        i += 1
    return "".join(out), mapping


def unmask_floats(text, mapping):
    for key, lit in mapping.items():
        text = text.replace(f'"{key}"', lit)
    return text


def set_title(visual, name):
    """Structural edit: add the name, reusing an existing title card if present."""
    vco = visual.setdefault("visualContainerObjects", {})
    cards = vco.get("title")
    if not isinstance(cards, list) or not cards:
        cards = [{}]
        vco["title"] = cards
    props = cards[0].setdefault("properties", {})
    props["text"] = {"expr": {"Literal": {"Value": f"'{name}'"}}}
    props.setdefault("show", {"expr": {"Literal": {"Value": "false"}}})


def main():
    ap = argparse.ArgumentParser(
        prog="name-visuals.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__.split("\n\n")[0] + "\n\n" + __doc__.split("\n\n")[1],
        epilog=(
            "exit codes:\n"
            "  0  ran (dry run or write); the counts say what it did\n"
            "  2  no visual.json found under <root> (wrong directory?)\n\n"
            "Respects .powerbi-scan-ignore."))
    ap.add_argument("root", nargs="?", default=".",
                    help="repo root holding the *.Report directories "
                         "(default: the current directory)")
    ap.add_argument("--apply", action="store_true",
                    help="write the names; default is a dry run")
    ap.add_argument("--lang", default="en", choices=["cs", "en"],
                    help="language of the generated names (default: en)")
    ap.add_argument("--upgrade-generic", action="store_true",
                    help="also replace names that are just a bare type label")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    _common.load_ignore(root)

    files = _common.visual_json_files(root)
    if not files:
        print(f"no visuals found under {root}")
        return 2

    named = skipped_fmt = already = 0
    samples = []
    for f in files:
        text, nl = _common.read_text(f)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            skipped_fmt += 1
            continue

        visual = obj.get("visual")
        if not visual or not visual.get("visualType"):
            continue
        current = title_text(visual)
        if current:
            # Generic names must be recognized in the language they were written
            # in, or --upgrade-generic never matches anything.
            keys = TYPES.get(a.lang) or TYPES["cs"]
            generic = {label(t, a.lang).capitalize() for t in keys} | {SLICER[a.lang]}
            if not (a.upgrade_generic and current in generic):
                already += 1
                continue
        name = derive(visual, a.lang)
        if not name or name == current:
            already += 1
            continue

        flat = text.replace("\r\n", "\n")
        masked, fmap = mask_floats(flat)
        try:
            mobj = json.loads(masked)
        except json.JSONDecodeError:
            skipped_fmt += 1
            continue
        trailing = "\n" if flat.endswith("\n") else ""
        if json.dumps(mobj, ensure_ascii=False, indent=2) + trailing != masked:
            skipped_fmt += 1      # formatting we cannot reproduce -- hands off
            continue
        set_title(mobj["visual"], name)
        updated = unmask_floats(
            json.dumps(mobj, ensure_ascii=False, indent=2) + trailing, fmap)
        try:
            back = json.loads(updated)
        except json.JSONDecodeError:
            skipped_fmt += 1
            continue
        if title_text(back.get("visual", {})) != name:
            skipped_fmt += 1
            continue
        named += 1
        if len(samples) < 25:
            samples.append((visual.get("visualType"), name))
        if a.apply:
            if nl == "\r\n":
                updated = updated.replace("\n", "\r\n")
            _common.write_text(f, updated)

    print(f"{len(files)} visuals; {already} already named, {skipped_fmt} skipped (unsupported shape)")
    print(f"{'named' if a.apply else 'would name'} {named}\n")
    for vt, n in samples:
        print(f"  {vt:<26} {n}")
    if named and not a.apply:
        print("\nDry run. Re-run with --apply, then check `git diff --stat`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
