---
name: pinecone-full-text-search
description: Create, ingest into, and query a Pinecone full-text-search (FTS) document index using the graduated document-schema API (Python SDK 10.0.0, API version 2026-07). Use when the user or agent asks to build a text search index on Pinecone, add dense or sparse vector fields, ingest documents, construct score_by clauses (text / query_string / dense_vector / sparse_vector), or compose with text-match filters ($match_phrase / $match_all / $match_any). Ships `scripts/ingest.py` for safe bulk ingestion (batch_upsert + error inspection + readiness polling); query construction is documented inline in this skill — write `documents.search(...)` calls directly, validated against `pc.indexes.describe(...)` output.
---

# Pinecone Full-Text Search

> **Requires `pinecone` Python SDK ≥ 10.0.0** (`pip install pinecone>=10.0.0`). The document-schema API graduated out of `pinecone.preview` in 10.0.0 — it is now a first-class, SemVer-covered part of the SDK, reachable directly off `pc` (`pc.indexes`, `pc.index(...)`). If you land on this skill from an older habit of importing `pinecone.preview`, stop: that package is deleted outright in 10.0.0 (`ModuleNotFoundError`, no shim). The packaged helper script pins `pinecone==10.0.0` via PEP 723 inline metadata; if you're writing your own code against this skill, pin at least that version. The wire API version is `2026-07`.

> **Authoritative reference (last resort).** If you hit a question this skill and its `references/*.md` files don't answer, the official Pinecone FTS docs are at <https://docs.pinecone.io/guides/search/full-text-search>. Prefer this skill's content for anything covered here — the docs may describe surfaces (e.g. classic vector API, or the older `pinecone.preview` shape) that don't apply to the graduated document-schema path. Consult the link only when you're genuinely stuck.

> **Tell the user up front:** "This skill ships a helper at `scripts/ingest.py` that handles bulk ingestion safely (batched upsert, error inspection, readiness polling). When we get to the ingest step, I'll use it." Surface this at the start of the conversation so the user knows the helper exists. Query construction is hand-written `documents.search(...)` per the **Querying** section below — there is no query helper.

A workflow skill for building a Pinecone full-text-search index with the graduated document-schema API (`pc.indexes`, `pc.index(name)`, API version `2026-07`). Covers schema design (text, dense vector, sparse vector, filterable metadata), ingestion (including async indexing and polling), and query construction (`text` / `query_string` / `dense_vector` / `sparse_vector` scoring; `$match_phrase` / `$match_all` / `$match_any` text-match filters; `$eq` / `$in` / `$gte` / `$exists` / `$and` / `$or` / `$not` metadata filters).

## Scope — this skill is for the document-schema FTS API only

This skill covers `pc.indexes.create(..., schema=...)`, `pc.index(name)`, `idx.documents.upsert(...)` / `idx.documents.batch_upsert(...)` / `idx.documents.search(...)`. If you find yourself reaching for any of the following, **stop** — those are different Pinecone APIs and this skill's guidance and helpers won't apply:

- **Classic vector / records API**: `pc.Index(name)`, `index.upsert(vectors=[...])`, `index.query(vector=..., sparse_vector=...)`, `pc.create_index(dimension=..., metric=..., spec=ServerlessSpec(...))`. This is the *deprecated sugar* path in 10.0.0 — it still runs, but it creates a schemaless index served by the vector data plane, addressing the vector by the reserved `_values` field. It cannot hold `full_text_search` fields.
- **Integrated-embedding / records indexes**: `pc.create_index_for_model(...)` / `pc.indexes.create_for_model(...)` with `embed={...}`. Pinecone vectorizes text server-side, and the resulting `semantic_text` field is served by the **records** API (`upsert_records` / `search_records`), not the documents API. Different upsert/search shapes. A `semantic_text` field cannot be combined with `full_text_search` fields in the same index.

If the user already has a non-document-schema index, they can stand up a separate document-schema index alongside it — the two are independent — but you can't add FTS fields to a classic or integrated-embedding index after the fact, and a document-schema index only ever serves reads and writes through `index.documents.*` — never `index.upsert` / `index.query` / `index.upsert_records` (those calls are refused with "This index has a document schema, so writes must go through the documents API").

## Querying — construct `documents.search(...)` calls

For any task that asks you to query an FTS index, you write a `documents.search(...)` call directly. The schema is authoritative — describe the index live before constructing the call so you know which fields are FTS-enabled, which are filterable, and which are vectors.

**Workflow:**

1. **Discover the schema.** Call `pc.indexes.describe(<index>)` and read the `schema.fields` dict. Each field's class indicates its type (`StringField`, `FloatField`, `DenseVectorField`, etc.); attributes tell you whether it's FTS-enabled (`full_text_search`), filterable, or carries a `dimension`. Skip this step only if you've already seen the schema in this conversation.
2. **Construct the call** matching the rules below — one scoring type per request, hard requirements in `filter`, ranking signals in `score_by`, `include_fields` explicit on every call.
3. **Execute** with `idx = pc.index(name=<index>); resp = idx.documents.search(...)` and read `resp.matches`.

**Canonical shapes:**

```python
# Pure BM25 keyword search
resp = idx.documents.search(
    namespace="__default__",
    top_k=10,
    score_by=[{"type": "text", "field": "body", "query": "machine learning"}],
    filter={"year": {"$gt": 2024}, "category": {"$eq": "ai"}},  # optional
    include_fields=["*"],   # always pass explicitly
)

# Hybrid: dense ranking with a lexical filter (one type in score_by + filter narrows)
resp = idx.documents.search(
    namespace="__default__",
    top_k=10,
    score_by=[{"type": "dense_vector", "field": "embedding", "values": query_embedding}],
    filter={"body": {"$match_all": "TensorFlow"}, "year": {"$gt": 2024}},
    include_fields=["*"],
)
```

**Key rules** (the server enforces these; following them locally keeps the agent loop tight):

- `score_by` is a list of clauses, but **exactly one scoring type per request** (server rejects mixed types). Multi-field BM25 is the one exception: multiple `text` clauses, or one `query_string` with `fields: [...]`. To combine BM25 + dense signals, restrict the dense search with a text-match filter (`$match_all` / `$match_phrase` / `$match_any`); do NOT mix scoring types in `score_by`.
- `filter` keys are field names (must exist in schema, or be an auto-indexed metadata field from upserted documents — see **Filterable metadata isn't declared in the schema** below) OR logical operators (`$and`, `$or`, `$not`). Field values are operator dicts (`{"$gt": 5}`, NOT bare values).
- `include_fields` is required on every call. Pass `["*"]` for all stored fields, `[]` for ids+score only, or a list of names. Omitting it on some SDK/backend builds 400s.

**Clause shapes** (for `score_by`):

| `type` | Required keys | When to pick this |
|---|---|---|
| `text` | `field` (string FTS), `query` | Open-ended keyword search; BM25 ranking on one field |
| `query_string` | `query` (Lucene), `fields` optional | Lucene boost (`^N`), proximity (`~N`), cross-field boolean, phrase prefix |
| `dense_vector` | `field` (dense_vector), `values` (list of floats) | Semantic / mood / topic ranking |
| `sparse_vector` | `field` (sparse_vector), `sparse_values` ({indices, values}) | Custom sparse-encoder ranking |

`text` / `dense_vector` / `sparse_vector` use singular `field`. Only `query_string` accepts a `fields` array (and also accepts singular `field` as an alias). `sparse_vector` uses `sparse_values` (NOT `values`) — distinct from dense.

**Filter operators by field type:**

| Field type | Legal operators |
|---|---|
| `string` with FTS | `$match_phrase`, `$match_all`, `$match_any` |
| filterable metadata (string / auto-indexed) | `$eq`, `$ne`, `$in`, `$nin`, `$exists` |
| `string_list` filterable (auto-indexed, not schema-declared) | `$in`, `$nin`, `$exists` |
| `float` filterable (auto-indexed, not schema-declared) | `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$exists` |
| `boolean` filterable (auto-indexed, not schema-declared) | `$eq`, `$exists` |
| logical wrappers | `$and: [filters]`, `$or: [filters]`, `$not: filter` |

**Match shape on response:**

```python
for m in resp.matches:
    m._id        # document id
    m._score     # match score (NOT `score`)
    m.to_dict()  # full doc payload (when include_fields includes the field)
```

For deeper coverage — multi-field BM25, Lucene patterns, hybrid composition, RRF merges, common error symptoms — see `references/querying.md`. For schema field types and what they enable on the query side, see `references/schema-design.md`.

## Ingesting — use the packaged helper

For **any task that asks you to bulk-ingest a JSONL file into an existing FTS index**, the canonical path is to invoke the bundled helper, NOT to hand-write a Python script. **Do not read the script's source** — everything you need is in this section.

The script does three things bare-LLM ingest code reliably skips, each of which corresponds to a silent production failure:

1. **Bulk-upserts in batches.** No per-doc `upsert` loops.
2. **Inspects every batch result.** `batch_upsert` returns 202 even when individual documents fail; the failures live in `result.errors` / `result.has_errors`. Without inspection, "100 docs ingested" silently becomes "73 docs ingested + 27 lost."
3. **Polls until searchable.** After upsert, Pinecone is still building the inverted index. A `documents.search` call during that window returns empty. Without the poll, the user debugs their *query* code for an hour without finding the indexing race.

You provide a prepared, schema-conformant JSONL file and the index name; the script does the rest. Schema validation is upstream concerns (your prep pipeline, or `prepare_documents.py` when it lands) — `ingest.py` trusts what you hand it.

**Invocation:**

```bash
uv run --script scripts/ingest.py \
  --data processed.jsonl \
  --index <index_name> \
  --sentinel-field <fts_field>
```

**Flags:**

| Flag | Short | Required | Purpose |
|---|---|---|---|
| `--data` | `-d` | yes | Path to JSONL file with prepared documents (one per line) |
| `--index` | `-i` | yes | Pinecone index name (must already exist) |
| `--sentinel-field` | `-f` | yes | An FTS-enabled field on the index, used for the readiness-poll query. Pick the longest free-text field on your schema. |
| `--namespace` | `-n` | no | Default `__default__` |
| `--batch-size` | `-b` | no | Default 50 (matches the SDK's own `batch_upsert` default). **Reduce for large dense vectors.** A 50-doc batch with 3072-dim float vectors lands ~5-10 MB and can be rejected; drop to `--batch-size 25` (or lower) at high dimensions. |
| `--max-concurrency` | — | no | Default 4. Parallel HTTP connections used to upload batches. |
| `--poll-deadline` | — | no | Default 300 (seconds). Time to wait for documents to become searchable before giving up. |
| `--sentinel` | `-s` | no | Token used for the readiness-poll query. Default: first whitespace-separated token of `doc[0][sentinel-field]`. |

**What the script prints:**

```
Loading processed.jsonl ...
Loaded 5000 document(s).
Sentinel: body='The'

Upserting in batches of 50 ...
  batch @     0:   50 docs in  0.31s  (total: 50/5000)
  batch @    50:   50 docs in  0.29s  (total: 100/5000)
  ...

Upsert complete: 5000 doc(s) in 21.4s.

Polling for searchability (deadline 300s) ...
Searchable after 12.3s (3 probe(s)).

Done — total 33.7s.
```

If a batch fails, the script prints every error message and exits non-zero. If the poll deadline expires, the script prints a hint about why (sentinel field isn't FTS-enabled, deadline too tight, docs structurally upserted but rejected by the inverted-index builder) and exits non-zero. **Don't suppress these errors** — they're surfacing real problems with the data or the index.

**When you should NOT use the script:**

- The user is doing per-doc patch updates. Use `documents.update(...)` for partial field updates (see **Updating documents** in `references/ingestion.md`) — the script is for bulk loads, not per-record operations.
- The user is ingesting from a non-JSONL source (CSV, Parquet, Postgres dump). Convert to JSONL first; the script doesn't parse other formats.
- The user explicitly asks you to write the ingestion code from scratch (teaching context). Honor the request and follow the canonical pattern: `documents.batch_upsert` + `result.has_errors` inspection + `documents.search` polling with sentinel and deadline.

The script lives at `scripts/ingest.py` relative to this skill directory. PEP 723 inline-metadata script — `uv run --script` installs `typer` and `pinecone` automatically on first invocation. No setup needed.

## Use cases

Three concrete shapes to model your task on. Match the user's request to the closest one and follow its steps; improvise if the task is genuinely a hybrid.

### UC-1: Index a new corpus end-to-end

**Trigger.** "Index this CSV / JSONL / folder for search," "build a search backend over [my articles / products / tickets / transcripts]," "make my [dataset] searchable."

**For unprocessed / messy data, load the onboarding walkthrough first.** If the user is showing up with raw data (unclear field types, possibly long text fields exceeding FTS limits, comma-separated tag strings, dates as strings, possibly duplicate IDs, etc.) and they haven't given you an explicit schema, **read `references/onboarding-walkthrough.md` and follow it stage-by-stage.** It's a conversational guide — meet the data, surface the processing decisions to the user, propose a schema, confirm before creating, then process+ingest+verify together. The walkthrough exists because schemas are immutable and "onboarding a new corpus" is a high-stakes flow that benefits from explicit user buy-in at each decision point.

If the user already gave you a clean JSONL + a schema spec, follow the abbreviated steps below.

**Steps (when data is already prepared and the schema is decided):**
1. Inspect the corpus shape — text fields, structured metadata, do you also need a vector? Match it to one of the canonical shapes in `references/schema-design.md` (articles, products, tickets, image library, code).
2. Pick analyzer settings on each text field — `language`, `stemming`, `stop_words`. Stemming on for long prose, off for proper nouns / identifiers. **Decide which fields are FTS and which are filterable-only metadata** — see **Filterable metadata isn't declared in the schema** below; filterable-only metadata is a documents-side decision, not a schema field.
3. Assemble the schema with `SchemaBuilder` and **confirm it with the user before calling `indexes.create`** — schemas are immutable in `2026-07`, so a wrong call costs a re-ingest.
4. Create the index. `pc.indexes.create(...)` polls until the index is ready by default — no separate wait loop needed unless you passed `timeout=-1`.
5. **Run `scripts/ingest.py --data <jsonl> --index <name> --sentinel-field <fts_field>`** — see the **Ingesting — use the packaged helper** section above. The script handles `batch_upsert` + per-batch error inspection + post-upsert readiness polling in one invocation. Don't hand-write the loop unless the user explicitly asks you to.
6. (The script polls automatically — by the time it exits cleanly, the index is searchable. If you skip the script and roll your own, you must poll `documents.search` with a sentinel query and a deadline; `batch_upsert` returning ≠ searchable — this is a *document*-indexing wait, separate from and in addition to the index-creation wait in step 4.)
7. Validate with one or two probe queries against fields you know contain the sentinel content.

**Result.** A working `documents.search` call against the user's data, returning ranked matches.

### UC-2: Add a dense (or sparse) signal to a text-only corpus

**Trigger.** "Add semantic search," "add embeddings," "make this hybrid," or any prompt that describes a query pattern text alone can't serve (visual similarity, mood, cross-modal "looks like").

**Steps.**
1. Confirm the new signal represents a **modality or signal text can't express** — image / audio / external score, *or* a different corpus than the existing FTS field. Re-encoding the same text into a dense field is an anti-pattern (`references/schema-design.md` → "When to add a dense field at all").
2. Because schemas are immutable, **plan a new index, not a migration**. Get user confirmation before recreating. A hybrid index must declare its `sparse_vector` field explicitly at creation — there is no way to add one later.
3. Pick an embedding provider and pin its output dimension at schema time. Beware payload-size pitfalls at native dimensions — Gemini-3072 etc. need truncation (`references/ingestion.md` → "Dense-vector payload size").
4. Schema → create (blocks until ready by default) → ingest with embeddings inline or pre-cached.
5. Validate with a **hybrid query**: `dense_vector` score_by + text-match filter (`$match_phrase` / `$match_all`). That's the supported single-call cross-modal shape.

**Result.** One index, two retrieval shapes — pure text *and* dense+filter hybrid — both runnable without further setup.

### UC-3: Build a `documents.search` call from a natural-language user prompt (agent mode)

**Trigger.** Agent receives a user prompt like "find articles about machine learning that mention TensorFlow and were published after 2024" or "documents about climate policy ranked by similarity to this paragraph." The index already exists.

**Steps.**
1. **(Optional) Discover the schema** by calling `pc.indexes.describe(<NAME>)` and reading `schema.fields`. Skip if you already know the field types from earlier in the conversation.
2. **Decompose the user's prompt** into `score_by` / `filter` shapes using the agent-mode decomposition table below. (Hard requirements → `filter`. Ranking signals → `score_by`. Always include `include_fields` explicitly.)
3. **Construct the `documents.search(...)` call** following the rules in the Querying section above — one scoring type per request, operator/field-type matching, `include_fields` always set.
4. **Execute** the call. The response carries `resp.matches`; iterate to get `m._id`, `m._score`, and field values via `m.to_dict()`. Use the matches in whatever shape the user asked for.
5. If results come back empty or wrong, walk the failure tree in `Common gotchas`.

**Result.** Live search results matching the user's intent.

**The four common UC-3 mistakes** to actively avoid:
- Mixing scoring types in `score_by` (server rejects). Put hard requirements in `filter`; rank by one signal in `score_by`.
- Putting hard requirements in `score_by` as BM25 terms instead of in `filter` as `$match_all` / `$match_phrase` (returns ranked results that don't *guarantee* the term is present).
- Operator/field-type mismatches (e.g. `$match_all` on a float field, `$gt` on a string field). Consult the operator table in the Querying section.
- Omitting `include_fields` (some SDK/backend builds 400). Always pass it explicitly.

## Agent-mode query decomposition

Map user prompt cues to API shapes. Read top-down — identify the cue, copy the corresponding shape.

| User prompt cue | API shape |
|---|---|
| Open-ended keywords ("articles about machine learning", search-bar query) | `score_by=[{"type": "text", "field": "<field>", "query": "<terms>"}]` — BM25 token-OR |
| Exact phrase, drives ranking ("rank by 'beautifully written'") | `score_by=[{"type": "query_string", "query": '<field>:("phrase here")'}]` |
| Exact phrase, hard requirement ("must contain 'machine learning'") | `filter={"<field>": {"$match_phrase": "machine learning"}}` |
| Required tokens, any order ("must mention TensorFlow", "must be about Illinois") | `filter={"<field>": {"$match_all": "tokens space-separated"}}` — preferred over `query_string` `+token` because it's a true hard filter, doesn't contribute to score |
| At least one of these tokens ("contains AI or ML or robotics") | `filter={"<field>": {"$match_any": "AI ML robotics"}}` |
| Excluded tokens ("not about deprecated", "no opinion pieces") | `filter={"$not": {"<field>": {"$match_any": "deprecated opinion"}}}` — or `-token` inside `query_string` |
| Boolean / boost / slop / phrase-prefix ("weight 'eagle' 3x", "within N words") | `score_by=[{"type": "query_string", "query": '<expr with ^N / ~N / "…"*>'}]` — only Lucene supports these |
| Cross-field boolean ("title or body contains X") | `score_by=[{"type": "query_string", "query": 'title:(X) OR body:(X)'}]` |
| Numeric / date / range / boolean metadata ("after 2024", "rating > 4", "in stock") | `filter={"<field>": {"$gt": ..., "$gte": ..., "$eq": ..., "$exists": true}}` |
| Category / tag / list membership ("category = fiction", "tagged X") | `filter={"<field>": {"$in": [...]}}` (works on plain filterable metadata and `string_list` filterable fields) |
| Semantic similarity / mood / topic ("articles about ML", "documents that feel sombre") | `score_by=[{"type": "dense_vector", "field": "<embedding_field>", "values": embed(<text>)}]` — requires a `dense_vector` field |
| Visual appearance / cross-modal text query against an image corpus | Same dense_vector shape, with the embedding model that produced the stored image vectors. Multimodal embedders (Gemini-2 etc.) map a text query into the image space. |
| Hybrid: lexical requirement + semantic ranking ("articles about ML that mention TensorFlow") | Lexical → `filter` (`$match_all` / `$match_phrase`); semantic → `score_by` (`dense_vector`). Single call. |

**Two structural rules the agent must enforce, no exceptions:**

- **One scoring type per request.** `score_by` accepts `text` / `query_string` / `dense_vector` / `sparse_vector`, but a request ranks by *one*. Don't mix dense + text in `score_by` — the server rejects it. Multi-field BM25 is the only "list" pattern that's allowed (multiple `text` clauses, or one cross-field `query_string`).
- **Hybrid = filter + score_by, not two `score_by` clauses.** When a prompt has both a lexical requirement and a semantic ranking signal, lexical goes in `filter` (via `$match_*` operators) and semantic goes in `score_by`. If both signals genuinely need to drive *ranking*, run two searches and merge IDs client-side.

## Filterable metadata isn't declared in the schema at all

This is the single biggest shape change from the old `pinecone.preview` API, and it's easy to get only half right.

On a **managed** index (the deployment type every example in this skill uses — `{"deployment_type": "managed", "cloud": ..., "region": ...}`, which is also the default when `deployment=` is omitted), the schema may **only** declare fields that participate in **search**: `dense_vector`, `sparse_vector`, and `string` fields with `full_text_search` enabled. **Every other field type — `string` (filterable, no FTS), `string_list`, `float`, `boolean` — is rejected at create time with a 400 if it appears in the schema.** This is confirmed live, not just documented: the server's own error names all four types explicitly — *"The schema only accepts fields used for search (field types `dense_vector`, `sparse_vector`, and `string` with `full_text_search` configuration). To use field '&lt;name&gt;' for filtering (field types `boolean`, `float`, `string`, or `string_list`), omit it from the schema and include it in documents."* (That restriction is specific to managed/BYOC deployments — schema-declared filterable metadata is only legal on **pod** deployments, which this skill doesn't cover.) The `SchemaBuilder` methods `add_float_field`, `add_boolean_field`, and `add_string_list_field` still exist and still work correctly for a pod deployment; for the managed deployments this skill always uses, don't call any of them.

Instead: **don't declare any filterable-only field in the schema, of any type.** Just include the field in the documents you upsert — Pinecone indexes whatever's present on an upserted document for filtering automatically (exact-match on strings and numbers/booleans, membership on lists), whether or not it appears in the schema, with no configuration needed.

```python
# WRONG on a managed index — the server 400s on EVERY one of these, not just category:
schema = (
    SchemaBuilder()
    .add_string_field("body", full_text_search={"language": "en"})
    .add_string_field("category", filterable=True)      # <-- rejected
    .add_float_field("year", filterable=True)            # <-- also rejected
    .add_string_list_field("tags", filterable=True)      # <-- also rejected
    .build()
)

# RIGHT — the schema declares only search fields. category/year/tags are
# simply included on upserted documents and auto-index for filtering.
schema = (
    SchemaBuilder()
    .add_string_field("body", full_text_search={"language": "en"})
    .build()
)

idx.documents.upsert(namespace=NAMESPACE, documents=[{
    "_id": "doc-1",
    "body": "...",
    "year": 2025.0,          # not in the schema — still filterable via $gt / $gte / $eq
    "tags": ["classic"],     # not in the schema — still filterable via $in / $nin
    "category": "fiction",   # not in the schema — still filterable via $eq / $in / $exists
}])
```

The **forward-looking note** in `references/schema-design.md` from the old preview docs — "declare metadata fields today to be future-proof" — no longer applies; declaring any filterable-only field is now actively wrong, not just unnecessary.

## Workflow at a glance

Three phases. Each has its own reference file — consult it before writing code for that phase.

1. **Design the schema.** Decide which string fields are full-text-searchable (declared in the schema), whether you need a `dense_vector` field (and whether it earns its place), and whether you also need a `sparse_vector` field — those are the *only* things that ever go in the schema. Every filterable metadata field — string, string_list, float, boolean alike — is NOT declared; it's just included on upserted documents. Schemas are **fixed at index creation** in `2026-07` — plan carefully. → `references/schema-design.md`
2. **Ingest documents.** For bulk loads from a prepared JSONL, run the bundled `scripts/ingest.py` helper (it does `batch_upsert` + error inspection + readiness polling correctly by construction — see the **Ingesting — use the packaged helper** section above). For per-doc patch updates, use `documents.update(...)`. Either way, documents are indexed asynchronously after the HTTP call returns; `batch_upsert` returning 202 ≠ searchable. → `references/ingestion.md` for the canonical pattern in detail.
3. **Query the index.** A single search request ranks by **one** scoring type — pass exactly one of `text`, `query_string`, `dense_vector`, or `sparse_vector` in `score_by` (multi-field BM25 is supported via multiple `text` clauses or a cross-field `query_string`). Layer `filter={...}` for text-match (`$match_phrase` / `$match_all` / `$match_any`) and metadata filters (`$eq` / `$in` / `$gte` / `$exists` / `$and` / `$or` / `$not`). Control the response payload with `include_fields`. → `references/querying.md`

## Quick template

End-to-end skeleton for a minimal text + filterable-metadata index. Copy it and edit every spot marked `# TODO:`. The template deliberately omits external embedding calls so it stays generic; see `references/ingestion.md` for dense / sparse field patterns and embedding-provider integration, and `references/querying.md` for the four scoring shapes plus text-match and metadata filters.

```python
import time
from pinecone import Pinecone, SchemaBuilder

INDEX_NAME = "my-fts-index"        # TODO: name your index (lowercase alphanumeric + hyphens, 1-45 chars)
NAMESPACE = "__default__"          # TODO: pick a namespace; auto-created on first upsert

pc = Pinecone()                    # reads PINECONE_API_KEY
# TODO: preprod backends require an x-environment header on the client:
#   pc = Pinecone(additional_headers={"x-environment": "preprod-aws-0"})

# 1. Schema — one FTS string field. That's the only kind of field that goes
#    here: `category` and `year` below are deliberately NOT in the schema —
#    see "Filterable metadata isn't declared in the schema at all" in
#    SKILL.md. Field names must NOT start with `_` (reserved for `_id` /
#    `_score`) or `$` (reserved for filter operators), and are limited to 64
#    bytes.
schema = (
    SchemaBuilder()
    .add_string_field("body", full_text_search={"language": "en"})  # TODO: rename for your content
    .build()
)

# 2. Create the index. Polls until ready by default (pass timeout=-1 to
#    return immediately instead). Deployment defaults to managed/aws/us-east-1
#    when omitted; pass `deployment=` explicitly to pick a different region.
#    read_capacity defaults to {"mode": "OnDemand"}; pass
#    {"mode": "Dedicated", ...} only if you specifically want provisioned reads.
if not pc.indexes.exists(INDEX_NAME):
    pc.indexes.create(
        name=INDEX_NAME,
        schema=schema,
        deployment={"deployment_type": "managed", "cloud": "aws", "region": "us-east-1"},
    )

idx = pc.index(name=INDEX_NAME)

# 3. Upsert a single document. `_id` is required, every other field is optional.
#    `category` and `year` aren't in the schema but are still filterable —
#    see above.
#    upsert REPLACES the document on conflict; use documents.update(...) for
#    per-field patches (references/ingestion.md).
idx.documents.upsert(
    namespace=NAMESPACE,
    documents=[{
        "_id": "doc-1",
        "body": "Full-text search is great for keyword queries.",
        "category": "intro",
        "year": 2025.0,
    }],
)

# 4. Poll until the FTS side is searchable (upsert returns BEFORE docs are indexed).
deadline = time.time() + 300
while time.time() < deadline:
    resp = idx.documents.search(
        namespace=NAMESPACE, top_k=1,
        score_by=[{"type": "text", "field": "body", "query": "search"}],  # TODO: sentinel query likely to hit
        include_fields=[],          # required on every search; [] = lightest payload (ids + _score only)
    )
    if resp.matches:
        break
    time.sleep(5)

# 5. Search — text scoring composed with metadata filter.
resp = idx.documents.search(
    namespace=NAMESPACE,
    top_k=5,
    score_by=[{"type": "text", "field": "body", "query": "keyword queries"}],
    filter={"year": {"$gte": 2024}},        # TODO: adjust filter or drop it
    include_fields=["*"],                    # "*" = all stored fields; [] = `_id` + `_score` only
)
for m in resp.matches:
    print(m._id, m._score, m.to_dict())
```

## Common gotchas

- **No filterable metadata field goes in the schema on managed indexes — string, string_list, float, and boolean alike.** Only `dense_vector`, `sparse_vector`, and FTS-enabled `string` fields are legal in `schema=`; every other field type is rejected with `400`. Confirmed live against the real API, not just documented. Omit it and let it auto-index from upserted documents instead. See **Filterable metadata isn't declared in the schema at all** above — this is the change most likely to break code carried over from the old `pinecone.preview` API, where such fields were declarable.
- **One scoring type per search request.** `score_by` accepts `text`, `query_string`, `dense_vector`, or `sparse_vector` — but a request ranks by *one* type. Multi-field BM25 is fine (pass several `text` clauses, or a single cross-field `query_string`). To combine BM25 ranking with a `dense_vector` (or `sparse_vector`) signal, restrict the dense search with a text-match `filter` operator (`$match_phrase` / `$match_all` / `$match_any`) on the lexical field, *not* by mixing types in `score_by`. The "blend a dense vector and a text clause in `score_by`" pattern is rejected by the server.
- **Text-match filter operators are the cross-modal hinge.** `$match_phrase` (exact phrase), `$match_all` (every token, any order), `$match_any` (at least one token) are filter-side operators on `full_text_search` fields. Each takes a single string (max 128 tokens). They reuse the field's tokenizer / stemmer, compose under `$and` / `$or` / `$not`, and are the supported way to compose lexical pre-filtering with dense or sparse ranking. **Phrase slop (`"…"~N`), term boost (`^N`), and phrase prefix (`"… word"*`) are scoring-only — they live in `query_string`, not in `filter`.**
- **Preprod backends need `additional_headers={"x-environment": "..."}` on the `Pinecone()` client.** Missing the header lands you on prod and you'll see "index not found" / empty-result symptoms that look like code bugs but aren't.
- **`include_fields` is required on every `documents.search(...)` call.** Pass `["*"]` for all stored fields or a list of names to project. Omitting it on some SDK/backend builds yields `400` instead of a sane default; always pass it explicitly to avoid surprises.
- **Match score is `_score`; doc id is `_id`.** The system match score is always on the `_score` field so a user metadata field literally named `score` can coexist. Always read `m._score`, never `m.score`.
- **Reserved field names: leading `_` and `$`, max 64 bytes.** `_` is for system fields (`_id`, `_score`); `$` is for filter operators. Schema validation rejects names that violate either rule. Length cap is bytes, not characters — be careful with non-ASCII names.
- **Vector-field cardinality: at most one `dense_vector` and at most one `sparse_vector` per index** in `2026-07`. Multiple text fields are fine.
- **A hybrid index must declare its `sparse_vector` field at create time — there's no adding one later.** `metric="dotproduct"` on the dense field is NOT a hybrid declaration by itself in `2026-07` (it was in the old preview API). The create call succeeds either way; if the `sparse_vector` field is missing, only the *sparse writes* are refused, later, often from a different part of the codebase. If you're porting an old preview schema, audit every `metric="dotproduct"` dense field for a missing sparse field before recreating it.
- **`batch_upsert` failures are silent by default.** The return value carries `has_errors`, `failed_batch_count`, and a list of `BatchError` objects with `error_message`. If you don't inspect them, you'll see "Uploaded 0 / N" and an indefinite "not yet indexed" poll — with the real cause (payload-too-large, schema mismatch, reserved field name) hidden. Always print `result.errors[*].error_message` before downstream steps.
- **Dense-vector payload size matters at batch time.** A 50-doc batch with 3072-dim float vectors lands around 5–10 MB and can be rejected. If every batch fails, try reducing the embedding dimension via your provider's truncation knob (e.g. Gemini's `output_dimensionality=768`) before debugging schema.
- **Async indexing: `batch_upsert` returning ≠ searchable.** The server builds inverted indexes in the background after the HTTP call returns. If you query immediately you'll see empty result sets. Always poll `documents.search` with a sentinel query and a deadline (pattern in `references/ingestion.md`). This is separate from — and in addition to — `pc.indexes.create()`'s own default polling for the *index* becoming ready.
- **String FTS field shape is `full_text_search={...}` (dict), or `True` for server defaults.** **User-settable sub-fields:** `language`, `stemming`, `stop_words`, `ngram`. **Server-applied** (visible in `describe()` responses but NOT settable at index creation): `lowercase` (default `true`) and `max_term_len`. Stemming is opt-in (default `false`) and required if `stop_words=True` is set. A string field is *either* FTS-enabled *or* filterable, never both on a managed index — passing `filterable=True` alongside `full_text_search` makes the server silently keep the filter and drop the search config.
- **Schemas are fixed at index creation in `2026-07`.** Adding, removing, or retyping fields after creation is not supported. Changing dimension or metric on an existing vector field requires a new index. Plan the schema once.
- **Per-field updates are supported: `documents.update(...)`.** Pass `documents=[{"_id": ..., "set_fields": {...}}]`-style records, or `filter=` + `set_fields=`/`remove_fields=` to patch many documents at once by metadata match. `documents.upsert` still fully replaces a document on conflicting `_id` if that's what you want instead. See `references/ingestion.md` → "Updating documents".
- **Document operations: search, fetch, and delete all support `filter` now.** `documents.fetch` and `documents.delete` both gained a `filter` parameter — pass exactly one of `ids`, `filter`, or (for delete) `delete_all`. A filtered `fetch` is paginated (up to 10,000 docs per page via `pagination_token`); an ID-based fetch is never paginated. `documents.delete` returns a response object with `matched_records` (a point-in-time count for filtered deletes; `None` for ID-list or `delete_all` deletes — the delete itself is applied asynchronously).
- **`documents.list(...)` enumerates document IDs in a namespace, with no equivalent in the old preview API.** Lazily-paginated, sorted by ID, optionally filtered by `prefix`. See `references/querying.md` → "`documents.list` — enumerate document IDs".
- **Namespaces auto-create on first upsert.** Pass any namespace string to `documents.upsert` / `batch_upsert` and the namespace is created on the fly; documents from different namespaces are fully isolated. Use `"__default__"` if you don't need partitioning.
- **Namespace management and `describe_index_stats` now work on document-schema indexes.** `idx.create_namespace(name=...)`, `idx.list_namespaces()`, `idx.describe_namespace(name=...)`, `idx.delete_namespace(name=...)`, and `idx.describe_index_stats()` are all available and confirmed working — see `references/ingestion.md` → "Namespace management" for signatures and examples.
- **Document and request size limits**: per-document max **2 MB**; per-request max **2 MB and 1000 documents**; per FTS-enabled `string` field max **100 KB and 10,000 tokens** (tokens > 256 bytes are truncated by the analyzer); per-document filterable metadata (everything *not* in an FTS field) max **40 KB**. A schema can declare up to **100 FTS string fields**. For long-prose corpora, chunk before ingest — see `references/ingestion.md`.
- **`score_by` clause shape — singular `field` is canonical for `text`/`dense_vector`/`sparse_vector`; only `query_string` takes a `fields` array.**
    - `text`: `{"type":"text", "field":"<fts_field>", "query":"<terms>"}`.
    - `query_string`: `{"type":"query_string", "query":"<lucene>", "fields":["<a>","<b>"]}` (the optional `fields` array; `query_string` also accepts a bare `"fields":"body"` string and the legacy `"field":"body"` as an alias).
    - `dense_vector`: `{"type":"dense_vector", "field":"<dense_field>", "values":[/*floats*/]}`.
    - `sparse_vector`: `{"type":"sparse_vector", "field":"<sparse_field>", "sparse_values":{"indices":[...],"values":[...]}}` — note `sparse_values` (NOT `values`) for sparse clauses.
- **Single-term prefix wildcards aren't supported.** `auto*` doesn't work in `query_string`; use phrase prefix (`"machine lea"*` — phrase must contain at least two terms, last term is matched as prefix).
- **Indexes can't be created in CMEK-enabled projects alongside any `full_text_search` field, no backup/restore** for document-shaped indexes in `2026-07`. If either of these is a hard requirement, the document-schema FTS surface isn't yet ready.
- **Fuzzy (`term~N`) and regex (`field:/pattern/`) search are supported**, but only under `type: "query_string"` — see [Query syntax](https://docs.pinecone.io/guides/search/full-text-search/query-syntax) and `references/querying.md`. Neither works under `type: "text"`.
- **Bulk import from object storage is supported by Pinecone for document-shaped indexes** (see [Import data](https://docs.pinecone.io/guides/index-data/import-data)) — this skill just doesn't implement it. Use `documents.upsert` / `documents.batch_upsert` (via `scripts/ingest.py`, see above) for ingestion here, or a dedicated import skill when one exists.

## Extension points

Currently shipped under `scripts/`:

- `scripts/ingest.py` — bulk-ingest a prepared JSONL into an existing FTS index. Handles `batch_upsert` in safe-sized chunks, inspects every batch's `result.errors` and aborts loudly on failure, then polls `documents.search` with a sentinel + deadline until docs are searchable. Schema-agnostic: takes only `--data`, `--index`, `--sentinel-field`. Usage in **Ingesting — use the packaged helper** section above.

Query construction does NOT have a packaged helper — write `documents.search(...)` calls directly per the **Querying** section above.
