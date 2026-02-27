# Skills Repo — Authoring Guidelines

This is the **base skills repo**. Skills here must work across any agent environment (Claude Code, Cursor, Gemini, etc.). IDE-specific repos fork from here and contextualize as needed.

## Generalization Rules

**No IDE-specific tool calls.** Don't use `AskUserQuestion` or any tool that isn't universally available. Use plain prose: "ask the user which they prefer."

**Never assume `PINECONE_API_KEY` is inherited.** Always check first. If not set:
- Tell the user to `export PINECONE_API_KEY=...` (terminal envs)
- Or create a `.env` file and run scripts with `uv run --env-file .env scripts/...` (IDE envs that don't inherit shell vars)

**MCP-dependent skills must say so.** If a skill requires MCP, state it in the description and fail fast with a helpful message if tools aren't available.

**No IDE-specific language.** Avoid phrases like "Claude Code console" or references to specific IDE UI.

**No fake API key literals.** Never write `pcsk_...` or similar patterns — use `your-key` as a placeholder. Security linters will flag fake key patterns.

## Linting

Run from `../tools/` (one directory up):

```bash
uv run ../tools/check-skills.py --skills-dir skills/
uv run ../tools/check-source-tags.py --dir .
uv run ../tools/check-links.py --skills-dir skills/
```
