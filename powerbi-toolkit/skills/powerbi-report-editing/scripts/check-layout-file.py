#!/usr/bin/env python3
"""Report the state of a project's POWERBI-LAYOUT.md.

The skill holds no formatting values -- they live only in this per-project file --
so it matters that the file exists, is current, and actually belongs to this
project. Run it before layout/formatting work:

    python3 <skill>/scripts/check-layout-file.py [project-root]

Reports: template version, which required sections are missing, unreviewed status,
leftover {{PLACEHOLDERS}}, and whether the title names a DIFFERENT project (which
is what a copy-pasted file from another repo looks like).

The directory walk skips dead copies of the project tree -- .claude/worktrees,
node_modules, .git, __pycache__, .venv (and any other dotdir) -- so an old git
worktree under the repo is not searched alongside the real tree.

Exit 0 = current and complete, 1 = needs attention (including: the repo holds
reports but no layout file), 2 = nothing to check here at all.
"""
import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

CURRENT_VERSION = 2
FILENAME = "POWERBI-LAYOUT.md"

REQUIRED = [
    "Page canvas",
    "Grid & spacing",
    "Header / title band",
    "Slicers",
    "Visual sizing & rows",
    "Naming",
    "Typography, colors & theme",
    "Placeholders & shorthand",
    "Copying another report's structure",
    "Project deviations & validator exceptions",
]

VERSION_RE = re.compile(r"<!--\s*layout-template-version:\s*(\d+)\s*-->")
TITLE_RE = re.compile(r"^#\s+(.*)$", re.MULTILINE)
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def find_layout_file(root):
    direct = os.path.join(root, FILENAME)
    if os.path.isfile(direct):
        return direct
    for dirpath, dirnames, filenames in _common.walk(
            root, prune=lambda _d, name: name.startswith(".") or name == "node_modules"):
        if FILENAME in filenames:
            return os.path.join(dirpath, FILENAME)
        if dirpath.count(os.sep) - root.count(os.sep) > 2:
            dirnames[:] = []
    return None


def has_powerbi_content(root):
    """True when the repo actually holds Power BI artefacts. A missing layout
    file next to real reports is a finding; a missing one in a directory with no
    reports at all just means this check does not apply here."""
    for _dirpath, dirnames, _filenames in _common.walk(root):
        for d in dirnames:
            if d.endswith(".Report") or d.endswith(".SemanticModel"):
                return True
    return False


def build_parser():
    ap = argparse.ArgumentParser(
        prog="check-layout-file.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Report the state of a project's POWERBI-LAYOUT.md -- the per-project\n"
            "file that holds every layout, sizing, naming and formatting value the\n"
            "skill itself deliberately does not carry. Run it before any layout or\n"
            "formatting work.\n\n"
            "It reports the template version, which required sections are missing,\n"
            "whether the values are still UNREVIEWED template defaults, leftover\n"
            "{{PLACEHOLDERS}}, and whether the title names a DIFFERENT project --\n"
            "which is what a file copy-pasted from another repo looks like, values\n"
            "and all. It reads only; nothing is written."),
        epilog=(
            "exit codes:\n"
            "  0  a layout file was found and is current and complete\n"
            "  1  something to raise with the user: an outdated or incomplete file,\n"
            "     or no layout file at all in a repo that does hold reports\n"
            "  2  the check does not apply -- no layout file and no *.Report or\n"
            "     *.SemanticModel anywhere under <root> (wrong directory?)\n\n"
            "Respects .powerbi-scan-ignore and skips worktrees, dotdirs,\n"
            "node_modules, .git, __pycache__ and .venv."))
    ap.add_argument("root", nargs="?", default=".",
                    help="project root to inspect (default: the current directory)")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = os.path.abspath(args.root)
    _common.load_ignore(root)
    path = find_layout_file(root)
    if not path:
        print(f"NO LAYOUT FILE under {root}")
        print(f"  -> generate one from references/layout-standard-template.md as {FILENAME}")
        print("     before doing any layout, sizing, naming or formatting work.")
        if has_powerbi_content(root):
            # Reports are here and the file that governs their layout is not:
            # that is a finding, not a check that cannot run.
            print("     This repo DOES hold Power BI reports/models, so the file is missing,")
            print("     not merely inapplicable.")
            return 1
        print("     (No *.Report or *.SemanticModel found here either -- if you expected")
        print("      some, this is probably the wrong directory.)")
        return 2

    text = io.open(path, encoding="utf-8").read()
    print(f"layout file: {path}")

    issues = []

    m = VERSION_RE.search(text)
    version = int(m.group(1)) if m else None
    if version is None:
        print(f"  version   : UNVERSIONED (predates template v{CURRENT_VERSION})")
        issues.append("written against an older template -- offer to migrate")
    elif version < CURRENT_VERSION:
        print(f"  version   : v{version} (current is v{CURRENT_VERSION})")
        issues.append(f"template v{version} -- offer to migrate to v{CURRENT_VERSION}")
    else:
        print(f"  version   : v{version} (current)")

    headings = [_norm(h) for h in re.findall(r"^#{2,3}\s+(.*)$", text, re.MULTILINE)]
    missing = [s for s in REQUIRED if not any(_norm(s) in h for h in headings)]
    if missing:
        print(f"  sections  : {len(REQUIRED) - len(missing)}/{len(REQUIRED)} present")
        for s in missing:
            print(f"      MISSING  {s}")
        issues.append(f"{len(missing)} required section(s) missing")
    else:
        print(f"  sections  : {len(REQUIRED)}/{len(REQUIRED)} present")

    titles = TITLE_RE.findall(text)
    if titles:
        title = titles[0].strip()
        named = title.split("—")[-1].strip() if "—" in title else ""
        project = os.path.basename(root.rstrip(os.sep))
        print(f"  title     : {title}")
        if named and _norm(named) not in _norm(project) and _norm(project) not in _norm(named):
            print(f"      WARNING  title names {named!r} but the project directory is {project!r}")
            print("               -- a file copy-pasted from another repo carries that repo's")
            print("                  VALUES too; do not assume they were meant for this project.")
            issues.append(f"title names a different project ({named})")

    if "UNREVIEWED" in text:
        print("  status    : UNREVIEWED DEFAULT -- values are template defaults, not decisions")
        issues.append("never reviewed for this project")

    left = sorted(set(PLACEHOLDER_RE.findall(text)))
    if left:
        print(f"  placeholders left: {', '.join(left)}")
        issues.append(f"{len(left)} unfilled placeholder(s)")

    print()
    if issues:
        print(f"{len(issues)} thing(s) to raise with the user:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("layout file is current and complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
