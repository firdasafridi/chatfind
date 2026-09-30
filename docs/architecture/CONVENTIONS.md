Classification: INTERNAL

# Doc conventions

These are the rules for everything in `docs/architecture/`. The short version: one topic per file, cite the code, and cut anything that doesn't help.

## Frontmatter

Every spoke starts with these four fields and nothing else:

```yaml
---
topic: search                 # same as the folder name
status: ready                 # ready | stale
related: [ingest, evaluation] # other topic slugs
code:                         # the files this doc describes, plain paths
  - app/backend/engine.py
---
```

If you change a listed file and the doc no longer matches, set `stale`. Whoever re-checks the doc against the code sets it back to `ready`.

## Spoke layout

Use these sections, in this order, and skip any that would be empty: TL;DR, Entry points, Sequence, Schema, Key components, Data, Failure and state, See also. Topic-specific sections are fine, such as "Fusion" in search.

## Writing

- Write plainly, like you're explaining it to a colleague. Use short sentences, and give a reason when a rule isn't obvious.
- Use sentence-case headings, no emojis and no em dashes. Bold only for real warnings.
- Say what the code does now. Leave plans out of these docs.
- Label anything you haven't checked in the code as ASSUMPTION.

## Code references

- In prose, use `path:line` or `path:start-end`. Only cite a line you've opened and checked. If you're unsure, give the path alone.
- In frontmatter, list plain paths only.

## Diagrams and examples

- Use Mermaid in a ` ```mermaid ` block inside the README. Solid arrows are sync calls; dashed arrows (`-.->`) are async or offline.
- Put JSON examples in ` ```json ` blocks. Keys must match the code exactly. Mark made-up values as illustrative.
- Don't create `diagrams/` or `examples/` folders. One topic is one file.

## When to update

Ask three questions when you change code:

1. Did a flow described here change (steps, routes, schema, knobs, gate)? Update that spoke and keep `status: ready`.
2. Did you add or rename something the docs name? Add it to `GLOSSARY.md` first, then extend a spoke or add a new one and link it from the hub.
3. Is it cosmetic (formatting, a local rename, a comment)? Leave the docs alone.

## File naming

Topic folders are kebab-case (`query-understanding/`). Each folder has one `README.md`. Cross-cutting topics go under `flows/cross-cutting/`.
