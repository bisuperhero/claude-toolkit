#!/usr/bin/env python3
"""Pick issues out of a DAX Optimizer Markdown report for a fix pass.

`daxopt-report.py` (the sibling `dax-optimizer-report` skill) turns a DAX
Optimizer analysis into one Markdown report per run, with issues numbered
1..N in section "1. Issues by relevance", the same issues written out in
full in section "3. Issues" (rule, flagged expression, full DAX, TMDL
definition), and a "5. Technical" table carrying the stable fingerprints and
character spans that survive a later re-analysis of the same model. This
script re-parses that Markdown -- the report is the only artifact a fix pass
has to go on, there is no side-channel JSON -- filters it down to the
issues someone actually wants to work on, and prints them as data (JSON by
default, or a compact Markdown plan) instead of a human skimming a
five-section report by hand.

It is deliberately dumb about *how* to fix anything: it only locates and
filters. The companion `daxopt-fixlog.py` uses the same parser (imported
from this file, see below) to look up an issue's measure/rule/fingerprint
when recording that a fix was applied.

Parsing approach: the report format is fixed by `daxopt-report.py`
(`render_report`), so this reads it structurally --
  - section 1's table gives, per issue number: measure, rule title,
    relevance, kind (CPU/materialization/both), reach, and the rule's KB
    link (hence its docId);
  - section 3's per-issue write-up (`### N. `measure` -- rule title`) gives
    the flagged expression, the full DAX (its own ```dax block, or resolved
    through "Full DAX: see issue #n"), and the TMDL definition line if the
    report was rendered with --model;
  - section 5's table gives the issue/measure fingerprints, the node name
    and the character span.
The three sections are cross-checked by issue number; a mismatch (missing
section 5, or section 1 and 5 disagreeing on how many issues there are)
means the report is truncated or hand-edited, and this script refuses to
guess.

Usage:
    python3 daxopt-select.py [REPORT] [--dir docs/dax-optimizer] \\
        [--issues 3,7,12-15] [--rules 100200,103000] \\
        [--measure "<substring>"] [--format json|md] \\
        [--model <path>.SemanticModel]

    REPORT            a report file to read. Omitted: the newest `*.md` in
                       --dir (by file name -- report names start with the
                       run's timestamp, so this is the latest run), skipping
                       any `*_fixes.md` fix log. A bare word (no "/", no
                       ".md", not an existing file) is instead taken as a
                       slug filter: the newest report in --dir whose file
                       name contains it. Which report was picked is always
                       printed to stderr.
    --dir DIR          folder to search when REPORT is omitted or a slug
                       (default: docs/dax-optimizer)
    --issues SPEC      issue numbers to keep, e.g. "3,7,12-15"
    --rules SPEC       rule docIds to keep, e.g. "100200,103000"
    --measure TEXT     keep only issues whose measure name contains TEXT
                       (case-insensitive substring)
                       Filters combine as an intersection; no filter given
                       at all keeps every issue in the report.
    --format FORMAT    "json" (default): {"report", "run", "issues": [...]}
                       sorted by issue number. "md": a compact plan table
                       (# | Measure | Rule | Relevance | Definition),
                       grouped under one "### <docId> <title>" heading per
                       rule, for pasting into a plan.
    --model PATH       a *.SemanticModel folder (or its tables folder) to
                       resolve TMDL definitions for issues whose report has
                       no "- Definition:" line (i.e. it was rendered without
                       --model) -- same lookup `daxopt-report.py` uses.

Exit codes:
    0  ok, the (filtered) issue list is non-empty
    1  the filters matched nothing -- stdout still carries valid JSON (or
       an empty Markdown plan)
    2  the report could not be found or does not parse structurally
       (missing section 5, or section 1 / section 5 issue counts disagree)

This script only reads the report (and, with --model, TMDL files to resolve
definitions); it never writes anything. Standard library only.
"""
import argparse
import glob
import io
import json
import os
import re
import sys


def force_utf8_stdout():
    """Print UTF-8 whatever the console claims to be.

    Measure names and rule titles come straight from the report (em dashes,
    Ʃ/Δ/Ø and whatever else a modeler called their measures); on a Windows
    console defaulting to cp1252 that is a hard UnicodeEncodeError.
    `reconfigure` exists from Python 3.7 on -- older interpreters and
    replaced streams just keep theirs.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


force_utf8_stdout()


class ReportError(Exception):
    """The report file is missing, or does not parse structurally."""


# --------------------------------------------------------------------------- #
# --model: locating each measure's TMDL definition (copy of daxopt-report.py's
# find_measure_definitions -- kept in sync by hand, not imported, so this
# script has no import-time dependency on the sibling skill's script)
# --------------------------------------------------------------------------- #

MEASURE_PATTERN = re.compile(r"^\s*measure\s+('([^']+)'|(\S+?))\s*=")


def _tmdl_files(tables_dir):
    """*.tmdl in tables_dir, including dot-prefixed ones (glob() never
    matches a leading dot, and a model's measure-holding table is commonly
    named `.Measures.tmdl`)."""
    return sorted(
        glob.glob(os.path.join(tables_dir, "*.tmdl"))
        + glob.glob(os.path.join(tables_dir, ".*.tmdl")))


def find_measure_definitions(model_dir):
    """-> {measure name: "path/relative/to/model:line"} for every `measure
    NAME =` declaration under model_dir. Looks under definition/tables first
    (PBIP TMDL layout), falling back to tables/ if that does not exist.
    """
    tables_dir = os.path.join(model_dir, "definition", "tables")
    if not os.path.isdir(tables_dir):
        tables_dir = os.path.join(model_dir, "tables")
    result = {}
    if not os.path.isdir(tables_dir):
        return result
    for path in _tmdl_files(tables_dir):
        try:
            with io.open(path, encoding="utf-8-sig", newline="") as fh:
                text = fh.read()
        except OSError:
            continue
        lines = text.replace("\r\n", "\n").split("\n")
        rel = os.path.relpath(path, model_dir).replace(os.sep, "/")
        for lineno, line in enumerate(lines, start=1):
            m = MEASURE_PATTERN.match(line)
            if not m:
                continue
            name = m.group(2) if m.group(2) is not None else m.group(3)
            result.setdefault(name, "{0}:{1}".format(rel, lineno))
    return result


# --------------------------------------------------------------------------- #
# report discovery
# --------------------------------------------------------------------------- #

def find_newest_report(directory, slug=None):
    """-> path of the newest `*.md` in `directory` (by file name -- report
    names are `<YYYY-MM-DD_HHMM>_<slug>.md`, so lexicographic order is
    chronological order), skipping `*_fixes.md`. `slug`, if given, is a
    case-insensitive substring the file name must contain. None if nothing
    matches or the directory does not exist.
    """
    if not os.path.isdir(directory):
        return None
    candidates = []
    for name in os.listdir(directory):
        if not name.endswith(".md") or name.endswith("_fixes.md"):
            continue
        if slug and slug.lower() not in name.lower():
            continue
        candidates.append(name)
    if not candidates:
        return None
    candidates.sort()
    return os.path.join(directory, candidates[-1])


def resolve_report(report_arg, directory):
    """-> path to the report to read, per the REPORT / --dir rules in the
    module docstring. Raises ReportError if nothing matches.
    """
    if report_arg:
        looks_like_path = (
            "/" in report_arg or "\\" in report_arg
            or report_arg.endswith(".md") or os.path.isfile(report_arg))
        if looks_like_path:
            if not os.path.isfile(report_arg):
                raise ReportError("report not found: {0}".format(report_arg))
            path = report_arg
        else:
            path = find_newest_report(directory, slug=report_arg)
            if path is None:
                raise ReportError(
                    "no report matching slug {0!r} found in {1}".format(
                        report_arg, directory))
    else:
        path = find_newest_report(directory)
        if path is None:
            raise ReportError("no report (*.md) found in {0}".format(directory))
    return path


RUN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{4})_")


def extract_run(basename):
    """-> the run timestamp encoded in a report's file name, or "" if the
    file was not named by daxopt-report.py's convention."""
    m = RUN_RE.match(basename)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- #
# Markdown table parsing
# --------------------------------------------------------------------------- #

SEPARATOR_ROW_RE = re.compile(r"^\|?[\s:|\-]+\|?$")
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def split_row(line):
    """One `| a | b\\|c | d |` table row -> ["a", "b|c", "d"], reversing the
    "|" -> "\\|" escaping `daxopt-report.py`'s render_table applies."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [cell.strip().replace("\\|", "|") for cell in _UNESCAPED_PIPE_RE.split(line)]


def md_escape_cell(text):
    """Escape the one character that would break a Markdown table cell --
    same rule `daxopt-report.py` writes with."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def parse_table_in_lines(lines):
    """-> (header cells, [row cells, ...]) for the first Markdown table
    found in `lines` -- located by scanning for a "|"-led line immediately
    followed by a separator row ("|---|---|..."), so leading prose/bullets
    (section 5 has both before its table) are skipped rather than
    mistaken for the header. (None, []) if no table is found (a "No issues
    found." section, most commonly).
    """
    n = len(lines)
    for idx in range(n):
        line = lines[idx].strip()
        if not line.startswith("|"):
            continue
        if idx + 1 < n and SEPARATOR_ROW_RE.match(lines[idx + 1].strip()):
            header = split_row(lines[idx])
            rows = []
            j = idx + 2
            while j < n and lines[j].strip().startswith("|"):
                rows.append(split_row(lines[j]))
                j += 1
            return header, rows
    return None, []


# --------------------------------------------------------------------------- #
# report parsing
# --------------------------------------------------------------------------- #

SECTION_HEADING_RE = re.compile(r"^## (\d+)\.\s*(.*)$")
ISSUE_HEADING_RE = re.compile(r"^### (\d+)\.\s*`(.*)`\s+\u2014\s+(.*)$")
DEFINITION_LINE_RE = re.compile(r"^- Definition: `(.*)`$")
FULL_DAX_SEE_RE = re.compile(r"^Full DAX: see issue #(\d+)\.$")
SPAN_RE = re.compile(r"^(\d+)-(\d+)$")
REACH_RE = re.compile(r"^(\d+)\s*/\s*(\d+)$")
KB_LINK_RE = re.compile(r"^\[(\S+)\]\((\S+)\)$")

THIN_SPACE = "\u202f"
NOT_FOUND_IN_MODEL = "not found in model"


def _find_sections(lines):
    """-> {section number: (first content line index, index one past the
    section's last line)} for every top-level "## N. Title" heading."""
    heading_idxs = []
    for i, line in enumerate(lines):
        m = SECTION_HEADING_RE.match(line)
        if m:
            heading_idxs.append((i, int(m.group(1))))
    heading_idxs.append((len(lines), None))
    sections = {}
    for k in range(len(heading_idxs) - 1):
        start, num = heading_idxs[k]
        end, _next_num = heading_idxs[k + 1]
        if num is not None:
            sections.setdefault(num, (start + 1, end))
    return sections


def _parse_relevance(text):
    return float(text.replace(THIN_SPACE, ""))


def _extract_fence(lines, start_idx):
    """lines[start_idx] is assumed to be inside a ```dax fence (the opening
    fence line itself already consumed by the caller). -> (fence content
    joined by "\\n", index one past the closing ``` line)."""
    content = []
    i = start_idx
    n = len(lines)
    while i < n and lines[i] != "```":
        content.append(lines[i])
        i += 1
    if i >= n:
        raise ReportError("unterminated ```dax block")
    return "\n".join(content), i + 1


def parse_report(text):
    """-> issues: a list of dicts, sorted by issue number, one per
    (measure, recommendation) pair, with keys: number, measure,
    rule_doc_id, rule_title, rule_kb, relevance, kind, reach
    ({"direct", "indirect"} or None), issue_fingerprint,
    measure_fingerprint, node, span ({"from", "to"} or None),
    flagged_expression, full_dax, definition (a "path:line" string, or None
    if the report carries no --model-resolved definition for it).

    Raises ReportError if section 5 is missing, or if section 1 and
    section 5 disagree on how many issues there are -- the two conditions
    the caller is asked to treat as "this report cannot be trusted".
    """
    lines = text.split("\n")
    sections = _find_sections(lines)

    if 5 not in sections:
        raise ReportError(
            "report has no '## 5. Technical' section -- cannot verify issue "
            "count or read fingerprints")
    if 1 not in sections:
        raise ReportError("report has no '## 1. Issues by relevance' section")

    s1_start, s1_end = sections[1]
    _header1, rows1 = parse_table_in_lines(lines[s1_start:s1_end])
    s5_start, s5_end = sections[5]
    _header5, rows5 = parse_table_in_lines(lines[s5_start:s5_end])

    n1, n5 = len(rows1), len(rows5)
    if n1 != n5:
        raise ReportError(
            "issue count mismatch: section 1 lists {0} issue(s), section 5 "
            "lists {1} -- report looks truncated or hand-edited".format(n1, n5))

    issues_by_num = {}
    for row in rows1:
        if len(row) < 7:
            raise ReportError("malformed section 1 row: {0!r}".format(row))
        try:
            num = int(row[0])
        except ValueError:
            raise ReportError("non-numeric issue number in section 1: {0!r}".format(row[0]))
        kb_m = KB_LINK_RE.match(row[6].strip())
        reach_m = REACH_RE.match(row[5].strip())
        issues_by_num[num] = {
            "number": num,
            "measure": row[1],
            "rule_title": row[2],
            "relevance": _parse_relevance(row[3]),
            "kind": row[4],
            "reach": ({"direct": int(reach_m.group(1)), "indirect": int(reach_m.group(2))}
                      if reach_m else None),
            "rule_doc_id": kb_m.group(1) if kb_m else None,
            "rule_kb": kb_m.group(2) if kb_m else None,
            "issue_fingerprint": None,
            "measure_fingerprint": None,
            "node": None,
            "span": None,
            "definition": None,
            "flagged_expression": None,
            "full_dax": None,
        }

    for row in rows5:
        if len(row) < 6:
            raise ReportError("malformed section 5 row: {0!r}".format(row))
        try:
            num = int(row[0])
        except ValueError:
            raise ReportError("non-numeric issue number in section 5: {0!r}".format(row[0]))
        if num not in issues_by_num:
            raise ReportError(
                "issue #{0} is in section 5 but not section 1".format(num))
        span_m = SPAN_RE.match(row[5].strip())
        issue = issues_by_num[num]
        issue["issue_fingerprint"] = row[1]
        issue["measure_fingerprint"] = row[2]
        issue["node"] = row[4]
        issue["span"] = ({"from": int(span_m.group(1)), "to": int(span_m.group(2))}
                          if span_m else None)

    expected = set(range(1, n1 + 1))
    if set(issues_by_num) != expected:
        raise ReportError(
            "issue numbers are not a contiguous 1..{0} sequence: got {1}".format(
                n1, sorted(issues_by_num)))

    # --- section 3: flagged expression, full DAX, TMDL definition -------- #
    s3_start, s3_end = sections.get(3, (0, 0))
    sec3_lines = lines[s3_start:s3_end]
    chunk_starts = [i for i, l in enumerate(sec3_lines) if l.startswith("### ")]
    chunk_starts.append(len(sec3_lines))

    full_dax_by_num = {}
    full_dax_ref_by_num = {}
    seen_in_sec3 = set()

    for k in range(len(chunk_starts) - 1):
        cstart, cend = chunk_starts[k], chunk_starts[k + 1]
        chunk = sec3_lines[cstart:cend]
        heading_m = ISSUE_HEADING_RE.match(chunk[0])
        if not heading_m:
            raise ReportError("malformed issue heading in section 3: {0!r}".format(chunk[0]))
        num = int(heading_m.group(1))
        if num not in issues_by_num:
            raise ReportError(
                "issue #{0} is in section 3 but not section 1".format(num))
        seen_in_sec3.add(num)

        definition = None
        flagged = None
        full_dax = None
        i = 1
        n_chunk = len(chunk)
        while i < n_chunk:
            line = chunk[i]
            dm = DEFINITION_LINE_RE.match(line)
            if dm:
                val = dm.group(1)
                definition = None if val == NOT_FOUND_IN_MODEL else val
                i += 1
                continue
            stripped = line.strip()
            if stripped == "Flagged expression:":
                i += 1
                if i < n_chunk and chunk[i].strip() == "```dax":
                    flagged, i = _extract_fence(chunk, i + 1)
                continue
            if stripped == "Full DAX:":
                i += 1
                if i < n_chunk and chunk[i].strip() == "```dax":
                    full_dax, i = _extract_fence(chunk, i + 1)
                continue
            see_m = FULL_DAX_SEE_RE.match(stripped)
            if see_m:
                full_dax_ref_by_num[num] = int(see_m.group(1))
                i += 1
                continue
            i += 1

        issue = issues_by_num[num]
        issue["definition"] = definition
        issue["flagged_expression"] = flagged
        if full_dax is not None:
            issue["full_dax"] = full_dax
            full_dax_by_num[num] = full_dax

    missing_from_sec3 = expected - seen_in_sec3
    if missing_from_sec3:
        raise ReportError(
            "issue(s) missing from section 3: {0}".format(sorted(missing_from_sec3)))

    for num, issue in issues_by_num.items():
        if issue["full_dax"] is not None:
            continue
        ref = full_dax_ref_by_num.get(num)
        if ref is None:
            raise ReportError(
                "issue #{0} has neither a Full DAX block nor a "
                "'Full DAX: see issue #n' reference".format(num))
        resolved = full_dax_by_num.get(ref)
        if resolved is None:
            raise ReportError(
                "issue #{0}: 'Full DAX: see issue #{1}' does not resolve to "
                "an issue with its own Full DAX block".format(num, ref))
        issue["full_dax"] = resolved

    return [issues_by_num[n] for n in sorted(issues_by_num)]


def fill_definitions_from_model(issues, model_dir):
    """Fill in `definition` for issues the report left blank (no --model at
    report time, or the measure was not found then), using a fresh TMDL
    lookup under model_dir. Mutates `issues` in place."""
    defs = find_measure_definitions(model_dir)
    for issue in issues:
        if not issue.get("definition"):
            issue["definition"] = defs.get(issue["measure"])


# --------------------------------------------------------------------------- #
# filters
# --------------------------------------------------------------------------- #

def parse_int_ranges(spec):
    """"3,7,12-15" -> {3, 7, 12, 13, 14, 15}. Raises ValueError on anything
    that isn't a plain integer or an ascending a-b range."""
    result = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a_txt, b_txt = part.split("-", 1)
            try:
                a, b = int(a_txt), int(b_txt)
            except ValueError:
                raise ValueError("not a valid range: {0!r}".format(part))
            if a > b:
                raise ValueError("range start is after its end: {0!r}".format(part))
            result.update(range(a, b + 1))
        else:
            try:
                result.add(int(part))
            except ValueError:
                raise ValueError("not a valid issue number: {0!r}".format(part))
    return result


def apply_filters(issues, issues_spec, rules_spec, measure_spec):
    """Intersection of the given filters; any filter left as None/"" is
    skipped, and no filters at all keeps every issue."""
    result = issues
    if issues_spec:
        wanted = parse_int_ranges(issues_spec)
        result = [i for i in result if i["number"] in wanted]
    if rules_spec:
        wanted_rules = set(r.strip() for r in rules_spec.split(",") if r.strip())
        result = [i for i in result if i["rule_doc_id"] in wanted_rules]
    if measure_spec:
        needle = measure_spec.lower()
        result = [i for i in result if needle in i["measure"].lower()]
    return result


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #

def public_issue_fields(issue):
    """Field order for one issue in the JSON output."""
    return {
        "number": issue["number"],
        "measure": issue["measure"],
        "rule_doc_id": issue["rule_doc_id"],
        "rule_title": issue["rule_title"],
        "rule_kb": issue["rule_kb"],
        "relevance": issue["relevance"],
        "kind": issue["kind"],
        "reach": issue["reach"],
        "issue_fingerprint": issue["issue_fingerprint"],
        "measure_fingerprint": issue["measure_fingerprint"],
        "node": issue["node"],
        "span": issue["span"],
        "flagged_expression": issue["flagged_expression"],
        "full_dax": issue["full_dax"],
        "definition": issue["definition"],
    }


def render_json(report_path, run, issues):
    payload = {
        "report": report_path,
        "run": run,
        "issues": [public_issue_fields(i) for i in sorted(issues, key=lambda x: x["number"])],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_md_plan(issues):
    """A compact plan: one "### <docId> <title>" heading per rule (rules
    ordered by their highest-relevance issue, ties by docId), each with a
    `| # | Measure | Rule | Relevance | Definition |` table of its issues
    (ordered by issue number, i.e. the report's own relevance order)."""
    if not issues:
        return ""
    groups = {}
    for issue in issues:
        groups.setdefault(issue["rule_doc_id"] or "?", []).append(issue)

    def group_key(doc_id):
        return (-max(m["relevance"] for m in groups[doc_id]), doc_id or "")

    out = []
    for doc_id in sorted(groups, key=group_key):
        members = sorted(groups[doc_id], key=lambda m: m["number"])
        out.append("### {0} {1}".format(doc_id, members[0]["rule_title"]))
        out.append("")
        out.append("| # | Measure | Rule | Relevance | Definition |")
        out.append("|---:|---|---|---:|---|")
        for m in members:
            out.append("| {0} | {1} | {2} | {3:.1f} | {4} |".format(
                m["number"], md_escape_cell(m["measure"]), md_escape_cell(m["rule_title"]),
                m["relevance"], md_escape_cell(m["definition"] or "-")))
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    ap = argparse.ArgumentParser(
        prog="daxopt-select.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Filter a DAX Optimizer Markdown report (from daxopt-report.py) "
            "down to a set of issues, printed as JSON (default) or a "
            "compact Markdown plan, for a fix pass to work from."),
        epilog=(
            "exit codes:\n"
            "  0  ok, the (filtered) issue list is non-empty\n"
            "  1  the filters matched nothing (stdout still has valid output)\n"
            "  2  the report was not found or does not parse structurally\n"))
    ap.add_argument("report", nargs="?",
                     help="report .md to read, or a bare slug substring to "
                          "search --dir for; omitted: newest report in --dir")
    ap.add_argument("--dir", default="docs/dax-optimizer",
                     help="folder to search when REPORT is omitted or a slug "
                          "(default: docs/dax-optimizer)")
    ap.add_argument("--issues", help="issue numbers/ranges, e.g. 3,7,12-15")
    ap.add_argument("--rules", help="rule docIds, e.g. 100200,103000")
    ap.add_argument("--measure", help="case-insensitive substring of the measure name")
    ap.add_argument("--format", choices=["json", "md"], default="json",
                     help="json (default) or md (compact plan table)")
    ap.add_argument("--model",
                     help="*.SemanticModel folder to resolve TMDL definitions "
                          "the report itself does not carry")
    return ap


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        report_path = resolve_report(args.report, args.dir)
    except ReportError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2
    print("report: {0}".format(report_path), file=sys.stderr)

    try:
        with io.open(report_path, encoding="utf-8-sig") as fh:
            text = fh.read()
        issues = parse_report(text)
    except (OSError, ReportError) as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2

    if args.model:
        if not os.path.isdir(args.model):
            print("warning: --model path not found, skipping definition "
                  "lookup: {0}".format(args.model), file=sys.stderr)
        else:
            fill_definitions_from_model(issues, args.model)

    try:
        filtered = apply_filters(issues, args.issues, args.rules, args.measure)
    except ValueError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2

    run = extract_run(os.path.basename(report_path))

    if args.format == "md":
        sys.stdout.write(render_md_plan(filtered))
    else:
        sys.stdout.write(render_json(report_path, run, filtered))

    return 0 if filtered else 1


if __name__ == "__main__":
    sys.exit(main())
