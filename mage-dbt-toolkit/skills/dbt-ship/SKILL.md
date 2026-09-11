---
name: dbt-ship
description: Safe rollout of a dbt change — dev build, tests, dev vs prod column diff, permission check as the consuming role, commit only the touched files. Run manually with /dbt-ship before pushing.
disable-model-invocation: true
effort: high
---
# dbt-ship — pre-push gate

Context: !`git status --short` · !`git diff --name-only origin/main -- '**/dbt/**'`

1. **Changed models**: derive the models from the list above (`models/**/*.sql`, `*.yml`).
2. **Dev build**: `dbt build --select <models>+` (the repo's venv). On error, stop — nothing further.
3. **Dev vs prod column diff** for each changed model: through both the dev and the prod toolbox tool
   `SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='<s>' AND table_name='<t>' ORDER BY ordinal_position`.
   A name/type difference = FAIL (the prod dbt run would fail / the report would silently lose its binding).
4. **Permissions as the consumer**: for a new schema/table
   `SELECT has_schema_privilege('powerbi','<s>','USAGE'), has_table_privilege('powerbi','<s>.<t>','SELECT')`. FALSE = FAIL.
5. **Reporting layer**: if a `*_reporting/` model changed, list which columns have to go into the semantic model in `*_powerbi`.
6. **Hanging queries**: `SELECT pid, state, now()-query_start AS age, left(query,80) FROM pg_stat_activity WHERE application_name LIKE 'claude%'` — a hanging query of your own = warning.
7. Output: a PASS/FAIL table per step, with the verbatim query output. On any FAIL **do not push**, do not commit.
8. On PASS: `git add <only the touched files>` and a Conventional Commits message. Push only when told to.
