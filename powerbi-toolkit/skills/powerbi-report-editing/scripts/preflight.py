#!/usr/bin/env python3
"""Check that the external tools this skill assumes are actually installed.

The skill drives four tools it does not install -- the Tabular Editor CLI, the
PBIR authoring CLI, the Power BI Desktop bridge and (optionally) the Modeling
MCP server -- and the sibling dax-optimizer-report skill adds two optional ones,
the DAX Optimizer CLI and DAX Studio's dscmd.exe. Until now nothing verified
them, so a missing one surfaced as
`command not found` in the middle of an edit, several steps after the point
where it could still have been planned around.

    python3 preflight.py [--all] [--quick]

Prints one row per tool -- found (with its version) or missing -- then, for
anything that is missing or degraded, what stops working without it and how to
install it. The platform is detected first: Power BI Desktop is Windows-only, so
on Linux and macOS the bridge and every live-model operation are reported as
"not available on this platform" rather than as something to go install.

It also reads the Tabular Editor early-preview expiry date out of `te --help`.
The tested build (0.5.2) is an early preview that stops running on a fixed date,
and after that `te format` and offline TMDL scripting fail for a reason nothing
else in the toolkit would explain.

Exit 0 when everything usable on this platform is present, 1 when something is
missing but part of the toolkit still works, 2 when nothing does (no usable
Python).
"""
import argparse
import datetime
import glob
import io
import os
import platform
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

MIN_PYTHON = (3, 8)
EXPIRY_WARN_DAYS = 30

# Status values. REQUIRED/RECOMMENDED tools decide the exit code; OPTIONAL ones
# and anything the platform cannot have never do.
OK, MISSING, NA, DEGRADED = "ok", "MISSING", "n/a", "degraded"


class Tool(object):
    """One row of the report."""

    def __init__(self, name, status, version=None, tier="required",
                 without=(), still=(), install=(), notes=()):
        self.name = name
        self.status = status
        self.version = version
        self.tier = tier            # required | recommended | optional
        self.without = list(without)    # what stops working
        self.still = list(still)        # what keeps working anyway
        self.install = list(install)    # how to get it
        self.notes = list(notes)        # warnings worth printing even when ok

    @property
    def counts_against(self):
        return self.status in (MISSING, DEGRADED) and self.tier in ("required", "recommended")


# --------------------------------------------------------------------------- #
# environment
# --------------------------------------------------------------------------- #

def detect_platform():
    """-> (key, human label). key in {wsl, windows, linux, macos, unknown}."""
    if sys.platform == "win32":
        return "windows", "Windows %s" % platform.release()
    if sys.platform == "darwin":
        release = platform.mac_ver()[0]
        return "macos", ("macOS %s" % release).strip()
    if sys.platform.startswith("linux"):
        release = platform.release()
        marker = release.lower()
        try:
            with io.open("/proc/version", encoding="utf-8", errors="replace") as fh:
                marker += " " + fh.read().lower()
        except OSError:
            pass
        if "microsoft" in marker or os.environ.get("WSL_DISTRO_NAME"):
            flavor = "WSL2" if "wsl2" in marker or "-microsoft-standard" in marker else "WSL"
            return "wsl", "%s on %s (%s)" % (
                flavor, os.environ.get("WSL_DISTRO_NAME", "Linux"), release)
        return "linux", "Linux %s" % release
    return "unknown", sys.platform


def has_desktop(plat):
    """Can Power BI Desktop possibly run here? It is Windows-only."""
    return plat in ("windows", "wsl")


def run(cmd, timeout=60):
    """-> (returncode, combined output). None returncode when it could not run."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def first_version(text):
    """The first version-looking token in a tool's output, or None."""
    m = re.search(r"\b(\d+\.\d+(?:\.\d+){0,2})\b", text or "")
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# the tools
# --------------------------------------------------------------------------- #

def check_python():
    running = ".".join(str(n) for n in sys.version_info[:3])
    on_path = shutil.which("python3") or shutil.which("python")
    notes = []
    if sys.version_info < MIN_PYTHON:
        return Tool(
            "python3", MISSING, running,
            without=["every script in this skill -- the checkers, doctor.py and "
                     "the bulk tools all need Python %d.%d+."
                     % MIN_PYTHON],
            install=["Install Python %d.%d or newer and re-run." % MIN_PYTHON])
    if not on_path:
        notes.append("running interpreter is fine, but no `python3` on PATH -- "
                     "the documented `python3 <script>` invocations will fail.")
    else:
        code, out = run([on_path, "--version"], timeout=30)
        found = first_version(out)
        if found and tuple(int(x) for x in found.split(".")[:2]) < MIN_PYTHON:
            notes.append("`python3` on PATH is %s, older than the %d.%d minimum; "
                         "this script is running under %s."
                         % (found, MIN_PYTHON[0], MIN_PYTHON[1], running))
    return Tool("python3", OK, running, notes=notes)


def parse_expiry(text):
    """Pull the early-preview expiry date out of te's banner, or None.

    The banner reads `Early preview expires in 25 day(s), on 2026-09-30.` on the
    tested build. Anything else -- a wording change, a build with no banner at
    all, a locale that formats the date differently -- means no date, which is
    fine: an unknown expiry is simply not reported. Never let this raise.
    """
    if not text:
        return None
    for pattern in (r"expir\w*[^.\n]*?\bon\s+(\d{4})-(\d{2})-(\d{2})",
                    r"(?:early preview|preview build)[^.\n]*?(\d{4})-(\d{2})-(\d{2})"):
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def check_tabular_editor():
    install = [
        "Download the CLI build for your OS from https://tabulareditor.com/downloads,",
        "then:  install -m 755 ~/Downloads/te ~/.local/bin/te",
    ]
    without = [
        "`backfill-dax-blocks.py --format` (DAX formatting),",
        "scripted TMDL edits: te ls/get/find/deps/set/add/mv/rm/replace, bpa,",
        "validate, format, diff, script.",
    ]
    still = [
        "all seven doctor checks, name-visuals.py, measure-catalog.py, and",
        "backfill-dax-blocks.py without --format -- none of them shell out to te.",
    ]
    if not shutil.which("te"):
        return Tool("te (Tabular Editor CLI)", MISSING, tier="required",
                    without=without, still=still, install=install)

    code, out = run(["te", "--version"], timeout=60)
    version = first_version(out)
    if code is None:
        return Tool("te (Tabular Editor CLI)", DEGRADED, tier="required",
                    without=without, still=still, install=install,
                    notes=["`te` is on PATH but would not run -- not executable, "
                           "or the wrong build for this OS."])

    # The expiry banner rides on --help, not on --version.
    _hcode, help_out = run(["te", "--help"], timeout=60)
    expiry = parse_expiry((out or "") + "\n" + (help_out or ""))
    notes, status = [], OK
    if expiry:
        left = (expiry - datetime.date.today()).days
        if left < 0:
            status = DEGRADED
            notes.append("EXPIRED early preview: this build stopped working on %s. "
                         "`te format` and offline TMDL operations fail until you "
                         "download a newer build from "
                         "https://tabulareditor.com/downloads."
                         % expiry.isoformat())
        elif left <= EXPIRY_WARN_DAYS:
            notes.append("early preview expires on %s -- %d day(s) left. After that "
                         "`te format` and offline TMDL operations stop working; "
                         "download a newer build from "
                         "https://tabulareditor.com/downloads."
                         % (expiry.isoformat(), left))
        else:
            notes.append("early preview build, expires on %s (%d days left)."
                         % (expiry.isoformat(), left))
    return Tool("te (Tabular Editor CLI)", status, version, tier="required",
                without=without, still=still, install=install, notes=notes)


def check_report_author():
    install = ["npm install -g powerbi-report-author    (needs Node on PATH)"]
    without = [
        "powerbi-report-author validate, and preview-visuals / preview-pages /",
        "preview-filters / preview-themes for navigating granular PBIR JSON.",
    ]
    still = ["everything else -- the checkers read the JSON directly."]
    if not shutil.which("powerbi-report-author"):
        return Tool("powerbi-report-author", MISSING, tier="required",
                    without=without, still=still, install=install)
    code, out = run(["powerbi-report-author", "--version"], timeout=60)
    if code is None:
        return Tool("powerbi-report-author", DEGRADED, tier="required",
                    without=without, still=still, install=install,
                    notes=["on PATH but would not run."])
    return Tool("powerbi-report-author", OK, first_version(out), tier="required",
                without=without, still=still, install=install)


def check_powershell(plat):
    """Only meaningful where Windows is reachable."""
    without = ["the Desktop bridge, which must be called through it from WSL."]
    if not has_desktop(plat):
        return Tool("powershell.exe", NA, tier="optional",
                    notes=["Windows interop only -- nothing on this platform uses it."])
    if plat == "windows":
        exe = shutil.which("powershell") or shutil.which("powershell.exe") \
            or shutil.which("pwsh")
    else:
        exe = shutil.which("powershell.exe")
    if not exe:
        return Tool("powershell.exe", MISSING, tier="recommended",
                    without=without,
                    still=["every offline operation -- see the Desktop bridge row."],
                    install=["On WSL this comes from Windows interop; check that",
                             "/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0 is on PATH",
                             "and that interop is enabled in /etc/wsl.conf."])
    return Tool("powershell.exe", OK, "found", tier="recommended",
                without=without,
                still=["every offline operation -- see the Desktop bridge row."],
                )


def check_desktop_bridge(plat, quick):
    """`powerbi-desktop`, which on WSL is only valid through powershell.exe.

    A WSL PATH often resolves the Windows npm shim directly; calling it that way
    is exactly the mistake the skill warns about, so the probe goes through
    powershell.exe and the direct hit is reported as not counting.
    """
    without = [
        "the safe edit protocol's `status` check, `reload` and `screenshot`,",
        "and verifying a built measure catalog in a running Desktop.",
    ]
    still = [
        "offline TMDL and PBIR editing, all seven doctor checks, the bulk tools",
        "(name-visuals, backfill-dax-blocks, measure-catalog), theme work.",
    ]
    if not has_desktop(plat):
        return Tool("powerbi-desktop (bridge)", NA, tier="optional",
                    without=without, still=still,
                    notes=["Power BI Desktop is Windows-only, so there is nothing "
                           "here to drive -- this is not something to install."])
    install = ['powershell.exe -Command "npm install -g powerbi-desktop"',
               "(Power BI Desktop itself must be installed on Windows too.)"]
    if quick:
        return Tool("powerbi-desktop (bridge)", NA, tier="optional",
                    notes=["--quick: the bridge probe was skipped."])
    if plat == "windows":
        if not shutil.which("powerbi-desktop"):
            return Tool("powerbi-desktop (bridge)", MISSING, tier="recommended",
                        without=without, still=still, install=install)
        code, out = run(["powerbi-desktop", "--version"], timeout=90)
    else:
        if not shutil.which("powershell.exe"):
            return Tool("powerbi-desktop (bridge)", MISSING, tier="recommended",
                        without=without, still=still,
                        install=["needs powershell.exe first -- see the row above."])
        code, out = run(["powershell.exe", "-NoProfile", "-Command",
                         "powerbi-desktop --version"], timeout=90)
    version = first_version(out)
    if code != 0 or not version:
        return Tool("powerbi-desktop (bridge)", MISSING, tier="recommended",
                    without=without, still=still, install=install,
                    notes=["probe returned no version" +
                           (" (exit %s)" % code if code is not None else "")])
    notes = []
    if plat == "wsl" and shutil.which("powerbi-desktop"):
        notes.append("a `powerbi-desktop` on the WSL PATH is the Windows npm shim; "
                     "always call it as powershell.exe -NoProfile -Command "
                     '"powerbi-desktop <cmd>" anyway.')
    return Tool("powerbi-desktop (bridge)", OK, version, tier="recommended",
                without=without, still=still, notes=notes)


MCP_NAME = "powerbi-modeling"


def check_modeling_mcp(plat):
    """Optional. Registration lives in Claude's own config, so look there.

    Deliberately no `claude mcp list`: that probes every registered server over
    the network and takes seconds. Reading the config says whether it is
    registered, which is the question preflight is here to answer.
    """
    without = ["editing a *live* model (open in Desktop or in the Service) through "
               "MCP; the fallbacks are the Desktop bridge or te.exe --local."]
    still = ["all offline work -- the MCP server was never in that path."]
    binaries = sorted(glob.glob(os.path.expanduser(
        "~/.vscode-server/extensions/analysis-services.powerbi-modeling-mcp-*/"
        "server/powerbi-modeling-mcp*")))
    binaries += sorted(glob.glob(os.path.expanduser(
        "~/.vscode/extensions/analysis-services.powerbi-modeling-mcp-*/"
        "server/powerbi-modeling-mcp*")))
    registered = False
    for path in (os.path.expanduser("~/.claude.json"),
                 os.path.expanduser("~/.claude/settings.json"),
                 os.path.join(os.getcwd(), ".mcp.json")):
        try:
            with io.open(path, encoding="utf-8", errors="replace") as fh:
                if MCP_NAME in fh.read():
                    registered = True
                    break
        except (OSError, ValueError):
            continue
    if registered:
        return Tool("Power BI Modeling MCP", OK, "registered", tier="optional",
                    without=without, still=still,
                    notes=["confirm it is actually connected with `claude mcp list`."])
    install = ["claude mcp add powerbi-modeling -- <extension>/server/"
               "powerbi-modeling-mcp --readonly",
               "It ships inside the analysis-services.powerbi-modeling-mcp VS Code",
               "extension. Register it --readonly; the default mode writes to a",
               "live model without confirming."]
    if binaries:
        install.insert(0, "found but not registered: %s" % binaries[0])
    if not has_desktop(plat):
        return Tool("Power BI Modeling MCP", NA, tier="optional",
                    without=without, still=still,
                    notes=["optional, and there is no local Desktop on this platform "
                           "to point it at (it can still reach a published model)."])
    return Tool("Power BI Modeling MCP", MISSING, "not registered", tier="optional",
                without=without, still=still, install=install)


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def check_dax_optimizer_cli(plat, quick):
    """Optional: the DAX Optimizer CLI (`daxoptimizer`, NuGet Dax.Optimizer.CLI).

    Only the dax-optimizer-report skill uses it. It is a cross-platform .NET
    tool, but this toolkit runs it on the Windows side (the browser login and
    the VPAX extraction from Desktop live there), so on WSL the probe goes
    through powershell.exe like the bridge does.
    """
    without = ["the dax-optimizer-report skill: uploading a VPAX to DAX Optimizer "
               "and fetching the analysis JSON."]
    still = ["everything else in the toolkit; and daxopt-report.py can still render "
             "a result zip someone else produced."]
    install = ['powershell.exe -NoProfile -Command "dotnet tool install --global '
               'Dax.Optimizer.CLI --add-source https://api.nuget.org/v3/index.json"',
               "(needs the .NET SDK on Windows; without --add-source a machine whose",
               "NuGet config lacks nuget.org fails with 'not found in NuGet feeds')."]
    if quick:
        return Tool("daxoptimizer (DAX Optimizer CLI)", NA, tier="optional",
                    notes=["--quick: the probe was skipped."])
    if plat == "windows":
        if not shutil.which("daxoptimizer"):
            return Tool("daxoptimizer (DAX Optimizer CLI)", MISSING, tier="optional",
                        without=without, still=still, install=install)
        code, out = run(["daxoptimizer", "--version"], timeout=60)
    elif plat == "wsl":
        if not shutil.which("powershell.exe"):
            return Tool("daxoptimizer (DAX Optimizer CLI)", MISSING, tier="optional",
                        without=without, still=still,
                        install=["needs powershell.exe first -- see the row above."])
        code, out = run(["powershell.exe", "-NoProfile", "-Command",
                         "daxoptimizer --version"], timeout=60)
    else:
        exe = shutil.which("daxoptimizer")
        if not exe:
            return Tool("daxoptimizer (DAX Optimizer CLI)", MISSING, tier="optional",
                        without=without, still=still,
                        install=["dotnet tool install --global Dax.Optimizer.CLI",
                                 "(cross-platform; the browser login must be able to "
                                 "open a browser from here)."])
        code, out = run([exe, "--version"], timeout=60)
    version = first_version(out)
    if code != 0 or not version:
        return Tool("daxoptimizer (DAX Optimizer CLI)", MISSING, tier="optional",
                    without=without, still=still, install=install,
                    notes=["probe returned no version" +
                           (" (exit %s)" % code if code is not None else "")])
    return Tool("daxoptimizer (DAX Optimizer CLI)", OK, version, tier="optional",
                without=without, still=still,
                notes=["login state is not checked here -- the skill runs "
                       "`daxoptimizer account show` before it needs the service."])


DSCMD_WINDOWS = r"C:\Program Files\DAX Studio\dscmd.exe"
DSCMD_WSL = "/mnt/c/Program Files/DAX Studio/dscmd.exe"


def check_dax_studio_cli(plat):
    """Optional: DAX Studio's `dscmd.exe`, the VPAX extractor for a running Desktop.

    Windows-only by nature (it talks to the local Analysis Services instance
    that Power BI Desktop starts). The version is in the banner of any command.
    """
    without = ["extracting a VPAX from a running Power BI Desktop for the "
               "dax-optimizer-report skill (the `desktop` source)."]
    still = ["the `file` source: a .vpax exported from DAX Studio's GUI, "
             "Tabular Editor 3 or Bravo."]
    install = ["Install DAX Studio 3.x from https://daxstudio.org (the CLI ships "
               "with it, as dscmd.exe next to DaxStudio.exe)."]
    if not has_desktop(plat):
        return Tool("dscmd.exe (DAX Studio CLI)", NA, tier="optional",
                    without=without, still=still,
                    notes=["needs a Windows Power BI Desktop to read from -- "
                           "not something to install here."])
    exe = DSCMD_WINDOWS if plat == "windows" else DSCMD_WSL
    if not os.path.isfile(exe):
        return Tool("dscmd.exe (DAX Studio CLI)", MISSING, tier="optional",
                    without=without, still=still, install=install)
    code, out = run([exe, "--help"], timeout=60)
    # Banner reads "DSCMD  v3.6.0"; first_version() would stop at the word
    # boundary after the "v" and report "6.0".
    m = re.search(r"\bv(\d+\.\d+(?:\.\d+){0,2})\b", out or "")
    version = m.group(1) if m else first_version(out)
    if not version:
        return Tool("dscmd.exe (DAX Studio CLI)", OK, "found", tier="optional",
                    without=without, still=still,
                    notes=["present, but its banner printed no version."])
    return Tool("dscmd.exe (DAX Studio CLI)", OK, version, tier="optional",
                without=without, still=still)


def print_table(tools):
    head = ("Tool", "Status", "Version")
    rows = [(t.name, t.status, t.version or "-") for t in tools]
    widths = [max(len(head[i]), max(len(r[i]) for r in rows)) for i in range(3)]
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(head)).rstrip()
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip())


def print_detail(tool, show_all=False):
    header = {OK: "ok", MISSING: "MISSING", NA: "not available here",
              DEGRADED: "degraded"}[tool.status]
    print("\n## %s -- %s" % (tool.name, header))
    for note in tool.notes:
        print("   note:        " + note)
    # A tool that is present and working does not need its whole consequence
    # block reprinted; its note, if any, is the whole point.
    if tool.status == OK and not show_all:
        return
    if tool.without:
        print("   Without it:  " + tool.without[0])
        for extra in tool.without[1:]:
            print("                " + extra)
    if tool.still:
        print("   Still works: " + tool.still[0])
        for extra in tool.still[1:]:
            print("                " + extra)
    if tool.install and tool.status in (MISSING, DEGRADED):
        print("   Install:     " + tool.install[0])
        for extra in tool.install[1:]:
            print("                " + extra)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="preflight.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Check the external tools this skill drives but does not install:\n"
            "the Tabular Editor CLI, the PBIR authoring CLI, the Power BI Desktop\n"
            "bridge and the optional Modeling MCP server. Run it before a task\n"
            "that needs one of them -- a missing tool found here is a plan, a\n"
            "missing tool found later is a half-finished edit.\n\n"
            "The platform is detected first: Power BI Desktop is Windows-only, so\n"
            "on Linux and macOS the bridge and live-model work are reported as not\n"
            "available here rather than as something to install. It only reads and\n"
            "runs --version/--help; it changes nothing."),
        epilog=(
            "It also reads the Tabular Editor early-preview expiry date out of its\n"
            "banner. The tested build is a preview that stops running on a fixed\n"
            "date; after that `te format` and offline TMDL scripting fail with no\n"
            "hint as to why.\n\n"
            "exit codes:\n"
            "  0  everything usable on this platform is present\n"
            "  1  something is missing or expired -- part of the toolkit still works,\n"
            "     and the report says which part\n"
            "  2  unusable: no Python new enough to run the scripts at all"))
    ap.add_argument("--all", action="store_true", dest="show_all",
                    help="print the 'without it / install' detail for every tool, "
                         "not just the ones that need attention")
    ap.add_argument("--quick", action="store_true",
                    help="skip the Desktop bridge probe, which shells out through "
                         "powershell.exe and can take a few seconds")
    a = ap.parse_args(argv)

    plat, plat_label = detect_platform()
    print("Power BI preflight -- %s" % plat_label)
    print("=" * 72)

    python_tool = check_python()
    if python_tool.status == MISSING:
        print_table([python_tool])
        print_detail(python_tool)
        print("\n" + "=" * 72)
        print("UNUSABLE: nothing in this toolkit runs without Python %d.%d+."
              % MIN_PYTHON)
        return 2

    tools = [python_tool, check_tabular_editor(), check_report_author(),
             check_powershell(plat), check_desktop_bridge(plat, a.quick),
             check_modeling_mcp(plat),
             check_dax_optimizer_cli(plat, a.quick), check_dax_studio_cli(plat)]

    print_table(tools)
    for tool in tools:
        if a.show_all or tool.status != OK or tool.notes:
            print_detail(tool, a.show_all)

    print("\n" + "=" * 72)
    if not has_desktop(plat):
        print("No Power BI Desktop on this platform. Still fully available:")
        print("  offline TMDL and PBIR editing, all seven doctor.py checks, and the")
        print("  bulk tools (name-visuals, backfill-dax-blocks, measure-catalog).")
        print("Out of reach: the safe edit protocol's status/reload, screenshots,")
        print("  verifying a built catalog, and live-model edits.")
    missing = [t.name for t in tools if t.counts_against and t.status == MISSING]
    degraded = [t.name for t in tools if t.counts_against and t.status == DEGRADED]
    optional = [t.name for t in tools
                if t.status == MISSING and t.tier == "optional"]
    if optional:
        print("Optional, not installed: " + ", ".join(optional) + ".")
    if missing:
        print("MISSING: " + ", ".join(missing) + ".")
    if degraded:
        print("PRESENT BUT UNUSABLE: " + ", ".join(degraded) +
              " -- see the note above.")
    if missing or degraded:
        print("Say which tool and what it blocks before starting the task; the "
              "rest of the")
        print("toolkit still works, and the rows above say which part.")
        return 1
    print("All tools available on this platform are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
