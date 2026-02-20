---
name: query
description: Query integrated indexes using text with Pinecone MCP. IMPORTANT - This skill ONLY works with integrated indexes (indexes with built-in Pinecone embedding models like multilingual-e5-large). For standard indexes or advanced vector operations, use the CLI skill instead. Requires PINECONE_API_KEY environment variable and Pinecone MCP server to be configured.
argument-hint: query [q] index [indexName] namespace [ns] topK [k] reranker [rerankModel]
---

# Pinecone Query Skill

Search for records in Pinecone integrated indexes using natural language text queries via the Pinecone MCP server.

## What is this skill for?

This skill provides a simple way to query **integrated indexes** (indexes with built-in Pinecone embedding models) using text queries. The MCP server automatically converts your text into embeddings and searches the index.

### Prerequisites

**Required:**
1. ✅ **Pinecone MCP server must be configured** - Check if MCP tools are available
2. ✅ **PINECONE_API_KEY environment variable must be set** - Get a free API key at https://app.pinecone.io/?sessionType=signup
3. ✅ **Index must be an integrated index** - Uses Pinecone embedding models (e.g., multilingual-e5-large, llama-text-embed-v2, pinecone-sparse-english-v0)

### When NOT to use this skill

**Use the CLI skill instead if:**
- ❌ Your index is a standard index (no integrated embedding model)
- ❌ You need to query with custom vector values (not text)
- ❌ You need advanced vector operations (fetch by ID, list vectors, bulk operations)
- ❌ Your index uses third-party embedding models (OpenAI, HuggingFace, Cohere)

**MCP Limitation**: The Pinecone MCP currently only supports integrated indexes. For all other use cases, use the Pinecone CLI skill.

## How it works

Utilize Pinecone MCP's `search-records` tool to search for records within a specified Pinecone integrated index using a text query.

## Workflow
When necessary, try to use the AskUserQuestion tool to make entering multiple choice responses easier.

**IMPORTANT: Before proceeding, verify the Pinecone MCP tools are available.** If MCP tools are not accessible:
- Inform the user that the Pinecone MCP server needs to be configured
- Check if `PINECONE_API_KEY` environment variable is set
- Direct them to the MCP setup documentation or the pinecone:help skill

1. Parse the user's input for:
   - `query` (required): The text to search for.
   - `index` (required): The name of the Pinecone index to search.
   - `namespace` (optional): The namespace within the index.
   - `reranker` (optional): The reranking model to use for improved relevance.

2. If the user omits required arguments:
   - If only the index name is provided, use the `describe-index` tool to retrieve available namespaces and prompt the user to choose with AskUserQuestion.
   - If only a query is provided, use `list-indexes` to get available indexes, prompt the user to pick one, then use `describe-index` for namespaces if needed.

3. Call the `search-records` tool with the gathered arguments to perform the search.

4. Format and display the returned results in a clear, readable table for the Claude Code console, including field highlights (such as ID, score, and relevant metadata).

---

## Troubleshooting

***IMPORTANT** Pinecone API Key is required for using this plugin, command and MCP server!

A user must have a Pinecone API key to use this command and the MCP server. One can be obtained for free by making a Pinecone account at https://app.pinecone.io/?sessionType=signup
Then, the user must export the API key to their environment, as a variable named PINECONE_API_KEY. 

If you run into an error regarding access, it's likely an API isn't set. Advise a 
user to set their API key accordingly, and restart their Claude Code instance.

**IMPORTANT** At the moment, the /query command can only be used with integrated indexes, which use hosted Pinecone embedding models to embed and search for data.
If a user attempts to query an index that uses a third party API model such as OpenAI, or HuggingFace embedding models, remind them that this capability is not available yet
with the Pinecone MCP server.

- If required arguments are missing, prompt the user to supply them, using Pinecone MCP tools as needed (e.g., `list-indexes`, `describe-index`).
- Guide the user interactively through argument selection until the search can be completed.
- If an invalid value is provided for any argument (e.g., nonexistent index or namespace), surface the error and suggest valid options.

## Tools Reference

- `search-records`: Search records in a given index with optional metadata filtering and reranking.
- `list-indexes`: List all available Pinecone indexes.
- `describe-index`: Get index configuration and namespaces.
- `describe-index-stats`: Get stats including record counts and namespaces.
- `rerank-documents`: Rerank returned documents using a specified reranking model.
- Helper: Use AskUserQuestion to interactively clarify missing information.

---
