"""
System prompt builder — injects the skills catalog into the agent's system prompt.

Mirrors OpenClaw's prompt construction in src/agents/system-prompt.ts:
- buildAgentSystemPrompt: assembles identity, tooling, skills, workspace sections
- buildSkillsSection: formats the skills catalog with routing instructions
- formatSkillsForPrompt: renders each skill as a compact entry
"""

from __future__ import annotations

from .skill_loader import Skill


def format_skills_for_prompt(skills: list[Skill]) -> str:
    """Render the skills list as a compact prompt block (mirrors formatSkillsForPrompt)."""
    if not skills:
        return ""

    lines = ["<available_skills>"]
    for skill in skills:
        emoji_prefix = f"{skill.emoji} " if skill.emoji else ""
        lines.append(
            f"- {emoji_prefix}{skill.name}: {skill.description}"
        )
        lines.append(f"  location: {skill.file_path}")
    lines.append("</available_skills>")
    return "\n".join(lines)


def build_skills_section(skills: list[Skill]) -> str:
    """Build the Skills (mandatory) section (mirrors buildSkillsSection in system-prompt.ts)."""
    skills_block = format_skills_for_prompt(skills)
    if not skills_block:
        return ""

    return "\n".join([
        "## Skills (mandatory)",
        "Before replying: scan <available_skills> <description> entries.",
        "- If exactly one skill clearly applies: select it, read its SKILL.md, then follow it.",
        "- If multiple could apply: choose the most specific one, then read/follow it.",
        "- If none clearly apply: do not use any skill.",
        "Constraints: never read more than one skill up front; only read after selecting.",
        "",
        skills_block,
    ])


def build_system_prompt(
    skills: list[Skill],
    *,
    workspace_dir: str = ".",
    extra_context: str = "",
) -> str:
    """Assemble the full agent system prompt with skills injection.

    Mirrors buildAgentSystemPrompt in src/agents/system-prompt.ts.
    """
    skills_section = build_skills_section(skills)

    sections = [
        "You are a personal assistant running inside OpenClaw.",
        "",
        "## Tooling",
        "You have the following tools available:",
        "- read: Read file contents",
        "- write: Create or overwrite files",
        "- exec: Run shell commands",
        "- web_search: Search the web",
        "- web_fetch: Fetch content from a URL",
        "",
        "## Tool Call Style",
        "Default: do not narrate routine tool calls (just call the tool).",
        "Narrate only when it helps: multi-step work, complex problems, or when the user asks.",
        "",
    ]

    if skills_section:
        sections.append(skills_section)
        sections.append("")

    sections.extend([
        "## Workspace",
        f"Your working directory is: {workspace_dir}",
        "",
    ])

    if extra_context:
        sections.extend([
            "## Additional Context",
            extra_context,
            "",
        ])

    sections.extend([
        "## Response Guidelines",
        "- Be concise and helpful.",
        "- When a skill applies, follow its instructions.",
        "- When using a tool, report the result to the user.",
        (
            "- If you selected a skill, begin your response with "
            '"[Skill: <name>]" so the user can see which skill was activated.'
        ),
    ])

    return "\n".join(sections)
