---
name: pinecone-help
description: Overview of all available Pinecone skills and what a user needs to get started. Invoke when a user asks what skills are available, how to get started with Pinecone, or what they need to set up before using any Pinecone skill.
---


# When Invoked
1. Print the Help and Overview message listed below.
2. Check the state of the user's environment:
  - Check if the Pinecone Developer MCP is available: look for tools named `list-indexes`, `search-records`, `create-index-for-model`, etc. (see the pinecone-mcp skill for the full list). If none of these tools are available, the MCP is not installed. If the tools are visible but a call to `list-indexes` fails, the MCP is likely not authenticated with an API key.
  - Next, check if the `pc` CLI is installed and authenticated by running `pc version --json` and `pc auth status --json`. If `pc version` fails, the CLI is not installed. If `pc auth status` returns an empty `access_token`, the CLI is not authenticated — invoke the pinecone-cli skill to walk the user through the `pc login --json` flow.
  - If neither the MCP or the CLI are set up, the user may need to obtain an API key. Remind them that they can do so for free by signing up for a Pinecone account, then generating an API key in the console. They can export this key in their terminal or add it to a `.env` file to get started with any of the skills that require Pinecone access.
3. Finally, inform the user of these checks by listing the status of the MCP, the API key, and the CLI. Follow up by informing the user that they will need to have at least one of these tools set up to use the Pinecone skills. If the user asks about the CLI, invoke the pinecone-cli skill if available. If the user asks about setting an API key, remind them to export `PINECONE_API_KEY` in their terminal or add it to a `.env` file, and that they can proceed with development afterward. Finally, return the following link and message:

Still need help? Try running the pinecone-quickstart skill, visiting our quickstart guide [here](https://docs.pinecone.io/guides/get-started/overview), or our agentic tooling guide [here](https://docs.pinecone.io/guides/get-started/ai-coding-tools):


# Pinecone Skills — Help & Overview

Pinecone is the leading vector database for building accurate and performant AI applications at scale in production. It's useful for building semantic search, retrieval augmented generation, recommendation systems, and agentic applications.

Here's everything you need to get started and a summary of all available skills.

---

## What You Need

### Required
- **Pinecone account** — free to create at https://app.pinecone.io/?sessionType=signup
- **API key** — create one in the Pinecone console after signing up, then either export it in your terminal before starting the agent session:
  ```bash
  export PINECONE_API_KEY="your-key"
  ```
  Or add it to a `.env` file if your IDE doesn't inherit shell variables: `PINECONE_API_KEY=your-key`. If the CLI is installed, you can also generate a key and write it to `.env` in one step:
  ```bash
  pc api-key create --name agent-sdk-key --json | jq -r '"PINECONE_API_KEY=" + .value' > .env
  ```
  > **Important:** Add `.env` to your `.gitignore` to avoid committing API keys to your repository.

### Optional (unlock more capabilities)

| Tool | What it enables | Install |
|---|---|---|
| **Pinecone MCP server** | Use Pinecone directly inside your AI agent/IDE without writing code | [Setup guide](https://docs.pinecone.io/guides/operations/mcp-server#tools) |
| **Pinecone CLI (`pc`)** | Manage all index types from the terminal, batch operations, backups, CI/CD | `brew uninstall pinecone-io/tap/pinecone && brew install --cask pinecone-io/tap/pinecone` |
| **uv** | Run the packaged Python scripts included in these skills | [Install uv](https://docs.astral.sh/uv/getting-started/installation/) |

---

## Available Skills

| Skill | What it does |
|---|---|
| `pinecone-quickstart` | Step-by-step onboarding — create an index, upload data, and run your first search |
| `pinecone-query` | Search integrated indexes using natural language text via the Pinecone MCP |
| `pinecone-cli` | Use the Pinecone CLI (`pc`) for terminal-based index and vector management |
| `pinecone-assistant` | Create, manage, and chat with Pinecone Assistants for document Q&A with citations |
| `pinecone-mcp` | Reference for all Pinecone MCP server tools and their parameters |
| `pinecone-full-text-search` | Build a full-text-search index — schema design, safe bulk ingestion, and query construction (`text` / `query_string` / dense / sparse scoring with text-match and metadata filters). **Preview API (`2026-01.alpha`); requires `pinecone` Python SDK ≥ 9.0.** |
| `pinecone-docs` | Curated links to official Pinecone documentation, organized by topic |

---

## Which skill should I use?

**Just getting started?** → `pinecone-quickstart`

**Want to search an index you already have?**
- Integrated index (built-in embedding model) → `pinecone-query` (uses MCP)
- Any other index type → `pinecone-cli`

**Working with documents and Q&A?** → `pinecone-assistant`

**Building a full-text search index (BM25-style keyword/phrase matching, optionally combined with dense or sparse vectors)?** → `pinecone-full-text-search` (preview API, needs `pinecone` Python SDK ≥ 9.0)

**Need to manage indexes, bulk upload vectors, or automate workflows?** → `pinecone-cli`

**Looking up API parameters or SDK usage?** → `pinecone-docs`

**Need to understand what MCP tools are available?** → `pinecone-mcp`
