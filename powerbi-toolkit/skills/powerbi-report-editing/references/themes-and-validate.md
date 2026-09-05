# Theme JSON and the PBIR validator

Two things that come up together: what a theme can set, and why the validator's
output cannot be read as pass/fail. Visual authoring itself is `pbir-visuals.md`.

## Themes

- The authoritative source for `*theme.json` cards and properties is Microsoft's
  official **report theme JSON Schema** (powerbi-desktop-samples repo, Draft-7, one
  file per monthly Desktop release). Download the newest and inspect
  `definitions.visual-<visualType>` (e.g. `visual-pivotTable`, `visual-tableEx`).
  It is a big file and grepping it has no decision value — **delegate the lookup**
  and have the agent return just the card/property names and their allowed values.
- Visual **title** color is `fontColor`, not `color` (`color` is silently ignored).
- Matrix subtotal/total fonts use separate cards `subTotals` / `columnTotal` /
  `rowTotal` (not the flat `*` card); `subTotals` takes `$id: "Row"|"Column"`.
- Date slicers size via `date.textSize`, list/dropdown slicers via `items.textSize`.

### Registering a theme in a report

Don't point a new report at a theme file sitting in the repo root — that copy is
routinely a different version from what the running reports actually use. Copy the
theme out of an existing working report instead.

1. `StaticResources/RegisteredResources/<ThemeName><17 digits>.json` — the theme
   copy; the filename is unique per report.
2. `StaticResources/SharedResources/BaseThemes/<BaseTheme>.json` — the base theme.
3. In `definition/report.json`: `themeCollection.customTheme` of type
   `RegisteredResources` + `baseTheme` of type `SharedResources`, both with
   `reportVersionAtImport`, plus the matching `resourcePackages`.

The theme's internal `name` stays as-is and will not match the filename. That is
correct — running reports look the same.

## `validate` — read by code, never by pass/fail

`powerbi-report-author validate` is **not** a usable pass/fail gate. Its
metadata provider is incomplete and it returns hundreds of false positives against
valid, documented properties. **Filter by diagnostic CODE.**

*Verified against `powerbi-report-author` v0.1.x; a later release may narrow the
false positives, so re-check the code list below before trusting or ignoring it.*

Trust: `PBIR_FILTER_NAME_DUPLICATE_GLOBAL` (real copy-paste artifacts),
malformed-JSON / structural errors.

Ignore (verified against reports that are live and in production):

| Code | Why it's noise |
|---|---|
| `PBIR_FORMATTING_OBJECT_UNKNOWN` | valid documented properties the provider doesn't know |
| `PBIR_THEME_VISUAL_PROP_UNKNOWN` | same |
| `PBIR_THEME_FILE_NAME_MISMATCH` | expected — theme `name` ≠ filename by design |
| `PBIR_SLICER_HEIGHT_BELOW_FLOOR` | the validator pushes slicers to 76px; the project's layout file may specify less **on purpose** — that file wins |
| "Category missing" | fires on measures-only comparison charts |

`--no-schema` does **not** silence the UNKNOWN families.

And it is blind to entire classes of real defect: malformed projections (zero
findings on either of the two broken visuals in `pbir-visuals.md`), broken M
escaping in the model, and
anything below the report definition such as a `.pbix` packaging problem. Passing
`validate` means nothing on its own — the screenshot is the check.
