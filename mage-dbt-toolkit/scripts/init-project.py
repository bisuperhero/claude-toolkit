#!/usr/bin/env python3
"""Onboard a Mage.ai + dbt repo: draft its CLAUDE.md from the template, or check one.

Onboarding a new repo used to be "copy the template, replace ~34 placeholders by
hand, walk the checklist, hope nothing was missed". A good half of those values
are already written down somewhere in the repo, and nothing ever verified that
the finished file had no `{{PLACEHOLDER}}` left in it. This does both halves.

    python3 <plugin>/scripts/init-project.py <repo>            # dry run -- prints the plan
    python3 <plugin>/scripts/init-project.py <repo> --apply    # write <repo>/CLAUDE.md
    python3 <plugin>/scripts/init-project.py <repo> --apply --force   # overwrite an existing one
    python3 <plugin>/scripts/init-project.py <repo> --check    # audit an existing CLAUDE.md

What it reads out of the repo (and nothing more -- an unreadable value stays a
placeholder, it is never guessed):

  project name       basename of the repo path
  Mage directory     the directory holding metadata.yaml + pipelines/
  dbt directory      the directory holding dbt_project.yml
  dbt layer table    the real folder names under <dbt>/models/, one row each
  pipeline count     subdirectories of <mage>/pipelines/ that carry a metadata.yaml
  toolbox tools      tool names in the root toolbox*.yaml files, dev vs prod
  warehouse host     host/port/database of the dev toolbox source (never credentials)
  Power BI           directories holding a *.pbip -- or the section is dropped
  infrastructure     compose profiles and published host ports
  environment        setting NAMES in .env.example / io_config.yaml.example

Everything else -- business context, source-system domain rules, the production
URL, GlitchTip org/project/tags, notification channels -- cannot be read out of
a repo and is left as a placeholder, listed at the end of the run.

Exit codes follow the toolkit convention: 0 clean, 1 findings/work left,
2 unusable input (bad path, missing template, refusing to clobber a file).
"""
import argparse
import os
import re
import sys

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
KEY_RE = re.compile(r"^(\s*)([A-Za-z_][\w.\-]*)\s*:\s*(.*?)\s*$")
BLOCK_SCALAR_RE = re.compile(r"^[|>][-+0-9]*$")
ENV_NAME_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
PORT_RE = re.compile(r'^\s*-\s*"?([^"\s]+?):(\d+)"?\s*$')

# Directories that never hold project structure but do hold thousands of files.
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".venv", "venv", "env",
    "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "site-packages", "logs", "mage_data", ".terraform",
}

# Naming conventions per medallion layer -- these come from the
# `mage-dbt-conventions` skill, they are not inferred from the repo.
LAYER_NAMING = [
    ("staging", "`stg_<src>__*`"),
    ("intermediate", "`int__*`"),
    ("core", "`dim_*`, `fct_*`"),
    ("marts", "`dim_*`, `fct_*`"),
    ("mart", "`dim_*`, `fct_*`"),
    ("reporting", "renamed cols"),
    ("report", "renamed cols"),
]

MAX_ENV_NAMES = 12
MAX_IO_GROUPS = 8


def force_utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def relpath(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def walk(root, maxdepth):
    """Yield directories under root, pruned and depth-limited."""
    root = os.path.abspath(root)
    queue = [(root, 0)]
    while queue:
        current, depth = queue.pop(0)
        yield current
        if depth >= maxdepth:
            continue
        try:
            entries = sorted(os.scandir(current), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if entry.name in SKIP_DIRS or entry.name.startswith("."):
                continue
            queue.append((entry.path, depth + 1))


# ---------------------------------------------------------------------------
# A deliberately small YAML reader
#
# The toolkit takes no dependencies, so there is no PyYAML here. This reads
# exactly one shape: top-level mappings whose children are named blocks of
# scalars (`sources:` / `tools:` in a toolbox file, profiles in io_config).
# Anything it is not sure about it simply does not return, and the caller then
# leaves a placeholder -- a missing value is always better than a wrong one.
# ---------------------------------------------------------------------------
def parse_simple_yaml(text):
    """Return {top_key: {child_key: {scalar: value}}} for the shapes described above."""
    entries = []          # (indent, key, value)
    skip_below = None     # indent of a block scalar whose body must be ignored
    for raw in text.splitlines():
        if skip_below is not None:
            if raw.strip() and (len(raw) - len(raw.lstrip(" "))) > skip_below:
                continue
            skip_below = None
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        match = KEY_RE.match(raw.split(" #")[0].rstrip())
        if not match:
            continue
        indent = len(match.group(1))
        key, value = match.group(2), match.group(3)
        if BLOCK_SCALAR_RE.match(value):
            skip_below = indent
            value = ""
        entries.append((indent, key, value))

    result = {}
    for i, (indent, key, value) in enumerate(entries):
        if indent != 0 or value:
            continue
        block = {}
        child_indent = None
        for child_indent_j, child_key, child_value in entries[i + 1:]:
            if child_indent_j == 0:
                break
            if child_indent is None:
                child_indent = child_indent_j
            if child_indent_j == child_indent:
                block[child_key] = {}
                current = block[child_key]
            elif child_indent_j == child_indent * 2 and block:
                current[child_key] = child_value.strip("'\"")
        result[key] = block
    return result


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def find_mage_dir(root):
    """The directory that holds metadata.yaml plus Mage's block folders."""
    strong, weak = [], []
    for directory in walk(root, 4):
        if not os.path.isfile(os.path.join(directory, "metadata.yaml")):
            continue
        markers = sum(
            os.path.isdir(os.path.join(directory, name))
            for name in ("pipelines", "data_loaders", "data_exporters", "custom")
        )
        (strong if markers >= 2 else weak).append(directory)
    if not strong and not weak:
        # Last resort: the `<Name>Mage/` naming convention, without metadata.yaml.
        for directory in walk(root, 4):
            if directory != root and directory.lower().endswith("mage"):
                weak.append(directory)
    return strong or weak


def find_dbt_projects(root):
    return [d for d in walk(root, 6) if os.path.isfile(os.path.join(d, "dbt_project.yml"))]


def find_dbt_layers(dbt_dir):
    models = os.path.join(dbt_dir, "models")
    if not os.path.isdir(models):
        return []
    try:
        names = sorted(
            e.name for e in os.scandir(models)
            if e.is_dir(follow_symlinks=False) and not e.name.startswith(".")
        )
    except OSError:
        return []
    return names


def count_pipelines(mage_dir):
    pipelines = os.path.join(mage_dir, "pipelines")
    if not os.path.isdir(pipelines):
        return None
    count = 0
    try:
        for entry in os.scandir(pipelines):
            if entry.is_dir(follow_symlinks=False) and os.path.isfile(
                os.path.join(entry.path, "metadata.yaml")
            ):
                count += 1
    except OSError:
        return None
    return count or None


def find_toolbox_files(root):
    found = []
    try:
        for entry in sorted(os.scandir(root), key=lambda e: e.name):
            name = entry.name
            if not entry.is_file(follow_symlinks=False):
                continue
            if not name.startswith("toolbox") or name.endswith(".example"):
                continue
            if not (name.endswith(".yaml") or name.endswith(".yml")):
                continue
            found.append(entry.path)
    except OSError:
        pass
    return found


def read_toolbox(paths):
    """Split toolbox tools into dev and prod, and pick up the dev warehouse address."""
    dev_tools, prod_tools, dev_sources = [], [], []
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        parsed = parse_simple_yaml(text)
        file_is_prod = "prod" in os.path.basename(path).lower()
        for tool in parsed.get("tools", {}):
            if "prod" in tool.lower() or file_is_prod:
                prod_tools.append(tool)
            else:
                dev_tools.append(tool)
        if file_is_prod:
            continue
        for name, body in parsed.get("sources", {}).items():
            if "prod" in name.lower():
                continue
            host, database = body.get("host"), body.get("database")
            if host and database:
                dev_sources.append((host, body.get("port", ""), database))
    dedupe = lambda seq: sorted(set(seq))
    return dedupe(dev_tools), dedupe(prod_tools), dedupe(dev_sources)


def find_powerbi_dirs(root):
    dirs = set()
    for directory in walk(root, 4):
        try:
            for entry in os.scandir(directory):
                if entry.name.endswith(".pbip") and entry.is_file(follow_symlinks=False):
                    dirs.add(directory)
                elif entry.name.endswith((".Report", ".SemanticModel")) and entry.is_dir(
                    follow_symlinks=False
                ):
                    dirs.add(directory)
        except OSError:
            continue
    return sorted(dirs)


def first_existing(directories, names):
    for directory in directories:
        for name in names:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                return candidate
    return None


def read_compose(path):
    """Compose profiles and published host ports -- both are facts, not guesses."""
    text = read_text(path)
    if text is None:
        return [], []
    profiles, ports = set(), set()
    in_profiles = in_ports = False
    profiles_indent = ports_indent = 0
    for raw in text.splitlines():
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip(" "))
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.startswith("profiles:"):
            inline = stripped[len("profiles:"):].strip()
            if inline.startswith("["):
                profiles.update(p.strip(" '\"") for p in inline.strip("[]").split(",") if p.strip())
                in_profiles = False
            else:
                in_profiles, profiles_indent = True, indent
            in_ports = False
            continue
        if stripped.startswith("ports:"):
            in_ports, ports_indent = True, indent
            in_profiles = False
            continue
        if in_profiles:
            if indent > profiles_indent and stripped.startswith("- "):
                profiles.add(stripped[2:].strip(" '\""))
                continue
            in_profiles = False
        if in_ports:
            match = PORT_RE.match(raw)
            if indent > ports_indent and match:
                ports.add((match.group(1), match.group(2)))
                continue
            in_ports = False
    return sorted(p for p in profiles if p), sorted(ports)


def read_env_names(path):
    text = read_text(path)
    if text is None:
        return []
    names = []
    for line in text.splitlines():
        match = ENV_NAME_RE.match(line)
        if match and match.group(1) not in names:
            names.append(match.group(1))
    return names


def read_io_config_profiles(path):
    text = read_text(path)
    if text is None:
        return [], []
    parsed = parse_simple_yaml(text)
    profiles = sorted(parsed)
    groups = set()
    for body in parsed.values():
        for key in body:
            groups.add(key.split("_")[0] if "_" in key else key)
    return profiles, sorted(groups)


# ---------------------------------------------------------------------------
# Template surgery
# ---------------------------------------------------------------------------
def heading_index(lines, prefix):
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            return i
    return -1


def section_end(lines, start):
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            return i
    return len(lines)


def drop_comment_block(lines, start, stop):
    """Remove the first <!-- ... --> block between start and stop."""
    for i in range(start, min(stop, len(lines))):
        if lines[i].lstrip().startswith("<!--"):
            for j in range(i, min(stop, len(lines))):
                if "-->" in lines[j]:
                    del lines[i:j + 1]
                    while i < len(lines) and not lines[i].strip():
                        del lines[i]
                    return True
            return False
    return False


def drop_comment_above(lines, index, window=12):
    """Remove the <!-- ... --> block that ends just above `index`. Returns the new index."""
    close = index - 1
    if close < 0 or "-->" not in lines[close]:
        return index
    for open_at in range(close, max(-1, close - window), -1):
        if lines[open_at].lstrip().startswith("<!--"):
            del lines[open_at:close + 1]
            return index - (close - open_at + 1)
    return index


def purpose_placeholder(folder):
    slug = re.sub(r"[^A-Z0-9]+", "_", folder.upper()).strip("_") or "LAYER"
    return "{{PURPOSE_%s}}" % slug


def layer_naming(folder):
    lowered = folder.lower()
    for token, naming in LAYER_NAMING:
        if token in lowered:
            return naming
    return "{{NAMING_%s}}" % (re.sub(r"[^A-Z0-9]+", "_", folder.upper()).strip("_") or "LAYER")


def render_layer_table(layers):
    rows = ["| Folder | Naming | Purpose |", "|---|---|---|"]
    for folder in layers:
        rows.append("| `%s/` | %s | %s |" % (folder, layer_naming(folder), purpose_placeholder(folder)))
    return rows


def build_document(template, facts, notes):
    lines = template.splitlines()

    # 1. Swap the template's own "how to fill this in" header for a generated one.
    if drop_comment_block(lines, 0, min(20, len(lines))):
        lines[1:1] = [
            "",
            "<!--",
            "  Drafted by mage-dbt-toolkit `init-project.py` from CLAUDE.template.md.",
            "  Anything still written in double braces could not be read out of the repo --",
            "  fill it in by hand, delete the guidance comments, then verify with",
            "      init-project.py <repo> --check",
            "-->",
        ]

    # 2. dbt layer table -- the real folders, not the template's generic four.
    index = heading_index(lines, "### dbt layers")
    if index != -1 and facts.get("layers"):
        stop = section_end(lines, index)
        drop_comment_block(lines, index, stop)
        stop = section_end(lines, index)
        table_start = next(
            (i for i in range(index, stop) if lines[i].startswith("| Folder")), -1
        )
        if table_start != -1:
            table_stop = table_start
            while table_stop < stop and lines[table_stop].startswith("|"):
                table_stop += 1
            lines[table_start:table_stop] = render_layer_table(facts["layers"])
    elif index != -1:
        notes.append("dbt layer table: no `models/` folders found -- left generic.")

    # 3. Secondary dbt project: one extra dbt_project.yml, or the line goes.
    index = next((i for i in range(len(lines)) if "{{SECONDARY_DBT_PROJECT}}" in lines[i]), -1)
    if index != -1:
        if facts.get("secondary_dbt"):
            lines[index] = "- **Secondary dbt project**: %s" % ", ".join(
                "`%s`" % d for d in facts["secondary_dbt"]
            )
            drop_comment_above(lines, index)
        else:
            del lines[index]
            drop_comment_above(lines, index)

    # 4. Infrastructure deviations from docker-compose.yml.
    index = next((i for i in range(len(lines)) if "{{INFRA_DEVIATIONS}}" in lines[i]), -1)
    if index != -1 and facts.get("infra_bullets"):
        index = drop_comment_above(lines, index)
        lines[index:index + 1] = facts["infra_bullets"]

    # 5. Environment expectations, appended to Connections.
    index = next((i for i in range(len(lines)) if "{{SOURCE_DB_ACCESS}}" in lines[i]), -1)
    if index != -1 and facts.get("env_bullets"):
        lines[index + 1:index + 1] = facts["env_bullets"]

    # 6. Power BI: fill the section in, or drop it whole.
    index = heading_index(lines, "## Power BI reports")
    if index != -1:
        stop = section_end(lines, index)
        if facts.get("pbi_dirs"):
            drop_comment_block(lines, index, stop)
        else:
            del lines[index:stop]
            notes.append("Power BI: no `*.pbip` found -- the reports section was dropped.")

    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"

    for name, value in facts["values"].items():
        text = text.replace("{{%s}}" % name, value)
    return text


# ---------------------------------------------------------------------------
# Gathering
# ---------------------------------------------------------------------------
def gather(root, notes):
    facts = {"values": {}}
    values = facts["values"]
    values["PROJECT_NAME"] = os.path.basename(os.path.abspath(root))

    mage_dirs = find_mage_dir(root)
    mage_dir = None
    if len(mage_dirs) == 1:
        mage_dir = mage_dirs[0]
        values["MAGE_DIR"] = relpath(root, mage_dir) + "/"
    elif len(mage_dirs) > 1:
        notes.append(
            "Mage directory: %d candidates (%s) -- left as a placeholder."
            % (len(mage_dirs), ", ".join(relpath(root, d) for d in mage_dirs))
        )
    else:
        notes.append("Mage directory: no `metadata.yaml` found -- left as a placeholder.")

    dbt_dirs = find_dbt_projects(root)
    if dbt_dirs:
        candidates = dbt_dirs
        if mage_dir:
            inside = [d for d in dbt_dirs if d.startswith(mage_dir + os.sep)]
            if inside:
                candidates = inside
        # `main_transformations` is the conventional name for the primary dbt
        # project (see the mage-dbt-conventions skill); otherwise take the
        # shallowest, and break ties alphabetically so runs are reproducible.
        named = [d for d in candidates if os.path.basename(d) == "main_transformations"]
        primary = (named or sorted(candidates, key=lambda d: (d.count(os.sep), d)))[0]
        values["DBT_DIR"] = relpath(root, primary) + "/"
        facts["layers"] = find_dbt_layers(primary)
        facts["secondary_dbt"] = [relpath(root, d) + "/" for d in dbt_dirs if d != primary]
        if not facts["layers"]:
            notes.append("dbt layers: `%s/models/` has no subfolders." % relpath(root, primary))
    else:
        notes.append("dbt project: no `dbt_project.yml` found -- layers left generic.")
        facts["layers"] = []
        facts["secondary_dbt"] = []

    if mage_dir:
        count = count_pipelines(mage_dir)
        if count:
            values["PIPELINE_COUNT"] = str(count)
        else:
            notes.append("Pipeline count: `%spipelines/` unreadable or empty." % values.get("MAGE_DIR", ""))

    toolbox_files = find_toolbox_files(root)
    dev_tools, prod_tools, dev_sources = read_toolbox(toolbox_files)
    if not toolbox_files:
        notes.append("toolbox: no `toolbox*.yaml` in the repo root -- tool names left as placeholders.")
    # The template already wraps these in backticks -- emit the bare name.
    if len(dev_tools) == 1:
        values["TOOLBOX_DEV_TOOL"] = dev_tools[0]
    elif dev_tools:
        notes.append("toolbox dev tool: %s -- pick one." % ", ".join("`%s`" % t for t in dev_tools))
    if len(prod_tools) == 1:
        values["TOOLBOX_PROD_TOOL"] = prod_tools[0]
    elif prod_tools:
        notes.append("toolbox prod tool: %s -- pick one." % ", ".join("`%s`" % t for t in prod_tools))
    if len(dev_sources) == 1:
        host, port, database = dev_sources[0]
        values["DB_HOST"] = host
        if port:
            values["DB_PORT"] = str(port)
        values["DB_NAME"] = database
    elif dev_sources:
        notes.append(
            "warehouse address: %d dev toolbox sources -- left as placeholders."
            % len(dev_sources)
        )

    pbi_dirs = find_powerbi_dirs(root)
    facts["pbi_dirs"] = pbi_dirs
    if pbi_dirs:
        # The template wraps this in backticks; a second directory reopens them.
        values["PBI_REPORTS_DIR"] = "`, `".join(relpath(root, d) + "/" for d in pbi_dirs)

    search_dirs = [root]
    if mage_dir:
        parent = os.path.dirname(mage_dir)
        if parent not in search_dirs:
            search_dirs.append(parent)
        search_dirs.append(mage_dir)

    infra_bullets = []
    compose = first_existing(search_dirs, ("docker-compose.yml", "docker-compose.yaml", "compose.yaml"))
    if compose:
        profiles, ports = read_compose(compose)
        where = relpath(root, compose)
        if profiles and sorted(profiles) != ["dev", "prod"]:
            infra_bullets.append(
                "- Compose profiles in `%s`: %s." % (where, ", ".join("`%s`" % p for p in profiles))
            )
        published = ["`%s:%s`" % (h, c) for h, c in ports if h != c]
        if published:
            infra_bullets.append("- Published host ports: %s." % ", ".join(published))
        if compose != os.path.join(root, os.path.basename(compose)):
            infra_bullets.append("- `docker-compose.yml` lives in `%s`, not the repo root." % os.path.dirname(where))
    facts["infra_bullets"] = infra_bullets

    env_bullets = []
    env_example = first_existing(search_dirs, (".env.example", "example.env", ".env.sample", "env.example"))
    if env_example:
        names = read_env_names(env_example)
        if names:
            shown = names[:MAX_ENV_NAMES]
            more = "" if len(names) <= MAX_ENV_NAMES else " (+%d more)" % (len(names) - MAX_ENV_NAMES)
            env_bullets.append(
                "- `.env` is not committed; `%s` expects %s%s."
                % (relpath(root, env_example), ", ".join("`%s`" % n for n in shown), more)
            )
    io_example = first_existing(search_dirs, ("io_config.yaml.example",))
    if io_example:
        profiles, groups = read_io_config_profiles(io_example)
        detail = []
        if profiles:
            detail.append("profiles %s" % ", ".join("`%s`" % p for p in profiles))
        if groups:
            more = "" if len(groups) <= MAX_IO_GROUPS else ", +%d more" % (len(groups) - MAX_IO_GROUPS)
            detail.append(
                "settings %s%s" % (", ".join("`%s_*`" % g for g in groups[:MAX_IO_GROUPS]), more)
            )
        io_real = os.path.join(os.path.dirname(io_example), "io_config.yaml")
        state = "" if os.path.isfile(io_real) else " (the real `io_config.yaml` is not in the repo)"
        env_bullets.append(
            "- `%s`%s%s."
            % (relpath(root, io_example), state, (" -- " + "; ".join(detail)) if detail else "")
        )
    facts["env_bullets"] = env_bullets
    return facts


# ---------------------------------------------------------------------------
# Check mode
# ---------------------------------------------------------------------------
STUB_RE = re.compile(r"\b(TODO|TBD|FIXME)\b")
HEADING_RE = re.compile(r"^(#{2,})\s+(.*)$")


def check_document(text):
    findings = []
    lines = text.splitlines()

    hits = {}
    for number, line in enumerate(lines, 1):
        for name in PLACEHOLDER_RE.findall(line):
            hits.setdefault(name, []).append(number)
    if hits:
        total = sum(len(v) for v in hits.values())
        findings.append(
            "%d unfilled placeholder(s), %d distinct:" % (total, len(hits))
        )
        for name in sorted(hits):
            where = ", ".join(str(n) for n in hits[name][:5])
            extra = "" if len(hits[name]) <= 5 else ", ..."
            findings.append("    {{%s}}  line %s%s" % (name, where, extra))

    if "UNIVERSAL TEMPLATE" in text:
        findings.append(
            "still carries the template's \"UNIVERSAL TEMPLATE\" header comment -- "
            "this looks like an unedited copy of CLAUDE.template.md."
        )

    # A heading whose body is empty. The document title and any heading that
    # only introduces sub-headings are not "unfilled" -- their content is the
    # section below them.
    empty = []
    for i, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        has_content = False
        in_comment = False
        for j in range(i + 1, len(lines)):
            candidate = lines[j].strip()
            sub = HEADING_RE.match(lines[j])
            if lines[j].startswith("#"):
                if sub and len(sub.group(1)) > level:
                    has_content = True
                break
            if in_comment:
                if "-->" in candidate:
                    in_comment = False
                continue
            if candidate.startswith("<!--"):
                in_comment = "-->" not in candidate
                continue
            if candidate:
                has_content = True
                break
        if not has_content:
            empty.append("    line %d: %s" % (i + 1, line.strip()))
    if empty:
        findings.append("%d section(s) with no content:" % len(empty))
        findings.extend(empty)

    stubs = []
    in_comment = False
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            in_comment = "-->" not in stripped
            continue
        if STUB_RE.search(line.upper()):
            stubs.append("    line %d: %s" % (number, stripped[:80]))
        elif stripped in ("-", "-.", "- ."):
            stubs.append("    line %d: empty bullet" % number)
    if stubs:
        findings.append("%d line(s) that read as unfinished:" % len(stubs))
        findings.extend(stubs)

    return findings


def run_check(target):
    if os.path.isdir(target):
        path = os.path.join(target, "CLAUDE.md")
    else:
        path = target
    if not os.path.isfile(path):
        print("no CLAUDE.md at %s -- wrong path, or the project was never onboarded." % path)
        print("Draft one with: init-project.py %s --apply" % target)
        return 2
    text = read_text(path)
    if text is None:
        print("cannot read %s" % path)
        return 2

    findings = check_document(text)
    print("checking %s" % path)
    if not findings:
        print("  clean -- no placeholders, no empty sections.")
        return 0
    for finding in findings:
        print(finding if finding.startswith("    ") else "  " + finding)
    print("\nFill the entries above in by hand, then re-run --check.")
    return 1


# ---------------------------------------------------------------------------
# Generate mode
# ---------------------------------------------------------------------------
def default_template():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "templates", "CLAUDE.template.md")


def run_generate(root, args):
    if not os.path.isdir(root):
        print("%s is not a directory -- pass the repo root." % root)
        return 2

    template_path = args.template or default_template()
    template = read_text(template_path)
    if template is None:
        print("cannot read the template at %s" % template_path)
        print("Pass --template <path> if the plugin lives somewhere else.")
        return 2

    target = os.path.join(root, "CLAUDE.md")
    exists = os.path.isfile(target)
    if exists and args.apply and not args.force:
        print("%s already exists -- refusing to overwrite it." % target)
        print("Audit it with --check, or re-run with --apply --force to replace it.")
        return 2

    notes = []
    facts = gather(root, notes)
    document = build_document(template, facts, notes)

    print("init-project -- %s%s" % (root, "" if args.apply else "   [DRY RUN]"))
    print("\nRead out of the repo:")
    for name in sorted(facts["values"]):
        print("  %-18s %s" % (name, facts["values"][name]))
    if facts.get("layers"):
        print("  %-18s %s" % ("dbt layers", ", ".join(facts["layers"])))
    for bullet in facts.get("infra_bullets", []) + facts.get("env_bullets", []):
        print("  %-18s %s" % ("", bullet.lstrip("- ")))

    remaining = sorted(set(PLACEHOLDER_RE.findall(document)))
    if notes:
        print("\nCould not be read:")
        for note in notes:
            print("  - %s" % note)
    if remaining:
        print("\nStill to fill in by hand (%d):" % len(remaining))
        for name in remaining:
            print("  {{%s}}" % name)

    if args.apply:
        try:
            with open(target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(document)
        except OSError as error:
            print("\ncannot write %s: %s" % (target, error))
            return 2
        print("\n%s %s." % ("overwrote" if exists else "wrote", target))
        print("Fill the placeholders above in, then: init-project.py %s --check" % root)
    else:
        print("\nWould write %s (%d lines). Re-run with --apply." % (target, len(document.splitlines())))
        if exists:
            print("That file already exists -- --apply --force would be needed to replace it.")

    return 1 if remaining else 0


def main(argv):
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", nargs="?", default=".",
                        help="the repo to onboard; with --check, a repo or a CLAUDE.md path")
    parser.add_argument("--check", action="store_true",
                        help="audit an existing CLAUDE.md for leftover placeholders and empty sections")
    parser.add_argument("--apply", action="store_true",
                        help="write CLAUDE.md; the default is a dry run that touches nothing")
    parser.add_argument("--force", action="store_true",
                        help="with --apply, replace an existing CLAUDE.md")
    parser.add_argument("--template", help="use a different CLAUDE.template.md")
    args = parser.parse_args(argv)

    if args.check:
        if args.apply or args.force:
            print("--check never writes; drop --apply/--force.")
            return 2
        return run_check(args.repo)
    return run_generate(os.path.abspath(args.repo), args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
