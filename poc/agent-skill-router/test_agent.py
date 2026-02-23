"""Tests for the OpenClaw agent skill router POC."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from openclaw_agent.skill_loader import (
    Skill,
    SkillRequirements,
    _parse_frontmatter,
    _parse_skill,
    load_skills,
    load_skills_from_dir,
)
from openclaw_agent.system_prompt import (
    build_skills_section,
    build_system_prompt,
    format_skills_for_prompt,
)
from openclaw_agent.router import RoutingResult, ExecutionResult, SkillRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SKILL_MD = """\
---
name: weather
description: "Get current weather and forecasts."
emoji: "🌤️"
requires:
  bins:
    - curl
---

# Weather Skill

Get weather via wttr.in.
"""

SAMPLE_SKILL_NO_FRONTMATTER = """\
# Plain Skill

No frontmatter here.
"""

SAMPLE_SKILL_NESTED_METADATA = """\
---
name: slack
description: "Use Slack."
metadata:
  openclaw:
    emoji: "💬"
    requires:
      bins:
        - slack-cli
---

# Slack Skill
"""


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory with sample SKILL.md files."""
    weather = tmp_path / "weather"
    weather.mkdir()
    (weather / "SKILL.md").write_text(SAMPLE_SKILL_MD)

    github = tmp_path / "github"
    github.mkdir()
    (github / "SKILL.md").write_text(
        "---\nname: github\ndescription: GitHub operations.\nemoji: '🐙'\n---\n\n# GitHub\n"
    )

    return tmp_path


@pytest.fixture
def sample_skills() -> list[Skill]:
    return [
        Skill(
            name="weather",
            description="Get current weather and forecasts.",
            file_path="/skills/weather/SKILL.md",
            body="# Weather\nGet weather via wttr.in.",
            emoji="🌤️",
            requires=SkillRequirements(bins=["curl"]),
        ),
        Skill(
            name="github",
            description="GitHub operations via gh CLI.",
            file_path="/skills/github/SKILL.md",
            body="# GitHub\nUse gh CLI.",
            emoji="🐙",
            requires=SkillRequirements(bins=["gh"]),
        ),
        Skill(
            name="coding",
            description="Code editing and debugging.",
            file_path="/skills/coding/SKILL.md",
            body="# Coding\nWrite and edit code.",
            emoji="💻",
            requires=SkillRequirements(),
        ),
    ]


# ---------------------------------------------------------------------------
# skill_loader tests
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_basic(self):
        fm, body = _parse_frontmatter(SAMPLE_SKILL_MD)
        assert fm["name"] == "weather"
        assert fm["emoji"] == "🌤️"
        assert "Weather Skill" in body

    def test_no_frontmatter(self):
        fm, body = _parse_frontmatter(SAMPLE_SKILL_NO_FRONTMATTER)
        assert fm == {}
        assert "Plain Skill" in body

    def test_nested_metadata(self):
        fm, body = _parse_frontmatter(SAMPLE_SKILL_NESTED_METADATA)
        assert fm["name"] == "slack"
        assert fm["metadata"]["openclaw"]["emoji"] == "💬"


class TestParseSkill:
    def test_parse_skill_file(self, tmp_path: Path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(SAMPLE_SKILL_MD)
        skill = _parse_skill(str(skill_md))
        assert skill is not None
        assert skill.name == "weather"
        assert skill.emoji == "🌤️"
        assert skill.requires.bins == ["curl"]

    def test_parse_missing_file(self):
        assert _parse_skill("/nonexistent/SKILL.md") is None

    def test_parse_nested_metadata(self, tmp_path: Path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(SAMPLE_SKILL_NESTED_METADATA)
        skill = _parse_skill(str(skill_md))
        assert skill is not None
        assert skill.name == "slack"
        assert skill.emoji == "💬"
        assert skill.requires.bins == ["slack-cli"]

    def test_fallback_name_from_dir(self, tmp_path: Path):
        myskill = tmp_path / "my-cool-skill"
        myskill.mkdir()
        (myskill / "SKILL.md").write_text("---\ndescription: test\n---\n\n# Body\n")
        skill = _parse_skill(str(myskill / "SKILL.md"))
        assert skill is not None
        assert skill.name == "my-cool-skill"


class TestLoadSkills:
    def test_load_from_dir(self, skills_dir: Path):
        skills = load_skills_from_dir(str(skills_dir))
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"weather", "github"}

    def test_load_from_missing_dir(self):
        assert load_skills_from_dir("/nonexistent") == []

    def test_load_multiple_dirs(self, skills_dir: Path, tmp_path: Path):
        extra = tmp_path / "extra"
        extra.mkdir()
        coding = extra / "coding"
        coding.mkdir()
        (coding / "SKILL.md").write_text("---\nname: coding\ndescription: Code.\n---\n\n# Code\n")

        skills = load_skills(str(skills_dir), str(extra))
        names = {s.name for s in skills}
        assert "weather" in names
        assert "coding" in names

    def test_eligible_filter(self, skills_dir: Path):
        all_skills = load_skills(str(skills_dir), check_eligible=False)
        eligible = load_skills(str(skills_dir), check_eligible=True)
        # At least weather (requires curl) should be eligible in most CI environments
        # but we can't guarantee it, so just check the filter runs without error
        assert len(eligible) <= len(all_skills)


class TestSkillEligibility:
    def test_no_requirements_eligible(self):
        skill = Skill(name="x", description="", file_path="", body="")
        assert skill.is_eligible() is True

    def test_missing_binary(self):
        skill = Skill(
            name="x", description="", file_path="", body="",
            requires=SkillRequirements(bins=["definitely_not_a_real_binary_xyz"]),
        )
        assert skill.is_eligible() is False

    def test_missing_env_var(self):
        skill = Skill(
            name="x", description="", file_path="", body="",
            requires=SkillRequirements(env=["DEFINITELY_NOT_SET_XYZ"]),
        )
        assert skill.is_eligible() is False


# ---------------------------------------------------------------------------
# system_prompt tests
# ---------------------------------------------------------------------------


class TestFormatSkillsForPrompt:
    def test_empty(self):
        assert format_skills_for_prompt([]) == ""

    def test_format(self, sample_skills: list[Skill]):
        result = format_skills_for_prompt(sample_skills)
        assert "<available_skills>" in result
        assert "🌤️ weather:" in result
        assert "🐙 github:" in result
        assert "location:" in result


class TestBuildSkillsSection:
    def test_empty(self):
        assert build_skills_section([]) == ""

    def test_with_skills(self, sample_skills: list[Skill]):
        section = build_skills_section(sample_skills)
        assert "## Skills (mandatory)" in section
        assert "scan <available_skills>" in section
        assert "create a new skill" in section
        assert "weather" in section


class TestBuildSystemPrompt:
    def test_has_identity(self, sample_skills: list[Skill]):
        prompt = build_system_prompt(sample_skills)
        assert "personal assistant" in prompt
        assert "OpenClaw" in prompt

    def test_has_tooling(self, sample_skills: list[Skill]):
        prompt = build_system_prompt(sample_skills)
        assert "## Tooling" in prompt
        assert "read:" in prompt

    def test_has_skills(self, sample_skills: list[Skill]):
        prompt = build_system_prompt(sample_skills)
        assert "## Skills (mandatory)" in prompt
        assert "weather" in prompt
        assert "github" in prompt

    def test_has_workspace(self, sample_skills: list[Skill]):
        prompt = build_system_prompt(sample_skills, workspace_dir="/project")
        assert "/project" in prompt

    def test_extra_context(self, sample_skills: list[Skill]):
        prompt = build_system_prompt(sample_skills, extra_context="Custom notes")
        assert "Custom notes" in prompt

    def test_no_skills(self):
        prompt = build_system_prompt([])
        assert "## Skills (mandatory)" not in prompt
        assert "personal assistant" in prompt


# ---------------------------------------------------------------------------
# router tests
# ---------------------------------------------------------------------------


class TestKeywordRouting:
    def test_weather_match(self, sample_skills: list[Skill]):
        router = SkillRouter(sample_skills)
        result = router.route("What's the weather in Tokyo?")
        assert result.selected_skill is not None
        assert result.selected_skill.name == "weather"
        assert result.mode == "keyword"

    def test_github_match(self, sample_skills: list[Skill]):
        router = SkillRouter(sample_skills)
        result = router.route("Open a PR on GitHub for the login fix")
        assert result.selected_skill is not None
        assert result.selected_skill.name == "github"

    def test_coding_match(self, sample_skills: list[Skill]):
        router = SkillRouter(sample_skills)
        result = router.route("Fix the bug in my code and add tests")
        assert result.selected_skill is not None
        assert result.selected_skill.name == "coding"

    def test_no_match(self):
        router = SkillRouter([])
        result = router.route("Hello, how are you?")
        assert result.selected_skill is None
        assert "No matching skill" in result.response

    def test_skill_name_mention(self, sample_skills: list[Skill]):
        """Mentioning a skill name directly should boost its score."""
        router = SkillRouter(sample_skills)
        result = router.route("use github to check my PRs")
        assert result.selected_skill is not None
        assert result.selected_skill.name == "github"


class TestRoutingResult:
    def test_dataclass(self, sample_skills: list[Skill]):
        result = RoutingResult(
            selected_skill=sample_skills[0],
            response="test",
            all_skills=sample_skills,
            mode="keyword",
        )
        assert result.selected_skill.name == "weather"
        assert result.mode == "keyword"


class TestSkillRouter:
    def test_system_prompt_accessible(self, sample_skills: list[Skill]):
        router = SkillRouter(sample_skills)
        assert "personal assistant" in router.system_prompt
        assert "weather" in router.system_prompt

    def test_keyword_fallback_without_api_key(self, sample_skills: list[Skill]):
        router = SkillRouter(sample_skills, api_key="")
        result = router.route("Check the weather")
        assert result.mode == "keyword"

    def test_create_skill_from_args(self, sample_skills: list[Skill], tmp_path: Path):
        router = SkillRouter(sample_skills, workspace_dir=str(tmp_path), api_key="")
        created = router._create_skill_from_args(
            {
                "skill_name": "translation",
                "description": "Translate text between languages.",
                "body": "# Translation\n\nTranslate text accurately.",
            },
        )
        assert created is not None
        assert created.name == "translation"
        assert (tmp_path / "translation" / "SKILL.md").exists()

    def test_create_skill_rejects_invalid_name(self, sample_skills: list[Skill], tmp_path: Path):
        router = SkillRouter(sample_skills, workspace_dir=str(tmp_path), api_key="")
        created = router._create_skill_from_args(
            {
                "skill_name": "../bad",
                "description": "Bad",
                "body": "# Bad",
            },
        )
        assert created is None

    def test_route_via_llm_can_create_skill(self, sample_skills: list[Skill], tmp_path: Path, monkeypatch):
        class _FakeToolCall:
            def __init__(self):
                self.function = type(
                    "Fn", (),
                    {
                        "name": "create_skill",
                        "arguments": (
                            '{"skill_name":"translation","description":"Translate text.","'
                            'body":"# Translation\\n\\nUse translation tooling.","'
                            'response":"[Skill: translation] Created and selected translation skill."}'
                        ),
                    },
                )()

        class _FakeChoice:
            def __init__(self):
                self.message = type(
                    "Msg", (),
                    {"tool_calls": [_FakeToolCall()], "content": ""},
                )()

        class _FakeCompletions:
            @staticmethod
            def create(**_kwargs):
                return type("Resp", (), {"choices": [_FakeChoice()]})()

        class _FakeClient:
            def __init__(self, **_kwargs):
                self.chat = type("Chat", (), {"completions": _FakeCompletions()})()

        monkeypatch.setattr("openclaw_agent.router._get_openai_client_class", lambda: _FakeClient)
        router = SkillRouter(sample_skills, workspace_dir=str(tmp_path), api_key="test-key")
        result = router.route("Translate hello to Spanish")
        assert result.mode == "llm"
        assert result.selected_skill is not None
        assert result.selected_skill.name == "translation"
        assert (tmp_path / "translation" / "SKILL.md").exists()


# ---------------------------------------------------------------------------
# skill_manager tests
# ---------------------------------------------------------------------------


from openclaw_agent.skill_manager import SkillManager


class TestSkillManager:
    def test_create_and_get(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        created = mgr.create("test-skill", "A test skill.", "# Test\n\nBody.")
        assert created is not None
        assert created.name == "test-skill"
        assert mgr.get("test-skill") is not None
        assert (tmp_path / "test-skill" / "SKILL.md").exists()

    def test_create_rejects_invalid_name(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        assert mgr.create("../bad", "Bad", "# Bad") is None
        assert mgr.create("", "Empty", "# Empty") is None
        assert mgr.create("-leading", "Bad", "# Bad") is None

    def test_create_rejects_duplicate(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        mgr.create("dupe", "First.", "# First")
        assert mgr.create("dupe", "Second.", "# Second") is None

    def test_list_names(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        mgr.create("beta", "B.", "# B")
        mgr.create("alpha", "A.", "# A")
        assert mgr.list_names() == ["alpha", "beta"]

    def test_update(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        mgr.create("updatable", "Old desc.", "# Old body")
        updated = mgr.update("updatable", description="New desc.")
        assert updated is not None
        assert updated.description == "New desc."
        assert updated.body == "# Old body"  # body unchanged

    def test_update_body(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        mgr.create("updatable", "Desc.", "# Old body")
        updated = mgr.update("updatable", body="# New body")
        assert updated is not None
        assert updated.body == "# New body"

    def test_update_nonexistent(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        assert mgr.update("ghost", description="x") is None

    def test_delete(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        mgr.create("doomed", "To delete.", "# Doomed")
        assert mgr.delete("doomed") is True
        assert mgr.get("doomed") is None
        assert not (tmp_path / "doomed").exists()

    def test_delete_nonexistent(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        assert mgr.delete("ghost") is False

    def test_reload(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        mgr.create("reload-test", "Desc.", "# Body")
        mgr2 = SkillManager(str(tmp_path))
        assert mgr2.get("reload-test") is not None

    def test_create_with_emoji(self, tmp_path: Path):
        mgr = SkillManager(str(tmp_path))
        created = mgr.create("emoji-skill", "Has emoji.", "# Body", emoji="🎉")
        assert created is not None
        assert created.emoji == "🎉"


# ---------------------------------------------------------------------------
# skill execution tests
# ---------------------------------------------------------------------------


class TestSkillExecution:
    def test_extract_commands_bash(self):
        skill = Skill(
            name="test",
            description="",
            file_path="",
            body="# Test\n\n```bash\necho hello\necho world\n```\n",
        )
        cmds = SkillRouter.extract_commands(skill)
        assert cmds == ["echo hello", "echo world"]

    def test_extract_commands_shell(self):
        skill = Skill(
            name="test",
            description="",
            file_path="",
            body="# Test\n\n```shell\nls -la\n```\n",
        )
        cmds = SkillRouter.extract_commands(skill)
        assert cmds == ["ls -la"]

    def test_extract_commands_skips_non_shell(self):
        skill = Skill(
            name="test",
            description="",
            file_path="",
            body="# Test\n\n```python\nprint('hi')\n```\n",
        )
        cmds = SkillRouter.extract_commands(skill)
        assert cmds == []

    def test_extract_commands_skips_comments(self):
        skill = Skill(
            name="test",
            description="",
            file_path="",
            body="# Test\n\n```bash\n# comment\necho ok\n```\n",
        )
        cmds = SkillRouter.extract_commands(skill)
        assert cmds == ["echo ok"]

    def test_extract_commands_no_blocks(self):
        skill = Skill(
            name="test",
            description="",
            file_path="",
            body="# No code blocks here.",
        )
        cmds = SkillRouter.extract_commands(skill)
        assert cmds == []

    def test_extract_commands_skips_untagged(self):
        skill = Skill(
            name="test",
            description="",
            file_path="",
            body="# Test\n\n```\necho should-be-skipped\n```\n",
        )
        cmds = SkillRouter.extract_commands(skill)
        assert cmds == []

    def test_execute_skill_success(self, sample_skills: list[Skill], tmp_path: Path):
        skill = Skill(
            name="echo-test",
            description="Test.",
            file_path="",
            body="# Echo\n\n```bash\necho hello-world\n```\n",
        )
        router = SkillRouter([skill], workspace_dir=str(tmp_path), api_key="")
        result = router.execute_skill(skill)
        assert result.success
        assert "hello-world" in result.stdout
        assert result.command == "echo hello-world"

    def test_execute_skill_no_commands(self, tmp_path: Path):
        skill = Skill(
            name="empty", description="", file_path="", body="# No commands"
        )
        router = SkillRouter([skill], workspace_dir=str(tmp_path), api_key="")
        result = router.execute_skill(skill)
        assert not result.success
        assert "No executable commands" in result.stderr

    def test_execute_skill_index_out_of_range(self, tmp_path: Path):
        skill = Skill(
            name="one-cmd",
            description="",
            file_path="",
            body="```bash\necho ok\n```\n",
        )
        router = SkillRouter([skill], workspace_dir=str(tmp_path), api_key="")
        result = router.execute_skill(skill, command_index=5)
        assert not result.success
        assert "out of range" in result.stderr


# ---------------------------------------------------------------------------
# router management integration tests
# ---------------------------------------------------------------------------


class TestRouterManagement:
    def test_list_skills(self, sample_skills: list[Skill]):
        router = SkillRouter(sample_skills, api_key="")
        listing = router.list_skills()
        assert len(listing) == 3
        names = {s["name"] for s in listing}
        assert names == {"weather", "github", "coding"}

    def test_update_skill(self, sample_skills: list[Skill], tmp_path: Path):
        router = SkillRouter(sample_skills, workspace_dir=str(tmp_path), api_key="")
        # First create a skill that's managed on disk
        router._create_skill_from_args({
            "skill_name": "managed",
            "description": "Old.",
            "body": "# Old",
        })
        updated = router.update_skill("managed", description="New description.")
        assert updated is not None
        assert updated.description == "New description."
        # Verify prompt was rebuilt
        assert "New description." in router.system_prompt

    def test_delete_skill(self, sample_skills: list[Skill], tmp_path: Path):
        router = SkillRouter(sample_skills, workspace_dir=str(tmp_path), api_key="")
        router._create_skill_from_args({
            "skill_name": "temp",
            "description": "Temporary.",
            "body": "# Temp",
        })
        assert router.delete_skill("temp") is True
        assert router._find_skill_by_name("temp") is None
        assert "temp" not in router.system_prompt

    def test_handle_tool_call_update(self, sample_skills: list[Skill], tmp_path: Path):
        router = SkillRouter(sample_skills, workspace_dir=str(tmp_path), api_key="")
        router._create_skill_from_args({
            "skill_name": "editable",
            "description": "Before.",
            "body": "# Before",
        })
        result = router._handle_tool_call("update_skill", {
            "skill_name": "editable",
            "description": "After.",
            "response": "Updated!",
        })
        assert result.response == "Updated!"
        assert router._find_skill_by_name("editable").description == "After."

    def test_handle_tool_call_delete(self, sample_skills: list[Skill], tmp_path: Path):
        router = SkillRouter(sample_skills, workspace_dir=str(tmp_path), api_key="")
        router._create_skill_from_args({
            "skill_name": "deleteme",
            "description": "Bye.",
            "body": "# Bye",
        })
        result = router._handle_tool_call("delete_skill", {
            "skill_name": "deleteme",
            "response": "Deleted!",
        })
        assert result.response == "Deleted!"
        assert router._find_skill_by_name("deleteme") is None

    def test_handle_tool_call_list(self, sample_skills: list[Skill]):
        router = SkillRouter(sample_skills, api_key="")
        result = router._handle_tool_call("list_skills", {
            "response": "Here are the skills...",
        })
        assert "Here are the skills" in result.response

    def test_created_flag_set(self, sample_skills: list[Skill], tmp_path: Path):
        router = SkillRouter(sample_skills, workspace_dir=str(tmp_path), api_key="")
        result = router._handle_tool_call("create_skill", {
            "skill_name": "new-one",
            "description": "New.",
            "body": "# New",
            "response": "Created!",
        })
        assert result.created is True
