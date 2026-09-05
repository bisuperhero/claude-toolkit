# Commit message standard

Shared across all Mage/dbt projects. Use Conventional Commits, **no emojis**.

## Header
`<type>(scope?): short summary`
- Max 50 characters.
- Type ∈ `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`,
  `build`, `ci`, `revert`.
- Scope optional, use when helpful: `feat(dbt): ...`, `fix(loader): ...`.
- Imperative, present tense: "Add", "Fix", "Update".

## Body
Blank line after header, then one bullet per individual change. Wrap ~72 chars.

## Footer (optional)
- Breaking change: `BREAKING CHANGE: description`
- Issue refs: `Closes #123`, `Refs #456`

## Example

```
fix(dbt): correct issued-invoice date casting

- Cast DOCDATE via to_date() guarded by a format check, then truncate
- Exclude rows with unparseable dates from the fact
- Update test fixtures for the new grain

Closes #321
```

## Suggested scopes for these projects
`loader`, `exporter`, `config`, `transformer`, `dbt`, `staging`, `intermediate`,
`marts`, `reporting`, `compose`, `docker`, `mage`, `ci`.
