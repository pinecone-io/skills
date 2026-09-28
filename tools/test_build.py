#!/usr/bin/env python3
# Pinned exactly, not floating. These install at CI job time in a job that holds a
# write token for the plugin repos, so a compromised release would run there. The
# same floating-lower-bound habit is what let pinecone 9 break every skill script.
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pytest==9.1.1",
#   "pyyaml==6.0.3",
#   "typer==0.27.1",
# ]
# ///
"""Tests for tools/build.py.

Run: uv run tools/test_build.py

The cross-reference tests are the important ones. That rewrite is the only part of
the transform that can silently corrupt content, and an early version of it did:
`\\bpinecone-assistant\\b` matched inside `@pinecone-database/n8n-nodes-pinecone-assistant`
and rewrote a real npm package name. Every no-op case below is a string that
actually appears in this repo's content.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

SLUGS = ["assistant", "cli", "docs", "full-text-search", "help", "mcp", "n8n", "query", "quickstart"]
CLAUDE = {"include": SLUGS, "cross_reference": "pinecone:{slug}", "dir_name": "{slug}",
          "source_tag": "claude_code_plugin", "ide_source": "claude-code-plugin"}
CURSOR = {"include": SLUGS, "cross_reference": "pinecone-{slug}", "dir_name": "pinecone-{slug}",
          "source_tag": "cursor_plugin", "ide_source": "cursor-plugin"}


def xref(text, manifest=CLAUDE):
    return build.rewrite_cross_references(text, manifest)


class TestCrossReferencesRewritten:
    @pytest.mark.parametrize("before,after", [
        ("see pinecone-assistant", "see pinecone:assistant"),
        ("`pinecone-cli`", "`pinecone:cli`"),
        ("use the pinecone-full-text-search skill", "use the pinecone:full-text-search skill"),
        ("pinecone-quickstart.", "pinecone:quickstart."),
        ("(pinecone-n8n)", "(pinecone:n8n)"),
        ("pinecone-docs and pinecone-help", "pinecone:docs and pinecone:help"),
        ("pinecone-mcp\n", "pinecone:mcp\n"),
    ])
    def test_rewritten(self, before, after):
        assert xref(before) == after

    def test_start_of_string(self):
        assert xref("pinecone-query is the skill") == "pinecone:query is the skill"


class TestCrossReferencesLeftAlone:
    """Every one of these is a real string from this repo. A regression here
    corrupts published content silently."""

    @pytest.mark.parametrize("text", [
        # the bug that shipped: hyphen before `pinecone` is a \b, so \b was not enough
        "`@pinecone-database/n8n-nodes-pinecone-assistant`",
        "@pinecone-database/n8n-nodes-pinecone-assistant.pineconeAssistant",
        "@pinecone-database/n8n-nodes-pinecone-assistant.pineconeAssistantTool",
        # not slugs
        "https://github.com/pinecone-io/skills",
        "pinecone-plugin-assistant",
        "claude/skills/pinecone-fts-index/scripts/ingest.py",
        "pinecone-database",
        # slug followed by a hyphen is a different identifier
        "pinecone-cli-tool",
        "pinecone-assistant-v2",
        # substring of a longer word
        "pinecone-clients",
        # unrelated
        "pinecone_skills:assistant",
        "brew install --cask pinecone-io/tap/pinecone",
    ])
    def test_untouched(self, text):
        assert xref(text) == text


class TestSkillPaths:
    """`pinecone-<slug>/` inside a path follows dir_name, not cross_reference.
    Rendering `../pinecone:assistant/scripts/create.py` shipped a path that cannot
    exist; rendering `../pinecone-assistant/` for Claude ships one that no longer
    does, because the plugin renames the directory."""

    @pytest.mark.parametrize("before,after", [
        ("uv run ../pinecone-assistant/scripts/create.py",
         "uv run ../assistant/scripts/create.py"),
        ("see pinecone-full-text-search/references/querying.md",
         "see full-text-search/references/querying.md"),
        ("skills/pinecone-quickstart/SKILL.md", "skills/quickstart/SKILL.md"),
    ])
    def test_claude_path_follows_dir_name(self, before, after):
        assert xref(before) == after

    def test_cursor_path_is_a_noop(self):
        s = "uv run ../pinecone-assistant/scripts/create.py"
        assert xref(s, CURSOR) == s

    def test_non_slug_path_segment_untouched(self):
        s = "claude/skills/pinecone-fts-index/scripts/ingest.py"
        assert xref(s) == s

    def test_trailing_slash_alone_is_still_a_path(self):
        assert xref("the pinecone-cli/ directory") == "the cli/ directory"


class TestIdentityTarget:
    def test_cursor_cross_reference_is_a_noop(self):
        for s in ["pinecone-assistant", "the pinecone-cli skill", "`pinecone-n8n`"]:
            assert xref(s, CURSOR) == s


class TestSourceTag:
    def test_rewrites_neutral_prefix(self):
        line = 'pc = Pinecone(api_key=k, source_tag="pinecone_skills:assistant")'
        assert build.rewrite_source_tag(line, CLAUDE) == \
            'pc = Pinecone(api_key=k, source_tag="claude_code_plugin:assistant")'

    def test_preserves_operation_suffix(self):
        line = 'source_tag="pinecone_skills:quickstart_upsert"'
        assert build.rewrite_source_tag(line, CURSOR) == 'source_tag="cursor_plugin:quickstart_upsert"'

    def test_leaves_an_already_targeted_tag_alone(self):
        line = 'source_tag="claude_code_plugin:assistant"'
        assert build.rewrite_source_tag(line, CURSOR) == line


class TestSnippets:
    """Snippets carry the wording that really does differ per plugin. They replaced
    an agent that inferred the same difference and answered differently each run."""

    CL = dict(CLAUDE, snippets={"api_key_setup": "export it in your shell"})
    CU = dict(CURSOR, snippets={"api_key_setup": "add it to a `.env` file"})

    def test_fills_per_target(self):
        src = "Set the key: <<api_key_setup>>\n"
        assert build.fill_snippets(src, self.CL, Path("x")) == "Set the key: export it in your shell\n"
        assert build.fill_snippets(src, self.CU, Path("x")) == "Set the key: add it to a `.env` file\n"

    def test_multiple_markers_in_one_file(self):
        m = dict(self.CL, snippets={"a": "AAA", "b": "BBB"})
        assert build.fill_snippets("<<a>> then <<b>>", m, Path("x")) == "AAA then BBB"

    def test_undefined_marker_is_an_error(self):
        """Publishing a skill with `<<api_key_setup>>` in the text is worse than
        either wording, so this must fail rather than pass the marker through."""
        with pytest.raises(ValueError, match="no snippet 'mystery'"):
            build.fill_snippets("<<mystery>>", self.CL, Path("x"))

    def test_trailing_newline_is_stripped(self):
        m = dict(self.CL, snippets={"a": "one\ntwo\n"})
        assert build.fill_snippets("<<a>>\nafter", m, Path("x")) == "one\ntwo\nafter"

    def test_n8n_expressions_are_not_markers(self):
        """pinecone-n8n/SKILL.md is full of `={{ $json.urls }}`. Nothing may touch it."""
        src = '"url": "={{ $json.urls }}",\n'
        assert build.fill_snippets(src, self.CL, Path("x")) == src

    def test_no_marker_no_snippets_defined_is_fine(self):
        assert build.fill_snippets("plain text", CLAUDE, Path("x")) == "plain text"

    def test_snippet_content_goes_through_the_other_rules(self):
        """Snippets fill first on purpose, so their text passes through the same
        guards as base content rather than around them."""
        m = dict(CLAUDE, skill_name="pinecone:{slug}", frontmatter={},
                 snippets={"hint": "see pinecone-cli and ../pinecone-assistant/scripts/x.py"})
        out = build.render_file(Path("references/a.md"), "<<hint>>\n", "docs", m, Path("x"))
        assert out == "see pinecone:cli and ../assistant/scripts/x.py\n"

    def test_identity_target_snippet_is_not_retargeted(self):
        m = dict(CURSOR, skill_name="pinecone-{slug}", frontmatter={},
                 snippets={"hint": "see pinecone-cli and ../pinecone-assistant/scripts/x.py"})
        out = build.render_file(Path("references/a.md"), "<<hint>>\n", "docs", m, Path("x"))
        assert out == "see pinecone-cli and ../pinecone-assistant/scripts/x.py\n"


class TestIdeSource:
    """The real bug this rule fixes: base hardcoded `claude-code-plugin`, so a sync
    would have stamped every Cursor-created assistant as Claude Code."""

    LINE = 'metadata={"agentic-ide-source":"pinecone-skills"}'

    def test_retargets_for_claude(self):
        out = build.rewrite_ide_source(self.LINE, CLAUDE, Path("x"))
        assert out == 'metadata={"agentic-ide-source":"claude-code-plugin"}'

    def test_retargets_for_cursor(self):
        out = build.rewrite_ide_source(self.LINE, CURSOR, Path("x"))
        assert out == 'metadata={"agentic-ide-source":"cursor-plugin"}'

    def test_tolerates_spacing(self):
        line = 'metadata={"agentic-ide-source": "pinecone-skills"}'
        assert 'cursor-plugin' in build.rewrite_ide_source(line, CURSOR, Path("x"))

    def test_already_targeted_is_idempotent(self):
        line = 'metadata={"agentic-ide-source":"cursor-plugin"}'
        assert build.rewrite_ide_source(line, CURSOR, Path("x")) == line

    def test_a_foreign_target_name_is_an_error(self):
        """Base drifting back to a hardcoded target name must fail the build, not be
        silently overwritten — silence is how this survived the first time."""
        line = 'metadata={"agentic-ide-source":"claude-code-plugin"}'
        with pytest.raises(ValueError, match="base must use"):
            build.rewrite_ide_source(line, CURSOR, Path("x"))

    def test_py_dispatch_applies_both_scalars(self):
        text = 'source_tag="pinecone_skills:assistant"\n{"agentic-ide-source":"pinecone-skills"}\n'
        out = build.render_file(Path("scripts/create.py"), text, "assistant", CURSOR, Path("x"))
        assert "cursor_plugin:assistant" in out
        assert "cursor-plugin" in out
        assert "pinecone-skills" not in out

    def test_ide_source_value_is_not_eaten_by_cross_references(self):
        """`pinecone-skills` is not a slug, so no rule should touch it in prose."""
        assert xref("pinecone-skills") == "pinecone-skills"


class TestFrontmatter:
    BASE = "---\nname: pinecone-quickstart\ndescription: Do a thing.\n---\nBody here.\n"

    def test_name_rewritten_and_allowed_tools_appended_last(self):
        m = dict(CLAUDE, skill_name="pinecone:{slug}",
                 frontmatter={"quickstart": {"allowed-tools": "Skill, Bash, Read"}})
        out = build.render_skill_md(self.BASE, "quickstart", m, Path("x"))
        assert out.startswith(
            "---\nname: pinecone:quickstart\ndescription: Do a thing.\nallowed-tools: Skill, Bash, Read\n---\n"
        )

    def test_argument_hint_precedes_allowed_tools(self):
        src = "---\nname: pinecone-cli\ndescription: D\nargument-hint: install | auth\n---\nB\n"
        m = dict(CLAUDE, skill_name="pinecone:{slug}",
                 frontmatter={"cli": {"allowed-tools": "Bash, Read"}})
        out = build.render_skill_md(src, "cli", m, Path("x"))
        keys = [l.split(":")[0] for l in out.split("---\n")[1].strip().splitlines()]
        assert keys == ["name", "description", "argument-hint", "allowed-tools"]

    def test_no_allowed_tools_when_manifest_has_none(self):
        m = dict(CURSOR, skill_name="pinecone-{slug}", frontmatter={})
        out = build.render_skill_md(self.BASE, "quickstart", m, Path("x"))
        assert "allowed-tools" not in out
        assert "name: pinecone-quickstart" in out

    def test_description_cross_references_rewritten(self):
        src = "---\nname: pinecone-help\ndescription: See pinecone-cli for more.\n---\nB\n"
        m = dict(CLAUDE, skill_name="pinecone:{slug}", frontmatter={})
        out = build.render_skill_md(src, "help", m, Path("x"))
        assert "description: See pinecone:cli for more." in out

    def test_wrong_base_name_is_an_error(self):
        src = "---\nname: pinecone-wrong\ndescription: D\n---\nB\n"
        m = dict(CLAUDE, skill_name="pinecone:{slug}", frontmatter={})
        with pytest.raises(ValueError, match="expected"):
            build.render_skill_md(src, "quickstart", m, Path("x"))

    def test_unknown_frontmatter_key_is_an_error(self):
        """Better to fail than to silently drop a key a future skill adds."""
        src = "---\nname: pinecone-help\ndescription: D\nmystery: x\n---\nB\n"
        m = dict(CLAUDE, skill_name="pinecone:{slug}", frontmatter={})
        with pytest.raises(ValueError, match="unhandled frontmatter"):
            build.render_skill_md(src, "help", m, Path("x"))

    def test_missing_frontmatter_is_an_error(self):
        with pytest.raises(ValueError, match="must open with"):
            build.render_skill_md("no frontmatter here\n", "help", CLAUDE, Path("x"))


class TestFileDispatch:
    def test_py_gets_source_tag_only_not_cross_refs(self):
        text = '# see pinecone-assistant\nsource_tag="pinecone_skills:cli"\n'
        out = build.render_file(Path("scripts/x.py"), text, "cli", CLAUDE, Path("x"))
        assert "claude_code_plugin:cli" in out
        assert "pinecone-assistant" in out, "python comments are not skill prose; leave them alone"

    def test_reference_md_gets_cross_refs(self):
        out = build.render_file(Path("references/a.md"), "see pinecone-cli\n", "docs", CLAUDE, Path("x"))
        assert out == "see pinecone:cli\n"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
