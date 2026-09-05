# Generated page furniture — script it, don't hand-edit it

Some page elements exist identically (or near-identically) on every page of a
report: header bar, page title/subtitle, navigation menu, a currency/unit
switcher, a footer. The pattern that holds up is **generate that furniture with
a script, run it per page, and never hand-edit the generated `visual.json`
files.** This reference describes the pattern in general; the actual generator
is project code, not part of this skill (see "Where the generator lives" below).

## When it's worth it

Rule of thumb: **more than about five pages share the same element.** Below
that, hand-building each page's header is less total work than writing and
maintaining a generator. Above it, the arithmetic flips — every element is
several `visual.json` files (a bar, a title textbox, a nav slicer, a divider
line, a home button, ...), each with the same fiddly PBIR quirks (per-state
`fill`/`outline`/`text` selectors, stateful cards, a shape that needs its
outline turned off in two places at once). Multiply that by a dozen pages and
hand-editing stops being "copy the JSON and change two things" and starts being
"copy the JSON, change two things, and hope you changed them in all twelve
copies the same way."

Typical candidates: header/title band, top or side navigation, footer, a
unit/currency/language switcher — anything that is (a) visually identical or
parametrically identical across pages, and (b) driven at least partly by data
(e.g. a nav menu whose items come from a model table) rather than being purely
static content.

## How the script knows what to touch

The generator has to be able to tell "furniture I own" apart from "everything
else on the page" — both to write the furniture and, on a second run, to remove
furniture elements that no longer apply (a renamed page, a dropped nav item)
without deleting anything else.

The concrete mechanism in production (one project's `_data/gen_header.py`,
a header generator): every furniture visual is placed in the top band by **position**
and stacked at the top of the **z-order** — the sweep identifies "mine" by
`position.y < <header height>` **and** `position.z >= 5000`, and only the
visuals matching both are candidates for deletion on a re-run. Ordinary
content visuals live below the header band and in the normal z-range, so they
never match and are never touched.

The specific numbers (92px, z ≥ 5000) are this project's choice, not a rule —
the point that generalizes is: **pick an unambiguous, cheap-to-check property
that only the generator's own output has**, and gate deletion on it. A reserved
name prefix works too; a reserved position/z-range is one option that happens
to also double as a layout constraint (furniture must stay in its band).

This makes the generator **idempotent by construction**: run it twice with the
same arguments and the second run deletes what the first wrote and writes the
same thing back. That has to be true — the generator has to be safe to run
whenever a page is touched, not just once at page-creation time, or the whole
point (furniture never drifts out of sync) is lost the first time someone
regenerates only some pages.

## Parametrize, don't fork variants

Differences between pages or between projects (page title, active nav item,
which model table backs the menu, a light vs. dark visual style) are **CLI
arguments to one script**, not separate copies of the generator or separate
copies of the JSON:

```
python3 _data/gen_header.py <page-id> --title "Sales" \
    --subtitle "..." --section SALES --active "Revenue Overview" [--style light]
```

A `--style`-type switch that picks between named variants (e.g. a `dark` /
`light` palette dict keyed by the flag) keeps the two looks as data inside one
generator instead of two scripts that will inevitably diverge. Default the flag
to whatever existing pages already use, so re-running the generator over
unrelated pages doesn't change their look as a side effect.

## Why not hand-edit the generated files

Once furniture is generated, editing it by hand is worse than not having a
generator at all: the next regeneration either silently overwrites the hand
edit (if the field it changed is one the generator writes) or leaves it as an
undetected inconsistency (if it isn't). With a dozen pages, "the header is
subtly different on page 7" is not something a reviewer catches in a JSON diff
— nobody is going to spot a 2px offset or a missed color across twelve
`visual.json` files. Change the generator (or its arguments) and re-run it over
every affected page instead; that keeps the source of truth in one place and
makes the actual diff (what changed and on how many pages) visible in the
script edit and its output, not buried in JSON.

## What stays out of the generator

Content visuals — the tables, charts, cards that make up the actual page —
are not furniture and should not be pulled into the generator. The dividing
line is the same test used to decide *whether* to generate something at all:
furniture is the part that's identical or parametrically identical across
pages; content is what makes each page different, and it belongs to whatever
per-page authoring process (or reference layout section) already governs page
content. A generator that starts reaching into content visuals to "save
typing" is a sign the boundary was drawn wrong — split it back into a separate
step.

## Where the generator lives

**The generator is project code, in the project's own repo — not part of this
skill.** This skill is not the place to add a generic "generate page furniture"
script, because the actual output (colors, exact geometry, which model table
drives the nav, what counts as a style variant) is project design-system detail
of the same kind `POWERBI-LAYOUT.md` already owns. If a project has this
pattern, document it in that project's `POWERBI-LAYOUT.md` (a numbered
project-specific section, e.g. "Header and navigation") with the exact
invocation and the geometry/color table, the way that project does — and reference
that section here only in spirit, not by copying its values into this skill.
