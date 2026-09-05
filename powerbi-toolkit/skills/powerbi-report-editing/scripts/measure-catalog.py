#!/usr/bin/env python3
"""Turn the measure-holder table into a live measure catalog for a help page.

Every model in this estate parks its report-wide measures in one holder table --
`.Measures` or `00 MEASURES` depending on the project -- and that table is a
calculated table with the constant expression `{1}` and a single hidden `Value`
column. It holds measures and tells a reader nothing.

This rewrites that expression to derive the table from `INFO.VIEW.MEASURES()`:
one row per visible measure, with the table it lives in, its display folder, and
the two halves of its `///` description -- the prose, and the DAX after the
`---` separator. A report binds a table visual to those columns and gets a help
page that cannot go stale: the rows are rebuilt by the engine on every model
refresh, so there is nothing to generate, commit or keep in sync.

    python3 <skill>/scripts/measure-catalog.py <repo> [--apply]
    python3 <skill>/scripts/measure-catalog.py <repo> --lang en --apply   # default
    python3 <skill>/scripts/measure-catalog.py <repo> --lang cs --apply   # Czech columns
    python3 <skill>/scripts/measure-catalog.py <repo> --only 'Sales' --apply
    python3 <skill>/scripts/measure-catalog.py <repo> --check
    python3 <skill>/scripts/measure-catalog.py <repo> --create '.Measures' --apply

Dry-run by default: it prints what it would write and touches nothing. Honors
.powerbi-scan-ignore like every other script here.

Read references/measure-catalog.md before running it -- the report-side gotchas
(text wrap, the [Expression] permission gate, the refresh-after-publish trap)
are there, and none of them are visible from the TMDL.
"""
import argparse
import io
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common

_common.force_utf8_stdout()

HOLDER_NAMES = {".measures", "00 measures"}
MARKER = "INFO.VIEW.MEASURES"

# Column names are analyst-facing, so they follow the project's language
# (section 6 of its layout file). Order is the order they appear in the table.
COLUMNS = {
    "cs": ["Tabulka", "Míra", "Složka", "Popis", "DAX"],
    "en": ["Table", "Measure", "Folder", "Description", "DAX"],
}

# The `///` description of a table the script creates itself -- same language as
# its columns.
TABLE_DESCRIPTION = {
    "cs": "Katalog měr modelu — jeden řádek na každou viditelnou míru, odvozený z INFO.VIEW.MEASURES(). Zdroj pro help page v reportu; přepočítá se při každém refreshi modelu.",
    "en": "Measure catalog — one row per visible measure, derived from INFO.VIEW.MEASURES(). Source for the report help page; rebuilt on every model refresh.",
}

BLOCK_START = re.compile(r"^\t(///|measure\b|column\b|partition\b|hierarchy\b|annotation\b|calculationGroup\b)")
TABLE_DECL = re.compile(r"^table\s+('([^']+)'|\S+)")
PARTITION_DECL = re.compile(r"^\tpartition\s+('([^']+)'|\S+)\s*=\s*(\w+)")
COLUMN_DECL = re.compile(r"^\tcolumn\s+('([^']+)'|\S+)")
MEASURE_DECL = _common.MEASURE_TABBED


def find_models(root):
    """-> [<...>.SemanticModel/definition] under root, ignore-list applied."""
    out = []
    for dirpath, dirnames, _ in _common.walk(root):
        for d in dirnames:
            if d.endswith(".SemanticModel"):
                definition = os.path.join(dirpath, d, "definition")
                if os.path.isdir(os.path.join(definition, "tables")):
                    out.append(definition)
    return sorted(out)


def list_tables(definition):
    """Every table file. os.listdir, not glob -- glob skips dotfiles and the
    holder table is called `.Measures` in half of these models."""
    tables = os.path.join(definition, "tables")
    return sorted(os.path.join(tables, f) for f in os.listdir(tables)
                  if f.endswith(".tmdl"))


read_tmdl = _common.read_tmdl
write_tmdl = _common.write_tmdl


def parse_blocks(lines):
    """-> (header, blocks). A block is [lines] starting at a one-tab keyword or
    its leading `///` description; trailing blank lines are dropped so the file
    is re-emitted with exactly one blank line between blocks, which is what
    Desktop writes."""
    header, blocks, current = [], [], None
    for line in lines:
        if BLOCK_START.match(line):
            # `///` lines above a keyword are that object's description and stay
            # welded to it -- splitting them apart inserts a blank line between
            # the description and its measure, which Desktop then rewrites.
            if current is not None and _is_description_run(current):
                current.append(line)
                continue
            current = [line]
            blocks.append(current)
        elif current is None:
            header.append(line)
        else:
            current.append(line)
    return header, [_strip_trailing_blanks(b) for b in blocks]


def _is_description_run(block):
    """True while a block is still only `///` lines -- consecutive description
    lines belong to the same block, they do not each start a new one."""
    return all(l.startswith("\t///") for l in block)


def _strip_trailing_blanks(block):
    while block and not block[-1].strip():
        block.pop()
    return block


def block_kind(block):
    for line in block:
        if line.startswith("\t///"):
            continue
        m = re.match(r"^\t(\w+)", line)
        return m.group(1) if m else "?"
    return "description"


def block_name(block, pattern):
    for line in block:
        m = pattern.match(line)
        if m:
            return m.group(2) or m.group(1)
    return None


def catalog_source(names):
    """The DAX behind the catalog. `@Separator` locates the `---` that splits a
    measure's description into prose and DAX; measures without one keep their
    whole description as prose and get a blank formula."""
    table, measure, folder, desc, dax = names
    return [
        "SELECTCOLUMNS (",
        "    ADDCOLUMNS (",
        "        FILTER ( INFO.VIEW.MEASURES ( ), NOT [IsHidden] ),",
        '        "@Separator", SEARCH ( "---", [Description], 1, 0 )',
        "    ),",
        '    "%s", [Table],' % table,
        '    "%s", [Name],' % measure,
        '    "%s", [DisplayFolder],' % folder,
        '    "%s", TRIM ( IF ( [@Separator] = 0, [Description], LEFT ( [Description], [@Separator] - 1 ) ) ),' % desc,
        '    "%s", TRIM ( IF ( [@Separator] = 0, BLANK ( ), MID ( [Description], [@Separator] + 3, LEN ( [Description] ) ) ) )' % dax,
        ")",
    ]


def quote(name):
    return name if re.match(r"^[A-Za-z_]\w*$", name) else "'%s'" % name


def column_block(name, lineage_tag):
    """What Desktop writes for a calculated-table column: no dataType (it is
    inferred), isNameInferred + sourceColumn pointing at the expression's own
    column name."""
    return [
        "\tcolumn %s" % quote(name),
        "\t\tlineageTag: %s" % lineage_tag,
        "\t\tsummarizeBy: none",
        "\t\tisNameInferred",
        "\t\tsourceColumn: [%s]" % name,
        "",
        "\t\tannotation SummarizationSetBy = Automatic",
    ]


def rebuild(lines, table_name, names):
    """-> (new_lines, dropped_columns) or (None, reason)."""
    header, blocks = parse_blocks(lines)

    partition = next((b for b in blocks if block_kind(b) == "partition"), None)
    if partition is None:
        return None, "no partition block"
    m = next((PARTITION_DECL.match(l) for l in partition if PARTITION_DECL.match(l)), None)
    if m is None:
        # A partition block whose declaration line we cannot parse: TMDL we have
        # not seen. Say so instead of dying on AttributeError three lines down.
        decl = next((l.strip() for l in partition if l.strip()), "(empty block)")
        return None, ("partition declaration not understood: %r -- expected "
                      "`partition <name> = <mode>`" % decl)
    if m.group(3) != "calculated":
        return None, "partition is `%s`, not `calculated` -- this is a loaded table, leave it alone" % m.group(3)

    existing = {}
    for b in blocks:
        if block_kind(b) == "column":
            cname = block_name(b, COLUMN_DECL)
            tag = next((l.split(":", 1)[1].strip() for l in b if l.strip().startswith("lineageTag:")), None)
            existing[cname] = tag

    # Keep a column's lineageTag across runs so re-running is a no-op and the
    # report's field bindings survive.
    new_columns = []
    for name in names:
        new_columns.append(column_block(name, existing.get(name) or str(uuid.uuid4())))
    dropped = [c for c in existing if c not in names]

    new_partition = []
    for line in partition:
        if re.match(r"^\t\tsource\b", line):
            break
        new_partition.append(line)
    new_partition.append("\t\tsource =")
    new_partition += ["\t\t\t\t" + l for l in catalog_source(names)]

    out = list(header)
    emitted_columns = False
    for b in blocks:
        kind = block_kind(b)
        if kind == "column":
            if not emitted_columns:
                for cb in new_columns:
                    out += cb + [""]
                emitted_columns = True
            continue
        if kind == "partition":
            if not emitted_columns:
                for cb in new_columns:
                    out += cb + [""]
                emitted_columns = True
            out += new_partition + [""]
            continue
        out += b + [""]
    while out and not out[-1].strip():
        out.pop()
    # Desktop leaves a blank line at the end of some table files; keep exactly
    # what was there, or the last line shows up in every diff.
    tail = 0
    while tail < len(lines) and not lines[len(lines) - 1 - tail].strip():
        tail += 1
    out += [""] * tail
    return out, dropped


def report_references(root, table_name, columns):
    """Report JSON referring to a column we are about to drop. A binding to a
    dropped column breaks the visual silently, so this is a hard stop."""
    hits = []
    wanted = ["%s.%s" % (table_name, c) for c in columns]
    if not wanted:
        return hits
    for path in _report_json(root):
        try:
            text = io.open(path, encoding="utf-8-sig", errors="ignore", newline="").read()
        except OSError:
            continue
        for w in wanted:
            if w in text:
                hits.append((path, w))
    return hits


_REPORT_JSON = []


def _report_json(root):
    """Every report JSON under root, walked once and remembered -- this is
    asked per model and a repo can hold five of them."""
    if _REPORT_JSON:
        return _REPORT_JSON
    for dirpath, dirnames, filenames in _common.walk(root):
        if ".Report" not in dirpath:
            continue
        _REPORT_JSON.extend(os.path.join(dirpath, f) for f in filenames if f.endswith(".json"))
    return _REPORT_JSON


def existing_catalog(definition):
    """-> the name of the table already carrying a catalog, or None."""
    for path in list_tables(definition):
        lines, _, _ = read_tmdl(path)
        if not any(MARKER in l for l in lines):
            continue
        decl = next((TABLE_DECL.match(l) for l in lines if TABLE_DECL.match(l)), None)
        return (decl.group(2) or decl.group(1)) if decl else os.path.basename(path)
    return None


def find_holder(definition, wanted):
    """The holder table: by name when given or by convention, otherwise the
    calculated table with a constant expression that carries measures. Name is
    the weaker signal -- shape is what actually identifies it."""
    candidates = []
    for path in list_tables(definition):
        lines, _, _ = read_tmdl(path)
        decl = next((TABLE_DECL.match(l) for l in lines if TABLE_DECL.match(l)), None)
        if not decl:
            continue
        name = decl.group(2) or decl.group(1)
        has_measures = any(MEASURE_DECL.match(l) for l in lines)
        is_calc = any(PARTITION_DECL.match(l) and PARTITION_DECL.match(l).group(3) == "calculated"
                      for l in lines)
        is_catalog = any(MARKER in l for l in lines)
        constant = any(re.match(r"^\t\tsource = \{.*\}\s*$", l) for l in lines)
        if wanted:
            if name.lower() == wanted.lower():
                return path, name, is_catalog
            continue
        if name.lower() in HOLDER_NAMES or (is_calc and has_measures and (constant or is_catalog)):
            candidates.append((path, name, is_catalog))
    if wanted:
        return None, wanted, False
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        named = [c for c in candidates if c[1].lower() in HOLDER_NAMES]
        if len(named) == 1:
            return named[0]
    return None, None, False


def create_holder(definition, name, names, lang):
    """Write a new catalog table and register it in model.tmdl -- `ref table` is
    what makes TMDL load it."""
    path = os.path.join(definition, "tables", "%s.tmdl" % name)
    lines = [
        "/// " + TABLE_DESCRIPTION[lang],
        "table %s" % quote(name),
        "\tlineageTag: %s" % uuid.uuid4(),
        "",
    ]
    for cname in names:
        lines += column_block(cname, str(uuid.uuid4())) + [""]
    lines += ["\tpartition %s = calculated" % quote(name), "\t\tmode: import", "\t\tsource ="]
    lines += ["\t\t\t\t" + l for l in catalog_source(names)]

    model = os.path.join(definition, "model.tmdl")
    mlines, mnl, mtrail = read_tmdl(model)
    ref = "ref table %s" % quote(name)
    if ref not in mlines:
        idx = max((i for i, l in enumerate(mlines) if l.startswith("ref table ")), default=len(mlines) - 1)
        mlines.insert(idx + 1, ref)
    return path, lines, (model, mlines, mnl, mtrail)


def process(definition, root, args):
    label = os.path.basename(os.path.dirname(definition))

    # --create is both "this model has no holder" and the escape hatch for a
    # holder whose own columns are bound by visuals (or for keeping the catalog
    # off the table that hosts the measures): it puts the catalog in its own
    # table and leaves the holder alone.
    if args.create:
        have = existing_catalog(definition)
        if have and have.lower() != args.create.lower():
            # Mixed repo: some models were converted in place, others need the
            # separate table. Without this, --create gives them a second catalog.
            print("  %s: catalog already in `%s` -- skipping --create" % (label, have))
            return "ok"
        target = os.path.join(definition, "tables", "%s.tmdl" % args.create)
        if not os.path.exists(target):
            names = COLUMNS[args.lang]
            new_path, lines, (mpath, mlines, mnl, mtrail) = create_holder(
                definition, args.create, names, args.lang)
            print("  %s: would create table `%s` with columns %s"
                  % (label, args.create, ", ".join(names)))
            if args.apply:
                write_tmdl(new_path, lines, "\r\n", True)
                write_tmdl(mpath, mlines, mnl, mtrail)
                print("    created %s and registered it in model.tmdl" % os.path.basename(new_path))
            return "created"
        args = argparse.Namespace(**{**vars(args), "table": args.create})

    path, name, is_catalog = find_holder(definition, args.table)

    if path is None:
        print("  %s: no measure-holder table found -- pass --create '<name>' to add one" % label)
        return "none"

    lines, newline, trailing = read_tmdl(path)
    names = COLUMNS[args.lang]
    new_lines, dropped = rebuild(lines, name, names)
    if new_lines is None:
        print("  %s: %s -- SKIPPED (%s)" % (label, name, dropped))
        return "skipped"

    if new_lines == lines:
        print("  %s: %s -- already a catalog, unchanged" % (label, name))
        return "ok"

    hits = report_references(root, name, dropped)
    if hits:
        print("  %s: %s -- REFUSED, reports still bind columns this would drop:" % (label, name))
        for p, w in hits[:5]:
            print("      %s  (%s)" % (os.path.relpath(p, root), w))
        return "refused"

    verb = "rewrote" if args.apply else "would rewrite"
    print("  %s: %s -- %s partition to INFO.VIEW.MEASURES(), columns %s%s"
          % (label, name, verb, ", ".join(names),
             (" (drops %s)" % ", ".join(dropped)) if dropped else ""))
    if args.apply:
        write_tmdl(path, new_lines, newline, trailing)
    return "changed"


def check(definition):
    label = os.path.basename(os.path.dirname(definition))
    path, name, is_catalog = find_holder(definition, None)
    if path is None:
        return label, "no holder table"
    return label, ("catalog in `%s`" % name) if is_catalog else ("`%s` holds no catalog" % name)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--apply", action="store_true", help="write; default is a dry run")
    ap.add_argument("--lang", choices=sorted(COLUMNS), default="en",
                    help="language of the catalog's column names (default: en)")
    ap.add_argument("--table", help="holder table name, when detection picks the wrong one")
    ap.add_argument("--create", metavar="NAME",
                    help="put the catalog in a table of this name, creating it when missing")
    ap.add_argument("--only", metavar="SUBSTRING",
                    help="only models whose name contains this -- how you do the first one")
    ap.add_argument("--check", action="store_true",
                    help="report which models carry a catalog; never writes, never fails")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    _common.load_ignore(root)
    models = find_models(root)
    if not models:
        print("no semantic model found under %s -- wrong directory?" % root)
        return 2
    if args.only:
        models = [m for m in models if args.only.lower() in os.path.dirname(m).lower()]
        if not models:
            print("no model under %s matches --only %r" % (root, args.only))
            return 2

    if args.check:
        print("measure catalog -- %d model(s)" % len(models))
        missing = 0
        for definition in models:
            label, state = check(definition)
            if "catalog in" not in state:
                missing += 1
            print("  %-42s %s" % (label, state))
        print("\n%d of %d models carry a measure catalog." % (len(models) - missing, len(models)))
        if missing:
            print("Add one with: measure-catalog.py <repo> --apply   (see references/measure-catalog.md)")
        # 1 is backlog, not breakage -- doctor.py lists this check as a note.
        return 1 if missing else 0

    print("measure catalog -- %d model(s), column names: %s%s"
          % (len(models), args.lang, "" if args.apply else "   [DRY RUN]"))
    results = [process(d, root, args) for d in models]
    changed = results.count("changed") + results.count("created")
    print("\n%d model(s) %s." % (changed, "written" if args.apply else "would change"))
    if changed and not args.apply:
        print("Re-run with --apply. Then open ONE model in Desktop and refresh it before")
        print("rolling the rest out -- see references/measure-catalog.md, 'First run'.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
