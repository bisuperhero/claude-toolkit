# Power BI layout & formatting standard — {{PROJECT_NAME}}

<!-- layout-template-version: 2 -->

<!--
  Generated into this project by the powerbi-report-editing skill on first use.
  It is a copy of the skill's DEFAULT template; the values below are a starting
  point, not a rule. Review and adjust them for this project/brand before
  generating dashboards.

  This file is AUTHORITATIVE for this repo. It outranks the skill (which holds no
  formatting values at all) and it outranks `powerbi-report-author validate`
  wherever the two disagree. Keep the section headings as they are — the skill
  refers to them by name; change the values under them freely.

  Delete this comment once the file has been reviewed, but KEEP the
  `layout-template-version` marker above — the skill uses it to tell a current
  file from one written against an older template.
-->

Status: **UNREVIEWED DEFAULT** — replace with `Reviewed <date> by <who>` once
checked, so nobody mistakes the defaults for project decisions.

## 1. Page canvas

- Default page size: **1500 × 900**.
- Page view (`displayOption` in `page.json`): height ≤ 900 → `FitToPage`;
  height > 900 → `FitToWidth`.
- When a page holds more visuals than fit, increase **page height**, not visual
  density.
- Snap all X/Y/width/height to whole pixels; never overlap visuals.

## 2. Grid & spacing

- Standard gap: **10px** — between every element and against page edges. One value
  everywhere, no special cases beyond those listed below.

## 3. Header / title band

- **80px** tall at the top; content and slicers start at **Y=80** (no extra gap).
- Title textbox at `x=0, y=0, height=80, width=1200`; padding left/top/right = 10.
  It deliberately stops short of the 1500px page width: the right end of the band
  is reserved for header furniture — the two-slicer exception in section 4, a
  logo, navigation buttons. On a page with nothing there, widen it to the full
  page width. If the project has a reference "Sample title" textbox, copy that
  instead.
- Title: `Segoe UI Light`, 24pt, default color.
- Subtitle: second paragraph, `Segoe UI Light`, color `#666666`.

## 4. Slicers

- Default size **240 × 60**.
- Single column, stacked **touching** — no vertical gap. This is the one deliberate
  exception to the 10px rule.
- Column at X=10, first slicer at Y=80; main content starts at X=260 (10px gap).
- Exception: a page with only two slicers (e.g. date + one dimension) → place them
  in the right-hand side of the header, 10px from the top and right edges.

### Slicer mode (default appearance)

- Ordinary (list/category) slicers: **`Dropdown`**.
- Date slicers: **`Between`**.

Every slicer gets its mode set explicitly — don't leave it to whatever the visual
type happens to default to. Written as `visual.objects.data[0].properties.mode`
(the exact JSON is in the skill's `pbir-visuals.md` reference); other accepted
literals are `Basic`, `Single`, `Before`, `After` and `Relative`, which are
deviations worth recording in section 10.

## 5. Visual sizing & rows

- Visuals are arranged in rows; 10px gaps horizontally and vertically.
- A row of N visuals splits the content width equally; all outer and inner gaps
  are 10px.
- Rows split the available height (Y=80 down to a 10px bottom margin) into equal
  bands, so visuals fill the page vertically. On the default 1500 × 900 page that
  band is `900 − 80 − 10 = 810px`, and with a 10px gap between rows, N rows are
  `(810 − 10 × (N−1)) / N` tall each: **810px** for one row, **400px** for two,
  **263px** for three.
- **Non-KPI visuals ≥ 400px tall. KPI cards fixed at 180px.** 400 is exactly what
  two rows come to on the default page — i.e. two standard rows is the most a
  900px page holds. If equal splitting would push a non-KPI row below 400px,
  increase the page height instead. Exception: a non-KPI visual sharing a row with
  a KPI card matches the card's 180px.
- **Recomputing for another canvas height:** the content band is
  `H − 80 − 10`, so to fit N non-KPI rows of at least `h` px the page height must
  be `H ≥ 90 + N × h + 10 × (N−1)`. Three 400px rows therefore need
  `90 + 1200 + 20 = 1310px`. Change `h` here as well if the project changes the
  minimum.
- With no slicer column (or slicers in the header), content uses the full width
  (X=10 to X=1490 on a 1500-wide page; 10px both margins).

## 6. Naming

Every visual gets a name that reads clearly in Desktop's **Selection pane** —
`Card` or `Table` tells a reader nothing.

- Language for names: **{{NAMING_LANGUAGE}}**.
- Pattern: what it shows + where/what it is, e.g. `KPI cards in the page header`,
  `Revenue by division — column chart`, `Slicer: period` — written in
  `{{NAMING_LANGUAGE}}`.
- Applies to visuals whose title is hidden too; the name lives in the title text
  regardless of whether the title is displayed.
- Visual groups get a `displayName` on the same principle — never `Group 1`.
- Page names (`displayName` in `page.json`) follow the same rule.


### Measure descriptions

The `///` block above a measure is its Data-pane tooltip and has **two parts**:
prose saying what the measure means, then the DAX after a `---` separator. The DAX
block is required because a **thin report cannot see the model's definitions** —
the description is the only place the formula reaches the report author.

```
/// <meaning, and the trap if there is one>
/// 
/// ---
/// 
/// <the DAX>
```

- Language of descriptions: **{{DESCRIPTION_LANGUAGE}}**.
- Prose: one sentence of business meaning, plus a second only when there is a real
  trap (excluded from a denominator, sign convention, mixed currency, a filter it
  depends on, a unioned source). Target ≤160 characters **for the prose**; the DAX
  block is not counted.
- No boilerplate openers ("This measure…", "Displays…") — the formula is already
  in the `---` block, so don't restate it in words either.
- The DAX block is a copy: update it in the same edit whenever the measure changes.
- Every measure gets one. Non-negotiable for anything with a denominator, a sign
  convention, a filter dependency, a unioned source, or a config/color measure.

Mechanics and the anti-patterns: see the skill's `tmdl-and-model.md` reference
(this file is a copy in the project repo, so that reference is not beside it —
look in the powerbi-report-editing skill). Check coverage
with `scripts/check-measure-descriptions.py`.

## 7. Typography, colors & theme

- Theme file used by this project: `{{THEME_FILE}}` — registered per report under
  `StaticResources/RegisteredResources/` (registration steps are in the skill's
  `themes-and-validate.md` reference).
- Base theme: `{{BASE_THEME}}`.
- Semantic colors: positive `{{COLOR_POSITIVE}}`, negative `{{COLOR_NEGATIVE}}`.
- Table/matrix font size: `{{TABLE_FONT_SIZE}}`.
- Formatting is owned by the theme. **Don't change formatting unless it is
  explicitly part of the task.** Conditional formatting may be changed when needed.

### Comparison series colors

Charts with a previous-period or target series get a deliberate color, never the
theme's next palette slot. The skill **asks first**, then reads the value from a
color measure in the model, creating that measure from the default below if it
does not exist yet.

| Role | Color measure | Default | Rendered as |
|---|---|---|---|
| Previous period (PY, PQ, PW, PP, LY, MoM) | `_PY chart color` | `#666666` | muted fill behind the current series |
| Target / plan | `_Target chart color` | `#333333` | **dotted** line / reference line, not a fill |

- Measure names follow this project's existing color-measure convention if it has
  one (including a non-English prefix, when that is what the model already uses);
  the names above are the toolkit default.
- Keep these separate from **attainment** coloring (hit/miss → green/red), which
  is conditional formatting on its own `_color … vs Target` measures.
- Binding style: **literal hex read from the color measure** (the default). It is
  explicit and greppable, and one measure edit moves every chart. It is also a
  per-visual override the theme cannot reach, so it is listed in section 10 and a
  refactor must not strip it. The alternative, if a project prefers to stay inside
  the theme, is a palette shade (`ThemeDataColor` + negative `Percent`).

## 8. Placeholders & shorthand

- Generate empty dashboards with **table**-type placeholder visuals.
- Shorthand `"3-2-3"` = a slicer column (4 empty placeholder slicers) plus content
  rows of 3, 2 and 3 visuals.

## 9. Copying another report's structure

- Copy element **logic** only: visual types, fields/columns, metrics.
- Do **not** copy formatting, sizes or positions — recreate them from the rules
  above.
- Exception: do copy conditional formatting when a visual has it.

## 10. Project deviations & validator exceptions

Record here anything where this project deliberately departs from a general
expectation, so it is not "fixed" later by mistake.

- `PBIR_SLICER_HEIGHT_BELOW_FLOOR`: the validator pushes slicers to 76px; section 4
  specifies 60px **on purpose**. Ignore that code in this repo.
- Comparison-series colors (section 7) are written as literal hex on the visual.
  `find-theme-overrides.py` reports them as OVERRIDE — that is expected and
  deliberate; do not "clean them up" in a refactor.
- <!-- add further deviations as they are decided -->

## 11. Project-specific extras

Anything this project needs that the template doesn't model — reference pages,
header/navigation patterns, per-report grids measured off existing pages, PBIR
snippets proven in this repo. Free-form; keep sections 1–10 as the place a reader
looks first.
