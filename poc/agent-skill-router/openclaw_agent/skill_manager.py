"""
Skill manager — CRUD operations for skills (list, get, update, delete).

Provides a higher-level management API on top of the skill loader,
enabling the POC to fully handle skill lifecycle operations.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .skill_loader import Skill, _parse_skill, load_skills_from_dir


class SkillManager:
    """Manage skills in a workspace directory (create, read, update, delete)."""

    def __init__(self, workspace_dir: str) -> None:
        self.workspace_dir = workspace_dir
        self._skills: dict[str, Skill] = {}
        self.reload()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Re-scan the workspace directory and rebuild the in-memory registry."""
        self._skills.clear()
        for skill in load_skills_from_dir(self.workspace_dir):
            self._skills[skill.name] = skill

    @property
    def skills(self) -> list[Skill]:
        """Return all loaded skills as a list."""
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        """Look up a skill by name."""
        return self._skills.get(name)

    def list_names(self) -> list[str]:
        """Return sorted skill names."""
        return sorted(self._skills.keys())

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    _NAME_RE = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?")

    def create(
        self,
        name: str,
        description: str,
        body: str,
        *,
        emoji: str = "",
    ) -> Skill | None:
        """Create a new skill and persist it to disk.

        Returns the created Skill, or None if the name is invalid or the
        skill already exists.
        """
        name = name.strip().lower()
        if not self._NAME_RE.fullmatch(name):
            return None
        if name in self._skills:
            return None

        skill_dir = Path(self.workspace_dir) / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"

        frontmatter_lines = [
            "---",
            f"name: {name}",
            f'description: "{description}"',
        ]
        if emoji:
            frontmatter_lines.append(f'emoji: "{emoji}"')
        frontmatter_lines.append("---")

        content = "\n".join([*frontmatter_lines, "", body, ""])
        skill_path.write_text(content, encoding="utf-8")

        parsed = _parse_skill(str(skill_path))
        if parsed is None:
            return None
        self._skills[parsed.name] = parsed
        return parsed

    def update(
        self,
        name: str,
        *,
        description: str | None = None,
        body: str | None = None,
        emoji: str | None = None,
    ) -> Skill | None:
        """Update an existing skill on disk and in the registry.

        Only provided fields are changed. Returns the updated Skill, or None
        if the skill does not exist.
        """
        existing = self._skills.get(name)
        if existing is None:
            return None

        new_desc = description if description is not None else existing.description
        new_body = body if body is not None else existing.body
        new_emoji = emoji if emoji is not None else existing.emoji

        skill_path = Path(existing.file_path)
        frontmatter_lines = [
            "---",
            f"name: {name}",
            f'description: "{new_desc}"',
        ]
        if new_emoji:
            frontmatter_lines.append(f'emoji: "{new_emoji}"')
        frontmatter_lines.append("---")

        content = "\n".join([*frontmatter_lines, "", new_body, ""])
        skill_path.write_text(content, encoding="utf-8")

        parsed = _parse_skill(str(skill_path))
        if parsed is None:
            return None
        self._skills[name] = parsed
        return parsed

    def delete(self, name: str) -> bool:
        """Delete a skill from disk and the registry.

        Returns True if the skill was deleted, False if it did not exist.
        """
        existing = self._skills.get(name)
        if existing is None:
            return False

        skill_dir = Path(existing.file_path).parent
        if skill_dir.is_dir():
            shutil.rmtree(skill_dir)

        del self._skills[name]
        return True
