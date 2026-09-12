# Fix playbook — one entry per DAX Optimizer rule

Each entry below covers one DAX Optimizer (Tabular Tools) rule. Two classes:

- **mechanical** — a local, syntactic rewrite whose result is provably identical to the
  original (e.g. `DATEDIFF(a, b, DAY)` → `INT(b - a)`, hoisting a repeated measure/function
  call into a `VAR`). Even these carry traps listed in their entries; "provably identical"
  holds only once the trap has been ruled out for the measure at hand.
- **judgment** — the rewrite changes evaluation structure (moving a context transition,
  replacing `FILTER` with `KEEPFILTERS`/column predicates, reducing iterator cardinality)
  and can change results in edge cases that depend on the specific model and data.

The skill must never apply a judgment fix without the user approving that single change.
Mechanical fixes for a rule may be applied as one approved batch covering every occurrence
of that rule in the model. DAX Optimizer's scores are static estimates of relative engine
cost, not a correctness check — every rewrite, mechanical or judgment, must be verified to
produce equal results before/after (see `verification.md`). For rules where the knowledge
base itself says there is no general solution, pattern-matching the example is not enough:
read the actual measure and the model's relationships/keys before proposing anything.
The classification table below is the skill's authority: a one-line diff is still judgment
when its rule is.

## Classification

| Rule (docId) | Title | Class | Why |
|---|---|---|---|
| 100100 | Context transition in iterator | judgment | KB states no general solution; only valid when the transitioned value doesn't actually vary per iterated row |
| 100200 | Duplicated measure | mechanical | Hoisting a repeated same-context measure reference into a `VAR` is provably identical |
| 100300 | Duplicated function | mechanical | Hoisting a repeated same-context, same-argument function call into a `VAR` is provably identical |
| 100400 | Filtered table as iterator | judgment | Moves a row-context `FILTER` into filter-context `CALCULATE` arguments; AND/OR splitting and `KEEPFILTERS` must be exact |
| 100501 | Filtered table as filter argument (single column) | judgment | Replaces `FILTER` with a `KEEPFILTERS` column predicate; interacts with any pre-existing filter on that column |
| 100504 | Filtered table as filter argument (multi-column AND, `ALL`) | judgment | `REMOVEFILTERS` scope must match exactly what the original `ALL()` cleared |
| 100550 | Materialized table filter argument | judgment | KB: no general solution for OR conditions spanning tables; CROSSJOIN vs SUMMARIZE choice depends on cardinality |
| 100600 | Summarize extended columns | judgment | Moves aggregation from SUMMARIZE's row context into an explicit `CALCULATE`; group row-set equivalence must be checked |
| 100800 | Filter modifier function not used as filter argument | judgment | Changes a materialized row test into an intersected `CALCULATE` filter argument; `ALLSELECTED` semantics are context-sensitive |
| 100900 | Blank comparison | judgment | `x = BLANK()` is TRUE for 0 and `""` as well; `ISBLANK(x)` and `x == BLANK()` are not, so the rewrite changes results wherever such values exist |
| 101700 | SUMX iterator cardinality reduction to single column | judgment | Valid only when the row expression is additive and truly depends on just that one column |
| 101900 | SUMX iterator excessive CallbackDataId | judgment | Restructures calculation order/grain via pre-aggregation; wrong grain silently gives wrong values |
| 102000 | Function result invariant to current iterator | mechanical | Hoisting a call that provably doesn't depend on the iterated row into a `VAR` is identical |
| 102500 | FILTER instead of modifying the filter context (basic `ALL`) | judgment | `REMOVEFILTERS` scope (table vs column) must match the original `ALL()` argument exactly |
| 102501 | FILTER instead of modifying the filter context (`ALLNOBLANKROW`/grouped) | judgment | Technical blank row exclusion and grouped sources need different equivalents than a plain column predicate |
| 102502 | FILTER instead of modifying the filter context (`ALLSELECTED`) | judgment | `ALLSELECTED` result depends on the caller's visual/query selection, not just the DAX text |
| 102600 | Context transition in iterator without a unique key | judgment | Correctness rule, not just speed; KB flags this as best-practice/false-positive prone with no general fix |
| 103000 | Replace DATEDIFF with subtraction for day intervals | mechanical | Only equivalent when both date columns carry no time-of-day component |

## 100100 Context transition in iterator — judgment
- KB: https://kb.daxoptimizer.com/d/100100
- What it flags: an iterator (e.g. `SUMX`) whose row expression calls `CALCULATE`, `CALCULATETABLE`, or a measure, forcing a context transition on every row.
- Why it costs: each context transition re-derives the filter context and can trigger its own storage-engine work; repeated across every iterated row, and worse inside a nested outer iterator, this multiplies cost.
- Typical rewrite:
```dax
// Before
RevenueShare =
SUMX ( Sales, Sales[Amount] * CALCULATE ( [TotalRevenue] ) )

// After — only if TotalRevenue does not actually vary per Sales row
RevenueShare =
VAR TotalRev = [TotalRevenue]
RETURN
    SUMX ( Sales, Sales[Amount] * TotalRev )
```
- Equivalence traps:
  - Only valid when the transitioned expression genuinely doesn't depend on the iterated row (no relationship path or column from the row feeds it); otherwise hoisting freezes a value that should vary per row.
  - Row-level security scoped to the iterated table can rely on the per-row transition; hoisting removes that per-row filtering.
  - Reducing cardinality instead (iterating distinct values rather than the full table) changes results if other columns of the row also matter, or if duplicate/blank rows are significant.
  - No general fix exists when the transitioned value truly varies per row — the measure needs an algorithmic rewrite, not a pattern substitution.
- Verify with: a case where two sibling rows would legitimately produce different transitioned values (to catch a wrongly hoisted variable), and a context with row-level security or a slicer active on the iterated table.

## 100200 Duplicated measure — mechanical
- KB: https://kb.daxoptimizer.com/d/100200
- What it flags: the same measure referenced more than once within an identical filter context, e.g. across the branches of an `IF`.
- Why it costs: the formula engine can re-evaluate the measure's full expression tree at each reference instead of once.
- Typical rewrite:
```dax
// Before
SalesRatio = IF ( [TotalSales] > 1000, [TotalSales] * 1.1, [TotalSales] * 0.9 )

// After
SalesRatio =
VAR Sales_ = [TotalSales]
RETURN
    IF ( Sales_ > 1000, Sales_ * 1.1, Sales_ * 0.9 )
```
- Equivalence traps:
  - Only safe when every reference truly shares the same filter context; if one reference sits inside a nested `CALCULATE` that modifies filters, hoisting to an outer variable changes its result.
  - Per the KB, only hoist when the variable is guaranteed to be used at least once on the branch actually taken — unconditionally evaluating it can be slower, not faster, for rarely-hit branches.
  - A measure driven by a calculation group can format or evaluate differently depending on where it's invoked; hoisting bypasses that positional dependency.
- Verify with: the measure evaluated under at least two different filter contexts (e.g. different Product Category selections), checking both branches and BLANK propagation match exactly.

## 100300 Duplicated function — mechanical
- KB: https://kb.daxoptimizer.com/d/100300
- What it flags: a non-measure function called more than once with identical arguments in the same filter context, often inside sibling `CALCULATE` filter arguments.
- Why it costs: the formula engine repeats the same computation instead of reusing one result.
- Typical rewrite:
```dax
// Before
CategoryLabel =
IF (
    SELECTEDVALUE ( Product[Category] ) = "Bikes",
    SELECTEDVALUE ( Product[Category] ) & " (core)",
    SELECTEDVALUE ( Product[Category] )
)

// After
CategoryLabel =
VAR Cat = SELECTEDVALUE ( Product[Category] )
RETURN
    IF ( Cat = "Bikes", Cat & " (core)", Cat )
```
- Equivalence traps:
  - Valid only when both calls share the same filter context at the point of hoisting; if one call sits inside a `CALCULATE` that changes the relevant filter, the two results legitimately differ and must stay separate.
  - Context-dependent functions (`SELECTEDVALUE`, `MAX`, `LASTDATE`, …) are hoisted at the outermost scope common to all uses and before any filter-modifying `CALCULATE`; context-independent functions (`TRUNC`, `INT`) can be hoisted anywhere.
  - A `VAR` holding a table (`LASTDATE`, `VALUES`) is fine as a scalar where DAX converts a one-cell table, but not as a boolean `CALCULATE` filter argument — those may only reference columns, so hoist the *value* (`MAX`) rather than the table function there.
- Verify with: a scenario where two different date filters are active in sequence around the two calls, confirming the hoisted value is computed at the correct shared scope.

## 100400 Filtered table as iterator — judgment
- KB: https://kb.daxoptimizer.com/d/100400
- What it flags: `FILTER(...)` used directly as the table argument of an iterator (`SUMX`, `AVERAGEX`, …) instead of applying the condition through `CALCULATE`'s filter arguments.
- Why it costs: produces a nested-iteration query plan — the predicate is tested row by row inside the outer iterator instead of being resolved once at the filter-context level.
- Typical rewrite:
```dax
// Before
HighValueSales = SUMX ( FILTER ( Sales, Sales[Amount] > 100 ), Sales[Amount] )

// After
HighValueSales = CALCULATE ( SUM ( Sales[Amount] ), KEEPFILTERS ( Sales[Amount] > 100 ) )
```
- Equivalence traps:
  - AND-combined conditions become separate `CALCULATE` filter arguments, each wrapped in its own `KEEPFILTERS`; OR-combined conditions must stay together inside one `KEEPFILTERS` argument.
  - Omitting `KEEPFILTERS` turns the new filter into a context-replacing filter — a slicer already restricting the same column would be overridden instead of intersected.
  - If the original `FILTER`'s table argument wasn't the plain fact table but a differently-grained virtual table, there may be no direct column-predicate translation — fall back to reading the measure.
- Verify with: an external filter already active on the same column used in the predicate, and a case where zero rows qualify (BLANK vs 0 behavior).

## 100501 Filtered table as filter argument (single column) — judgment
- KB: https://kb.daxoptimizer.com/d/100501
- What it flags: `FILTER` wrapping an entire table inside `CALCULATE`/`CALCULATETABLE` when the predicate only touches one column.
- Why it costs: `FILTER` materializes every column of the table per row test instead of using the engine's cheaper single-column filter path.
- Typical rewrite:
```dax
// Before
CheapSales = CALCULATE ( SUM ( Sales[Amount] ), FILTER ( Sales, Sales[UnitPrice] < 50 ) )

// After
CheapSales = CALCULATE ( SUM ( Sales[Amount] ), KEEPFILTERS ( Sales[UnitPrice] < 50 ) )
```
- Equivalence traps:
  - Without `KEEPFILTERS`, the new predicate replaces rather than intersects any existing filter on that column from slicers/visuals.
  - If the table inside `FILTER` was actually a variable holding a previously-filtered version of the table (not the raw table), converting to a plain column predicate silently drops those prior filters.
  - BLANK handling in the comparison operator should match the original exactly — cross-check against the Blank comparison rule if the predicate uses `=`/`<>`.
- Verify with: a context where the column is already sliced to a subset, and a row where the column is BLANK.

## 100504 Filtered table as filter argument (multi-column AND, ALL) — judgment
- KB: https://kb.daxoptimizer.com/d/100504
- What it flags: `FILTER(ALL(Table), colA = x && colB = y)` filtering a whole table with an AND condition over multiple columns.
- Why it costs: materializes and iterates the entire table for a predicate needing only two columns, and clears filters on every column even though only two are tested.
- Typical rewrite:
```dax
// Before
BlackBikes = CALCULATE ( SUM ( Sales[Amount] ),
    FILTER ( ALL ( Product ), Product[Category] = "Bikes" && Product[Color] = "Black" ) )

// After
BlackBikes = CALCULATE ( SUM ( Sales[Amount] ),
    REMOVEFILTERS ( Product ), Product[Category] = "Bikes", Product[Color] = "Black" )
```
- Equivalence traps:
  - `REMOVEFILTERS(Product)` must clear exactly the columns `ALL(Product)` did; if the original used `ALL(Product[Category])` (one column), replace with `REMOVEFILTERS(Product[Category])`, not the whole table.
  - Splitting into separate filter arguments works only because `CALCULATE` ANDs them — never use this split when the original condition was OR-combined.
  - A bidirectional relationship on one of the columns can make the whole-table `REMOVEFILTERS` clear more cross-filtered context than the original `ALL()` did.
- Verify with: an active filter on a Product column not in the predicate (confirm it's cleared identically), and a bidirectional-relationship scenario if one exists.

## 100550 Materialized table filter argument — judgment
- KB: https://kb.daxoptimizer.com/d/100550
- What it flags: a whole physical table (or an unnecessarily wide table expression) passed as a `CALCULATE` filter argument when the condition needs only specific columns.
- Why it costs: the engine must build/hold the full row set (all columns) to evaluate the filter instead of a lean filter built from one or two columns.
- Typical rewrite:
```dax
// Before
FilteredMargin = CALCULATE ( SUM ( Sales[Amount] ), FILTER ( Sales, Sales[Quantity] > 1 ) )

// After
FilteredMargin = CALCULATE ( SUM ( Sales[Amount] ), KEEPFILTERS ( Sales[Quantity] > 1 ) )
```
- Equivalence traps:
  - An OR condition spanning two tables (e.g. `Product[Category] = "Bikes" || Sales[Quantity] > 5`) cannot be split into independent column filters since `CALCULATE` ANDs its arguments — the KB states there is no general solution here; a `CROSSJOIN` or `SUMMARIZE`-built virtual table limited to the referenced columns is needed instead.
  - `CROSSJOIN` fits low-cardinality columns; on high-cardinality columns it recreates the materialization cost the rule is trying to remove — check real cardinality, not just the sample.
  - Choosing `KEEPFILTERS` vs `REMOVEFILTERS` must mirror whether the original table argument was a live (intersecting) reference or an already-filtered (context-replacing) virtual table.
- Verify with: an OR condition spanning two tables under a pre-existing slicer on one of them, and confirmation that the chosen cardinality assumption (for CROSSJOIN vs SUMMARIZE) holds on real data.

## 100600 Summarize extended columns — judgment
- KB: https://kb.daxoptimizer.com/d/100600
- What it flags: `SUMMARIZE` used with extra aggregation/expression arguments ("extended columns") instead of only grouping columns.
- Why it costs: mixing grouping and per-group aggregation in one `SUMMARIZE` call gives the optimizer a worse plan than a clean two-step group-then-aggregate pattern.
- Typical rewrite:
```dax
// Before
SalesByCategory = SUMMARIZE ( Sales, Product[Category], "TotalAmt", SUM ( Sales[Amount] ) )

// After
SalesByCategory =
ADDCOLUMNS ( SUMMARIZE ( Sales, Product[Category] ), "TotalAmt", CALCULATE ( SUM ( Sales[Amount] ) ) )
```
- Equivalence traps:
  - The aggregation must be wrapped in `CALCULATE` in the `ADDCOLUMNS` form — without it, the expression evaluates in the outer context and returns the grand total for every group instead of a per-group value.
  - If the original `SUMMARIZE` used `ALLNOBLANKROW` or otherwise changed which groups appear, confirm `ADDCOLUMNS(SUMMARIZE(...))` with only the grouping columns produces the same row set (no implicit filtering was riding along).
  - When grouping columns span more than one table, confirm the relationship direction still yields the same combinations of groups after the rewrite.
- Verify with: a group value with zero matching Sales rows (does it appear with BLANK/0, or not at all, in both versions?), and totals cross-checked against a plain SUM for the same slice.

## 100800 Filter modifier function not used as filter argument — judgment
- KB: https://kb.daxoptimizer.com/d/100800
- What it flags: a filter-modifier function (`ALLEXCEPT`, `ALLSELECTED`, …) wrapped inside `FILTER()` instead of passed as its own `CALCULATE` argument.
- Why it costs: wrapping the modifier in `FILTER` forces it to materialize into a full table before the row predicate runs, discarding the cheap internal representation the modifier normally produces.
- Typical rewrite:
```dax
// Before
SalesKeepingCategory = CALCULATE ( SUM ( Sales[Amount] ),
    FILTER ( ALLEXCEPT ( Sales, Product[Category] ), Sales[Amount] > 0 ) )

// After
SalesKeepingCategory = CALCULATE ( SUM ( Sales[Amount] ), ALLEXCEPT ( Sales, Product[Category] ), Sales[Amount] > 0 )
```
- Equivalence traps:
  - `CALCULATE` ANDs separate filter arguments, while the original `FILTER` tested rows of the modifier's already-materialized table — equivalent only when the extra predicate doesn't need to see a column the modifier restored.
  - `ALLSELECTED` specifically depends on the caller's (visual/query) selection; moving it out of `FILTER` can change what "selected" resolves to if evaluated at a different point — test inside the real report, not only a query pane.
  - If the original predicate referenced a measure (an implicit context transition per row), it isn't reducible to a plain column filter argument — this pattern only applies to physical-column predicates.
- Verify with: a report visual with a real slicer selection on a column touched by the modifier, and a predicate referencing a column the modifier restores.

## 100900 Blank comparison — judgment
- KB: https://kb.daxoptimizer.com/d/100900
- What it flags: `x = BLANK()` or `x <> BLANK()` used instead of `ISBLANK()`/strict equality.
- Why it costs: the loose `=`/`<>` comparison against BLANK forces the engine to also check 0 (or `""`) alongside true BLANK, adding CPU work — and it silently misclassifies 0/`""` as blank.
- Typical rewrite:
```dax
// Before
IsMissing = IF ( Sales[DiscountPct] = BLANK(), "Missing", "Has value" )

// After
IsMissing = IF ( ISBLANK ( Sales[DiscountPct] ), "Missing", "Has value" )
```
- Equivalence traps:
  - **Not a no-op.** In DAX `0 = BLANK()` and `"" = BLANK()` are TRUE; `ISBLANK(0)` and `0 == BLANK()` are FALSE. Rows holding 0 or `""` flip from "Missing" to "Has value". Decide first what the author meant: "blank *or* zero" → keep `=` and mark the issue ignored; "truly blank" → `ISBLANK`/`==` and expect (and verify) the changed rows.
  - `<> BLANK()` becomes `NOT ISBLANK(...)`; do not write `ISBLANK(...) = FALSE()`, which reintroduces a loose comparison.
  - Downstream logic may already compensate for the old 0/blank conflation — check callers before assuming the fix is fully self-contained.
- Verify with: a row where the column is 0, one where it's an empty string (if text), and one that's genuinely BLANK, comparing old vs new output for all three.

## 101700 SUMX iterator cardinality reduction to single column — judgment
- KB: https://kb.daxoptimizer.com/d/101700
- What it flags: an iterator over a full table whose row expression, after context transition, only actually depends on one column of that table.
- Why it costs: iterating every row instead of the distinct values of the one relevant column multiplies the context-transition cost by however many duplicate values exist.
- Typical rewrite:
```dax
// Before
WeightedDiscount = SUMX ( Sales, Sales[DiscountPct] * CALCULATE ( SUM ( Sales[Amount] ) ) )

// After — only if the calc is additive per distinct DiscountPct value
WeightedDiscount =
SUMX ( DISTINCT ( Sales[DiscountPct] ), Sales[DiscountPct] * CALCULATE ( SUM ( Sales[Amount] ) ) )
```
- Equivalence traps:
  - Valid only when the row expression is additive across the distinct values and doesn't also depend on any other column of the row — a hidden dependency (e.g. on `ProductKey`) is silently dropped by collapsing to one column.
  - `DISTINCT()` still returns a BLANK member if the column can be BLANK; use `VALUES()` instead when the model's blank-row semantics for unmatched relationships must be preserved.
  - Duplicate rows that should each contribute separately (e.g. distinct Amounts sharing the same DiscountPct) are only safe to collapse when the math per equal value is genuinely identical.
- Verify with: a DiscountPct value repeated across rows with different Amounts, and a BLANK DiscountPct case.

## 101900 SUMX iterator excessive CallbackDataId — judgment
- KB: https://kb.daxoptimizer.com/d/101900
- What it flags: `SUMX` over a large fact table where each row triggers a lookup (e.g. a related-table measure) on a column whose real cardinality is far lower than the row count.
- Why it costs: every row generates its own formula-engine callback to resolve the lookup, even though most rows share the same key — a large number of redundant callbacks.
- Typical rewrite:
```dax
// Before
FXAdjustedSales = SUMX ( Sales, Sales[Amount] * CALCULATE ( MAX ( 'Date'[ExchangeRate] ) ) )

// After — iterate the grain the rate really varies at, once per date instead of once per row
FXAdjustedSales =
SUMX (
    SUMMARIZE ( Sales, 'Date'[Date], 'Date'[ExchangeRate] ),
    CALCULATE ( SUM ( Sales[Amount] ) ) * 'Date'[ExchangeRate]
)
```
- Equivalence traps:
  - Only valid when the lookup value is truly constant within the coarser grain (one rate per Date); if it can vary at a finer grain, the rewrite silently uses the wrong value for some rows.
  - Pre-aggregating changes evaluation order — any row-level security or filter that should apply while building the coarser table must still be in effect at that point, not lost by hoisting it into a `VAR`.
  - The `SUMMARIZE` grain must include every column the row expression reads; grouping by Year while multiplying by a per-date rate silently uses one rate for the whole year.
- Verify with: a case where the lookup value changes mid-period, and an RLS/filter scenario applied while the coarser table is built.

## 102000 Function result invariant to current iterator — mechanical
- KB: https://kb.daxoptimizer.com/d/102000
- What it flags: a function call inside an iterator's row expression whose result never actually changes across the rows being iterated.
- Why it costs: the formula engine re-evaluates the same context-independent result once per row instead of once total.
- Typical rewrite:
```dax
// Before
OrdersOnLastDate =
SUMX ( Sales, IF ( Sales[OrderDate] = LASTDATE ( 'Date'[Date] ), 1, 0 ) )

// After
OrdersOnLastDate =
VAR LastD = LASTDATE ( 'Date'[Date] )
RETURN
    SUMX ( Sales, IF ( Sales[OrderDate] = LastD, 1, 0 ) )
```
- Equivalence traps:
  - Confirm the call is truly row-invariant — it must depend only on the outer filter context, not on anything pulled from the iterated row (e.g. via `RELATED`); otherwise hoisting freezes a value that should vary.
  - Per the KB, only hoist when the variable is guaranteed to be used on the branch that actually executes; hoisting a value used only in a rarely-taken `IF` branch can make things slower, not faster.
  - If the "invariant" call is secretly a measure with an implicit context transition, double-check it isn't actually row-dependent before hoisting.
- Verify with: a Sales row set with one `OrderDate` matching `LASTDATE` and others not, and a case where the `IF` branch containing the call isn't taken.

## 102500 FILTER instead of modifying the filter context (basic ALL) — judgment
- KB: https://kb.daxoptimizer.com/d/102500
- What it flags: `FILTER` over `ALL(table)` (or similar) used as a `CALCULATE` filter argument where the predicate only touches physical columns.
- Why it costs: `FILTER` materializes the `ALL(table)` result before testing each row instead of letting `CALCULATE` apply the predicate directly against the cleared context.
- Typical rewrite:
```dax
// Before
PctOfAllSales =
DIVIDE ( [TotalSales], CALCULATE ( [TotalSales], FILTER ( ALL ( Sales ), Sales[Amount] > 0 ) ) )

// After
PctOfAllSales =
DIVIDE ( [TotalSales], CALCULATE ( [TotalSales], REMOVEFILTERS ( Sales ), Sales[Amount] > 0 ) )
```
- Equivalence traps:
  - `REMOVEFILTERS(Sales)` must clear the same scope `ALL(Sales)` did; if the original was `ALL(Sales[Amount])` (one column), use `REMOVEFILTERS(Sales[Amount])` instead of the whole table.
  - The predicate must depend only on physical columns — a predicate that's really a measure needs a context-transition pattern instead, since a plain filter argument can't express an implicit `CALCULATE`.
  - On DirectQuery sources, verify the rewrite still folds to the same generated SQL/row counts, not just check DAX semantics.
- Verify with: an existing slicer on Sales columns other than the one in the predicate, and, for DirectQuery, a row-count comparison of the generated query.

## 102501 FILTER instead of modifying the filter context (ALLNOBLANKROW / grouped) — judgment
- KB: https://kb.daxoptimizer.com/d/102501
- What it flags: the same `FILTER`-materialization anti-pattern as 102500, applied over `ALLNOBLANKROW` or a grouped/summarized source table.
- Why it costs: the same materialization overhead, compounded when the underlying table is itself a `SUMMARIZE` (double materialization).
- Typical rewrite:
```dax
// Before
SalesExcludingBlankRow =
CALCULATE ( SUM ( Sales[Amount] ), FILTER ( ALLNOBLANKROW ( Product[Category] ), TRUE () ) )

// After
SalesExcludingBlankRow =
CALCULATE ( SUM ( Sales[Amount] ), REMOVEFILTERS ( Product[Category] ), NOT ISBLANK ( Product[Category] ) )
```
- Equivalence traps:
  - `ALLNOBLANKROW`'s "no blank row" targets the technical blank row a relationship injects for unmatched keys — confirm that's the same set of rows a plain `ISBLANK()` predicate excludes in this model, rather than assuming they're synonyms.
  - For a grouped/summarized source, the correct equivalent is `CALCULATETABLE(SUMMARIZE(...))`, not a bare column predicate — collapsing straight to `REMOVEFILTERS` + predicate only holds for a genuine single-column `ALL()`/`ALLNOBLANKROW()`.
  - If a report relies on the technical blank row appearing as an "Unknown" bucket, the fix removes it, changing visible totals even though the DAX is more strictly correct.
- Verify with: a Sales key with no matching Product row, and a grouped-source variant compared row-by-row against the original.

## 102502 FILTER instead of modifying the filter context (ALLSELECTED) — judgment
- KB: https://kb.daxoptimizer.com/d/102502
- What it flags: `FILTER` wrapping `ALLSELECTED(table)` as the first argument to an iterator/`CALCULATE` instead of using `ALLSELECTED` as a plain filter modifier.
- Why it costs: the same `FILTER`-materialization overhead, plus `ALLSELECTED`'s meaning depends on the caller's outer selection, which row-by-row `FILTER` evaluation can obscure.
- Typical rewrite:
```dax
// Before
PctOfSelected =
DIVIDE ( [TotalSales], CALCULATE ( [TotalSales], FILTER ( ALLSELECTED ( Product ), TRUE () ) ) )

// After
PctOfSelected =
DIVIDE ( [TotalSales], CALCULATE ( [TotalSales], ALLSELECTED ( Product ) ) )
```
- Equivalence traps:
  - `ALLSELECTED` depends on what the visual or enclosing query had selected — a query run standalone in a scripting tool (no visual selection) can differ from the same measure inside an actual report; always validate in the real report.
  - If the original `FILTER` predicate added a real condition beyond `TRUE()`, it must be kept as a separate `CALCULATE` filter argument — dropping it silently changes which rows count.
  - Calculation groups applied to the measure can change which "outer" selection `ALLSELECTED` resolves against; retest with each relevant calculation item applied.
- Verify with: the measure inside an actual visual with a slicer narrower than the full dataset, and, if calculation groups exist, with each relevant item applied.

## 102600 Context transition in iterator without a unique key — judgment
- KB: https://kb.daxoptimizer.com/d/102600
- What it flags: an iterator triggering a context transition directly over a physical table with no column (or combination) marked as a unique key in the model.
- Why it costs: primarily correctness, not just speed — if the table has duplicate rows for the grain the calculation needs, the transition fires once per physical row instead of once per logical entity, silently multiplying the result.
- Typical rewrite:
```dax
// Before
OrderCount =
SUMX ( Sales, CALCULATE ( DISTINCTCOUNT ( Sales[OrderNumber] ) ) )

// After — only if OrderNumber + OrderLineNumber is the real unique grain
OrderCount =
SUMX (
    SUMMARIZE ( Sales, Sales[OrderNumber], Sales[OrderLineNumber] ),
    CALCULATE ( DISTINCTCOUNT ( Sales[OrderNumber] ) )
)
```
- Equivalence traps:
  - The KB flags this as a "no general solution" area: the right grouping columns depend entirely on what makes a row unique in this specific table — copying the `SUMMARIZE` columns from another model or measure can still leave duplicates or over-group.
  - Confirm duplicates actually exist at the relevant grain (e.g. compare row count vs `DISTINCTCOUNT` of the presumed key) before paying the `SUMMARIZE` materialization cost.
  - Some measures are already immune (pure additive `SUM` with no context transition) — applying this fix there is a pure regression, not an optimization; read the measure rather than pattern-matching the rule name.
- Verify with: a duplicated key combination found or injected in test data (confirm the original overcounts and the rewrite doesn't), and a table with zero duplicates (confirm the rewrite doesn't change the answer, only its cost).

## 103000 Replace DATEDIFF with subtraction for day intervals — mechanical
- KB: https://kb.daxoptimizer.com/d/103000
- What it flags: `DATEDIFF(date1, date2, DAY)` used to compute a day interval.
- Why it costs: `DATEDIFF` triggers formula-engine callbacks that a native column subtraction avoids entirely.
- Typical rewrite:
```dax
// Before
DaysToShip = DATEDIFF ( Sales[OrderDate], Sales[ShipDate], DAY )

// After
DaysToShip = INT ( Sales[ShipDate] - Sales[OrderDate] )
```
- Equivalence traps:
  - Only equivalent when both columns are pure dates with no time-of-day component; a fractional time part makes subtraction return a fractional day count while `DATEDIFF` returns whole calendar days.
  - Datetime columns with mixed midnight/non-midnight values diverge only on some rows, which a small before/after sample can easily miss.
  - Confirm both forms propagate BLANK the same way when either date column can be BLANK (e.g. an unshipped order): arithmetic treats BLANK as 0, i.e. as 1899-12-30, which may or may not be what `DATEDIFF` did on that row.
  - Argument order: `DATEDIFF` with a start later than the end raises an error on current engines, subtraction quietly returns a negative number — a row that used to error (and was perhaps caught by `IFERROR`) now yields a value.
  - Type: `DATEDIFF` returns a whole number, subtraction a decimal number of days. Wrap in `INT()` so the measure's data type and format string do not change.
- Verify with: a row with a non-midnight time component in either column (or confirmation the model guarantees none), a row with a BLANK date, and a row where the dates are in reverse order if such rows can exist.
