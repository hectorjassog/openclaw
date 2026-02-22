"""
OpenClaw Agent Skill Router — Python Proof of Concept

Mirrors OpenClaw's agent architecture:
  User input → System prompt (with skills catalog) → LLM → Skill selection → Execution

This POC demonstrates the core routing loop:
1. Load SKILL.md files from a skills directory (frontmatter + body)
2. Build a system prompt that injects the skills catalog
3. Send user input to an LLM that selects and follows the appropriate skill
4. Return the selected skill and the LLM's response
"""

from .skill_loader import load_skills, load_skills_from_dir, Skill
from .system_prompt import build_system_prompt
from .router import SkillRouter

__all__ = [
    "load_skills",
    "load_skills_from_dir",
    "Skill",
    "build_system_prompt",
    "SkillRouter",
]
