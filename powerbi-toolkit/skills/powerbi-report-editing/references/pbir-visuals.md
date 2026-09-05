# PBIR — authoring visuals, themes and pages

Everything here is a silent failure: the report still opens, the visual still
renders, and the setting is simply ignored — or a column quietly vanishes from the
query. None of it is reported by `powerbi-report-author validate`.

## Projections — the rules that break visuals

**Never author projections from scratch.** Copy the `visual.json` of an existing
Desktop-made visual of the **same `visualType`** and swap only `Property` /
`queryRef` / `nativeQueryRef`. Well structure differs per visual type — one field
builder reused across two types is exactly how this breaks. When you inspect the
reference, print the **full key set** of each projection, not just entity and
property; the keys are the part that differs. Finding that reference visual across
the reports on disk is a search with no judgement in it — delegate it, and ask for
the path plus the projection block verbatim.

### `active` belongs only to hierarchy wells

Surveyed across production report repos following this convention, `active`
legitimately appears in exactly two places:

- **hierarchy / axis wells** — `Rows` and `Columns` (`pivotTable`), `Category` and
  `Series` (charts), `Group` (`treemap`);
- **a slicer's single field** — note that slicers put it in the `Values` well, and
  that is correct. `advancedSlicerVisual` counts as a slicer here.

**Never in `Values` on a non-slicer visual** (`tableEx`, `pivotTable` values,
cards), and never in the other measure wells (`Data`, `Y`, `Tooltips`, …).

Desktop propagates the key when the visual is next edited and defaults
later-added fields to `false`, so those columns silently drop out of the visual's
query: visible in the Data pane, missing in the report, and still missing after
publishing to Services.

This has been observed repeatedly in production repos, more than once in the same
report. The first attempted fix — flipping `false` to
`true` on the one visible column — is a patch, not the cause; remove the key from
`Values` projections entirely.

### `drillFilterOtherVisuals: true`

Goes beside `visualType` on every data visual. Without it, clicking the visual
won't cross-filter the rest of the page. (In a surveyed production repo, 228 of
238 data visuals have it — the handful without are the exception, not the
pattern.)

Both rules are enforced by `scripts/check-visual-projections.py`; run it over the
whole repo before committing.

## `tableEx` / `pivotTable`

- **Title** goes in `visual.visualContainerObjects.title`, **not**
  `visual.objects.title` — the latter is silently ignored.
- **`columnWidth` selector** is `{"metadata": "<Entity>.<nativeQueryRef alias>"}` —
  for renamed measures the **alias**, not the `queryRef`. Values act as a desired
  width; a column never shrinks below its content width.
- **Conditional font color** from a `_color` measure: card `values`, property
  `fontColor` (**not** `fontColorPrimary`, which is static zebra styling), selector
  `{"data":[{"dataViewWildcard":{"matchingOption":0}}],"metadata":"<queryRef>"}`.
  `matchingOption` 0 = values + totals (colors matrix subtotal rows and Total),
  1 = leaf values only. Here the `queryRef` works, not the alias.
- **Matrix expand/collapse** persists via `expansionStates`: level `isCollapsed:
  true`, plus `root.children[].identityValues` with `isToggled: true` to expand one
  member.
- **Font size** is `fontSize` on the `columnHeaders` / `values` / `total` cards,
  written as a decimal literal (e.g. `"9D"`). Dropping a point or two is the lever
  that fits a wide table into its width — the project's layout file (section 7) says
  which size this project uses.
- A theme with `autoSizeColumnWidth: true` makes tables content-sized, which adapts
  well to slicer-driven periods (no truncation).

## `cardVisual`

Rename a card's label with **`displayName`** directly on the projection in
`query.queryState.Data.projections[]`:

```json
{
  "field": { "Measure": { "Expression": { "SourceRef": { "Entity": "_Measures" } }, "Property": "_Revenue" } },
  "queryRef": "_Measures._Revenue",
  "nativeQueryRef": "Revenue",
  "displayName": "Revenue"
}
```

What does **not** work: `nativeQueryRef` alone (it drives renames in
`pivotTable`/`tableEx`, but does not touch a card's label), and `objects.label`
with `labelText` / `labelContentType` — Desktop drops those properties on the next
save and leaves `"properties": {}`.

Reference labels do work, via `objects.referenceLabel` (value),
`referenceLabelTitle` (`titleContentType: "custom"` + `titleText`) and
`referenceLabelValue` (`valueFontColor` bound to a `_color` measure) — all with
selector `{"metadata": "<queryRef of the card's main field>", "id": "<unique id>"}`.

Note that a reference label pointing at a measure the model can't resolve is
**silently dropped** — the card renders without it and shows no error. On a thin
report that usually means a stale model schema, see `thin-reports.md`.

## Naming — what the Selection pane shows

Desktop's Selection pane lists a visual by its **title text**, falling back to the
visual type when there is none. A pane full of `Card`, `Table`, `Slicer` is
unreadable and makes every later edit a hunt.

Set `visualContainerObjects.title.properties.text` on every visual, including ones
whose title is not displayed — set the text and `show: false` together. That is
what a Selection-pane rename in Desktop produces, and production reports carry the
pattern.

```json
"visualContainerObjects": {
  "title": [{ "properties": {
    "text": { "expr": { "Literal": { "Value": "'KPI cards in the page header'" } } },
    "show": { "expr": { "Literal": { "Value": "false" } } }
  }}]
}
```

Note the literal is a **single-quoted string inside the JSON string**, as
everywhere else in PBIR expressions.

Groups carry their own label: `visualGroup.displayName` at the top level of
`visual.json` (a group has no `visual` block). Desktop writes `Group 1` there by
default — replace it.

The **wording and language** of names is a project convention: see section 6
"Naming" of the project's layout file. `scripts/check-visual-projections.py` warns
about visuals with no name at all.

## Slicers

Set the mode explicitly rather than relying on the visual's default:

```json
"objects": { "data": [{ "properties": {
  "mode": { "expr": { "Literal": { "Value": "'Dropdown'" } } }
}}]}
```

Accepted literals: `Dropdown`, `Basic`, `Single`, `Between`, `Before`, `After`,
`Relative`. **Which mode is the default for list slicers and for date slicers is a
project decision** — section 4 of the project's layout file.

A slicer is the one visual where `active` on its single field projection is
correct. `isInvertedSelectionMode` on the same `data` card flips it to exclusion.

## Comparison series — previous period and target

A chart that shows a comparison series (previous year/quarter/week/period — `PY`,
`PQ`, `PW`, `PP`, `LY`, `MoM`, or a target/plan) must not leave that series to the
theme's next palette slot. The comparison line has a **semantic role**: it is
context behind the current value, or a threshold — never another equal category.

**Always ask before applying it.** Adding a color is a visible design decision, so
put it to the user: *"apply the default comparison color to the PY series?"* Do
not apply it silently, and do not skip the question because the answer was yes
last time.

### Where the color comes from

In order:

1. **A color measure in the model**, if one exists — the project's registry. Read
   its constant value and use that. Naming follows the project's existing color
   measures; the toolkit's default names are `_PY chart color` and
   `_Target chart color`.
2. **If the measure does not exist, create it**, with the default from section 7 of
   the project's layout file, and tell the user you created it.

Creating it rather than inlining a hex is the point: the next chart, in any report
on this model, reads the same measure, and changing the shade later is one edit.
Put it beside the project's existing palette measures (`_color_green`,
`_color_red`, `_color_neutral …`, or whatever the project already calls them),
hidden, returning a string:

```tmdl
measure '_PY chart color' = "#666666"
	isHidden
```

### Writing it into the visual

A whole series takes a **static** color selected by the series' `queryRef` — this
is not conditional formatting, which colors data points within a series:

```json
"objects": { "dataPoint": [{
  "properties": { "fill": { "solid": { "color": {
      "expr": { "Literal": { "Value": "'#666666'" } } } } } },
  "selector": { "metadata": "_Measures.Σ Sales PY" }
}]}
```

So the measure is the **source of truth read at authoring time**, and its value is
written into the visual — a series fill cannot itself be bound to a measure.
Re-read the measure whenever you touch these visuals, so they don't drift from it.

### The theme trade-off — say it out loud

A literal hex is a per-visual override: `find-theme-overrides.py` will flag it, and
a later theme change will not reach it. Two legitimate answers, and the project
picks one in its layout file:

- **Literal from the color measure** (what this convention describes) — explicit,
  greppable, one measure to change, but outside the theme.
- **A theme palette shade** — `{"expr": {"ThemeDataColor": {"ColorId": 0, "Percent": -0.3}}}`
  darkens palette color 0 by 30%. Stays inside the theme and follows a rebrand.
  There is live precedent for exactly this on a `Σ Sales PY` series in a
  production report.

**The toolkit default is the literal**, per the layout template. That means these
fills are expected to show up as OVERRIDE in `find-theme-overrides.py` — the
layout file's section 10 says so, and a refactor must leave them alone.

### Targets are a different role

A target is a **threshold**, not context, so it gets its own color and its own
rendering: a **dotted line**, never a filled series in the previous-period grey —
that would make two different meanings look alike. Toolkit default `#333333`; the
project's layout file section 7 has the value.

A target series' line style lives on the `lineStyles` card, selected by the
series' `queryRef` exactly like `dataPoint`:

```json
"lineStyles": [{
  "properties": {
    "lineStyle":   { "expr": { "Literal": { "Value": "'dotted'" } } },
    "strokeWidth": { "expr": { "Literal": { "Value": "2L" } } }
  },
  "selector": { "metadata": "_Measures.Σ Sales Target" }
}]
```

A constant threshold with no measure behind it is a reference line instead —
`y1AxisReferenceLine`, selected by `{"id": "1"}`, with `style` taking the same
`'dotted'` literal and the color in `lineColor`.

Keep all of this separate from **attainment** coloring (hit/miss → green/red),
which is conditional formatting driven by the model's existing
`_color … vs Target` / `_color … attainment` measures. Two different mechanisms;
don't merge them.

## Themes and the validator

Theme cards and properties, registering a theme in a report, and how to read
`powerbi-report-author validate` are in `themes-and-validate.md`.

## Schema versions are per file, not per report

Every `visual.json` carries the `$schema` version it was last written with, and
Desktop upgrades a visual only when it re-saves that one visual. A report in
active development therefore holds several `visualContainer` versions at once —
2.4.0 through 2.12.0 in one surveyed production report, alongside `page` 2.0.0
and 2.1.0. Consequences when editing these files by hand or by script:

- Never rewrite or normalize a `$schema` declaration. Edit the file in place and
  leave the version Desktop gave it; nothing in this toolkit touches it.
- Do not assume a property exists everywhere just because it exists in one
  visual — an older container may predate it. Read the file you are editing.
- A property that Desktop writes in a newly saved visual may be rejected in an
  older one. If an edit makes Desktop refuse the file, check that visual's schema
  version before assuming the shape is wrong.

*Verified 2026-09-05 against a production report authored by Power BI Desktop
2.157.1354.0.*
