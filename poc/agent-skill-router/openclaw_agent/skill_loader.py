"""
Skill loader — parses SKILL.md files (YAML frontmatter + Markdown body).

Mirrors OpenClaw's skill discovery in src/agents/skills/workspace.ts:
- loadSkillsFromDir: walks a directory for SKILL.md files
- parseFrontmatter: extracts YAML frontmatter from markdown
- shouldIncludeSkill: checks binary/env requirements
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SkillRequirements:
    """Binary and environment requirements for a skill."""

    bins: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)


@dataclass
class Skill:
    """A loaded skill entry (frontmatter metadata + markdown body)."""

    name: str
    description: str
    file_path: str
    body: str
    emoji: str = ""
    requires: SkillRequirements = field(default_factory=SkillRequirements)

    def is_eligible(self) -> bool:
        """Check whether the skill's requirements are satisfied on this system."""
        for binary in self.requires.bins:
            if shutil.which(binary) is None:
                return False
        for var in self.requires.env:
            if not os.environ.get(var):
                return False
        return True


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a SKILL.md file into YAML frontmatter dict and markdown body."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    frontmatter_str = text[3:end].strip()
    body = text[end + 4 :].strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_str) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, body


def _parse_skill(file_path: str) -> Skill | None:
    """Parse a single SKILL.md file into a Skill object."""
    try:
        text = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return None

    fm, body = _parse_frontmatter(text)
    name = fm.get("name", "")
    if not name:
        # Fall back to parent directory name
        name = Path(file_path).parent.name

    description = fm.get("description", "")
    emoji = fm.get("emoji", "")

    # Requirements can be nested under 'requires' or under 'metadata.openclaw.requires'
    requires_raw = fm.get("requires") or {}
    if not requires_raw and isinstance(fm.get("metadata"), dict):
        oc = fm["metadata"].get("openclaw", {})
        requires_raw = oc.get("requires", {})
        emoji = emoji or oc.get("emoji", "")

    reqs = SkillRequirements(
        bins=requires_raw.get("bins", []) or [],
        env=requires_raw.get("env", []) or [],
    )

    return Skill(
        name=name,
        description=description,
        file_path=file_path,
        body=body,
        emoji=emoji,
        requires=reqs,
    )


def load_skills_from_dir(directory: str) -> list[Skill]:
    """Walk *directory* for SKILL.md files and return parsed skills."""
    skills: list[Skill] = []
    root = Path(directory)
    if not root.is_dir():
        return skills

    for skill_md in sorted(root.rglob("SKILL.md")):
        skill = _parse_skill(str(skill_md))
        if skill is not None:
            skills.append(skill)
    return skills


def load_skills(
    *directories: str,
    check_eligible: bool = False,
) -> list[Skill]:
    """Load skills from one or more directories, optionally filtering by eligibility."""
    all_skills: list[Skill] = []
    for d in directories:
        all_skills.extend(load_skills_from_dir(d))

    if check_eligible:
        all_skills = [s for s in all_skills if s.is_eligible()]

    return all_skills
