# `DaxOptimizer.json` structure

Observed on **optimizer version `1.9.21`**, undocumented by Tabular Tools —
re-check this file against the plan's spike notes when a run reports a
different `version`. Everything here comes from reading an actual result
zip, not from published API docs.

## Shape

```
version                       e.g. "1.9.21"
messages[]                    { category, level, text, objectType, objectName }
rules[]                       only rules that fired in this run
  docId
  url                         https://kb.daxoptimizer.com/d/<docId>
  localizations[]             { localeId, title, description }
objectAnalyses[]              one entry per analysed object
  objectName
  objectType                  1 = measure (confirmed); 8 seen once, meaning unconfirmed
  dax                         the object's full DAX expression, as text
  daxFingerprint               stable id for this object across runs (see below)
  weight                       relevance score shown in the web app (higher = shown first)
  cpuScore, cpuOptimizability
  materializationScore, materializationOptimizability
  directReferenceCount
  indirectReferenceCount
  totalExecutionCount
  maximumExecutionCount
  recommendationCount
  recommendationNodes[]        { type, from, to, name,
                                  recommendations[]: { ruleDocId, weight, cpuWeight,
                                                        materializationWeight, fingerprint } }
  referencedMeasures[]         { type, from, to, name, tableName }
  syntaxTokens[]                { type, fromChar, toChar }
  syntaxTree                    full AST of the expression
```

## Field notes

- **`from`/`to` and `fromChar`/`toChar` are character offsets into the
  object's `dax` string.** `toChar` is **inclusive** — verified against
  actual output; a naive `dax[fromChar:toChar]` (exclusive-end slice) will
  cut the last character. Use `dax[fromChar:toChar+1]` or equivalent.
- One **recommendation** = one issue. A single `recommendationNodes[]` entry
  (one syntax location) can carry several `recommendations[]` if more than
  one rule fires on the same span.
- `weight` is the relevance ordering used in the web app's Issues list
  (higher first). `cpuWeight` vs `materializationWeight` on a recommendation
  say which kind of cost it addresses — surface both, don't collapse them
  into one number.
- `messages[]` is how "not analysed" surfaces: an entry there (e.g. an SVG
  measure tripping "Invalid parameter specification: EXPR cannot be used
  with Scalar") means the analyser could not parse that object, not that the
  run failed. See `cli.md` on `SucceededWithErrors`.

## Not in this file

Fixed/Ignored state, textual severity labels, the body text of KB articles,
and remaining run quota all live only in the web app / service — none of
them come back in `DaxOptimizer.json`. The report therefore never claims a
Fixed/Ignored state; a later fix skill keeps its own local state keyed by
fingerprint.

## Fingerprints

`daxFingerprint` (on an object) and `fingerprint` (on a recommendation) are
stable identifiers for "this same issue on this same object", used to track
an issue across successive analysis runs **within the same obfuscation
mode**. They do not survive switching between obfuscated and un-obfuscated
uploads of the same model (see `vpax-extraction.md`) — zero overlap was
observed between two such runs of an otherwise identical model. Use
fingerprints to diff two runs of the same project (what disappeared, what's
new), never to compare across a mode switch.

## Deobfuscating tokens

When the source VPAX was obfuscated, `objectName`, `dax`, and every name
inside `syntaxTokens`/`referencedMeasures` are obfuscated strings. The report
script reverses this locally using the `.dict` file from extraction — the
service itself never sees or returns real names.

- `objectName` maps back cleanly for effectively all objects (825/825 in the
  verified run).
- DAX text is deobfuscated **token-by-token** using `syntaxTokens`, not by a
  blind find/replace over the whole string — a naive replace risks hitting
  the wrong occurrence when a short obfuscated token is a substring of a
  longer one elsewhere.
- Only remap tokens of type `TABLE`, `TABLE_OR_VARIABLE`,
  `COLUMN_OR_MEASURE`, and `STRING_LITERAL`. Strip the wrapping quote or
  bracket (`'…'`, `[…]`, `"…"`) before looking the inner text up in the
  dictionary, then put the wrapper back.
- Comments in the DAX are **not** tokens and stay obfuscated — there's no
  token span to remap them through.
- The rebuilt DAX matched the un-obfuscated run exactly for 822/825 measures
  in the verified comparison; the rest differ only in string-literal letter
  case (the dictionary is case-insensitive) or in comments. Good enough for a
  report — the authoritative DAX is in the repo's TMDL anyway.
- Token lengths change, so the script rebuilds every `from`/`to` span (node
  and referenced-measure positions) on the deobfuscated text; the spans in
  the report's technical section refer to the DAX **as printed there**.

## Where each field shows up in the report

| JSON field | Report location |
|---|---|
| `objectAnalyses[].weight`, `recommendationNodes[].recommendations[].weight` | relevance ordering in the issues table |
| `directReferenceCount`, `indirectReferenceCount` | "reach" column (how widely a measure is used) |
| `recommendations[].cpuWeight` / `materializationWeight` | cost-kind badge per issue |
| `rules[].url`, `rules[].localizations[].title` | issue heading + KB link |
| `objectAnalyses[].dax` + `recommendationNodes[].from/to` | the highlighted DAX snippet per issue |
| `messages[]` | "not analysed" section, separate from the issues list |
| `daxFingerprint` / `fingerprint` | technical section at the end — the stable ids a run-to-run diff and the fix skill use |

KB pages at `kb.daxoptimizer.com/d/<docId>` are public and need no login —
link to them; don't reproduce their text (see `cli.md`, Terms).
