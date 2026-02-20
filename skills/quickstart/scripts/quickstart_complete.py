#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pinecone>=8.0.0",
# ]
# ///

import os
from pinecone import Pinecone

api_key = os.environ.get("PINECONE_API_KEY")
if not api_key:
    raise ValueError("PINECONE_API_KEY environment variable not set")

pc = Pinecone(api_key=api_key, source_tag="pinecone_skills:index_quickstart")

# 1. Create a serverless index with an integrated embedding model
index_name = "quickstart"

if not pc.has_index(index_name):
    pc.create_index_for_model(
        name=index_name,
        cloud="aws",
        region="us-east-1",
        embed={
            "model": "llama-text-embed-v2",
            "field_map": {"text": "chunk_text"}
        }
    )

# 2. Upsert records
records = [
    {
        "_id": "rec1",
        "chunk_text": "The Eiffel Tower was built in 1889 as a temporary exhibit for the World's Fair in Paris and attracts millions of visitors each year.",
        "category": "architecture"
    },
    {
        "_id": "rec2",
        "chunk_text": "The Great Wall of China stretches over 13,000 miles and was built over many centuries to protect against invasions from the north.",
        "category": "architecture"
    },
    {
        "_id": "rec3",
        "chunk_text": "The Colosseum in Rome, completed in 80 AD, could hold between 50,000 and 80,000 spectators for gladiatorial contests and public spectacles.",
        "category": "architecture"
    },
    {
        "_id": "rec4",
        "chunk_text": "The Taj Mahal in Agra, India was commissioned in 1632 by Mughal Emperor Shah Jahan as a mausoleum for his beloved wife Mumtaz Mahal.",
        "category": "architecture"
    },
    {
        "_id": "rec5",
        "chunk_text": "Machu Picchu is a 15th-century Inca citadel located in the Andes Mountains of Peru, rediscovered by explorer Hiram Bingham in 1911.",
        "category": "architecture"
    },
    {
        "_id": "rec6",
        "chunk_text": "The Statue of Liberty was a gift from France to the United States, dedicated in 1886, and stands as a symbol of freedom and democracy.",
        "category": "architecture"
    },
    {
        "_id": "rec7",
        "chunk_text": "The Parthenon is a former temple on the Athenian Acropolis dedicated to the goddess Athena, constructed between 447 and 432 BC.",
        "category": "architecture"
    },
    {
        "_id": "rec8",
        "chunk_text": "Stonehenge is a prehistoric monument in Wiltshire, England, with the largest stones weighing up to 25 tons, dating to around 2500 BC.",
        "category": "architecture"
    },
]

dense_index = pc.Index(index_name)
dense_index.upsert_records("example-namespace", records)

# 3. Search records
query = "Famous historical structures and monuments"

results = dense_index.search(
    namespace="example-namespace",
    query={"top_k": 3, "inputs": {"text": query}}
)

print("Search results:")
for hit in results["result"]["hits"]:
    print(f"  id: {hit['_id']} | score: {round(hit['_score'], 2)} | text: {hit['fields']['chunk_text']}")

# 4. Search with reranking
reranked_results = dense_index.search(
    namespace="example-namespace",
    query={"top_k": 3, "inputs": {"text": query}},
    rerank={"model": "bge-reranker-v2-m3", "top_n": 3, "rank_fields": ["chunk_text"]}
)

print("\nReranked results:")
for hit in reranked_results["result"]["hits"]:
    print(f"  id: {hit['_id']} | score: {round(hit['_score'], 2)} | text: {hit['fields']['chunk_text']}")
