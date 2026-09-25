# Ingestion

Writing documents into a Pinecone document index uses two methods. Pick based on volume, then handle the *async indexing* gotcha on the other side.

## `documents.upsert` — small writes / patches

```python
idx = pc.index(name=INDEX_NAME)

upsert_resp = idx.documents.upsert(
    namespace=NAMESPACE,
    documents=[
        {
            "_id": "doc-1",
            "title": "A landmark work that every reader should experience.",
            "body": "Lorem ipsum...",
            "category": "fiction",   # not declared in schema — auto-indexed for filtering anyway
            "year": 2024.0,
        },
        # ... up to ~1000 documents per call
    ],
)
print(upsert_resp.upserted_count)
```

Use `upsert` when:

- You're writing a single document (e.g. a sentinel doc to verify end-to-end before a bulk load).
- You're streaming writes from user actions and each request fits in a single batch.
- You want to fully replace a document by `_id` (upsert always replaces the whole document on conflict — for a true per-field patch, use `documents.update` below instead).

Each document is a dict keyed by field name (or a `DocumentRecord`/`UpdateDocumentRecord` instance — both accept a plain dict positionally or fields as keyword arguments). `_id` is required and must be a non-empty unique string within the namespace. Values must match the declared schema types for the few fields actually declared in the schema (FTS strings → `str`, dense vectors → `list[float]`, sparse → `{"indices": [...], "values": [...]}`); every other field on the document — strings, numbers, booleans, string lists — is auto-indexed metadata with nothing declared for it. Field names that start with `_` or `$` are rejected; field names are limited to 64 bytes.

The endpoint returns `202 Accepted` (async) and the body's `upserted_count` is the number of items accepted, not the number that have finished indexing.

## `documents.batch_upsert` — bulk loads

```python
result = idx.documents.batch_upsert(
    namespace=NAMESPACE,
    documents=documents,        # list of dicts, any length
    batch_size=50,               # SDK default
    max_concurrency=4,           # SDK default
    show_progress=True,
)
print(f"{result.successful_item_count:,} / {result.total_item_count:,} succeeded")
if result.has_errors:
    print(f"Failed batches: {result.failed_batch_count}")
    # Always surface the actual reason — silent failures mask payload-size
    # caps, schema mismatches, and reserved-field-name violations.
    for err in result.errors[:3]:
        sample = err.items[0].get("_id") if err.items else "?"
        print(f"  batch #{err.batch_index} ({len(err.items)} items, "
              f"first _id={sample!r}): {err.error_message}")
```

The SDK splits `documents` into `batch_size`-sized chunks and uploads them over `max_concurrency` parallel HTTP connections. `show_progress=True` prints a tqdm-style bar. `max_concurrency` must be a plain `int` (default `4`) — it no longer accepts `None`.

### Tuning `batch_size` and `max_concurrency`

- **`batch_size=50`** (the SDK's own default) is the sweet spot — comfortably below the per-request cap and small enough that transient failures cost less to redo.
- **`max_concurrency=4`** (the SDK's own default) is a safe default for large (thousands-of-docs) loads where you're not simultaneously embedding. Ramp cautiously above 4 — you'll hit Pinecone or upstream embedding-provider rate limits first.
- If you're embedding on the fly (computing vectors inside the upsert loop), keep `max_concurrency` low so embedding latency dominates rather than index write latency.

### Document and request size caps

**Hard limits in `2026-07`:**

- **Per document**: max **2 MB** (serialized JSON, all stored fields combined).
- **Per `full_text_search` string field**: max **100 KB** AND max **10,000 tokens**. Tokens longer than 256 bytes are silently truncated by the analyzer.
- **Per upsert request**: max **2 MB total** AND max **1,000 documents**.
- **Per document filterable metadata** (everything *not* in an FTS field): max **40 KB** combined.
- **Schema-level**: up to **100 FTS string fields** per index.

If any one of these is exceeded, the batch fails as a whole. The most common limit to hit on long-prose corpora is the per-FTS-field 100 KB / 10,000-token cap on a single body field — chunking is the standard fix (see below).

### Dense-vector payload size

A high-dimensional dense field can silently turn a 50-doc batch into a 5–10 MB request, which the backend will reject wholesale. If every batch fails and the error message is opaque, the first thing to try is dropping the embedding dimension before debugging schema:

- **Gemini**: pass `config=types.EmbedContentConfig(output_dimensionality=768)`. The model uses Matryoshka representations, so smaller dimensions are valid truncations of the native output. 768 is usually a 4× payload reduction vs. the native 3072 and costs very little quality.
- **OpenAI `text-embedding-3-*`**: pass `dimensions=768` (or similar) to `embeddings.create`.
- **Pinecone hosted / fixed-dim models**: dimension is fixed; the only levers are `batch_size` (halve it to 25) and per-document body size.

## The async-indexing footgun

After `batch_upsert` returns, **your documents are written but not yet searchable.** The server builds inverted indexes for FTS fields and ANN graphs for vector fields in the background. A search query issued immediately will return empty matches. Schemas with multiple indexed fields (e.g. text + dense + sparse) may take slightly longer.

This is distinct from — and in addition to — `pc.indexes.create(...)`'s own polling for the *index itself* to become ready (which it does by default before returning). Even a fully-ready index needs this separate poll after each ingest.

**Always poll with a deadline** before trusting the index:

```python
import time

deadline = time.time() + 300  # up to 5 minutes
while time.time() < deadline:
    resp = idx.documents.search(
        namespace=NAMESPACE, top_k=1,
        score_by=[{"type": "text", "field": "<any_fts_field>", "query": "<sentinel>"}],
        include_fields=[],   # required on every search; [] = ids + _score only
    )
    if resp.matches:
        print("Data is searchable.")
        break
    time.sleep(5)
    print("Not yet indexed, retrying...")
else:
    print("WARNING: Documents may not be fully indexed after 5 minutes.")
```

Pick a sentinel query likely to hit at least one document. For a typical corpus, a single common token works (e.g. `"book"` for a book-reviews corpus). For a small corpus, use a term you *know* appears in at least one document.

## Chunking oversized text

Per the size caps above, the per-FTS-field hard limits are 100 KB and 10,000 tokens. In practice, plan for the *token* limit kicking in first on natural prose (~5,000 English words at ~2 tokens each is the rough ceiling). Probe before ingesting at scale — chunk anything that approaches either bound, with safety margin.

**Strategy: probe first, then chunk if needed.**

1. Find the longest document in your corpus: `max(len(doc["body"]) for doc in docs)`.
2. Try upserting it as-is. If the upsert errors, chunk.

**Chunking pattern:**

```python
def chunk_text(text, max_chars=32_000):
    # Simple paragraph-aware chunking. Adjust the boundary for your corpus.
    paras = text.split("\n\n")
    chunks, cur = [], []
    cur_len = 0
    for p in paras:
        if cur_len + len(p) > max_chars and cur:
            chunks.append("\n\n".join(cur))
            cur, cur_len = [p], len(p)
        else:
            cur.append(p)
            cur_len += len(p)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks

docs = []
for doc_id, text, title in source:
    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks):
        chunk_id = doc_id if i == 0 else f"{doc_id}#p{i + 1}"
        docs.append({
            "_id": chunk_id,
            "parent_doc_id": doc_id,    # duplicate identifying metadata across chunks
            "title": title,             # so title matches hit every chunk
            "body": chunk,
        })
```

Conventions:

- **Shared key prefix.** First chunk keeps the original `_id`; subsequent chunks append `#p2`, `#p3`. Easy to parse client-side.
- **Duplicate identifying metadata.** Fields like `title`, `parent_doc_id`, `url`, or whatever identifies the logical document should be present on every chunk so queries that filter or score against those fields work uniformly.
- **Deduplicate at query time.** After `documents.search`, group matches by `parent_doc_id` (or strip the `#p*` suffix from `_id`) and keep the highest-scoring chunk per parent. This preserves relevance ranking while collapsing duplicates in the UI.

## Updating documents

`2026-07` has real per-field updates via `documents.update(...)` — this replaces the fetch → modify → re-upsert workaround from the old preview API. Two shapes:

**By `_id`, patching specific fields:**

```python
idx.documents.update(
    namespace=NAMESPACE,
    documents=[{"_id": "doc-42", "set_fields": {"category": "biography"}}],
)
```

**By filter, patching every matching document at once:**

```python
resp = idx.documents.update(
    namespace=NAMESPACE,
    filter={"category": {"$eq": "fiction"}},
    set_fields={"featured": True},
    # remove_fields=["stale_field"],   # drop a field entirely, by name
)
print(resp.matched_records)   # point-in-time count, same semantics as documents.delete
```

`documents.update` accepts `documents=` (a list of per-record patches) *or* `filter=` + `set_fields=`/`remove_fields=` (a bulk patch by metadata match) — not both. `set_fields` merges into the existing document; fields you don't mention are left untouched. `remove_fields` deletes named fields outright. For a filtered update, `matched_records` on the response is a point-in-time count when the server accepted the request, the same caveat as `documents.delete`'s `matched_records` — the update itself applies asynchronously.

If you need to fully replace a document (including its vector fields) rather than patch it, `documents.upsert` with the complete document under the same `_id` is still the right tool — `upsert` replaces, `update` patches.

## Deletes

`documents.delete` accepts exactly one of `ids: [...]` (1–1000 items), `filter: {...}`, or `delete_all: true`:

```python
# Delete-by-filter — no need to search for IDs first anymore.
resp = idx.documents.delete(namespace=NAMESPACE, filter={"category": {"$eq": "archive"}})
print(resp.matched_records)
```

`delete_all=True` wipes the entire namespace. Use carefully.

## Namespace management

Confirmed working against document-schema indexes in `2026-07` — this was **not** supported in the old preview API, which could write to a namespace but not list, describe, create, or delete one via the API.

```python
# Create explicitly (namespaces otherwise auto-create on first upsert — see below).
ns = idx.create_namespace(name="movies-en")
print(ns.name, ns.record_count, ns.size_bytes)

# List every namespace on the index in one call.
for page in idx.list_namespaces():
    for ns in page.namespaces:
        print(ns.name, ns.record_count)

# Describe one namespace. Prefer list_namespaces() over repeated describe_namespace()
# calls — describe_namespace is rate-limited per index; list_namespaces isn't.
ns = idx.describe_namespace(name="movies-en")

# Delete a namespace and everything in it.
idx.delete_namespace(name="movies-en")
```

`create_namespace`'s optional `schema` parameter (`{"fields": {"<field>": {"filterable": True}}}`) controls *which metadata fields get indexed for filtering in that namespace specifically* — omitting it means the namespace inherits the index's own metadata-indexing configuration, which for the managed indexes this skill covers is "index everything" by default (see "Filterable metadata isn't declared in the schema at all" in SKILL.md). There's rarely a reason to pass it explicitly unless you're deliberately restricting which fields are filterable in one namespace.

`__default__` is reserved — it always exists and can't be created or deleted; every namespace-taking call already defaults to it when `namespace` is omitted, but it's worth knowing when you see it show up unbidden in a `list_namespaces()` result.

### `describe_index_stats` — also now works

```python
stats = idx.describe_index_stats()
print(stats.total_vector_count, stats.namespaces)   # total record count, namespace count
```

`describe_index_stats(filter=...)` is documented as rejected on every index type (there's no operation that returns a filtered count) — call it with no arguments.

## Integrating embedding providers

If your index has a dense or sparse vector field, you need embeddings. Three common paths:

### Pinecone hosted inference

Cleanest integration — no extra API keys, same client as the index.

```python
# Indexing side: use input_type="passage" for stored content
resp = pc.inference.embed(
    model="multilingual-e5-large",
    inputs=[doc["body"] for doc in batch],
    parameters={"input_type": "passage", "truncate": "END"},
)
embeddings = [e.values for e in resp.data]

# Query side: use input_type="query" for query strings
q_resp = pc.inference.embed(
    model="multilingual-e5-large",
    inputs=[user_query],
    parameters={"input_type": "query"},
)
q_emb = q_resp.data[0].values
```

The distinction between `input_type="passage"` (stored content) and `input_type="query"` (runtime queries) matters for models that encode them asymmetrically (`multilingual-e5-large` is one). For sparse learned embeddings like `pinecone-sparse-english-v0`, the same convention applies, and each embedding has `.sparse_indices` / `.sparse_values` rather than `.values`.

Batch size: ~96 inputs per `embed` call is the typical server limit. Loop in chunks:

```python
EMBED_BATCH = 96
embeddings = []
for i in range(0, len(docs), EMBED_BATCH):
    chunk = docs[i : i + EMBED_BATCH]
    resp = pc.inference.embed(
        model="multilingual-e5-large",
        inputs=[d["body"] for d in chunk],
        parameters={"input_type": "passage", "truncate": "END"},
    )
    embeddings.extend(e.values for e in resp.data)
```

### Generic pattern — any third-party provider

Wrap the provider-specific call in a thin adapter so ingestion logic doesn't know which provider is in use:

```python
def embed(content) -> list[float]:
    """Return a single dense embedding for a piece of content.

    `content` may be a string or a PIL.Image, depending on the provider.
    Swap the implementation to change providers without touching callers.
    """
    resp = provider.embed(content)
    return resp.values  # or resp.data[0].embedding, etc.

docs = [{"_id": d["id"], "body": d["text"], "embedding": embed(d["text"])} for d in source]
```

This adapter also gives you a single chokepoint for retries, rate-limit backoff, and caching — add them once in `embed()` rather than at every call site.

## Limits to be aware of

- **Bulk import (from object storage) is out of scope for this skill, not unsupported by Pinecone.** Pinecone supports bulk import for document-shaped indexes in `2026-07` (JSON Lines format — see [Import data](https://docs.pinecone.io/guides/index-data/import-data)); this skill just doesn't implement it. Load through `documents.upsert` / `documents.batch_upsert` here, or use a dedicated import skill when one exists.
- **No backup/restore.** If you need recoverability, snapshot your source data, not the index.
- **No CMEK projects alongside any `full_text_search` field** — such indexes can't be created in CMEK-enabled projects.
- **Indexing latency**: documents become searchable in ≲1 minute typically; multi-field schemas can take slightly longer.
