"""
OpenClaw Agent Skill Router — Python Proof of Concept

Mirrors OpenClaw's agent architecture:
  User input → System prompt (with skills catalog) → LLM → Skill selection → Execution

This POC demonstrates the core routing loop:
1. Load SKILL.md files from a skills directory (frontmatter + body)
2. Build a system prompt that injects the skills catalog
3. Send user input to an LLM that selects and follows the appropriate skill
4. Create new skills on demand when no existing skill matches
5. Manage skills (list, update, delete) and execute them
"""

from .skill_loader import load_skills, load_skills_from_dir, Skill
from .skill_manager import SkillManager
from .system_prompt import build_system_prompt
from .router import SkillRouter, ExecutionResult

__all__ = [
    "load_skills",
    "load_skills_from_dir",
    "Skill",
    "SkillManager",
    "build_system_prompt",
    "SkillRouter",
    "ExecutionResult",
]
