#!/usr/bin/env python3
"""Catch un-doubled quotes in SQL embedded in TMDL M partitions.

SQL passed to Value.NativeQuery lives inside an M string, so every quote in the
SQL must be doubled (""). A single un-doubled quote makes Power BI Desktop refuse
to open the WHOLE project:

    There's a problem with the definition content in your Power BI Project.
    M Engine error: 'Microsoft.Data.Mashup.Preview; Token ',' expected.'

Nothing else catches this: `te load` parses TMDL without validating M,
`te format --lang m` is lenient and hands out false greens, a naive quote-balance
check passes because quotes cancel in pairs, and `powerbi-report-author validate`
only looks at the report.

How this checks it: scan the M string with M's own rule -- "" is an escaped quote,
a lone " ends the string -- and then look at what follows the closing quote. In a
correct call the next non-blank character is `,` or `)`. An un-doubled quote ends
the string early, so something else follows, which is exactly where the M parser
gives up.

    python3 <skill>/scripts/check-m-escaping.py [root]

Skips dead copies of the model tree -- .claude/worktrees, node_modules, .git,
__pycache__, .venv -- so an old git worktree under the repo is not scanned
alongside the real tree. Respects .powerbi-scan-ignore.

Exits 1 when a partition is broken, 0 when clean, 2 when nothing was found.
"""
import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

CALL = "Value.NativeQuery"


def _scan_string(text, start):
    """Walk an M string literal opening at text[start] == '"'.

    Returns (payload, index just past the closing quote), or (None, None) when
    the string is never closed.
    """
    i = start + 1
    out = []
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            if i + 1 < n and text[i + 1] == '"':
                out.append('"')
                i += 2
                continue
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    return None, None


def check_text(text):
    """Yield (line_no, following_excerpt, payload_excerpt) per broken call."""
    pos = 0
    while True:
        call = text.find(CALL, pos)
        if call == -1:
            return
        pos = call + len(CALL)
        quote = text.find('"', call)
        if quote == -1:
            return
        payload, end = _scan_string(text, quote)
        if payload is None:
            yield (text.count("\n", 0, quote) + 1, "<unterminated string>", "")
            return
        rest = text[end:]
        nxt = rest.lstrip()
        if nxt[:1] not in (",", ")"):
            line = text.count("\n", 0, end) + 1
            yield (
                line,
                " ".join(nxt.split())[:60],
                " ".join(payload.split())[-60:],
            )
        pos = end


def build_parser():
    ap = argparse.ArgumentParser(
        prog="check-m-escaping.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Catch un-doubled quotes in SQL embedded in TMDL M partitions.\n\n"
            "SQL handed to Value.NativeQuery sits inside an M string, so every\n"
            "quote in it must be doubled (\"\"). One un-doubled quote makes Power BI\n"
            "Desktop refuse to open the whole project, and nothing else in the\n"
            "toolchain reports it. This scans every .tmdl under <root> and flags\n"
            "each Value.NativeQuery whose string ends somewhere other than at a\n"
            "`,` or `)`."),
        epilog=(
            "exit codes:\n"
            "  0  every Value.NativeQuery call scanned is correctly escaped\n"
            "  1  at least one M string ends early -- Desktop will not open the project\n"
            "  2  no .tmdl files found under <root> (nothing to check -- wrong directory?)\n\n"
            "Respects .powerbi-scan-ignore and skips worktrees, node_modules, .git,\n"
            "__pycache__ and .venv."))
    ap.add_argument("root", nargs="?", default=".",
                    help="repo or model root to scan (default: the current directory)")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = args.root
    _common.load_ignore(root)
    files = sorted(_common.tmdl_glob(root, "**"))
    files = [f for f in files if not _common.is_excluded(f)]
    if not files:
        print(f"no .tmdl files found under {root!r} -- wrong directory?")
        return 2

    errors = []
    checked = 0
    for f in files:
        try:
            text = io.open(f, encoding="utf-8-sig").read()
        except OSError as exc:
            errors.append(f"{f}: cannot read ({exc})")
            continue
        if CALL not in text:
            continue
        checked += 1
        for line, following, payload in check_text(text):
            errors.append(
                f"{f}:{line}: M string ends early -- an un-doubled quote in the SQL.\n"
                f"         string ended after: ...{payload}\n"
                f"         followed by       : {following}"
            )

    for e in errors:
        print(f"ERROR  {e}")
    print(
        f"\n{len(files)} tmdl files scanned, {checked} with {CALL} "
        f"-- {len(errors)} errors"
    )
    if errors:
        print('Double every quote inside the SQL: z.d AS ""Date""')
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
