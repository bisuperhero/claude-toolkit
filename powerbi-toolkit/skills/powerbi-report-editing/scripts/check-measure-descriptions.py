#!/usr/bin/env python3
"""Report measure-description coverage and anti-patterns in a TMDL model.

A `///` block above a measure is its Data-pane tooltip, and it has two parts:
prose saying what the measure MEANS, then the DAX after a `---` separator. The
DAX block matters because a thin report cannot see the model's definitions at
all -- the description is the only place the formula is visible.

    python3 <skill>/scripts/check-measure-descriptions.py [root] [--list]

Skips dead copies of the model tree -- .claude/worktrees, node_modules, .git,
__pycache__, .venv -- so an old git worktree under the repo is not scanned
alongside the real tree.

Advisory: coverage is a project decision, so this reports rather than gates --
doctor.py lists it as backlog, never as a blocking failure.
"""
import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

MEASURE = _common.MEASURE_HEAD
# Deliberately bilingual: these models were written in a mix of English and
# Czech, and a boilerplate opener is just as dead in either language.
BOILER = re.compile(r"^(this measure|shows |displays |zobrazuje |ukazuje |tato míra|tahle míra)", re.I)
LONG = 160


def split_desc(text):
    """-> (prose, dax). The DAX block follows a line that is just `---`."""
    parts = re.split(r"(?:^|\s)---(?:\s|$)", text, maxsplit=1)
    prose = parts[0].strip()
    dax = parts[1].strip() if len(parts) > 1 else ""
    return prose, dax


def scan(root):
    rows = []
    for f in _common.model_table_files(root):
        try:
            lines = io.open(f, encoding="utf-8-sig").read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            m = MEASURE.match(line)
            if not m:
                continue
            desc, j = [], i - 1
            while j >= 0 and lines[j].strip().startswith("///"):
                desc.insert(0, lines[j].strip()[3:].strip())
                j -= 1
            rows.append((f, i + 1, m.group(2) or m.group(1), " ".join(desc).strip()))
    return rows


def build_parser():
    ap = argparse.ArgumentParser(
        prog="check-measure-descriptions.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Report measure-description coverage and anti-patterns in the TMDL\n"
            "models under <root>. A `///` block above a measure is its Data-pane\n"
            "tooltip and has two halves: prose saying what the measure MEANS, then\n"
            "its DAX after a `---` separator. The DAX half matters because a thin\n"
            "report cannot see the model's definitions -- the description is the\n"
            "only place a report author ever sees the formula.\n\n"
            "It counts measures with no description, with no `---` DAX block, with\n"
            "a boilerplate opener, and with prose over %d characters. It reads\n"
            "only; backfill-dax-blocks.py writes the DAX halves." % LONG),
        epilog=(
            "exit codes:\n"
            "  0  every measure has a description, a DAX block and readable prose\n"
            "  1  findings to work through -- backlog, never blocking (doctor.py\n"
            "     lists them under 'Backlog (not blocking)')\n"
            "  2  no measures found under <root> (wrong directory?)\n\n"
            "Respects .powerbi-scan-ignore and skips worktrees, node_modules, .git,\n"
            "__pycache__ and .venv."))
    ap.add_argument("root", nargs="?", default=".",
                    help="repo or model root to scan (default: the current directory)")
    ap.add_argument("--list", dest="show", action="store_true",
                    help="list every offending measure, not just the counts")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    show = args.show
    root = os.path.abspath(args.root)
    _common.load_ignore(root)

    rows = scan(root)
    if not rows:
        print(f"no measures found under {root} -- wrong directory?")
        return 2

    missing = [r for r in rows if not r[3]]
    described = [r for r in rows if r[3]]
    split = {r[:3]: split_desc(r[3]) for r in described}
    no_dax = [r for r in described if not split[r[:3]][1]]
    boiler = [r for r in described if BOILER.match(split[r[:3]][0])]
    long_ = [r for r in described if len(split[r[:3]][0]) > LONG]
    lens = sorted(len(split[r[:3]][0]) for r in described)

    n = len(rows)
    print(f"{n} measures, {len(described)} described ({100 * len(described) // n}%)")
    if lens:
        print(f"prose length: median {lens[len(lens) // 2]}, max {lens[-1]} characters "
              f"(the --- DAX block is not counted)")
    print()
    print(f"  {len(missing):>5}  no description")
    print(f"  {len(no_dax):>5}  no `---` DAX block -- a thin report cannot see the formula any other way")
    print(f"  {len(boiler):>5}  boilerplate opener ('This measure shows...') -- start with the thing")
    print(f"  {len(long_):>5}  prose longer than {LONG} characters")

    findings = missing or no_dax or boiler or long_
    if show:
        for label, group in (("MISSING", missing), ("NO-DAX-BLOCK", no_dax),
                             ("BOILERPLATE", boiler), ("TOO-LONG", long_)):
            for f, ln, name, d in group:
                where = f"{os.path.relpath(f, root)}:{ln}"
                print(f"  {label:<12} {where}  {name}" + (f"  -- {d[:70]}" if d else ""))
    elif findings:
        print("\nRe-run with --list to see which measures.")
    # 1 is backlog, not breakage -- doctor.py lists this check as a note. Before
    # this it always returned 0, so doctor could never surface these at all.
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
