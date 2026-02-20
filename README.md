# Pinecone Agent Skills

Note: This repo is still WIP and will be finished soon!

Pinecone is the leading vector database for building accurate and performant AI applications at scale in production. Use it to build semantic search, retrieval augmented generation, recommendation systems, and agentic applications.

This is Pinecone's official Agent Skills library, compatible with agentic IDEs such as Cursor, GitHub Copilot, Windsurf, Gemini CLI, and more. Skills follow the [Agent Skills standard](https://agentskills.io).

---

## Installation

```bash
npx skills add pinecone-io/skills
```

Using Claude Code? Try our [official plugin](https://github.com/pinecone-io/pinecone-claude-code-plugin) instead.

---

## Skills

| Skill | Description |
|---|---|
| [`quickstart`](skills/quickstart/SKILL.md) | Step-by-step onboarding — create an index, upload data, and run your first search |
| [`query`](skills/query/SKILL.md) | Search integrated indexes using natural language text via the Pinecone MCP |
| [`cli`](skills/cli/SKILL.md) | Use the Pinecone CLI (`pc`) for terminal-based index and vector management across all index types |
| [`assistant`](skills/assistant/SKILL.md) | Create, manage, and chat with Pinecone Assistants for document Q&A with citations |
| [`mcp`](skills/mcp/SKILL.md) | Reference for all Pinecone MCP server tools and their parameters |
| [`pinecone-docs`](skills/pinecone-docs/SKILL.md) | Curated links to official Pinecone documentation, organized by topic |
| [`help`](skills/help/SKILL.md) | Overview of all skills and what you need to get started |

---

## Prerequisites

- **Pinecone account** — free at [app.pinecone.io](https://app.pinecone.io/?sessionType=signup)
- **API key** — create one in the console, then `export PINECONE_API_KEY="pcsk_..."`
- **Pinecone MCP** *(optional)* — enables the `query` skill and agent-native index operations. [Setup guide](https://docs.pinecone.io/guides/operations/mcp-server#tools)
- **Pinecone CLI** *(optional)* — enables the `cli` skill. `brew install pinecone-io/tap/pinecone`
- **uv** *(optional)* — runs the bundled Python scripts. `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

## Development

Validate all skills against the Agent Skills spec:
```bash
uv run tools/check-skills.py --skills-dir skills
```

Check for broken links:
```bash
uv run tools/check-links.py --skills-dir skills
```

Check source tag conventions in scripts:
```bash
uv run tools/check-source-tags.py --dir skills
```
