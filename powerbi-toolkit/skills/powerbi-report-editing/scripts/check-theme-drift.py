#!/usr/bin/env python3
"""Detect theme drift across PBIR reports in a repo.

Each PBIR report registers its own COPY of the theme:

  <Report>.Report/StaticResources/RegisteredResources/<Name><digits>.json
  <Report>.Report/definition/report.json
      themeCollection.customTheme  (type RegisteredResources, points at the copy)
      themeCollection.baseTheme    (type SharedResources, the built-in Power BI theme)

Because it is a copy per report -- not a shared reference -- reports drift apart
over time: someone tweaks the theme for report A and forgets to re-export it into
report B, or an older report was never updated after the "master" theme file (often
kept at the repo root, e.g. mytheme.json) moved on. There is no single
source of truth enforced by the file format; this script exists to catch when that
assumption has quietly broken.

    python3 check-theme-drift.py <repo-root> [--detail]

What it does:
  1. Find every *.Report directory under repo-root (skips .claude/worktrees,
     node_modules, .git, __pycache__, .venv, and .powerbi-scan-ignore entries).
  2. For each report, find its registered theme: the file under
     StaticResources/RegisteredResources/ that contains a "visualStyles" key
     (other files there can be images or topojson map shapes -- ignored).
  3. Hash each theme by its CANONICAL form -- json.dumps(sort_keys=True) of the
     parsed JSON, not the raw bytes -- so that whitespace/key-order differences
     from re-exporting do not register as false drift.
  4. Group reports by that hash. More than one group = drift.
  5. Compare *.json files sitting directly in repo-root that also contain
     "visualStyles" (candidate "canonical"/master copies) against the groups
     found in reports, and report whether they match any group or are yet
     another standalone version.
  6. With --detail, diff the drifting groups against the largest (majority)
     group: which dotted property paths differ and what values they hold on
     each side, capped at ~40 differences.

This script is read-only. It edits nothing.

Exit codes: 0 = single theme version in use everywhere, 1 = drift detected,
2 = no report or no theme found at all.
"""
import argparse
import glob
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()


def find_reports(root):
    """Find every *.Report directory under root, recursively."""
    return _common.report_dirs(root)


def load_json(path):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return None


def find_report_theme(report_dir):
    """Return (path, data) for the registered theme, or (None, None)."""
    pattern = os.path.join(report_dir, "StaticResources", "RegisteredResources", "*.json")
    for path in sorted(glob.glob(pattern)):
        data = load_json(path)
        if isinstance(data, dict) and "visualStyles" in data:
            return path, data
    return None, None


def canonical_hash(data):
    """sha256 of the canonicalized (sort_keys) JSON -- formatting-independent."""
    blob = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def find_root_theme_candidates(root):
    """*.json directly under root (not inside any .Report) containing visualStyles."""
    candidates = []
    for path in sorted(glob.glob(os.path.join(root, "*.json"))):
        data = load_json(path)
        if isinstance(data, dict) and "visualStyles" in data:
            candidates.append((path, data))
    return candidates


def flatten(node, prefix=""):
    """Yield (dotted.path, leaf_value) pairs.

    Singleton lists (the normal shape for a theme "card", e.g. values: [ {...} ])
    are transparently unwrapped so paths read like visualStyles.tableEx.*.values.fontSize
    instead of carrying a redundant [0] everywhere. Longer lists get an index.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            sub = f"{prefix}.{key}" if prefix else key
            yield from flatten(value, sub)
    elif isinstance(node, list):
        if len(node) == 1:
            yield from flatten(node[0], prefix)
        else:
            for i, value in enumerate(node):
                yield from flatten(value, f"{prefix}[{i}]")
    else:
        yield (prefix, node)


def diff_themes(base, other, limit=40):
    """Return up to `limit` (path, base_value, other_value) differences."""
    base_flat = dict(flatten(base))
    other_flat = dict(flatten(other))
    base_flat.pop("name", None)
    other_flat.pop("name", None)
    paths = sorted(set(base_flat) | set(other_flat))
    diffs = []
    for p in paths:
        bv = base_flat.get(p, "<missing>")
        ov = other_flat.get(p, "<missing>")
        if bv != ov:
            diffs.append((p, bv, ov))
            if len(diffs) >= limit:
                break
    total_paths_diff = sum(1 for p in paths if base_flat.get(p, "<missing>") != other_flat.get(p, "<missing>"))
    return diffs, total_paths_diff


def build_parser():
    ap = argparse.ArgumentParser(
        prog="check-theme-drift.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Detect theme drift across the PBIR reports in a repo.\n\n"
            "Every report registers its own COPY of the theme under\n"
            "StaticResources/RegisteredResources/ -- not a shared reference -- so\n"
            "reports drift apart: someone tweaks the theme for report A and never\n"
            "re-exports it into report B. This hashes each report's registered\n"
            "theme in canonical form (sort_keys, so re-export whitespace is not\n"
            "false drift), groups reports by that hash, and reports more than one\n"
            "group as drift. Candidate master theme *.json sitting directly at the\n"
            "repo root are compared against those groups too.\n"
            "It reads only; nothing is written."),
        epilog=(
            "exit codes:\n"
            "  0  every report with a registered theme uses the same version\n"
            "  1  drift: two or more different theme versions are in use\n"
            "  2  nothing to compare -- no *.Report under <root>, or none of them\n"
            "     carries a theme with a 'visualStyles' key (wrong directory?)\n\n"
            "Respects .powerbi-scan-ignore and skips worktrees, node_modules, .git,\n"
            "__pycache__ and .venv."))
    ap.add_argument("root", nargs="?", default=".",
                    help="repo root holding the *.Report directories "
                         "(default: the current directory)")
    ap.add_argument("--detail", action="store_true",
                    help="also diff each drifting group against the majority "
                         "group, property by property (capped at 40)")
    return ap


def main(argv=None):
    parsed = build_parser().parse_args(argv)
    detail = parsed.detail
    root = os.path.abspath(parsed.root)
    _common.load_ignore(root)

    reports = find_reports(root)
    if not reports:
        print(f"no *.Report directories found under {root}")
        return 2

    themed = []       # (report_dir, theme_path, data, hash)
    themeless = []     # report_dir with no theme found
    for r in reports:
        path, data = find_report_theme(r)
        if data is None:
            themeless.append(r)
            continue
        themed.append((r, path, data, canonical_hash(data)))

    if not themed:
        print(f"{len(reports)} report(s) found under {root}, but none carries a")
        print("registered theme with a 'visualStyles' key.")
        return 2

    groups = {}
    for r, path, data, h in themed:
        g = groups.setdefault(h, {"data": data, "theme_names": set(), "reports": []})
        g["theme_names"].add(data.get("name", "?"))
        g["reports"].append((r, path))

    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]["reports"]))

    print(f"repo root: {root}")
    print(f"{len(reports)} report(s) found, {len(themed)} with a registered theme, "
          f"{len(themeless)} without.\n")

    print(f"=== {len(ordered)} distinct theme version(s) in use ===")
    for i, (h, g) in enumerate(ordered, 1):
        names = ", ".join(sorted(g["theme_names"]))
        print(f"\n  group {i}: {len(g['reports'])} report(s)  theme name(s): {names}  sha256: {h[:12]}")
        for r, path in sorted(g["reports"]):
            rel = os.path.relpath(r, root)
            fname = os.path.basename(path)
            print(f"      {rel}  ({fname})")

    if themeless:
        print(f"\n  reports WITHOUT a registered theme ({len(themeless)}):")
        for r in sorted(themeless):
            print(f"      {os.path.relpath(r, root)}")

    drift = len(ordered) > 1
    print()
    if drift:
        print(f"DRIFT: {len(ordered)} different theme versions are in use across reports in this repo.")
    else:
        print("OK: every report with a registered theme uses the same theme version.")

    root_candidates = find_root_theme_candidates(root)
    if root_candidates:
        print(f"\n=== {len(root_candidates)} candidate root theme file(s) ===")
        for path, data in root_candidates:
            h = canonical_hash(data)
            match = next((i for i, (gh, _g) in enumerate(ordered, 1) if gh == h), None)
            rel = os.path.relpath(path, root)
            name = data.get("name", "?")
            if match:
                print(f"  {rel}  name={name!r}  sha256={h[:12]}  -> matches group {match}")
            else:
                print(f"  {rel}  name={name!r}  sha256={h[:12]}  -> STANDALONE, matches no report group")
    else:
        print("\nno candidate theme *.json found directly at repo root.")

    if drift and detail:
        base_h, base_g = ordered[0]
        base_names = ", ".join(sorted(base_g["theme_names"]))
        print(f"\n=== detail: diffs against majority group 1 ({len(base_g['reports'])} report(s), "
              f"{base_names}) ===")
        for h, g in ordered[1:]:
            names = ", ".join(sorted(g["theme_names"]))
            sample_report = sorted(g["reports"])[0][0]
            diffs, total = diff_themes(base_g["data"], g["data"])
            print(f"\n  group vs. ({len(g['reports'])} report(s), {names}) "
                  f"-- e.g. {os.path.relpath(sample_report, root)}")
            print(f"  {total} propert(ies) differ, showing up to {len(diffs)}:")
            for p, bv, ov in diffs:
                print(f"      {p}\n          group 1: {bv!r}\n          this group: {ov!r}")
            if total > len(diffs):
                print(f"      ... +{total - len(diffs)} more differences not shown")

    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
