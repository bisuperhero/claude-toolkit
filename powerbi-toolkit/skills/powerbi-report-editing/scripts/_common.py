#!/usr/bin/env python3
"""Helpers shared by every Power BI script in this directory.

All of these scripts scan the same kind of tree -- a repo holding `*.Report` and
`*.SemanticModel` folders -- and they used to carry byte-identical copies of the
same handful of helpers, which then drifted apart one copy at a time. This module
holds the single version of each. Import it the way doctor.py finds its siblings:

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _common

Nothing here changes what the scripts report; it only removes the duplicates.
"""
import glob
import io
import os
import re
import sys

IGNORE_FILE = ".powerbi-scan-ignore"

# Directories that never hold a "real" copy of the project tree: git worktrees
# checked out under .claude (used for parallel agent work -- a worktree can
# carry a full clone of the project and silently double-count everything in it),
# vendored deps, VCS internals, caches and virtualenvs.
EXCLUDE_SEGMENTS = {"node_modules", ".git", "__pycache__", ".venv"}

_IGNORE_PREFIXES = []


# --------------------------------------------------------------------------- #
# console
# --------------------------------------------------------------------------- #

def force_utf8_stdout():
    """Print UTF-8 whatever the console claims to be.

    These scripts print em dashes, ellipses and whatever the model calls its
    fields; on a Windows console defaulting to cp1252 that is a hard
    UnicodeEncodeError halfway through a report. `reconfigure` exists from
    Python 3.7 on -- older interpreters and replaced streams just keep theirs.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


# --------------------------------------------------------------------------- #
# scan scope
# --------------------------------------------------------------------------- #

def load_ignore(root, announce=True):
    """Read <root>/.powerbi-scan-ignore: one path prefix per line, # comments.

    Projects use it to keep archived or legacy report folders out of the checks
    and out of any bulk fix, without hiding them from git. Paths are relative to
    the scan root.
    """
    _IGNORE_PREFIXES.clear()
    path = os.path.join(root, IGNORE_FILE)
    if not os.path.isfile(path):
        return
    for line in io.open(path, encoding="utf-8"):
        line = line.split("#", 1)[0].strip().strip("/")
        if line:
            _IGNORE_PREFIXES.append(
                os.path.normpath(os.path.abspath(os.path.join(root, line))))
    if _IGNORE_PREFIXES and announce:
        print(f"({IGNORE_FILE}: skipping {len(_IGNORE_PREFIXES)} path(s))")


def is_excluded(path):
    """True when `path` sits inside a dead/duplicate tree that should be
    skipped (see EXCLUDE_SEGMENTS and .claude/worktrees above), or under a
    prefix listed in .powerbi-scan-ignore."""
    abs_path = os.path.normpath(os.path.abspath(path))
    for prefix in _IGNORE_PREFIXES:
        if abs_path == prefix or abs_path.startswith(prefix + os.sep):
            return True
    norm = "/" + path.replace(os.sep, "/").strip("/") + "/"
    if "/.claude/worktrees/" in norm:
        return True
    return any(seg in norm.split("/") for seg in EXCLUDE_SEGMENTS)


def walk(root, prune=None):
    """os.walk with one behavior for the whole toolkit.

    Half of these scripts found their files with glob('**'), which follows
    symlinks, and half with a bare os.walk, which does not -- so the same repo
    could report two different sets of reports depending on which script asked.
    This follows links (matching glob) and keeps a set of realpaths so a link
    pointing back up the tree cannot loop forever. Excluded directories are
    pruned before they are descended into; `prune(dirpath, dirname)` may reject
    more.
    """
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        real = os.path.realpath(dirpath)
        if real in seen:
            dirnames[:] = []          # already been here -- symlink loop
            continue
        seen.add(real)
        dirnames[:] = [d for d in dirnames
                       if not is_excluded(os.path.join(dirpath, d))
                       and (prune is None or not prune(dirpath, d))]
        yield dirpath, dirnames, filenames


# --------------------------------------------------------------------------- #
# finding the pieces of a PBIP repo
# --------------------------------------------------------------------------- #

def tmdl_glob(*parts):
    """glob() never matches a leading dot, and the measure-holder table is
    named `.Measures` in half of these models -- globbing only `*.tmdl` drops
    it silently, so its measures were not being counted at all. Match both."""
    base = os.path.join(*parts)
    return [f for pat in ("*.tmdl", ".*.tmdl")
            for f in glob.glob(os.path.join(base, pat), recursive=True)]


def model_table_files(root):
    """Every table .tmdl of every semantic model under root, ignore-list applied."""
    return [f for f in sorted(
        tmdl_glob(root, "**", "*.SemanticModel", "definition", "tables"))
        if not is_excluded(f)]


def report_dirs(root):
    """Every *.Report directory under root, ignore-list applied."""
    out = []
    for dirpath, dirnames, _filenames in walk(root):
        for d in dirnames:
            if d.endswith(".Report"):
                out.append(os.path.join(dirpath, d))
    return sorted(out)


def visual_json_files(root):
    """Every visual.json of every report page under root, ignore-list applied."""
    pattern = os.path.join(root, "**", "*.Report", "definition", "pages", "*",
                           "visuals", "*", "visual.json")
    return [f for f in sorted(glob.glob(pattern, recursive=True))
            if not is_excluded(f)]


def report_dir_of(path):
    """The *.Report directory that owns this path, or None."""
    parts = path.split(os.sep)
    for i, p in enumerate(parts):
        if p.endswith(".Report"):
            return os.sep.join(parts[: i + 1])
    return None


def warn_duplicate_reports(dirs):
    """Print a WARNING when the same *.Report basename exists in more than one
    place, so nobody edits a stale duplicate by mistake."""
    by_name = {}
    for d in dirs:
        by_name.setdefault(os.path.basename(d.rstrip(os.sep)), []).append(d)
    for name, paths in sorted(by_name.items()):
        if len(paths) > 1:
            print(f"WARNING  {name!r} exists in {len(paths)} places "
                  f"-- make sure you are editing the right one:")
            for p in sorted(paths):
                print(f"           {p}")


# --------------------------------------------------------------------------- #
# reading and writing without rewriting the file
# --------------------------------------------------------------------------- #

def read_text(path):
    """-> (text, newline). newline='' on the read keeps \\r\\n intact; without it
    Python translates on read, the CRLF detection below always says LF, and a
    write then rewrites every line in the file."""
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        text = fh.read()
    return text, ("\r\n" if "\r\n" in text else "\n")


def write_text(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def read_tmdl(path):
    """-> (lines, newline, trailing_newline), CRLF preserved."""
    text, newline = read_text(path)
    trailing = text.endswith(newline)
    lines = text.replace("\r\n", "\n").split("\n")
    if trailing:
        lines.pop()
    return lines, newline, trailing


def write_tmdl(path, lines, newline, trailing):
    write_text(path, newline.join(lines) + (newline if trailing else ""))


# --------------------------------------------------------------------------- #
# TMDL / PBIR shapes
# --------------------------------------------------------------------------- #

# The three shapes the scripts need of the same declaration. Capture groups
# differ, so they stay separate constants rather than one over-general regex.
#   MEASURE_FULL   1=indent 2=quoted-or-bare 3=inner name 4=rest of the line
#   MEASURE_HEAD   1=quoted-or-bare 2=inner name
#   MEASURE_TABBED 1=quoted-or-bare 2=inner name, anchored at one tab
MEASURE_FULL = re.compile(r"^(\s*)measure\s+('([^']+)'|[^\s=]+)\s*=(.*)$")
MEASURE_HEAD = re.compile(r"\s*measure\s+('([^']+)'|[^\s=]+)\s*=")
MEASURE_TABBED = re.compile(r"^\tmeasure\s+('([^']+)'|[^\s=]+)\s*=")


def title_text(visual):
    """The visual's Selection-pane name: its title text, displayed or not."""
    for card in (visual.get("visualContainerObjects") or {}).get("title") or []:
        if not isinstance(card, dict):
            continue
        value = (((card.get("properties") or {}).get("text") or {})
                 .get("expr", {}).get("Literal", {}).get("Value"))
        if value and value.strip("'").strip():
            return value.strip("'")
    return None
