# Target manifests

One YAML per publish target. `tools/build.py` reads `skills/` plus a manifest and
renders `dist/<target>/`. The build is a pure function: same inputs, same bytes.

This replaced the old arrangement, where each target repo ran its own agent
(`contextualize-skills.yml`) to rewrite skills on arrival. Three targets meant
three agents and three different answers to the same question. Those workflows are
gone as of 2026-08-12; nothing rewrites skills after they leave this repo.

## Fields

| Field | Meaning |
|---|---|
| `repo` | `owner/name` of the publish target. Used by the sync workflow. |
| `skills_path` | Directory inside the target repo that receives the skills tree. |
| `dir_name` | Template for the on-disk directory name. `{slug}` is the base name minus the `pinecone-` prefix. |
| `skill_name` | Template for the `name:` frontmatter value. |
| `cross_reference` | Template for how prose refers to *another* skill. See the rule below. |
| `source_tag` | Replaces `pinecone_skills` in the `source_tag=` argument inside `.py` files. |
| `ide_source` | Replaces `pinecone-skills` in the `agentic-ide-source` metadata value inside `.py` files. |
| `snippets` | Wording for the `<<name>>` markers in base. See "Snippets" below. |
| `include` | Slugs to render. Explicit, so adding a skill to base does not silently publish it everywhere. |
| `frontmatter` | Per-slug keys this target adds. Emitted after `argument-hint`. |

## Frontmatter contract

Base uses exactly four keys, and the build must emit them in this order:

```
name:            # rewritten per skill_name
description:     # passed through unchanged
argument-hint:   # passed through unchanged; only cli and query have one
allowed-tools:   # added from the manifest; base has none
```

`description` is byte-identical across base and both live targets for 8 of 9
skills. The exception is `query`, where the cursor copy has diverged — see
"Known deltas".

## The cross-reference rule

**Do not blanket-substitute `pinecone-` → `pinecone:`.** That string also appears
in prose, package names, URLs, and index names, and a global replace corrupts
content silently.

A cross-reference is only rewritten when the matched text is one of the nine
`include` slugs prefixed by `pinecone-`, and the match is bounded by a non-word
character on both sides. Concretely:

| Text | Rewrite? | Why |
|---|---|---|
| `` `pinecone-assistant` `` | yes | `assistant` is a slug |
| `the pinecone-cli skill` | yes | `cli` is a slug |
| `pinecone-plugin-assistant` | **no** | `plugin-assistant` is not a slug |
| `https://…/pinecone-io/skills` | **no** | `io` is not a slug |
| `index name pinecone-demo` | **no** | `demo` is not a slug |

The slug list is the guard. Anything not in `include` is left alone. The build
should fail loudly if a rewrite count changes unexpectedly between runs rather
than silently corrupting a file.

## Paths are not cross-references

A slug followed by `/` is a directory in a filesystem path, so it follows
`dir_name`, not `cross_reference`. The two rules are mutually exclusive: the
cross-reference pattern rejects an adjacent `/` on either side.

| Text | claude-code | cursor |
|---|---|---|
| `uv run ../pinecone-assistant/scripts/create.py` | `../assistant/scripts/…` | unchanged |
| `` `pinecone-assistant` `` (prose) | `pinecone:assistant` | unchanged |

This distinction is not theoretical. `pinecone-quickstart/SKILL.md` carries three
such paths, and running them through `cross_reference` emitted
`../pinecone:assistant/scripts/create.py` — a path that cannot exist on any
filesystem. It was caught by `tools/reconcile.py`, not by unit tests.

## Snippets

Some things really do differ per plugin, and base cannot state both. Cursor reads
`.env` through its own MCP config; Claude Code reads your shell. Claude Code has
working slash commands; Cursor declares none. Before this, an agent ran inside each
plugin repo and worked the difference out, giving a slightly different answer every
run. A snippet states it once.

Base leaves a marker:

```markdown
- **API key** — create one in the console, then make it available:
  <<api_key_setup>>
```

Each manifest fills it:

```yaml
snippets:
  api_key_setup: |
    - Add `PINECONE_API_KEY=your-key` to a `.env` file at your workspace root. The
      bundled MCP config reads it through Cursor's `envFile` field.
```

### Rules

- Marker syntax is `<<lower_snake_name>>`. **Not** `{{ name }}` — `pinecone-n8n`
  is full of real n8n expressions like `={{ $json.urls }}`, and a marker shaped
  like one would confuse the build and the next person to edit that file.
- Every marker in base must be defined by **every** target, or the build fails.
  A skill published with `<<api_key_setup>>` visible in the text is worse than
  either wording.
- Every defined snippet must be used by some included skill, or the build fails.
  This is the half that is easy to forget: stale wording sitting in a manifest
  looks authoritative.
- Snippets fill **first**, before path and cross-reference rewriting. So snippet
  text passes through the same guards as base content — write `pinecone-cli` in a
  snippet and it retargets correctly.
- Trailing newlines are stripped, so `|` block scalars sit cleanly inline.

### Writing snippets that land inside Python

Markers in `.py` files sit inside string literals. A snippet that ends with a `"`
directly before a closing `"""` produces a file that cannot be imported.

`check_python_syntax` catches this — every rendered `.py` must parse. Do not rely
on review for it. The current script snippets avoid decorative quotes for this
reason, which is a small, deliberate cosmetic difference from what the Claude
plugin shipped by hand.

### When to add one

Only where the plugins truly differ. Five of nine skills need no snippet at all,
and a blank in the middle of a sentence is cheaper than forking a file. If the same
wording is right everywhere, put it in base.

## Reconciling against the live repos

```bash
uv run tools/build.py --all
uv run tools/reconcile.py --target cursor --clone ../plugin-cursor --diff
```

`reconcile.py` buckets the difference three ways — `MISSING` (sync adds),
`EXTRA` (`rsync --delete` removes), `DIFFERS` (sync overwrites) — and exits
nonzero while any remain. Before the first sync it is a migration report; after,
a standing assertion that published content still matches what base renders.

`EXTRA` and `DIFFERS` both need reading rather than trusting. A target can be
legitimately *ahead* of base: `create.py` in the Claude plugin was, for months.

## Verification the build owes us

1. **Cursor is byte-identical to base except `source_tag`.** Cursor's manifest is
   an identity transform on names and adds no frontmatter, so this is a cheap,
   exact regression test. It replaces paid evals for that target.
2. **Idempotence.** Building twice produces identical bytes.
3. **Round-trip on names.** Every rendered `name:` matches the target's live
   value for all nine skills.

## Known deltas

Recorded here so the build is not blamed for pre-existing drift. Resolving these
is reconciliation work, not build work.

- **claude is missing three files.** `assistant/references/{context,list,sync}.md`
  exist in base and have never reached the plugin — the old sync diffed
  `HEAD~1..HEAD` under `fetch-depth: 2` and dropped them. A full build fixes this
  by construction.
- **cursor's `query` skill is ahead of base.** 22 diff lines: it uses
  `pinecone-cli` where base says "CLI skill", `/pinecone-query` where base says
  `/query`, and — importantly — its `PINECONE_API_KEY` guidance explains Cursor's
  `envFile` field, which base does not know about. That last one is a genuine
  improvement and should be back-ported to base before any full sync overwrites
  it. Same shape as the `create.py` case.
- **cursor carries `.gitkeep` files** in eight skills. Base has none, so
  `rsync --delete` will remove them. They are vestigial — every directory holding
  one also holds real files — but it is a deletion, so it should be a deliberate
  call rather than a surprise in the first sync PR.
