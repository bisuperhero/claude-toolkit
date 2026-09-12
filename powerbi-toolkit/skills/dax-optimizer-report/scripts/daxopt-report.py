#!/usr/bin/env python3
"""Turn a DAX Optimizer analysis result into a human-readable Markdown report.

DAX Optimizer (https://www.daxoptimizer.com/, by Tabular Tools) analyses every
measure in a semantic model and writes one `DaxOptimizer.json` -- either
loose or zipped up by `daxoptimizer analyze --output <file.zip>` -- listing,
per measure, the rules that fired against it and how much each one is
estimated to be worth fixing. That JSON is convenient for tooling but not
for a human to read or for a reviewer to skim in a pull request: this script
turns it into a Markdown report, ordered by "fix this first", plus a
technical section (fingerprints, spans) that a later automated "fix" pass
can key off without re-parsing the original JSON.

Why a separate script instead of reading the JSON by hand: the JSON encodes
positions as character offsets into each measure's DAX text (with the
sometimes-obfuscated names inline), spreads one finding's rule / weight /
location across three nested arrays (recommendationNodes, recommendations,
referencedMeasures), and -- when the input was produced with obfuscation
switched on (an `.ovpax` exported by DAX Studio's `dscmd.exe -i` or
`te vertipaq --obfuscate`, to share a model's shape without its names) -- carries scrambled identifiers that only make
sense once matched back through a `.dict` file. This script does that
matching once, deterministically, so the report and its technical section
agree with each other and with any later re-run against the same input.

Usage:
    python3 daxopt-report.py <result.zip|DaxOptimizer.json> \\
        [--output report.md | --output-dir docs/dax-optimizer] [--dict file.dict] \\
        [--model <path to .SemanticModel or TMDL folder>] \\
        [--title "<model name>"] \\
        [--meta key=value ...] [--top N]

    <result.zip|DaxOptimizer.json>  the zip written by `daxoptimizer analyze
                                     --output`, or the DaxOptimizer.json
                                     inside it
    --output FILE     write the report to exactly this path
    --output-dir DIR  write it as DIR/<YYYY-MM-DD_HHMM>_<model-slug>.md, the
                       timestamp being the analysis run's (from the zip
                       entry, UTC converted to local time), so a folder of
                       reports is a history and a later fix pass can name
                       one exactly. Neither option: stdout
    --dict FILE       deobfuscation dictionary (Id/Version/Texts/
                       UnobfuscatedValues JSON); reverses obfuscated
                       identifiers in measure names, DAX text and messages
    --model PATH      a *.SemanticModel folder (or its "definition/tables" /
                       "tables" folder) to resolve each measure's
                       TMDL definition line for the report
    --title TEXT      model name for the report's H1 (default: the input
                       file's stem)
    --meta KEY=VALUE  free metadata to print in the Technical section
                       (repeatable), e.g. --meta workspace=Sales
    --top N           limit the numbered per-issue write-ups in section 3
                       to the top N by relevance; the tables (sections 1,
                       2, 4, 5) are always complete (default: all)

Exit codes:
    0  report written (even when the result has zero issues)
    2  input unreadable, or it does not look like a DAX Optimizer result

This script only reads its inputs and writes the one report file (or
stdout); it never touches the semantic model or report files it is pointed
at with --model. Standard library only, no third-party dependencies.
"""
import argparse
import datetime
import glob
import io
import json
import os
import re
import sys
import zipfile


def force_utf8_stdout():
    """Print UTF-8 whatever the console claims to be.

    This report prints em dashes, arrows and whatever the model's authors
    called their measures; on a Windows console defaulting to cp1252 that is
    a hard UnicodeEncodeError halfway through a report. `reconfigure` exists
    from Python 3.7 on -- older interpreters and replaced streams just keep
    theirs.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


force_utf8_stdout()


class ResultError(Exception):
    """The input is not readable, or not a DAX Optimizer result."""


# --------------------------------------------------------------------------- #
# strings table (English only)
# --------------------------------------------------------------------------- #

STRINGS = {
    "en": {
        "h1": "DAX Optimizer report — {title}",
        "summary": (
            "Analysis run {run_time}, DAX Optimizer version {version}, input "
            "file `{input_name}`; report generated {generated}. "
            "{n_measures} measure(s) analysed, "
            "{n_with_issues} with issues, {n_issues} issue(s) across "
            "{n_rules} rule(s).{obf_note}{msg_note}"
        ),
        "obf_note": " Obfuscated input, dictionary applied.",
        "msg_note": " {n} measure(s) not analysed (see section 4).",
        "reading_guide": (
            "> Reading guide: **relevance** is the DAX Optimizer weight for "
            "that finding -- higher means fix it first. **Kind** is CPU vs. "
            "materialization cost, whichever weight is larger, or \"both\" "
            "when they tie. **Reach** is how many other measures reference "
            "this one, directly / indirectly -- a bigger reach means both a "
            "bigger payoff and a bigger blast radius if the fix changes "
            "behaviour. **KB** links to the public DAX Optimizer knowledge base "
            "article (Tabular Tools) for the rule."
        ),
        "sec1_title": "1. Issues by relevance",
        "sec1_headers": ["#", "Measure", "Rule", "Relevance", "Kind", "Reach", "KB"],
        "sec2_title": "2. Rules",
        "sec2_headers": ["Rule", "Title", "Issues", "Total relevance", "Measures", "KB"],
        "sec3_title": "3. Issues",
        "sec4_title": "4. Not analysed",
        "sec4_headers": ["Measure", "Message", "Count"],
        "sec5_title": "5. Technical",
        "no_issues": "No issues found.",
        "top_note": "Showing the top {top} of {total} issue(s) by relevance (--top {top}); "
                    "the tables above and below are complete.",
        "kind_cpu": "CPU",
        "kind_materialization": "materialization",
        "kind_both": "both",
        "issue_heading": "{n}. `{measure}` — {rule_title}",
        "field_rule": "Rule: [{doc_id} {title}]({url})",
        "field_relevance": "Relevance: {weight} (CPU {cpu}, materialization {materialization})",
        "field_reach": "Reach: referenced by {direct} measure(s) directly, {indirect} indirectly",
        "field_measure_relevance": (
            "Measure relevance: {weight}; CPU score {cpu_score} "
            "(optimizability {cpu_opt}); materialization score {mat_score} "
            "(optimizability {mat_opt})"
        ),
        "field_node": "Node: `{name}` at chars {frm}–{to}, line {line}:{col}",
        "field_definition": "Definition: `{definition}`",
        "not_found_in_model": "not found in model",
        "flagged_expression": "Flagged expression:",
        "full_dax": "Full DAX:",
        "full_dax_see": "Full DAX: see issue #{n}.",
        "meta_input_file": "Input file",
        "meta_run_time": "Analysis time",
        "meta_optimizer_version": "Optimizer version",
        "meta_generated": "Generated",
        "meta_dictionary": "Dictionary applied",
        "meta_dictionary_none": "no",
        "fingerprint_note": (
            "`daxFingerprint` and each recommendation's `fingerprint` are the "
            "stable ids DAX Optimizer keeps across re-analyses of the same "
            "model; a later fix/diff pass can use them to match an issue "
            "here to the same issue in a follow-up run, even if line numbers "
            "or wording shift."
        ),
    },
}


# --------------------------------------------------------------------------- #
# loading the result
# --------------------------------------------------------------------------- #

def load_result(path):
    """-> (parsed DaxOptimizer.json dict, analysis time, how that time was found).

    The JSON carries no timestamp. Inside the zip written by `daxoptimizer
    analyze --output`, the entry's modification time is the moment the service
    finished the analysis, in UTC (observed: it matches the run's
    `createdOn`, not the machine's local clock). That is the run's identity,
    so it names the report file. A loose .json has only its mtime, which is
    when someone unpacked it -- reported as such.
    """
    if not os.path.isfile(path):
        raise ResultError("file not found: {0}".format(path))
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                names = [n for n in zf.namelist() if n.endswith("DaxOptimizer.json")]
                if not names:
                    raise ResultError(
                        "{0}: no DaxOptimizer.json found inside the zip".format(path))
                info = zf.getinfo(sorted(names)[0])
                run_time = datetime.datetime(
                    *info.date_time, tzinfo=datetime.timezone.utc).astimezone()
                run_time_source = "zip entry time (UTC, service-side)"
                with zf.open(info) as fh:
                    raw = fh.read().decode("utf-8-sig")
        else:
            with io.open(path, encoding="utf-8-sig") as fh:
                raw = fh.read()
            run_time = datetime.datetime.fromtimestamp(
                os.path.getmtime(path)).astimezone()
            run_time_source = "file mtime (loose JSON -- unpack time, not analysis time)"
    except (OSError, zipfile.BadZipFile) as exc:
        raise ResultError("{0}: {1}".format(path, exc))
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ResultError("{0}: not valid JSON ({1})".format(path, exc))
    if not isinstance(data, dict) or "objectAnalyses" not in data:
        raise ResultError(
            "{0}: does not look like a DAX Optimizer result "
            "(no 'objectAnalyses' key)".format(path))
    return data, run_time, run_time_source


def slugify(text):
    """'Sales model v3' -> 'sales-model-v3': lowercase ASCII letters, digits
    and single dashes, so the name survives every filesystem and URL."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or "model"


def default_report_name(run_time, title):
    """<YYYY-MM-DD_HHMM>_<slug>.md -- the run time first so a folder of
    reports sorts into history and a fix pass can cite one exactly."""
    return "{0}_{1}.md".format(run_time.strftime("%Y-%m-%d_%H%M"), slugify(title))


def load_dict(path):
    """-> {obfuscated: original} reverse lookup built from a .dict file."""
    try:
        with io.open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ResultError("{0}: {1}".format(path, exc))
    texts = data.get("Texts")
    if not isinstance(texts, list):
        raise ResultError("{0}: does not look like a DAX Optimizer dictionary "
                           "(no 'Texts' array)".format(path))
    rev = {}
    for entry in texts:
        obf = entry.get("Obfuscated")
        val = entry.get("Value")
        if obf is not None and val is not None:
            rev[obf] = val
    return rev


# --------------------------------------------------------------------------- #
# deobfuscation
# --------------------------------------------------------------------------- #

# Token types that can carry an obfuscated identifier or string literal.
# Everything else (keywords, functions, operators, whitespace) is copied
# unchanged; comments are not tokens at all and stay obfuscated -- acceptable,
# per the DAX Optimizer author's own note.
_TARGET_TOKEN_TYPES = {"TABLE", "TABLE_OR_VARIABLE", "COLUMN_OR_MEASURE", "STRING_LITERAL"}

# A token's text is unwrapped before the dictionary lookup and rewrapped
# after, so 'Table Name', [Column Name] and "string literal" all look up by
# their inner text rather than by their punctuation.
_WRAP_PAIRS = (("'", "'"), ("[", "]"), ('"', '"'))


def _deobfuscate_token_text(text, rev):
    for open_c, close_c in _WRAP_PAIRS:
        if len(text) >= 2 and text[0] == open_c and text[-1] == close_c:
            inner = text[1:-1]
            return open_c + rev.get(inner, inner) + close_c
    return rev.get(text, text)


def deobfuscate_dax(dax, tokens, rev):
    """Rebuild `dax` with every target token's identifier deobfuscated.

    Returns (new_dax, boundary_map) where boundary_map maps every OLD
    character offset that sits on a token boundary to its corresponding NEW
    offset -- token lengths change under deobfuscation, so any from/to
    span recorded elsewhere in the result (recommendationNodes,
    referencedMeasures) that starts/ends exactly on a token boundary can be
    translated through this map. `tokens` is assumed to tile `dax` with no
    gaps or overlaps, which is what DAX Optimizer emits.
    """
    ordered = sorted(tokens, key=lambda t: t["fromChar"])
    parts = []
    new_len = 0
    boundary = {0: 0}
    pos = 0
    for tok in ordered:
        frm, to = tok["fromChar"], tok["toChar"]
        if frm > pos:
            gap = dax[pos:frm]
            parts.append(gap)
            new_len += len(gap)
            boundary[frm] = new_len
        segment = dax[frm:to + 1]
        if tok["type"] in _TARGET_TOKEN_TYPES:
            segment = _deobfuscate_token_text(segment, rev)
        parts.append(segment)
        new_len += len(segment)
        boundary[to + 1] = new_len
        pos = to + 1
    if pos < len(dax):
        tail = dax[pos:]
        parts.append(tail)
        new_len += len(tail)
        boundary[len(dax)] = new_len
    return "".join(parts), boundary


def remap_span(boundary, frm, to):
    """Old inclusive [frm, to] -> new inclusive [frm, to], via boundary map.

    Falls back to the untranslated offsets when a span does not land exactly
    on a token boundary -- should not happen on well-formed DAX Optimizer
    output, but this must never raise on real data.
    """
    new_from = boundary.get(frm, frm)
    new_to_excl = boundary.get(to + 1, (to + 1) - frm + new_from)
    return new_from, new_to_excl - 1


def apply_deobfuscation(data, rev):
    """Mutate `data` in place, replacing every obfuscated identifier."""
    for msg in data.get("messages", []) or []:
        name = msg.get("objectName")
        if name is not None:
            msg["objectName"] = rev.get(name, name)

    for oa in data.get("objectAnalyses", []) or []:
        oa["objectName"] = rev.get(oa["objectName"], oa["objectName"])
        new_dax, boundary = deobfuscate_dax(
            oa.get("dax", ""), oa.get("syntaxTokens", []) or [], rev)
        oa["dax"] = new_dax
        for node in oa.get("recommendationNodes", []) or []:
            if "name" in node:
                node["name"] = rev.get(node["name"], node["name"])
            node["from"], node["to"] = remap_span(boundary, node["from"], node["to"])
        for ref in oa.get("referencedMeasures", []) or []:
            ref["name"] = rev.get(ref.get("name"), ref.get("name"))
            ref["tableName"] = rev.get(ref.get("tableName"), ref.get("tableName"))
            ref["from"], ref["to"] = remap_span(boundary, ref["from"], ref["to"])


# --------------------------------------------------------------------------- #
# --model: locating each measure's TMDL definition
# --------------------------------------------------------------------------- #

# Measure names with spaces or special characters are single-quoted in TMDL;
# plain names are not. Doubled '' inside a quoted name is assumed not to
# occur (per the DAX Optimizer / TMDL data actually seen).
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
# rules, issues
# --------------------------------------------------------------------------- #

def rule_locale_text(rule, lang="en"):
    """-> (title, description) for `rule`, preferring the en-US localization,
    then whatever localization comes first. The report is English throughout
    (the rule text ships in English and a mixed-language report reads badly),
    so STRINGS has a single "en" table.
    """
    locs = rule.get("localizations") or []
    if not locs:
        return rule.get("docId", "?"), ""
    preferred = ("en-US", "en")
    for pref in preferred:
        for loc in locs:
            locale_id = loc.get("localeId", "")
            if locale_id == pref or locale_id.split("-")[0] == pref.split("-")[0]:
                return loc.get("title", rule.get("docId", "?")), loc.get("description", "")
    return locs[0].get("title", rule.get("docId", "?")), locs[0].get("description", "")


def issue_kind(rec, strings):
    cpu = rec.get("cpuWeight", 0.0)
    mat = rec.get("materializationWeight", 0.0)
    if cpu > mat:
        return strings["kind_cpu"]
    if mat > cpu:
        return strings["kind_materialization"]
    return strings["kind_both"]


def build_issues(data, rule_titles):
    """-> issues sorted by recommendation weight desc, ties by measure name
    then rule title then rule docId. One list entry per (object,
    recommendationNode, recommendation) triple -- one recommendation is one
    issue, as DAX Optimizer counts them (recommendationCount).
    """
    issues = []
    for oa in data.get("objectAnalyses", []) or []:
        for node in oa.get("recommendationNodes", []) or []:
            for rec in node.get("recommendations", []) or []:
                issues.append({"oa": oa, "node": node, "rec": rec})

    def sort_key(issue):
        doc_id = issue["rec"]["ruleDocId"]
        title = rule_titles.get(doc_id, (doc_id, ""))[0]
        return (-issue["rec"]["weight"], issue["oa"]["objectName"], title, doc_id)

    issues.sort(key=sort_key)
    return issues


# --------------------------------------------------------------------------- #
# formatting helpers
# --------------------------------------------------------------------------- #

THIN_SPACE = "\u202f"   # narrow no-break space: a thousands separator that
                        # reads the same in an English and a Czech report


def fmt1(x):
    """One decimal, with a thin-space thousands separator: DAX Optimizer
    weights range from 0.5 to tens of billions in the same table."""
    return "{0:,.1f}".format(x).replace(",", THIN_SPACE)


def fmt_num(x):
    """General-purpose number formatting for the per-issue detail fields --
    scores can be as small as 0.0001 or as large as several hundred, so a
    fixed decimal count either loses small values or pads large ones.
    """
    if x is None:
        return "-"
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, float):
        if x == int(x) and abs(x) < 1e15:
            return str(int(x))
        return "{0:.6g}".format(x)
    return str(x)


def line_col(text, offset):
    """1-based (line, column) of `offset` within `text`."""
    prefix = text[:offset]
    last_nl = prefix.rfind("\n")
    line = prefix.count("\n") + 1
    col = offset - last_nl if last_nl >= 0 else offset + 1
    return line, col


def trim_blank_lines(text):
    lines = text.split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines)


def node_display_name(node, dax):
    """A recommendationNode's human-readable label.

    Only reference-shaped nodes (measure/column/table, type 3/4 in the data
    seen) carry a `name`; an operator node (type 1: a comparison, a context
    transition site, ...) carries `operator` instead. Fall back to the exact
    flagged text so every node still gets a sensible label.
    """
    if "name" in node:
        return node["name"]
    if "operator" in node:
        return "operator {0}".format(node["operator"])
    return dax[node["from"]:node["to"] + 1].strip()


def kb_link(rule):
    return "[{0}]({1})".format(rule.get("docId", "?"), rule.get("url", ""))


def md_escape_cell(text):
    """Escape the one character that would break a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


# --------------------------------------------------------------------------- #
# report rendering
# --------------------------------------------------------------------------- #

ALIGN = {"l": "---", "r": "---:", "c": ":---:"}


def render_table(headers, rows, align=None):
    """`align` is one letter per column: l (default), r for numbers, c."""
    align = (align or "l" * len(headers)).ljust(len(headers), "l")
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(ALIGN[a] for a in align) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(md_escape_cell(c) for c in row) + " |")
    return "\n".join(lines)


def render_report(data, args, strings, rev_applied):
    rules_by_id = {r["docId"]: r for r in data.get("rules", []) or []}
    rule_titles = {doc_id: rule_locale_text(r)
                   for doc_id, r in rules_by_id.items()}

    issues = build_issues(data, rule_titles)
    object_analyses = data.get("objectAnalyses", []) or []
    messages = data.get("messages", []) or []

    n_measures = len(object_analyses)
    n_with_issues = sum(1 for oa in object_analyses if oa.get("recommendationCount", 0) > 0)
    n_issues = len(issues)
    n_rules = len(set(issue["rec"]["ruleDocId"] for issue in issues))

    input_name = os.path.basename(args.result)
    title = args.title or os.path.splitext(os.path.basename(args.result))[0]
    generated = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    run_time = args.run_time.isoformat(timespec="seconds")

    obf_note = strings["obf_note"] if rev_applied else ""
    msg_note = strings["msg_note"].format(n=len(messages)) if messages else ""

    out = []
    out.append("# " + strings["h1"].format(title=title))
    out.append("")
    out.append(strings["summary"].format(
        generated=generated, run_time=run_time,
        version=data.get("version", "?"), input_name=input_name,
        n_measures=n_measures, n_with_issues=n_with_issues, n_issues=n_issues,
        n_rules=n_rules, obf_note=obf_note, msg_note=msg_note))
    out.append("")
    out.append(strings["reading_guide"])
    out.append("")

    # --- section 1: issues by relevance --------------------------------- #
    out.append("## " + strings["sec1_title"])
    out.append("")
    if not issues:
        out.append(strings["no_issues"])
    else:
        rows = []
        for i, issue in enumerate(issues, start=1):
            oa, node, rec = issue["oa"], issue["node"], issue["rec"]
            doc_id = rec["ruleDocId"]
            rule = rules_by_id.get(doc_id)
            rule_title = rule_titles.get(doc_id, (doc_id, ""))[0]
            kb = kb_link(rule) if rule else doc_id
            rows.append([
                str(i),
                oa["objectName"],
                rule_title,
                fmt1(rec["weight"]),
                issue_kind(rec, strings),
                "{0} / {1}".format(oa.get("directReferenceCount", 0),
                                    oa.get("indirectReferenceCount", 0)),
                kb,
            ])
        out.append(render_table(strings["sec1_headers"], rows, "rllrlcl"))
    out.append("")

    # --- section 2: rules -------------------------------------------------#
    out.append("## " + strings["sec2_title"])
    out.append("")
    if not rules_by_id:
        out.append(strings["no_issues"])
    else:
        stats = {}
        for issue in issues:
            doc_id = issue["rec"]["ruleDocId"]
            st = stats.setdefault(doc_id, {"count": 0, "weight": 0.0, "measures": set()})
            st["count"] += 1
            st["weight"] += issue["rec"]["weight"]
            st["measures"].add(issue["oa"]["objectName"])

        ordered_rule_ids = sorted(
            rules_by_id.keys(),
            key=lambda d: (-stats.get(d, {}).get("weight", 0.0), d))

        rows = []
        for doc_id in ordered_rule_ids:
            rule = rules_by_id[doc_id]
            st = stats.get(doc_id, {"count": 0, "weight": 0.0, "measures": set()})
            title_text = rule_titles.get(doc_id, (doc_id, ""))[0]
            rows.append([
                doc_id, title_text, str(st["count"]), fmt1(st["weight"]),
                str(len(st["measures"])), kb_link(rule),
            ])
        out.append(render_table(strings["sec2_headers"], rows, "llrrrl"))
        out.append("")
        for doc_id in ordered_rule_ids:
            rule = rules_by_id[doc_id]
            title_text, description = rule_titles.get(doc_id, (doc_id, ""))
            out.append("- **{0} {1}** — {2}".format(doc_id, title_text, description))
    out.append("")

    # --- section 3: issues (detail) ---------------------------------------#
    out.append("## " + strings["sec3_title"])
    out.append("")
    if not issues:
        out.append(strings["no_issues"])
        out.append("")
    else:
        top = args.top if args.top is not None else len(issues)
        shown = issues[:top]
        first_full_dax_issue = {}
        for i, issue in enumerate(shown, start=1):
            oa = issue["oa"]
            first_full_dax_issue.setdefault(oa["objectName"], i)

        for i, issue in enumerate(shown, start=1):
            oa, node, rec = issue["oa"], issue["node"], issue["rec"]
            doc_id = rec["ruleDocId"]
            rule = rules_by_id.get(doc_id)
            rule_title, _desc = rule_titles.get(doc_id, (doc_id, ""))
            dax = oa.get("dax", "")

            out.append("### " + strings["issue_heading"].format(
                n=i, measure=oa["objectName"], rule_title=rule_title))
            if rule:
                out.append("- " + strings["field_rule"].format(
                    doc_id=doc_id, title=rule_title, url=rule.get("url", "")))
            out.append("- " + strings["field_relevance"].format(
                weight=fmt_num(rec["weight"]), cpu=fmt_num(rec.get("cpuWeight")),
                materialization=fmt_num(rec.get("materializationWeight"))))
            out.append("- " + strings["field_reach"].format(
                direct=oa.get("directReferenceCount", 0),
                indirect=oa.get("indirectReferenceCount", 0)))
            out.append("- " + strings["field_measure_relevance"].format(
                weight=fmt_num(oa.get("weight")),
                cpu_score=fmt_num(oa.get("cpuScore")),
                cpu_opt=fmt_num(oa.get("cpuOptimizability")),
                mat_score=fmt_num(oa.get("materializationScore")),
                mat_opt=fmt_num(oa.get("materializationOptimizability"))))
            line, col = line_col(dax, node["from"])
            out.append("- " + strings["field_node"].format(
                name=node_display_name(node, dax), frm=node["from"], to=node["to"],
                line=line, col=col))
            if args.model:
                definition = args.definitions.get(oa["objectName"], strings["not_found_in_model"])
                out.append("- " + strings["field_definition"].format(definition=definition))

            out.append(strings["flagged_expression"])
            out.append("```dax")
            out.append(dax[node["from"]:node["to"] + 1])
            out.append("```")

            first_i = first_full_dax_issue.get(oa["objectName"])
            if first_i == i:
                out.append(strings["full_dax"])
                out.append("```dax")
                out.append(trim_blank_lines(dax))
                out.append("```")
            else:
                out.append(strings["full_dax_see"].format(n=first_i))
            out.append("")

        if top < len(issues):
            out.append(strings["top_note"].format(top=top, total=len(issues)))
            out.append("")

    # --- section 4: not analysed ------------------------------------------#
    if messages:
        out.append("## " + strings["sec4_title"])
        out.append("")
        dedup = {}
        for m in messages:
            key = (m.get("objectName", ""), m.get("text", ""))
            dedup[key] = dedup.get(key, 0) + 1
        rows = [[name, text, str(count)]
                for (name, text), count in sorted(dedup.items())]
        out.append(render_table(strings["sec4_headers"], rows, "llr"))
        out.append("")

    # --- section 5: technical ----------------------------------------------#
    out.append("## " + strings["sec5_title"])
    out.append("")
    out.append("- {0}: `{1}`".format(strings["meta_input_file"], args.result))
    out.append("- {0}: {1}".format(strings["meta_optimizer_version"], data.get("version", "?")))
    out.append("- {0}: {1} ({2})".format(strings["meta_run_time"], run_time,
                                          args.run_time_source))
    out.append("- {0}: {1}".format(strings["meta_generated"], generated))
    dict_label = (os.path.basename(args.dict) if args.dict
                  else strings["meta_dictionary_none"])
    out.append("- {0}: {1}".format(strings["meta_dictionary"], dict_label))
    for key, value in args.meta or []:
        out.append("- {0}: {1}".format(key, value))
    out.append("")
    if issues:
        out.append(strings["fingerprint_note"])
        out.append("")
        rows = []
        for i, issue in enumerate(issues, start=1):
            oa, node, rec = issue["oa"], issue["node"], issue["rec"]
            rows.append([
                str(i),
                rec.get("fingerprint", ""),
                oa.get("daxFingerprint", ""),
                rec["ruleDocId"],
                node_display_name(node, oa.get("dax", "")),
                "{0}-{1}".format(node["from"], node["to"]),
            ])
        out.append(render_table(
            ["#", "Issue fingerprint", "Measure fingerprint", "Rule", "Node", "Span"], rows))
    else:
        out.append(strings["no_issues"])

    return "\n".join(out).rstrip("\n") + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _parse_meta(values):
    out = []
    for item in values or []:
        if "=" not in item:
            raise argparse.ArgumentTypeError(
                "--meta expects key=value, got {0!r}".format(item))
        key, value = item.split("=", 1)
        out.append((key, value))
    return out


def build_parser():
    ap = argparse.ArgumentParser(
        prog="daxopt-report.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Turn a DAX Optimizer analysis result (the zip written by\n"
            "`daxoptimizer analyze --output`, or the DaxOptimizer.json inside\n"
            "it) into a Markdown report: issues ranked by relevance, the rules\n"
            "that fired, per-issue detail, and a technical section (stable\n"
            "fingerprints and spans) for a later automated fix pass.\n\n"
            "Deterministic: the same input always produces the same report\n"
            "content (the generated-timestamp line aside)."),
        epilog=(
            "exit codes:\n"
            "  0  report written (even with zero issues)\n"
            "  2  input unreadable, or it does not look like a DAX Optimizer "
            "result\n"))
    ap.add_argument("result", help="the result .zip or DaxOptimizer.json to report on")
    ap.add_argument("--output", help="write the report to exactly this path")
    ap.add_argument("--output-dir", help="write the report into this folder as "
                                          "<YYYY-MM-DD_HHMM>_<model-slug>.md, the "
                                          "time being the analysis run's (default "
                                          "when neither is given: stdout)")
    ap.add_argument("--dict", help="deobfuscation dictionary (.dict JSON) to reverse "
                                    "obfuscated identifiers")
    ap.add_argument("--model", help="a *.SemanticModel folder (or its tables folder) "
                                     "to resolve each measure's TMDL definition line")
    ap.add_argument("--title", help="model name for the report H1 "
                                     "(default: stem of the input file)")
    ap.add_argument("--meta", action="append", metavar="KEY=VALUE",
                     help="free metadata to print in the Technical section "
                          "(repeatable)")
    ap.add_argument("--top", type=int, default=None,
                     help="limit the numbered per-issue write-ups in section 3 "
                          "to the top N by relevance (default: all); tables "
                          "are always complete")
    return ap


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.meta = _parse_meta(args.meta)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    if args.output and args.output_dir:
        parser.error("--output and --output-dir are mutually exclusive")
    try:
        data, args.run_time, args.run_time_source = load_result(args.result)
    except ResultError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2

    rev_applied = False
    if args.dict:
        try:
            rev = load_dict(args.dict)
        except ResultError as exc:
            print("error: {0}".format(exc), file=sys.stderr)
            return 2
        apply_deobfuscation(data, rev)
        rev_applied = True

    args.definitions = {}
    if args.model:
        if not os.path.isdir(args.model):
            print("warning: --model path not found, skipping definition "
                  "lookup: {0}".format(args.model), file=sys.stderr)
        else:
            args.definitions = find_measure_definitions(args.model)

    strings = STRINGS["en"]
    report = render_report(data, args, strings, rev_applied)

    if args.output_dir:
        title = args.title or os.path.splitext(os.path.basename(args.result))[0]
        os.makedirs(args.output_dir, exist_ok=True)
        args.output = os.path.join(args.output_dir,
                                   default_report_name(args.run_time, title))
    if args.output:
        with io.open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(report)
        n_issues = sum(len(node.get("recommendations", []) or [])
                        for oa in data.get("objectAnalyses", []) or []
                        for node in oa.get("recommendationNodes", []) or [])
        n_measures = len(data.get("objectAnalyses", []) or [])
        print("{0}: {1} measure(s), {2} issue(s) -> {3}".format(
            os.path.basename(args.result), n_measures, n_issues, args.output),
            file=sys.stderr)
    else:
        sys.stdout.write(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
