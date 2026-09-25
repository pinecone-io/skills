# Schema design

Everything a Pinecone document index needs is declared up-front via `SchemaBuilder`. The schema pins which fields are searchable — full-text or vector — and what their dimensions / metrics are. **Filterable-only metadata is never declared in the schema on a managed index, no matter its type** (see "Filterable metadata — never schema-declared on managed indexes" below). **Schemas are fixed at index creation in `2026-07`** — adding, removing, or retyping fields afterwards is not supported. Plan carefully.

## `SchemaBuilder` overview

```python
from pinecone import SchemaBuilder

schema = (
    SchemaBuilder()
    .add_string_field("title", full_text_search={"language": "en"})
    .add_string_field("body",  full_text_search={"language": "en", "stemming": True})
    .add_dense_vector_field("embedding",       dimension=1024, metric="cosine")
    .add_sparse_vector_field("sparse_embedding")              # no `metric` — sparse scoring isn't configurable
    .build()            # terminal: returns the schema object you pass to indexes.create
)
```

Notice there's no `category`, `year`, or `tags` field here even though the corpus this schema serves might have all three — on a managed index the server rejects **any** schema-declared filterable-only field, string or otherwise, with `400`. See "Filterable metadata — never schema-declared on managed indexes" below.

`.build()` is the terminal call — every chain ends with it. The resulting schema is passed to `pc.indexes.create(name=..., schema=schema, deployment=..., read_capacity=...)`. `deployment` defaults to a managed index on AWS `us-east-1` when omitted; pass `{"deployment_type": "managed", "cloud": ..., "region": ...}` to pick a different region. `read_capacity` defaults to `{"mode": "OnDemand"}` (auto-scaled shared reads); pass `{"mode": "Dedicated", "dedicated": {...}}` only if you specifically want provisioned read nodes. `pc.indexes.create(...)` polls until the index is ready by default — pass `timeout=-1` to return immediately instead, or a positive number of seconds for a bounded wait (raises `PineconeTimeoutError` past the deadline).

## Field types at a glance

| Type            | Purpose                                    | Declared in schema (managed index)? | Required options                          | How it's queried                          |
|-----------------|---------------------------------------------|---------------------|--------------------------------------------|--------------------------------------------|
| `string` (FTS)  | Full-text search (BM25 / Lucene)           | Yes                  | `full_text_search: {...}` (or `True` for defaults) | `score_by` `text` or `query_string`; filter via `$match_phrase` / `$match_all` / `$match_any` |
| `string` (metadata) | Exact-match metadata filtering          | **No**               | — just include the field on upserted documents | `filter` with `$eq` / `$in` / `$ne` / `$nin` / `$exists` |
| `string_list`   | Array-valued metadata filtering            | **No**               | — just include the field on upserted documents | `filter` with `$in` / `$nin` (membership) |
| `float`         | Numeric metadata filtering                 | **No**               | — just include the field on upserted documents | `filter` with `$eq` / `$gt` / `$gte` / `$lt` / `$lte` / `$in` / `$nin` |
| `boolean`       | Boolean metadata filtering                 | **No**               | — just include the field on upserted documents | `filter` with `$eq` / `$exists`           |
| `dense_vector`  | ANN similarity search                      | Yes                  | `dimension`, `metric` (`cosine` / `dotproduct` / `euclidean`) | `score_by` `dense_vector` |
| `sparse_vector` | Sparse-vector lexical / hybrid scoring     | Yes                  | none required (no `metric`, no `dimension`) | `score_by` `sparse_vector`                |

The `add_float_field`, `add_boolean_field`, and `add_string_list_field` `SchemaBuilder` methods still exist and still work for a **pod** deployment (not covered by this skill); on a managed deployment, don't call any of them — declaring the field in the schema is exactly what gets it rejected.

Every schema-declared field can also include an optional `description` string — surfaced by `DescribeIndex` and useful for agentic workflows where an LLM inspects the schema to decide how to query.

## Reserved field names

Field names must be unique, non-empty strings. Two hard rules:

- **Must not start with `_`** — reserved for system-managed fields (`_id`, `_score`).
- **Must not start with `$`** — reserved for filter operators.
- **Limited to 64 bytes** (bytes, not characters — non-ASCII names take extra space).

`_id` is required on every document. `_score` is the system match-score field name returned by `documents.search`. A user metadata field literally named `score` is allowed and won't collide with `_score`.

## Filterable metadata — never schema-declared on managed indexes

This is the single biggest behavioral change from the earlier `pinecone.preview` API, where filterable-only fields of any type were a normal schema declaration.

On a **managed or BYOC index** (the deployment type this skill always uses), the schema may declare **only** search-participating fields: FTS `string` fields, `dense_vector`, and `sparse_vector`. Every filterable-metadata shape — a plain `string` with no `full_text_search`, `string_list`, `float`, `boolean` — is rejected at create time with `400` if it's declared in the schema, confirmed against the live API:

> *"The schema only accepts fields used for search (field types `dense_vector`, `sparse_vector`, and `string` with `full_text_search` configuration). To use field '&lt;name&gt;' for filtering (field types `boolean`, `float`, `string`, or `string_list`), omit it from the schema and include it in documents. It will be indexed automatically."*

(All four of those schema-declared filterable shapes — including `add_float_field`/`add_boolean_field`/`add_string_list_field` — are legal only on **pod** deployments, which this skill doesn't cover.)

There's nothing to configure for the managed case: any field present on an upserted document — of any type, whether or not it's in the schema — is automatically indexed for filtering.

```python
# WRONG on a managed index — the server 400s on ALL THREE of these:
.add_string_field("category", filterable=True)
.add_float_field("year", filterable=True)
.add_string_list_field("tags", filterable=True)

# RIGHT — omit them from the schema entirely, and just include them on upserted docs:
idx.documents.upsert(namespace=NS, documents=[{
    "_id": "doc-1", "category": "fiction", "year": 2024.0, "tags": ["classic"], ...
}])
```

Confirmed live, end to end: `{"year": {"$gte": 2020}}`, `{"featured": {"$eq": True}}`, and `{"tags": {"$in": ["classic"]}}` all filter correctly against documents that never had those fields declared in any schema.

### Full-text-searchable string

```python
.add_string_field("body", full_text_search={"language": "en", "stemming": True})
```

`full_text_search` takes `True` (server defaults) or a dict; populate the dict with any of:

- `language` (string, default `"en"`) — selects the analyzer (tokenizer + stemmer + stopword set). Supported short codes: `ar`, `da`, `de`, `el`, `en`, `es`, `fi`, `fr`, `hu`, `it`, `nl`, `no`, `pt`, `ro`, `ru`, `sv`, `ta`, `tr`. Full names are also accepted (e.g. `"english"`, `"french"`, `"arabic"`). Stop-word lists are available for most languages but a few are tokenize/stem only (no stop_word filtering even when `stop_words: true` is set) — `ar`, `da`, `de` are notable cases; `en`, `es`, `fr` etc. have full stop-word support.
- `stemming` (boolean, default `false`) — if `true`, applies the language's stemmer so `running` matches `runs`. Required when `stop_words=True` is also set.
- `stop_words` (boolean, default `false`) — if `true`, the analyzer's stopword set is filtered out at index and query time. Requires `stemming=True`.
- `ngram` (dict, e.g. `{"min_gram": 2, "max_gram": 4}`) — character n-gram tokenization, for substring/autocomplete-style matching. Cannot be combined with `stemming` or `stop_words`.
- `lowercase` (boolean, default `true`, server-applied) — case-insensitive matching, not configurable via the SDK.
- `max_term_len` (server-applied) — discards excessively long tokens, not configurable via the SDK.

`SchemaBuilder.add_string_field` also accepts `language`, `stemming`, and `stop_words` as direct keyword arguments instead of nesting them in a `full_text_search=` dict — e.g. `add_string_field("title", full_text_search=True, language="en", stemming=True)`. When both forms are given for the same key, the keyword argument wins.

Heuristic on stemming: turn it on for long prose fields where morphological variants of a root should match (`running` ~ `runs` ~ `ran`); leave off for short / identifier fields like titles, tags, or proper nouns where stemming would over-match (a book titled `Running` probably shouldn't also match the query `ran`). Typical pattern: stemming on for `body`, off for `title` / proper-noun fields.

Enables, on `field_name`:
- BM25 token scoring with `score_by=[{"type": "text", "field": "field_name", "query": "..."}]`.
- Lucene scoring with `score_by=[{"type": "query_string", "query": "field_name:(a AND (b OR c)) NOT field_name:d"}]`.
- Phrase / token filters: `filter={"field_name": {"$match_phrase": "..."}}`, `{"$match_all": "..."}`, `{"$match_any": "..."}`.

## Filter operators by metadata type

None of these types are schema-declared on a managed index (see above) — they're just whatever value type you put on the field when you upsert:

- **Plain string** (e.g. `category`): `$eq`, `$ne`, `$in`, `$nin`, `$exists`.
- **Numeric** (e.g. `year`): there is no separate integer wire type and no `add_integer_field` helper even on a pod deployment — always upsert as a Python `float` (`2024.0`, not `2024`). Supports `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$exists`.
- **Boolean** (e.g. `featured: True`): `$eq`, `$exists`.
- **List of strings** (e.g. `tags: ["classic", "american"]`): `$in`, `$nin`, `$exists` — membership semantics, handy for tag-style metadata.

All filter operators compose under `$and`, `$or`, `$not`. Multiple keys at the top level of `filter` are combined with implicit AND.

> **Metadata size limit.** Filterable metadata on a single document is capped at **40 KB** combined (everything that's not in an FTS-enabled `string` field). FTS-enabled `string` fields don't count toward this — they have their own per-field limit (100 KB / 10,000 tokens, see `references/ingestion.md`).

## Dense vector fields

```python
.add_dense_vector_field("embedding", dimension=1024, metric="cosine")
```

- `dimension` and `metric` are both **required** on `add_dense_vector_field` (no longer `None`-defaulted).
- `dimension` must match whatever embedding model you'll store. If the model is chosen at runtime, query its default dimension first (e.g. `pc.inference.get_model(model="multilingual-e5-large").default_dimension`) and pass that in.
- `metric` is one of `"cosine"`, `"dotproduct"`, `"euclidean"`. Pick the metric the embedding provider recommends — most text embedders use cosine.
- Scored at query time with `score_by=[{"type": "dense_vector", "field": "embedding", "values": [...]}]`.

**At most one `dense_vector` field per index** in `2026-07`. If you need two semantically distinct dense signals, you need two indexes.

## Sparse vector fields

```python
.add_sparse_vector_field("sparse_embedding")
```

- No `dimension`, no `metric` — sparse vectors are variable-length and sparse scoring isn't configurable. Passing either raises `PineconeValueError` at schema-build time (the earlier preview API accepted and silently discarded `metric="dotproduct"` here; `2026-07` refuses it instead).
- Stored and queried as `{"indices": [...], "values": [...]}`; query side: `score_by=[{"type": "sparse_vector", "field": "sparse_embedding", "sparse_values": {"indices": [...], "values": [...]}}]`.
- **A hybrid index must declare its `sparse_vector` field at create time.** In the old preview API, `metric="dotproduct"` on the dense field alone was enough to accept sparse writes. That's no longer true: the create call succeeds either way, but without a declared `sparse_vector` field, sparse *writes* are refused later — often surfacing far from the original create call. There's no way to add the field afterward; an index created without one has to be recreated.

**At most one `sparse_vector` field per index** in `2026-07`.

## When to add a dense field at all

This is the key design question when the index already has FTS fields. **Only add a dense vector field when it represents a modality or signal that FTS cannot express.** Examples of justified dense fields:

- An **image embedding** over pictures associated with each document — visual appearance is not text.
- An **audio embedding** over voice clips or music — timbre and melody are not text.
- An **external ranking-model score** pre-computed and stored as a 1-D "vector" for sort purposes.
- A **semantic text embedding over a different corpus** than the one in the FTS field — e.g. the FTS field holds the product description, the dense field holds an embedding of the seller's support-ticket history for that product. Different data, different signal.

Anti-pattern: **re-encoding text that already lives in an FTS field on the same index.** Indexing the `body` string as FTS *and* embedding that same `body` into a dense text vector on the same index is redundant modeling, not an additive signal. FTS already gives you lexical retrieval; adding a dense re-encoding only pays off when the lexical signal is demonstrably insufficient (typically: very large corpus, very semantic queries, and you've measured the gap).

## Multi-field text design heuristics

When a document has a natural hierarchy (title → intro → body, or summary → transcript, or headline → lede → article), splitting across FTS fields enables two things you can't get from one blob:

1. **Per-field scoring.** A match on `title` is almost always a stronger signal than a match on `body`. With separate fields you can search just the title, just the body, or blend them at query time by listing each as its own `score_by` entry (see `references/querying.md` — multi-field BM25).
2. **Multi-field blended relevance.** Passing `score_by=[{text, title, q}, {text, intro, q}, {text, body, q}]` rewards documents that match in multiple fields. (`2026-07` weights every contributing field equally — no per-clause weight parameter.)

Keep it a single field when:

- The content has no natural subdivision (a tweet, a log line, a chat message).
- You will never want per-field weighting at query time.
- Your documents are short enough that inter-field distinctions are noise.

## Schemas are fixed at creation

`2026-07` does **not** support schema migration. You cannot:

- Add a new field after creation.
- Remove an existing field.
- Change a field's type or sub-config (e.g. flip a filterable string to FTS, toggle stemming, change dense vector dimension).
- Add a `sparse_vector` field to an index that didn't declare one at creation.

The supported workaround is to create a new index with the desired schema and reindex documents. Indexes from earlier API versions (including pre-graduation `pinecone.preview` indexes) cannot be backfilled with a `2026-07` schema — treat porting an old preview index as "design a new schema, create a new index, reingest," not an in-place upgrade.

## `description` for agentic / LLM-driven workflows

Each schema-declared field accepts an optional `description` string:

```python
.add_string_field(
    "body",
    full_text_search={"language": "en", "stemming": True},
    description="Full article text. Use for keyword searches, narrative phrases, and topical queries.",
)
```

Returned by `DescribeIndex`. Useful when an LLM is choosing how to query: it can read the descriptions and pick the right field + operator without hard-coded prompt engineering.
