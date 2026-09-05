#!/usr/bin/env python3
"""Append the measure's own DAX to its `///` description, after a `---` separator.

A thin report cannot see the model's definitions, so the description is the only
place a report author ever sees the formula. That half of the description is
purely mechanical -- the DAX is right there in the measure -- so this fills it in.

    python3 backfill-dax-blocks.py <repo-or-model> [--apply] [--format]

Dry run by default: prints what it would change. --apply writes the files.
--format runs the DAX through `te format` first (short lines, the te default).

It never touches the prose half, never overwrites an existing `---` block, and
skips measures that have no description at all -- writing a DAX block with no
explanation above it would just be noise. Write the prose first, then re-run.

Respects .powerbi-scan-ignore and skips worktrees/vendor dirs.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

MEASURE = _common.MEASURE_FULL

# How many expressions `te format` choked on this run. Silently handing back the
# unformatted DAX is what made --format look like it worked when it did not.
_FORMAT_FAILURES = []


def format_dax(expr):
    """Format via `te format -e` (short lines by default).

    Falls back to the input on failure, but records the miss so main() can say
    out loud how many expressions were written unformatted."""
    try:
        r = subprocess.run(["te", "format", "-e", expr, "--non-interactive"],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        out = "\n".join(l for l in r.stdout.splitlines()
                        if l.strip() and not l.startswith("Warning:"))
        if not out.strip():
            _FORMAT_FAILURES.append((expr, (r.stderr or "").strip()[:120] or "no output"))
            return expr.strip()
        return out.strip()
    except Exception as exc:
        _FORMAT_FAILURES.append((expr, f"{type(exc).__name__}: {exc}"))
        return expr.strip()


def measure_blocks(lines):
    """Yield (start_of_description, measure_line_index, indent, name, expr_lines)."""
    for i, line in enumerate(lines):
        m = MEASURE.match(line)
        if not m:
            continue
        indent, name, rest = m.group(1), m.group(3) or m.group(2), m.group(4)
        j = i - 1
        while j >= 0 and lines[j].strip().startswith("///"):
            j -= 1
        desc_start = j + 1
        if desc_start == i:
            continue  # no description at all -- prose comes first, skip
        # collect the expression: rest of the line, plus deeper-indented lines
        expr = [rest.strip()] if rest.strip() else []
        k = i + 1
        while k < len(lines):
            nxt = lines[k]
            if not nxt.strip():
                expr.append("")
                k += 1
                continue
            cur = len(nxt) - len(nxt.lstrip())
            if cur <= len(indent):
                break
            if re.match(r"\s*(formatString|lineageTag|displayFolder|isHidden|"
                        r"formatStringDefinition|annotation|changedProperty|"
                        r"dataType|sourceLineageTag)\b", nxt):
                break
            expr.append(nxt.strip())
            k += 1
        yield desc_start, i, indent, name, expr


def process(path, apply_changes, do_format):
    text, newline = _common.read_text(path)
    lines = text.replace("\r\n", "\n").split("\n")
    edits = []
    for desc_start, mi, indent, name, expr in measure_blocks(lines):
        desc = [lines[x].strip()[3:].strip() for x in range(desc_start, mi)]
        if any(d.strip() == "---" for d in desc):
            continue  # already has a DAX block
        dax = "\n".join(expr).strip()
        if not dax:
            continue
        if do_format:
            dax = format_dax(dax)
        block = [f"{indent}/// ", f"{indent}/// ---", f"{indent}/// "]
        block += [f"{indent}/// {l}".rstrip() for l in dax.split("\n")]
        edits.append((mi, block, name))
    if not edits:
        return 0
    for mi, block, _name in sorted(edits, key=lambda e: -e[0]):
        lines[mi:mi] = block
    if apply_changes:
        _common.write_text(path, newline.join(lines))
    return len(edits)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="backfill-dax-blocks.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__.split("\n\n")[0] + "\n\n" + __doc__.split("\n\n")[1],
        epilog=(
            "It never touches the prose half of a description, never overwrites an\n"
            "existing `---` block, and skips measures with no description at all --\n"
            "a DAX block with no explanation above it is just noise.\n\n"
            "exit codes:\n"
            "  0  ran (dry run or write); the counts say what it did\n"
            "  2  nothing to do: no model tables under <root>, or --format was\n"
            "     asked for without the Tabular Editor CLI on PATH\n\n"
            "Respects .powerbi-scan-ignore and skips worktrees and vendor dirs."))
    ap.add_argument("root", nargs="?", default=".",
                    help="repo or model root to scan (default: the current directory)")
    ap.add_argument("--apply", action="store_true",
                    help="write the files; default is a dry run")
    ap.add_argument("--format", action="store_true",
                    help="run each expression through `te format` first "
                         "(requires the Tabular Editor CLI on PATH)")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)

    if a.format and not shutil.which("te"):
        print("--format requires the Tabular Editor CLI ('te') on PATH; "
              "drop --format or install it (preflight.py says how).",
              file=sys.stderr)
        return 2

    _common.load_ignore(root)

    files = _common.model_table_files(root)
    if not files:
        print(f"no model tables found under {root}")
        return 2

    total = 0
    for f in files:
        n = process(f, a.apply, a.format)
        if n:
            total += n
            print(f"  {n:>4}  {os.path.relpath(f, root)}")
    verb = "added" if a.apply else "would add"
    print(f"\n{verb} a --- DAX block to {total} measure(s) in {len(files)} table file(s)")
    if _FORMAT_FAILURES:
        print(f"WARNING  `te format` failed on {len(_FORMAT_FAILURES)} expression(s); "
              "those were written unformatted.")
        for _expr, why in _FORMAT_FAILURES[:3]:
            print(f"           {why}")
        if len(_FORMAT_FAILURES) > 3:
            print(f"           ... and {len(_FORMAT_FAILURES) - 3} more")
        # When every single expression failed, the DAX is rarely the problem.
        # The tested `te` is an early preview build that stops running on a
        # fixed date, and an expired one fails exactly like this.
        print("           If they all failed: the Tabular Editor build may be an "
              "expired early")
        print("           preview -- run preflight.py, and download a newer build "
              "from")
        print("           https://tabulareditor.com/downloads if so.")
    if total and not a.apply:
        print("Dry run. Re-run with --apply to write, and check `git diff --stat`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
