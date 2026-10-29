#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pinecone==10.2.0",
# ]
# ///

import os
import time
from pinecone import Pinecone, SchemaBuilder

api_key = os.environ.get("PINECONE_API_KEY")
if not api_key:
    raise ValueError("PINECONE_API_KEY environment variable not set")

pc = Pinecone(api_key=api_key, source_tag="pinecone_skills:index_quickstart")

# 1. Create a document index with one text field that supports both kinds of search:
#    full_text_search indexes it for exact terms, and embed has Pinecone embed it for meaning.
index_name = "quickstart"

schema = (
    SchemaBuilder()
      .add_string_field("chunk_text", full_text_search={"language": "en"}, embed={})
      .build()
)
if not pc.indexes.exists(name=index_name):
    pc.indexes.create(name=index_name, schema=schema)
else:
    existing = pc.indexes.describe(name=index_name).schema
    field = existing.fields.get("chunk_text") if existing else None
    if not (getattr(field, "full_text_search", None) and getattr(field, "embed", None)):
        raise ValueError(f"Index '{index_name}' already exists with a different schema. Delete it or change index_name.")

while not pc.indexes.describe(name=index_name).status.ready:
    time.sleep(2)

index = pc.index(name=index_name)

# 2. Upsert documents. Pinecone embeds chunk_text on write, so you send plain text.
index.documents.upsert(
    namespace="__default__",
    documents=[
        {"_id": "1", "chunk_text": "Refund requests must be submitted within 30 days of purchase.", "category": "policy"},
        {"_id": "2", "chunk_text": "Enterprise customers get support with a 4-hour response time.", "category": "policy"},
        {"_id": "3", "chunk_text": "Error E1042: the connection timed out after 30 seconds. Retry with a longer timeout.", "category": "log"},
        {"_id": "4", "chunk_text": "To reset your password, open Settings and choose Security.", "category": "support"},
        {"_id": "5", "chunk_text": "Order 88231 shipped on 2026-08-20 via express courier.", "category": "order"},
    ],
)

time.sleep(10)  # documents are indexed asynchronously, so wait a moment

# 3. Search by meaning
meaning = index.documents.search(
    namespace="__default__",
    top_k=3,
    score_by=[{"type": "embed", "fields": ["chunk_text"], "query": "how do I get my money back?"}],
    include_fields=["chunk_text"],
)

print("Search by meaning:")
for m in meaning.matches:
    print(m._id, f"{m._score:.3f}", m.chunk_text)

# 4. Search by exact terms
terms = index.documents.search(
    namespace="__default__",
    top_k=3,
    score_by=[{"type": "text", "fields": ["chunk_text"], "query": "E1042"}],
    include_fields=["chunk_text"],
)

print("\nSearch by exact terms:")
for m in terms.matches:
    print(m._id, f"{m._score:.3f}", m.chunk_text)
