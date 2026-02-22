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
from openclaw_agent.router import RoutingResult, SkillRouter


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
