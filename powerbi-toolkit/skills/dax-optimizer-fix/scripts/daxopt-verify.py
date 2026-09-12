#!/usr/bin/env python3
"""Prove a rewritten DAX measure returns the same values as before.

DAX Optimizer's relevance scores (see the sibling `dax-optimizer-report`
skill) estimate engine cost, not correctness -- they say nothing about
whether a rewritten measure still returns the same numbers. This script is
the other half of the loop: it drives a running Power BI Desktop instance
through DAX Studio's command-line tool (`dscmd.exe`) to capture a measure's
values before a change and re-capture them after, then diffs the two.

Intended workflow, tied to the Desktop bridge (see the sibling
`powerbi-report-editing` skill's `references/desktop-bridge.md`):

    1. Desktop open, report saved (`hasUnsavedChanges: false`)
    2. `baseline`  -- capture the "before" values
    3. Desktop closed, the TMDL edited on disk
    4. Desktop reopened on the edited files
    5. `compare`   -- re-run the same queries, diff against the baseline

Every query goes through `dscmd.exe file <out> -s '<Report>.pbip' -d <GUID>`,
i.e. exactly the mechanics the `dax-optimizer-report` skill's
`references/vpax-extraction.md` (section "2. desktop") documents for finding
and addressing a running Desktop instance:

    - `-s` takes the **bare `.pbip` file name**, not a path -- dscmd matches
      it against a running Desktop window's title, and a full path fails
      with "Unable to find a running Power BI Desktop instance".
    - `-d <catalog GUID>` is mandatory for a reliable match. The GUID is the
      internal Analysis Services catalog name of the running instance, not
      anything shown in the Desktop UI. It is found by: running dscmd once
      to read the port off its own "Found running instance of '<name>' on
      port: <port>" log line, then querying
      `SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS` over ADOMD,
      using the `Microsoft.AnalysisServices.AdomdClient.dll` that ships
      inside the DAX Studio install (see `discover_catalog` below). The
      catalog GUID changes every time Desktop reloads the model, so it is
      always rediscovered, never cached across a baseline/compare pair.

One deliberate deviation from the naive "pass the DAX on the command line
with `-q`" approach: this script writes each query to a small temp `.dax`
file and calls `dscmd.exe file <out> ... -f <query.dax>` instead. Getting a
DAX string (which itself contains double-quoted string literals) through
three layers of quoting -- Python's subprocess argv, `powershell.exe
-Command`, and dscmd's own argument parser -- turned out to mangle the
query's quotes in practice; `-f` sidesteps all three layers by never putting
the DAX text on a command line at all. The queries dscmd runs are otherwise
exactly what the CLI below documents.

Queries per measure:

    total   EVALUATE ROW("value", <measure>)
    by col  EVALUATE
                TOPN(<top>, SUMMARIZECOLUMNS(<col>, "value", <measure>), <col>, ASC)
            ORDER BY <col> ASC

`TOPN(...)`'s own row order is **not** guaranteed to be sorted by its order
argument -- confirmed empirically: it returned the *selected* top-N rows by
`<col>` ascending, but emitted them in whatever order the storage engine
produced internally, not ascending. The trailing `ORDER BY` re-sorts that
same row set, so both the baseline and the after-run enumerate identical
rows in an identical, deterministic order -- required for the by-position
diff below to line values up correctly rather than by coincidence.

Value parsing: dscmd writes plain CSV, one row per DAX Studio result row,
using the *host machine's regional format* for numbers -- observed on a
Czech-locale Windows install as a decimal **comma** (`"223027479,95997921"`),
quoted because the comma would otherwise split the CSV field. This script
tries a comma-decimal parse first when a value looks like `-?<digits>,<digits>`,
then a plain `float()`, and only falls back to keeping the raw string when
neither parses -- so both a `.` and a `,` decimal host produce the same
float. A completely BLANK() DAX value becomes an empty CSV field (or, for a
single-column result, a wholly empty CSV line) and is read back as `None`.

Usage:
    daxopt-verify.py discover --pbip '<Report>.pbip' [--timeout 300]

    daxopt-verify.py baseline --pbip '<Report>.pbip' [--catalog GUID] \\
        --out baseline.json \\
        --measure '[Sales Amount]' [--measure '[Other Measure]' ...] \\
        [--by "'Date'[Year]"] [--by "'Product'[Category]"] \\
        [--top 200] [--timeout 300]

    daxopt-verify.py compare --pbip '<Report>.pbip' [--catalog GUID] \\
        --baseline baseline.json [--out after.json] \\
        [--tolerance 1e-9] [--measure '[Sales Amount]' ...] [--timeout 300]

`--catalog` omitted on any command: the script runs the same discovery
`discover` does, internally, before the first query.

`compare` reads which measures and `--by` columns to re-query from the
baseline file itself -- it does not take its own `--by`. A `--measure` on
`compare` narrows to a subset of the baseline's measures; a name not present
in the baseline is skipped with a warning, not an error.

A single measure's (or a single `--by` column's) query failing -- a typo, a
measure that no longer exists, a transient dscmd error -- is recorded as an
error for that measure/column and the run continues to the rest; it is not
treated the same as a total failure to reach Desktop at all. See "Exit
codes" below for exactly how that distinction maps to the process exit code.

Exit codes:
    discover
        0  printed {"port": N, "catalog": "<GUID>"}
        2  no running Desktop instance found for --pbip

    baseline
        0  baseline written (even if some measures/columns errored --
           check the file's "error" keys, and the warnings on stderr)
        2  could not resolve a catalog at all, or *every* measure's total
           query failed (nothing usable was captured), or --out could not
           be written

    compare
        0  every value equal within tolerance, no query errored
        1  at least one value differed, and/or at least one measure/column
           query errored while at least one other query still succeeded --
           i.e. equivalence was not fully proven, but this was not a total
           failure to reach Desktop
        2  could not read --baseline, could not resolve a catalog at all,
           or *every* requested measure's total query failed (dscmd's
           stderr is printed for the first such failure)

Only Windows and WSL2 (driving a Windows-side Power BI Desktop) can run any
of this -- see `references/verification.md` for why there is nothing this
script can do on Linux/macOS beyond being read for its query-generation and
diff logic. Standard library only, no third-party dependencies.
"""
import argparse
import csv
import datetime
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid


def force_utf8_stdout():
    """Print UTF-8 whatever the console claims to be.

    This script prints measure names and DAX text that can contain anything
    a modeller typed; on a Windows console defaulting to cp1252 that is a
    hard UnicodeEncodeError halfway through a run. `reconfigure` exists from
    Python 3.7 on -- older interpreters and replaced streams just keep
    theirs.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


force_utf8_stdout()


class VerifyError(Exception):
    """A step failed badly enough that the caller should stop and report it
    (catalog could not be resolved, --baseline unreadable, dscmd missing).
    Distinct from a single query failing, which is caught and recorded
    per-measure/per-column instead of raised."""


class QueryError(VerifyError):
    """One dscmd query failed. Caught at the measure/column level; never
    meant to abort a whole baseline/compare run by itself."""


# --------------------------------------------------------------------------- #
# platform / environment
# --------------------------------------------------------------------------- #

def is_wsl():
    if sys.platform != "linux":
        return False
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with io.open("/proc/version", encoding="utf-8", errors="replace") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


DSCMD_WINDOWS_PATH = r"C:\Program Files\DAX Studio\dscmd.exe"
DSCMD_WSL_MOUNT_PATH = "/mnt/c/Program Files/DAX Studio/dscmd.exe"


class Environment(object):
    """Everything about *where* this runs: how to invoke dscmd.exe and
    powershell.exe, and where to stage the small temp files a query needs
    (the DAX text going in, the CSV result coming out)."""

    def __init__(self, timeout):
        self.timeout = timeout
        self.wsl = is_wsl()
        self.native_windows = sys.platform == "win32"
        if not (self.wsl or self.native_windows):
            raise VerifyError(
                "this workflow needs Power BI Desktop + DAX Studio, which only "
                "run on Windows (natively, or as a WSL2 host); on Linux/macOS "
                "this script cannot discover, baseline or compare -- see "
                "references/verification.md")
        if self.wsl and not os.path.exists(DSCMD_WSL_MOUNT_PATH):
            raise VerifyError(
                "DAX Studio's dscmd.exe not found at '{0}' (expected {1} on "
                "the Windows side) -- install DAX Studio "
                "(https://daxstudio.org/) on the Windows host".format(
                    DSCMD_WSL_MOUNT_PATH, DSCMD_WINDOWS_PATH))
        if self.native_windows and not os.path.exists(DSCMD_WINDOWS_PATH):
            raise VerifyError(
                "DAX Studio's dscmd.exe not found at '{0}' -- install DAX "
                "Studio (https://daxstudio.org/)".format(DSCMD_WINDOWS_PATH))
        self._win_temp = None
        self._wsl_temp = None

    # -- temp files ---------------------------------------------------- #

    def _windows_temp_dirs(self):
        """-> (windows-side temp dir, same dir as a WSL path). Cached: one
        lookup per run. Native Windows never needs the WSL half."""
        if self._win_temp is not None:
            return self._win_temp, self._wsl_temp
        if self.native_windows:
            self._win_temp = tempfile.gettempdir()
            self._wsl_temp = None
            return self._win_temp, self._wsl_temp
        rc, out, err = self._run_powershell("$env:TEMP")
        if rc != 0 or not out.strip():
            raise VerifyError(
                "could not read $env:TEMP via powershell.exe: {0}".format(
                    (err or out).strip()))
        win_temp = out.strip().rstrip("\\")
        try:
            p = subprocess.run(["wslpath", "-u", win_temp], capture_output=True,
                                text=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            raise VerifyError("wslpath could not convert '{0}': {1}".format(
                win_temp, exc))
        if p.returncode != 0:
            raise VerifyError("wslpath could not convert '{0}': {1}".format(
                win_temp, p.stderr.strip()))
        self._win_temp = win_temp
        self._wsl_temp = p.stdout.strip()
        return self._win_temp, self._wsl_temp

    def _temp_paths(self, suffix):
        """-> (windows-side path to hand dscmd, local path this process can
        read/write). A random name avoids collisions between concurrent runs
        and with unrelated files already in the temp folder."""
        win_dir, wsl_dir = self._windows_temp_dirs()
        name = "daxopt-verify-{0}{1}".format(uuid.uuid4().hex[:12], suffix)
        win_path = win_dir + "\\" + name
        local_path = os.path.join(wsl_dir, name) if wsl_dir else win_path
        return win_path, local_path

    @staticmethod
    def _cleanup(local_path):
        try:
            os.remove(local_path)
        except OSError:
            pass

    # -- process invocation --------------------------------------------- #

    def _run_powershell(self, script):
        """-> (returncode, stdout, stderr). None returncode = it never ran
        (timeout, or powershell.exe missing)."""
        try:
            p = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", script],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.timeout)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return None, "", "powershell.exe timed out after {0}s".format(self.timeout)
        except OSError as exc:
            return None, "", str(exc)

    @staticmethod
    def _ps_quote(value):
        """Single-quote `value` for literal use inside a PowerShell command
        string -- no interpolation, so a `$` or backtick in a path is not a
        problem, only an embedded `'` needs doubling."""
        return "'" + value.replace("'", "''") + "'"

    def run_dscmd(self, dscmd_args):
        """Run dscmd.exe with `dscmd_args` (a flat list of already-final
        string arguments -- no further quoting needed by the caller).
        -> (returncode, combined stdout+stderr). None returncode = timed out
        or could not even start."""
        if self.native_windows:
            try:
                p = subprocess.run(
                    [DSCMD_WINDOWS_PATH] + dscmd_args, capture_output=True,
                    text=True, encoding="utf-8", errors="replace",
                    timeout=self.timeout)
                return p.returncode, (p.stdout or "") + (p.stderr or "")
            except subprocess.TimeoutExpired:
                return None, "dscmd.exe timed out after {0}s".format(self.timeout)
            except OSError as exc:
                return None, str(exc)
        script = "& " + " ".join(
            self._ps_quote(a) for a in [DSCMD_WINDOWS_PATH] + dscmd_args)
        rc, out, err = self._run_powershell(script)
        return rc, (out or "") + (err or "")


# --------------------------------------------------------------------------- #
# discovering the running Desktop instance
# --------------------------------------------------------------------------- #

_PORT_RE = re.compile(r"[Ff]ound running instance of '.*?' on port:\s*(\d+)")
_NOT_FOUND_RE = re.compile(r"Unable to find a running Power BI Desktop instance")

# Reused verbatim from dax-optimizer-report's references/vpax-extraction.md:
# the ADOMD DLL that ships inside the DAX Studio install answers the catalog
# name question without a separate ADOMD install. Add-Type is known to print
# a ReflectionTypeLoadException from unrelated assemblies in the same
# folder -- that lands on stderr and is not the failure signal; only stdout
# (the query's actual output) is read here.
_ADOMD_TEMPLATE = (
    "$dll = Get-ChildItem 'C:\\Program Files\\DAX Studio' -Recurse "
    "-Filter 'Microsoft.AnalysisServices.AdomdClient.dll' | "
    "Select-Object -First 1 -ExpandProperty FullName; "
    "Add-Type -Path $dll; "
    "$c = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("
    "'Data Source=localhost:{port}'); "
    "$c.Open(); "
    "$cmd = $c.CreateCommand(); "
    "$cmd.CommandText = 'SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS'; "
    "$r = $cmd.ExecuteReader(); "
    "while ($r.Read()) {{ $r[0] }}; "
    "$c.Close()"
)


def discover_port(env, pbip_bare):
    """-> port number of the running Desktop instance with `pbip_bare` open.

    Probes with a throwaway one-row query and no `-d`: dscmd logs the "Found
    running instance ... on port: N" line while still scanning for the
    instance, before it even gets to needing a database name, so the port is
    available whether or not the probe query itself succeeds.
    """
    win_out, local_out = env._temp_paths(".csv")
    win_dax, local_dax = env._temp_paths(".dax")
    try:
        with io.open(local_dax, "w", encoding="utf-8", newline="\n") as fh:
            fh.write('EVALUATE ROW("x", 1)')
        rc, combined = env.run_dscmd(["file", win_out, "-s", pbip_bare, "-f", win_dax])
    finally:
        env._cleanup(local_dax)
        env._cleanup(local_out)
    m = _PORT_RE.search(combined)
    if m:
        return int(m.group(1))
    if _NOT_FOUND_RE.search(combined) or rc is None:
        raise VerifyError(
            "no running Power BI Desktop instance has '{0}' open "
            "(dscmd: {1})".format(pbip_bare, combined.strip() or "no output"))
    raise VerifyError(
        "could not read a port from dscmd's output for '{0}': {1}".format(
            pbip_bare, combined.strip()))


def discover_catalog(env, pbip_bare):
    """-> (port, catalog GUID) for the running instance with `pbip_bare` open."""
    port = discover_port(env, pbip_bare)
    rc, out, err = env._run_powershell(_ADOMD_TEMPLATE.format(port=port))
    if rc is None:
        raise VerifyError("ADOMD catalog lookup on port {0} failed: {1}".format(
            port, err.strip() or out.strip()))
    catalog = ""
    for line in out.splitlines():
        line = line.strip()
        if line:
            catalog = line
            break
    if not catalog:
        raise VerifyError(
            "ADOMD catalog lookup on port {0} returned nothing (stderr: {1})".format(
                port, err.strip() or "none"))
    return port, catalog


def resolve_catalog(env, args, pbip_bare):
    """Shared by baseline/compare: use --catalog if given, else discover."""
    if args.catalog:
        return args.catalog
    _port, catalog = discover_catalog(env, pbip_bare)
    return catalog


# --------------------------------------------------------------------------- #
# queries
# --------------------------------------------------------------------------- #

def total_query(measure):
    return 'EVALUATE\nROW("value", {0})'.format(measure)


def by_query(measure, column, top):
    return (
        "EVALUATE\n"
        "TOPN({top}, SUMMARIZECOLUMNS({col}, \"value\", {measure}), {col}, ASC)\n"
        "ORDER BY {col} ASC"
    ).format(top=top, col=column, measure=measure)


_CZ_DECIMAL_RE = re.compile(r"^-?\d+,\d+$")


def coerce_number(raw):
    """-> float, the original string, or None for a blank cell.

    Tries a comma-decimal parse first (observed dscmd output on a
    Czech-locale host, e.g. "223027479,95997921"), then a plain float(); a
    value that is neither is kept as-is (a text --by key, or an error we
    have no business turning into a number).
    """
    if raw is None or raw == "":
        return None
    if _CZ_DECIMAL_RE.match(raw):
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            pass
    try:
        return float(raw)
    except ValueError:
        return raw


def read_csv_rows(path):
    """-> data rows (header stripped), each a list of raw string fields.

    A DAX Studio CSV result whose sole column is BLANK() collapses to a
    completely empty line -- csv.reader yields `[]` for it, not `['']` --
    so callers must handle a shorter-than-expected (or empty) row rather
    than indexing blindly.
    """
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    return rows[1:] if rows else []


def run_query(env, pbip_bare, catalog, dax_text):
    """Run one DAX query through `dscmd.exe file ... -f <query>.dax` and
    return its data rows (header stripped). Raises QueryError with dscmd's
    combined output on any non-zero exit or unreadable result."""
    win_out, local_out = env._temp_paths(".csv")
    win_dax, local_dax = env._temp_paths(".dax")
    try:
        with io.open(local_dax, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dax_text)
        rc, combined = env.run_dscmd(
            ["file", win_out, "-s", pbip_bare, "-d", catalog, "-f", win_dax])
        if rc != 0:
            raise QueryError(combined.strip() or "dscmd exited {0}".format(rc))
        try:
            return read_csv_rows(local_out)
        except OSError as exc:
            raise QueryError("dscmd reported success but the result file could "
                              "not be read: {0}".format(exc))
    finally:
        env._cleanup(local_dax)
        env._cleanup(local_out)


def query_total(env, pbip_bare, catalog, measure):
    rows = run_query(env, pbip_bare, catalog, total_query(measure))
    row = rows[0] if rows else []
    raw = row[0] if row else ""
    return coerce_number(raw)


def query_by(env, pbip_bare, catalog, measure, column, top):
    rows = run_query(env, pbip_bare, catalog, by_query(measure, column, top))
    pairs = []
    for row in rows:
        if not row:
            key, raw_val = None, ""
        elif len(row) == 1:
            key, raw_val = row[0], ""
        else:
            key, raw_val = row[0], row[-1]
        pairs.append([key if key != "" else None, coerce_number(raw_val)])
    return pairs


# --------------------------------------------------------------------------- #
# diffing
# --------------------------------------------------------------------------- #

def values_differ(before, after, tolerance):
    """A difference is |a-b| > tolerance*max(1,|a|,|b|) for two numbers,
    else plain !=. None vs None is equal; None vs a number/string is not."""
    if (isinstance(before, (int, float)) and not isinstance(before, bool)
            and isinstance(after, (int, float)) and not isinstance(after, bool)):
        a, b = float(before), float(after)
        return abs(a - b) > tolerance * max(1.0, abs(a), abs(b))
    return before != after


def fmt_value(value):
    if value is None:
        return "(blank)"
    if isinstance(value, float):
        return "{0:.10g}".format(value)
    return str(value)


def md_escape(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_diff_table(diffs):
    headers = ["Measure", "Grouping", "Key", "Before", "After"]
    lines = ["| " + " | ".join(headers) + " |",
              "|" + "|".join(["---"] * len(headers)) + "|"]
    for measure, grouping, key, before, after in diffs:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            md_escape(measure), md_escape(grouping),
            md_escape("(blank)" if key is None else key),
            md_escape(before), md_escape(after)))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI: discover
# --------------------------------------------------------------------------- #

def cmd_discover(args):
    try:
        env = Environment(args.timeout)
        pbip_bare = os.path.basename(args.pbip)
        port, catalog = discover_catalog(env, pbip_bare)
    except VerifyError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2
    print(json.dumps({"port": port, "catalog": catalog}))
    return 0


# --------------------------------------------------------------------------- #
# CLI: baseline
# --------------------------------------------------------------------------- #

def cmd_baseline(args):
    try:
        env = Environment(args.timeout)
    except VerifyError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2
    pbip_bare = os.path.basename(args.pbip)
    try:
        catalog = resolve_catalog(env, args, pbip_bare)
    except VerifyError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2

    measures_out = {}
    any_ok = False
    for measure in args.measure:
        entry = {}
        try:
            entry["total"] = query_total(env, pbip_bare, catalog, measure)
            any_ok = True
        except QueryError as exc:
            entry["error"] = str(exc)
            print("warning: {0}: total query failed: {1}".format(measure, exc),
                  file=sys.stderr)
            measures_out[measure] = entry
            continue
        by = {}
        for column in args.by:
            try:
                by[column] = query_by(env, pbip_bare, catalog, measure, column,
                                       args.top)
            except QueryError as exc:
                by[column] = {"error": str(exc)}
                print("warning: {0} by {1}: query failed: {2}".format(
                    measure, column, exc), file=sys.stderr)
        entry["by"] = by
        measures_out[measure] = entry

    if not any_ok:
        print("error: every measure's total query failed -- nothing captured",
              file=sys.stderr)
        return 2

    doc = {
        "pbip": args.pbip,
        "captured": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "top": args.top,
        "measures": measures_out,
    }
    try:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
    except OSError as exc:
        print("error: could not write {0}: {1}".format(args.out, exc), file=sys.stderr)
        return 2
    print("{0}: {1} measure(s) captured -> {2}".format(
        pbip_bare, len(args.measure), args.out), file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# CLI: compare
# --------------------------------------------------------------------------- #

def cmd_compare(args):
    try:
        with io.open(args.baseline, encoding="utf-8") as fh:
            baseline = json.load(fh)
    except (OSError, ValueError) as exc:
        print("error: {0}: {1}".format(args.baseline, exc), file=sys.stderr)
        return 2

    try:
        env = Environment(args.timeout)
    except VerifyError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2
    pbip_bare = os.path.basename(args.pbip)
    try:
        catalog = resolve_catalog(env, args, pbip_bare)
    except VerifyError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 2

    top = baseline.get("top", 200)
    base_measures = baseline.get("measures", {})
    wanted = args.measure if args.measure else list(base_measures.keys())
    for name in wanted:
        if name not in base_measures:
            print("warning: {0}: not in baseline, skipped".format(name),
                  file=sys.stderr)
    wanted = [m for m in wanted if m in base_measures]
    if not wanted:
        print("error: no requested measure is present in the baseline", file=sys.stderr)
        return 2

    after_measures = {}
    diffs = []
    total_failures = 0
    partial_errors = 0

    for measure in wanted:
        base_entry = base_measures[measure]
        after_entry = {}
        try:
            after_total = query_total(env, pbip_bare, catalog, measure)
            after_entry["total"] = after_total
        except QueryError as exc:
            after_entry["error"] = str(exc)
            after_measures[measure] = after_entry
            diffs.append((measure, "total", None,
                          base_entry.get("total", base_entry.get("error")),
                          "ERROR: {0}".format(exc)))
            total_failures += 1
            partial_errors += 1
            continue

        if "error" in base_entry:
            diffs.append((measure, "total", None,
                          "ERROR: {0}".format(base_entry["error"]), after_total))
            partial_errors += 1
        else:
            base_total = base_entry.get("total")
            if values_differ(base_total, after_total, args.tolerance):
                diffs.append((measure, "total", None, base_total, after_total))

        after_by = {}
        for column, base_pairs in (base_entry.get("by") or {}).items():
            baseline_errored = isinstance(base_pairs, dict) and "error" in base_pairs
            try:
                after_pairs = query_by(env, pbip_bare, catalog, measure, column, top)
            except QueryError as exc:
                after_by[column] = {"error": str(exc)}
                diffs.append((measure, column, None, "OK" if not baseline_errored
                              else "ERROR: {0}".format(base_pairs["error"]),
                              "ERROR: {0}".format(exc)))
                partial_errors += 1
                continue
            after_by[column] = after_pairs
            if baseline_errored:
                diffs.append((measure, column, None,
                              "ERROR: {0}".format(base_pairs["error"]),
                              "see by-column result"))
                partial_errors += 1
                continue
            base_dict = dict((k, v) for k, v in base_pairs)
            after_dict = dict((k, v) for k, v in after_pairs)
            keys = sorted(set(base_dict) | set(after_dict),
                          key=lambda k: (k is None, "" if k is None else k))
            for key in keys:
                if key not in base_dict:
                    diffs.append((measure, column, key, "(missing)", after_dict[key]))
                elif key not in after_dict:
                    diffs.append((measure, column, key, base_dict[key], "(missing)"))
                elif values_differ(base_dict[key], after_dict[key], args.tolerance):
                    diffs.append((measure, column, key, base_dict[key], after_dict[key]))

        after_entry["by"] = after_by
        after_measures[measure] = after_entry

    if args.out:
        doc = {
            "pbip": args.pbip,
            "captured": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "top": top,
            "measures": after_measures,
        }
        try:
            with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False, sort_keys=True)
                fh.write("\n")
        except OSError as exc:
            print("warning: could not write {0}: {1}".format(args.out, exc),
                  file=sys.stderr)

    if total_failures == len(wanted):
        print("error: every requested measure's query failed against this "
              "Desktop instance", file=sys.stderr)
        return 2

    if diffs:
        print(render_diff_table(diffs))
        print("")
    n_diff_rows = len(diffs)
    if n_diff_rows or partial_errors:
        print("{0} difference(s)/error(s) across {1} measure(s) compared "
              "(tolerance {2}).".format(n_diff_rows, len(wanted), args.tolerance))
        return 1
    print("All {0} measure(s) equal (tolerance {1}).".format(
        len(wanted), args.tolerance))
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    ap = argparse.ArgumentParser(
        prog="daxopt-verify.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Prove a rewritten DAX measure returns the same values as before,\n"
            "by driving DAX Studio's dscmd.exe against a running Power BI\n"
            "Desktop instance: capture values before a change (baseline),\n"
            "then re-query and diff after it (compare)."),
        epilog=(
            "exit codes:\n"
            "  discover: 0 found, 2 no running Desktop instance\n"
            "  baseline: 0 written, 2 no catalog / every measure failed\n"
            "  compare:  0 all equal, 1 differences and/or partial query\n"
            "            errors, 2 no catalog / every measure failed / no\n"
            "            baseline\n"))
    sub = ap.add_subparsers(dest="command", required=True)

    common_pbip = argparse.ArgumentParser(add_help=False)
    common_pbip.add_argument("--pbip", required=True,
                              help="the .pbip file Desktop has open (a full path "
                                   "is fine -- only the bare file name is used, "
                                   "since that is all dscmd matches on)")
    common_pbip.add_argument("--timeout", type=float, default=300.0,
                              help="seconds to wait for each dscmd/powershell "
                                   "call (default: 300)")

    common_catalog = argparse.ArgumentParser(add_help=False)
    common_catalog.add_argument("--catalog",
                                 help="Desktop's Analysis Services catalog GUID "
                                      "(default: run discovery first)")

    ap_discover = sub.add_parser(
        "discover", parents=[common_pbip],
        help="find the running instance's port and catalog GUID")
    ap_discover.set_defaults(func=cmd_discover)

    ap_baseline = sub.add_parser(
        "baseline", parents=[common_pbip, common_catalog],
        help="capture measure values before a change")
    ap_baseline.add_argument("--out", required=True, help="baseline JSON to write")
    ap_baseline.add_argument("--measure", action="append", required=True,
                              metavar="DAX",
                              help="a measure as written in DAX, e.g. "
                                   "'[Sales Amount]' (repeatable)")
    ap_baseline.add_argument("--by", action="append", default=[],
                              metavar="COLUMN",
                              help="a fully qualified column to group by, e.g. "
                                   "\"'Date'[Year]\" (repeatable; none = total "
                                   "only)")
    ap_baseline.add_argument("--top", type=int, default=200,
                              help="max rows per --by column (default: 200)")
    ap_baseline.set_defaults(func=cmd_baseline)

    ap_compare = sub.add_parser(
        "compare", parents=[common_pbip, common_catalog],
        help="re-query after a change and diff against a baseline")
    ap_compare.add_argument("--baseline", required=True,
                             help="baseline JSON from a prior `baseline` run")
    ap_compare.add_argument("--out", help="write the re-queried \"after\" values "
                                           "to this JSON, in the same shape as "
                                           "--baseline's --out")
    ap_compare.add_argument("--tolerance", type=float, default=1e-9,
                             help="relative+absolute tolerance for numeric "
                                  "comparison (default: 1e-9)")
    ap_compare.add_argument("--measure", action="append",
                             metavar="DAX",
                             help="restrict to these measures (repeatable; "
                                  "default: every measure in the baseline)")
    ap_compare.set_defaults(func=cmd_compare)

    return ap


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
