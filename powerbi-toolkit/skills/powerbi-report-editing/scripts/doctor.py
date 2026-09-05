#!/usr/bin/env python3
"""Run every Power BI check over a repo and print one prioritized report.

Seven separate commands is friction, and friction means the checks do not get
run. This is the single habit before committing:

    python3 <skill>/scripts/doctor.py [repo-root] [--detail]

Exit 0 when nothing blocking was found, 1 when a check reported a real defect,
2 when there was nothing here to check at all (no model and no report under the
root -- almost always the wrong directory).

Advisory findings (naming backlog, description coverage, theme drift, formatting
that fights the theme) are shown but never fail the run -- they are backlog, not
breakage.

`--tools` runs preflight.py instead: are the external tools (te, the PBIR
authoring CLI, the Desktop bridge) installed? That is a separate question from
"is the repo sound", which is why it is a mode and not an extra check -- none of
the seven checks shells out to anything, so a failing check is never a missing
tool and prepending a tool report to every run would just be noise.

Respects .powerbi-scan-ignore, like the individual checks.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

HERE = os.path.dirname(os.path.abspath(__file__))

# (script, args, blocking?)  -- blocking checks decide the exit code
CHECKS = [
    ("check-visual-projections.py", [], True),
    ("check-m-escaping.py", [], True),
    ("check-layout-file.py", [], False),
    ("check-measure-descriptions.py", [], False),
    ("measure-catalog.py", ["--check"], False),
    ("check-theme-drift.py", [], False),
    ("find-theme-overrides.py", [], False),
]


def run(script, args, root):
    path = os.path.join(HERE, script)
    if not os.path.isfile(path):
        return None, f"{script}: not found next to doctor.py"
    try:
        # encoding is not optional here: these checks print em dashes and field
        # names, and on a cp1252 Windows console text=True alone raises.
        p = subprocess.run([sys.executable, path, root] + args,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900)
    except subprocess.TimeoutExpired:
        return None, f"{script}: timed out"
    return p.returncode, p.stdout.rstrip() + (("\n" + p.stderr.rstrip()) if p.stderr.strip() else "")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="doctor.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Run every Power BI structural check over a repo and print one\n"
            "prioritized report. Seven separate commands is friction, and friction\n"
            "means the checks do not get run -- this is the single habit before\n"
            "committing. It only reads; each check is read-only.\n\n"
            "--tools switches to the other question -- are the external tools\n"
            "installed? -- by running preflight.py instead of the checks."),
        epilog=(
            "exit codes:\n"
            "  0  no blocking defect (advisory backlog may still be listed)\n"
            "  1  a blocking check failed -- fix before committing\n"
            "  2  nothing to check: every check reported n/a, so there is no model\n"
            "     and no report under this root (wrong directory?)\n\n"
            "With --tools the codes are preflight.py's: 0 all tools present, 1 one\n"
            "is missing or expired, 2 not even Python is usable."))
    ap.add_argument("root", nargs="?", default=".",
                    help="repo root to check (default: the current directory)")
    ap.add_argument("--detail", action="store_true",
                    help="print each check's full output, not just its last lines")
    ap.add_argument("--tools", action="store_true",
                    help="check the external tools (te, powerbi-report-author, the "
                         "Desktop bridge) instead of the repo -- runs preflight.py")
    a = ap.parse_args(argv)
    if a.tools:
        import preflight
        return preflight.main([])
    detail = a.detail
    root = os.path.abspath(a.root)

    print(f"Power BI doctor -- {root}\n" + "=" * 72)
    blocking_failed, notes = [], []
    ran = na = 0

    for script, extra, blocking in CHECKS:
        code, out = run(script, extra, root)
        label = script.replace("check-", "").replace(".py", "")
        if code is None:
            print(f"\n## {label}\n  SKIPPED -- {out}")
            continue
        summary = [l for l in out.splitlines() if l.strip()]
        ran += 1
        if code == 2:
            state = "n/a"
            na += 1
        elif code == 1 and blocking:
            state = "FAIL"
            blocking_failed.append(label)
        elif code == 1:
            state = "note"
            notes.append(label)
        elif code == 0:
            state = "ok"
        else:
            # A traceback, a signal, a check that grew a new exit code: whatever
            # it is, it is not a clean pass, and reporting it as one is how a
            # broken check goes unnoticed for months.
            state = f"ERROR (exit {code})"
            blocking_failed.append(f"{label} (crashed, exit {code})")
        print(f"\n## {label}  [{state}]")
        print("\n".join("  " + l for l in (summary if detail else summary[-6:])))

    print("\n" + "=" * 72)
    if ran and na == ran:
        print(f"NOTHING TO CHECK: every check reported n/a for {root} --")
        print("no semantic model and no report were found anywhere under it.")
        print("This is almost always the wrong directory; point doctor.py at the")
        print("repo root that holds the *.Report / *.SemanticModel folders.")
        return 2
    if blocking_failed:
        print("BLOCKING: " + ", ".join(blocking_failed) + " -- fix before committing.")
    else:
        print("No blocking defects.")
    if notes:
        print("Backlog (not blocking): " + ", ".join(notes))
    print("Structural checks pass != the report looks right. Screenshot the pages you changed.")
    return 1 if blocking_failed else 0


if __name__ == "__main__":
    sys.exit(main())
