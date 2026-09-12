#!/usr/bin/env python3
"""Track the fix status of DAX Optimizer issues alongside their report.

`daxopt-report.py` writes one immutable Markdown report per analysis run;
`daxopt-select.py` (this skill's other script) reads one back into a list of
issues. Neither keeps track of what a human or a fix pass actually *did*
about any of those issues across sessions -- that is this script's only
job. It keeps one small Markdown file per report, named
`<report>_fixes.md`, with one row per issue number: its status (proposed,
fixed, skipped, ignored, reverted), the result of an equivalence check
between the before/after DAX (`Verified`), an optional commit sha, and a
free-text note.

The fingerprint column is the important one for anything past a single
session: DAX Optimizer's `fingerprint` (per recommendation) and
`daxFingerprint` (per measure) are stable across re-analyses of the *same*
model, unlike the issue's number, which is only that run's rank by
relevance and will shift the moment any weight changes. A later report from
the same model is matched against this fix log by fingerprint, not by
issue number -- numbers are just how a human addresses an issue on the
command line.

Usage:
    python3 daxopt-fixlog.py REPORT set 3,7 --status fixed \\
        [--verified equal|differs|not-run] [--commit <sha>] [--note "..."]
    python3 daxopt-fixlog.py REPORT show [--status fixed]

    REPORT           the report .md this fix log tracks (its fix log lives
                      at "<report without .md>_fixes.md" next to it)
    set ISSUES       upsert one row per issue number/range (e.g. "3,7,12-15")
                      in the report; measure, rule and fingerprint are
                      (re)read from the report every time, --status is
                      required, and any of --verified/--commit/--note left
                      unset keeps that row's previous value (or blank, for a
                      new row)
    show             print the current table, optionally filtered by
                      --status

Fields not given on the command line are preserved across `set` calls, rows
stay sorted by issue number, and the file is byte-identical between two runs
that pass the same arguments -- safe to run the same `set` twice, and easy
to diff in a PR.

Exit codes:
    0  ok
    2  the report was not found, does not parse (see daxopt-select.py), or
       an issue number given to `set` is not in the report

This script only reads the report and reads/writes its one fix-log file; it
never touches the semantic model, TMDL or the report itself. Standard
library only.
"""
import argparse
import importlib.util
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# daxopt-select.py's file name has a hyphen, so it cannot be `import`ed by
# name; load it explicitly from its path instead. This is what gives us
# parse_report, ReportError, parse_int_ranges, split_row and
# md_escape_cell -- the exact same report parser daxopt-select.py uses, so
# a fix log always agrees with `daxopt-select.py REPORT` about what issue #7
# even is.
_spec = importlib.util.spec_from_file_location(
    "daxopt_select", os.path.join(_HERE, "daxopt-select.py"))
daxopt_select = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(daxopt_select)


def force_utf8_stdout():
    """Print UTF-8 whatever the console claims to be (see daxopt-select.py
    for why -- measure/rule names can carry non-ASCII characters)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


force_utf8_stdout()


STATUSES = ("proposed", "fixed", "skipped", "ignored", "reverted")
VERIFIED_VALUES = ("equal", "differs", "not-run")

ROW_FIELDS = ("measure", "rule", "fingerprint", "status", "verified", "commit", "note")


# --------------------------------------------------------------------------- #
# fix-log file: path, parse, render
# --------------------------------------------------------------------------- #

def fixlog_path(report_path):
    """"docs/dax-optimizer/2026-01-05_1420_sales.md" ->
    "docs/dax-optimizer/2026-01-05_1420_sales_fixes.md"."""
    base, _ext = os.path.splitext(report_path)
    return base + "_fixes.md"


def parse_fix_log(path):
    """-> {issue number: {"measure", "rule", "fingerprint", "status",
    "verified", "commit", "note"}}. {} if the file does not exist yet."""
    rows = {}
    if not os.path.isfile(path):
        return rows
    with io.open(path, encoding="utf-8-sig") as fh:
        lines = fh.read().split("\n")
    in_table = False
    for line in lines:
        if line.startswith("|---"):
            in_table = True
            continue
        if not in_table or not line.strip().startswith("|"):
            continue
        cells = daxopt_select.split_row(line)
        if len(cells) < 1 + len(ROW_FIELDS):
            continue
        try:
            num = int(cells[0])
        except ValueError:
            continue
        rows[num] = dict(zip(ROW_FIELDS, cells[1:1 + len(ROW_FIELDS)]))
    return rows


def render_fix_log(report_name, rows):
    esc = daxopt_select.md_escape_cell
    out = []
    out.append("# Fix log — " + report_name)
    out.append("")
    out.append("Statuses: proposed | fixed | skipped | ignored | reverted. "
                "`Verified` is the result of the before/after comparison "
                "(equal | differs | not run).")
    out.append("")
    out.append("| # | Measure | Rule | Issue fingerprint | Status | Verified | Commit | Note |")
    out.append("|---:|---|---|---|---|---|---|---|")
    for num in sorted(rows):
        row = rows[num]
        out.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
            num,
            esc(row.get("measure", "")),
            esc(row.get("rule", "")),
            esc(row.get("fingerprint", "")),
            esc(row.get("status", "")),
            esc(row.get("verified", "")),
            esc(row.get("commit", "")),
            esc(row.get("note", ""))))
    return "\n".join(out) + "\n"


def rule_cell(issue):
    """"[<docId> <title>](<url>)" -- same shape daxopt-report.py links a
    rule with elsewhere in the report."""
    return "[{0} {1}]({2})".format(
        issue.get("rule_doc_id") or "", issue.get("rule_title") or "",
        issue.get("rule_kb") or "")


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def cmd_set(args):
    if not os.path.isfile(args.report):
        print("error: report not found: {0}".format(args.report), file=sys.stderr)
        return 2
    with io.open(args.report, encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        issues = daxopt_select.parse_report(text)
    except daxopt_select.ReportError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2
    issues_by_num = {i["number"]: i for i in issues}

    try:
        numbers = daxopt_select.parse_int_ranges(args.issues)
    except ValueError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2

    missing = sorted(n for n in numbers if n not in issues_by_num)
    if missing:
        print("error: issue number(s) not in report: {0}".format(
            ", ".join(str(n) for n in missing)), file=sys.stderr)
        return 2

    path = fixlog_path(args.report)
    rows = parse_fix_log(path)

    for num in numbers:
        issue = issues_by_num[num]
        existing = rows.get(num, {})
        rows[num] = {
            "measure": issue["measure"],
            "rule": rule_cell(issue),
            "fingerprint": issue.get("issue_fingerprint") or "",
            "status": args.status,
            "verified": args.verified if args.verified is not None else existing.get("verified", ""),
            "commit": args.commit if args.commit is not None else existing.get("commit", ""),
            "note": args.note if args.note is not None else existing.get("note", ""),
        }

    content = render_fix_log(os.path.basename(args.report), rows)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    print("{0}: {1} row(s)".format(path, len(rows)), file=sys.stderr)
    return 0


def cmd_show(args):
    path = fixlog_path(args.report)
    rows = parse_fix_log(path)
    if args.status:
        rows = {n: r for n, r in rows.items() if r.get("status") == args.status}
    sys.stdout.write(render_fix_log(os.path.basename(args.report), rows))
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    ap = argparse.ArgumentParser(
        prog="daxopt-fixlog.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Record and show the fix status of DAX Optimizer issues from a "
            "report written by daxopt-report.py, in a small Markdown file "
            "next to it (<report>_fixes.md)."),
        epilog=(
            "exit codes:\n"
            "  0  ok\n"
            "  2  report not found/unparsable, or an issue number is not in it\n"))
    ap.add_argument("report", help="the DAX Optimizer report .md this fix log tracks")
    sub = ap.add_subparsers(dest="command", required=True)

    set_p = sub.add_parser("set", help="upsert fix-log rows for one or more issue numbers")
    set_p.add_argument("issues", help="issue numbers/ranges, e.g. 3,7,12-15")
    set_p.add_argument("--status", required=True, choices=STATUSES)
    set_p.add_argument("--verified", choices=VERIFIED_VALUES,
                        help="leave unset to keep the row's previous value")
    set_p.add_argument("--commit", help="leave unset to keep the row's previous value")
    set_p.add_argument("--note", help="leave unset to keep the row's previous value")
    set_p.set_defaults(func=cmd_set)

    show_p = sub.add_parser("show", help="print the fix log table")
    show_p.add_argument("--status", choices=STATUSES, help="show only rows with this status")
    show_p.set_defaults(func=cmd_show)

    return ap


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
