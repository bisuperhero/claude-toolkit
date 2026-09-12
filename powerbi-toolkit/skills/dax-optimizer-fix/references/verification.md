# Verifying a rewrite

## Why this exists

DAX Optimizer's relevance scores (`dax-optimizer-report`) estimate engine
cost from the model's shape and statistics. They say nothing about whether a
rewritten measure still returns the same numbers — several rules' own
knowledge-base entries admit "no general solution", meaning the rewrite can
silently change results in edge cases the rule can't see. A fix is not done
because it scores better; it is done because it was proven to return the
same values it did before, on the actual model and data. `daxopt-verify.py`
is that proof, not a formality around it.

## The four-step workflow

The tool only ever talks to a **running** Power BI Desktop instance through
DAX Studio's `dscmd.exe`, so the sequence matters and each step depends on
the previous one landing cleanly:

1. **Desktop open, report saved.** `powerbi-desktop status` (the Desktop
   bridge, see the `powerbi-report-editing` skill's
   `references/desktop-bridge.md`) must show `hasUnsavedChanges: false`
   before a baseline — a baseline taken against unsaved in-memory edits
   describes a model state that isn't in git, so a later diff against it
   proves nothing about the committed change.
2. **`baseline`.** Captures the "before" values for the measures and `--by`
   groupings that matter for this fix.
3. **Desktop closed, TMDL edited.** Desktop owns the model file while open
   and rewrites it on save, silently clobbering an external edit — the
   rewrite must happen while Desktop is not holding the file. Confirm closed
   with `status` → `not_connected`.
4. **Desktop reopened, `compare`.** `powerbi-desktop open <report>` loads
   the edited TMDL into a fresh instance (a `reload` does **not** re-read
   the semantic model, only the report layer — see `desktop-bridge.md`).
   Once `status` shows connected, `compare` re-runs the same queries and
   diffs them against the baseline.

Skipping step 1's unsaved-changes check, or running `compare` against a
`reload` instead of a fresh `open`, both produce a comparison that looks
clean but didn't actually exercise the edited DAX.

## Choosing `--by` columns

A grand total can hide a wrong answer that only shows up sliced. Pick:

- **The Date table's year and month** (or whatever grain the model's
  measures are normally viewed at) — catches a rewrite that changes results
  only in some periods (e.g. a `LASTDATE`/context-transition fix that
  behaves differently once "no rows this period" is possible).
- **One or two dimension attributes the measure is typically sliced by** in
  the report it feeds — reproduces the filter contexts a rewrite actually
  has to survive, not just the unfiltered total.
- **A column that exercises the specific trap named in the rule's own "Verify
  with" hint** (`references/fix-playbook.md`) — most often a column that has
  rows with a `BLANK` group, since several rules' failure modes are exactly a
  changed BLANK/0 boundary (blank comparisons, `ALL`/`ALLNOBLANKROW`
  variants, filtered-table rewrites). If the playbook names a more specific
  scenario (a duplicate key, a mid-period lookup change), prefer a `--by`
  column that actually produces that scenario over a generic one.

## What "equal" means

`compare`'s tolerance is `|before - after| > tolerance * max(1, |before|,
|after|)` (default `1e-9`, `--tolerance` to change it) — a relative
comparison for large numbers, an absolute one near zero. This exists purely
to absorb floating-point noise between two DAX Studio sessions (formula
engine evaluation order, cached vs. fresh storage engine reads), not to wave
through a real change. If a difference could plausibly be "the same
calculation, different rounding", tighten `--tolerance` and re-run before
deciding it's noise; do not raise the tolerance to make a real difference
disappear (see `fix-playbook.md`'s standing rule against this).

## On a difference

`compare` exits `1` and prints a Markdown table (measure, grouping, key,
before, after) for every value outside tolerance and every key present on
only one side. The default action is to **revert** the change (`git
checkout` the touched TMDL file, or undo the edit) and re-run `compare` to
confirm the revert restores equality. Keeping a difference is only valid
when the user reads the table, agrees the new numbers are the *correct* ones
(the rewrite fixed a latent bug, not just DAX Optimizer's complaint), and
says so explicitly — record that acceptance in the fix log
(`daxopt-fixlog.py`), don't infer it from silence.

## Limits

- **Row-level security is not exercised.** Queries run as whoever has
  Desktop open, with no RLS role applied — a rewrite that only breaks under
  a specific role's filter is invisible to this tool. If a measure is
  wrapped in RLS-sensitive logic, say this limit out loud rather than
  reporting equivalence.
- **Calculation groups are only exercised when a `--by` column is the calc
  group's own column** (selecting a calculation item), since that's the only
  way a `--by` grouping can bring one into the filter context; the calc
  group's other items are otherwise silently untested.
- **DirectQuery is slow.** Every query round-trips to the source system;
  large `--top` values or many `--by` columns multiply that. Prefer a
  smaller `--top` and fewer, targeted columns over broad coverage.
- **The exact numeric coincidence.** Comparing a handful of totals and a
  couple of hundred grouped rows cannot prove equivalence for every possible
  filter context — it raises confidence, it does not replace understanding
  *why* a rewrite is equivalent (or isn't) from the DAX itself.

## Linux/macOS

There is no Power BI Desktop on Linux or macOS, so `daxopt-verify.py`
refuses immediately on those platforms (see its module docstring) — every
command needs a live Desktop instance reachable through `dscmd.exe`, which
is Windows-only (native, or a WSL2 host driving a Windows-side Desktop). On
those platforms the fix skill can still read the playbook, propose a
rewrite and show the diff, but it stops there: it proposes, it does not
apply, because the change cannot be proven equivalent on that machine.
