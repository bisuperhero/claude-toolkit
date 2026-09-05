# Refactoring an existing page onto the current layout

The before/after screenshots this procedure is built around need **Power BI
Desktop on Windows** (or WSL2 with access to a Windows Desktop install); on Linux
or macOS the geometry edits are possible but the refactor cannot be verified.

Take a page the user names and rebuild it to the project's current standard:
right canvas size, recomputed geometry, formatting handed back to the theme,
readable names. **Structure and content stay; presentation is redone.**

The values come from the project's layout file, never from this document —
run `scripts/check-layout-file.py` first and read that file's sections 1–7.

## 0. Preconditions

- The layout file is current (`check-layout-file.py` exits 0). If it is missing,
  unreviewed or a copy from another project, **stop and settle that first** — a
  refactor against wrong values is worse than no refactor.
- Working tree clean, or the page's files committed, so the diff is reviewable
  and revert is one command.
- The report is closed in Desktop, or the bridge is ready (`desktop-bridge.md`).
- **Take a "before" screenshot.** You cannot judge the result without it.

Confirm with the user which page, and which report if the name is ambiguous.
Refactor **one page at a time**.

## 1. Inventory the page

Read `page.json` (canvas size, `displayOption`, `displayName`) and every
`visuals/*/visual.json`. **Delegate this** — it is bulk reading with no decision
in it; have a subagent return the inventory as a table, not the files. Refactoring
several pages? One agent per page, sent in one message. For each visual record: `visualType`, `position`
(x/y/z/width/height/tabOrder), the wells and fields, the title text, whether it
is a slicer, a Card, a shape/textbox/button, or part of a `visualGroup`.

From that, derive the page's **logical structure** — this is what survives:

- which visuals form a row, and their left-to-right order within it;
- the row order top to bottom;
- what is the slicer column/panel, and the slicers' order;
- what is header furniture (title, navigation, buttons — often `y` inside the
  title band and a high `z`);
- which visuals are decoration (shapes behind panels) and must move with the
  thing they sit behind.

## 2. Recompute geometry

From the layout file, sections 1–5. Rules that hold regardless of project:

- **Never scale old positions proportionally.** Aspect ratios differ between
  canvas sizes, so scaling distorts the layout. Recompute from the rules.
- Set the canvas to the standard size and `displayOption` per section 1.
- Place the slicers per section 4 — including the panel's backing shape, when the
  project uses one; it is drawn first (lowest `z`) and its height is a function of
  the slicer count.
- Split rows per section 5: equal width per row, standard gaps, the project's
  minimum visual height, cards at their fixed height. If equal splitting would
  break the minimum, **grow the page height** rather than shrink visuals.
- Where a row is several old single-value KPI cards side by side, collapse it into
  one Card visual if the layout file says so — and if that empties a row, drop the
  row from the height split instead of leaving a band of air.
- Snap everything to whole pixels; no overlaps.

Keep `z` order and `tabOrder` meaningful: decoration below content, header on top.

## 3. Hand formatting back to the theme

This is the part that makes the page part of the design system again:

```bash
python3 <skill-dir>/scripts/find-theme-overrides.py <report-dir> --detail
```

On a page with many findings, hand the `--detail` output to a subagent to apply
the agreed removals; keep the decision about which overrides are deliberate.

- **OVERRIDE** — the visual sets a different value than the theme, so the theme no
  longer reaches it and a future theme change will skip this page. Take these back
  to the theme unless the value is a deliberate exception.
- **REDUNDANT** — the visual repeats the theme's own value. It does nothing today
  and freezes the old look the moment the theme changes. Delete.

Judgement, not blanket deletion:

- **Keep** conditional/data-driven formatting, anything with a data or state
  selector (the script already skips those), and deliberate accents — record the
  deliberate ones in the layout file section 10 so the next pass leaves them alone.
- **Never strip `title.text`** — it is the visual's name in the Selection pane.
- If the project's theme is missing a value the page genuinely needs everywhere,
  the fix is the theme, not a per-visual override.

Where the layout file names structural requirements (e.g. matrices must be
`pivotTable`, not legacy `matrix`; cards need zero padding), apply them here too.

## 4. Naming pass

While you are in every visual anyway, give each one a Selection-pane name per
section 6 of the layout file — mechanics in `pbir-visuals.md`. A refactored page
with a pane full of `Card`, `Table`, `Slicer` is only half done.

## 5. Verify

```bash
python3 <skill-dir>/scripts/check-visual-projections.py <repo-root>
python3 <skill-dir>/scripts/find-theme-overrides.py <report-dir>
git diff --stat
```

Then **screenshot the page and compare against the "before" shot**. What to check:
every visual still renders every field it had, nothing overlaps or is clipped, the
slicer panel and header sit where the layout file says, and the page reads as the
same page — same data, better geometry.

`git diff --stat` also catches the line-ending mistake: a refactor touches many
files, so a whole-file rewrite is easy to hide (see the editing rules in `SKILL.md`).

## What a refactor must not do

- Change which fields a visual shows, or its measures and filters.
- Rename model objects, or change the page's `displayName` unless asked.
- Reformat or reorder JSON that the refactor did not otherwise touch.
- Touch other pages. One page, one reviewable diff.
