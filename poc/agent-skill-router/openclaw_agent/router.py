"""
Skill router — sends user input through the LLM with the skills-injected system prompt.

This is the core of the POC: it demonstrates how OpenClaw routes user messages
to the appropriate skill via the LLM's own reasoning.

Supports two modes:
1. **LLM mode** (default): uses OpenAI-compatible API to route via a real model
2. **Keyword mode** (fallback): simple keyword matching when no API key is available

Also provides skill management tools (list, update, delete) and skill execution
so the POC can handle the full skill lifecycle.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .skill_loader import Skill, _parse_skill
from .skill_manager import SkillManager
from .system_prompt import build_system_prompt

# Cache the OpenAI import so we don't retry on every call
_openai_class: type | None = None
_openai_checked = False


def _get_openai_client_class() -> type | None:
    """Return the OpenAI client class, or None if not installed."""
    global _openai_class, _openai_checked  # noqa: PLW0603
    if not _openai_checked:
        try:
            from openai import OpenAI  # type: ignore[import-untyped]

            _openai_class = OpenAI
        except ImportError:
            _openai_class = None
        _openai_checked = True
    return _openai_class


@dataclass
class RoutingResult:
    """Result of routing a user message through the agent."""

    selected_skill: Skill | None
    response: str
    all_skills: list[Skill] = field(default_factory=list)
    mode: str = "keyword"  # "llm" or "keyword"
    created: bool = False


@dataclass
class ExecutionResult:
    """Result of executing a skill's commands."""

    skill: Skill
    command: str
    stdout: str
    stderr: str
    returncode: int

    @property
    def success(self) -> bool:
        return self.returncode == 0


class SkillRouter:
    """Routes user input to skills via an LLM or keyword fallback.

    Mirrors the agent loop in OpenClaw's pi-embedded-runner:
    1. Build system prompt with skills catalog
    2. Send user message to the LLM
    3. LLM selects and follows the appropriate skill
    """

    def __init__(
        self,
        skills: list[Skill],
        *,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        workspace_dir: str = ".",
    ):
        self.skills = skills
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or "https://api.openai.com/v1"
        self.workspace_dir = workspace_dir
        self.manager = SkillManager(workspace_dir)
        self._system_prompt = build_system_prompt(
            skills, workspace_dir=workspace_dir,
        )

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, user_message: str) -> RoutingResult:
        """Route *user_message* to a skill. Uses LLM when available, else keywords."""
        if self.api_key:
            return self._route_via_llm(user_message)
        return self._route_via_keywords(user_message)

    # ------------------------------------------------------------------
    # LLM-based routing (primary path — mirrors OpenClaw's agent loop)
    # ------------------------------------------------------------------

    def _route_via_llm(self, user_message: str) -> RoutingResult:
        """Send the message to an OpenAI-compatible chat API."""
        OpenAI = _get_openai_client_class()
        if OpenAI is None:
            return self._route_via_keywords(user_message)

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_message},
        ]

        tools = self._build_llm_tools()

        completion = client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
        )

        choice = completion.choices[0]

        # Extract tool call result
        if choice.message.tool_calls:
            call = choice.message.tool_calls[0]
            try:
                args = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                args = {"skill_name": "", "response": choice.message.content or ""}

            return self._handle_tool_call(call.function.name, args)

        return RoutingResult(
            selected_skill=None,
            response=choice.message.content or "",
            all_skills=self.skills,
            mode="llm",
        )

    @staticmethod
    def _build_llm_tools() -> list[dict]:
        """Build the tool definitions sent to the LLM."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "select_skill",
                    "description": (
                        "Select the most appropriate skill for the user's request. "
                        "Return the skill name and a brief response."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "description": "Name of the selected skill, or empty string if none applies",
                            },
                            "response": {
                                "type": "string",
                                "description": "Your response to the user following the skill instructions",
                            },
                        },
                        "required": ["skill_name", "response"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_skill",
                    "description": (
                        "Create a new skill when none of the available skills fit the user's request."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "description": "Short skill name (letters, numbers, dashes).",
                            },
                            "description": {
                                "type": "string",
                                "description": "One-line description for the new skill.",
                            },
                            "body": {
                                "type": "string",
                                "description": "SKILL.md body content for the new skill.",
                            },
                            "response": {
                                "type": "string",
                                "description": "Response to send to the user after skill creation.",
                            },
                        },
                        "required": ["skill_name", "description", "body", "response"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_skill",
                    "description": "Update an existing skill's description or body content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "description": "Name of the skill to update.",
                            },
                            "description": {
                                "type": "string",
                                "description": "New description (omit to keep current).",
                            },
                            "body": {
                                "type": "string",
                                "description": "New SKILL.md body (omit to keep current).",
                            },
                            "response": {
                                "type": "string",
                                "description": "Response to send to the user.",
                            },
                        },
                        "required": ["skill_name", "response"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_skill",
                    "description": "Delete a skill that is no longer needed.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "description": "Name of the skill to delete.",
                            },
                            "response": {
                                "type": "string",
                                "description": "Response to send to the user.",
                            },
                        },
                        "required": ["skill_name", "response"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_skills",
                    "description": "List all available skills with their descriptions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "response": {
                                "type": "string",
                                "description": "Response listing the skills for the user.",
                            },
                        },
                        "required": ["response"],
                    },
                },
            },
        ]

    def _handle_tool_call(self, tool_name: str, args: dict) -> RoutingResult:
        """Dispatch a tool call from the LLM to the appropriate handler."""
        response_text = args.get("response", "")

        if tool_name == "create_skill":
            created = self._create_skill_from_args(args)
            if not response_text:
                if created:
                    response_text = f"[Skill: {created.name}] Created a new skill for this request."
                else:
                    response_text = "Couldn't create a new skill, so I'll continue without one."
            return RoutingResult(
                selected_skill=created,
                response=response_text,
                all_skills=self.skills,
                mode="llm",
                created=created is not None,
            )

        if tool_name == "update_skill":
            name = args.get("skill_name", "")
            updated = self.update_skill(
                name,
                description=args.get("description"),
                body=args.get("body"),
            )
            if not response_text:
                response_text = f"Updated skill '{name}'." if updated else f"Skill '{name}' not found."
            return RoutingResult(
                selected_skill=updated,
                response=response_text,
                all_skills=self.skills,
                mode="llm",
            )

        if tool_name == "delete_skill":
            name = args.get("skill_name", "")
            deleted = self.delete_skill(name)
            if not response_text:
                response_text = f"Deleted skill '{name}'." if deleted else f"Skill '{name}' not found."
            return RoutingResult(
                selected_skill=None,
                response=response_text,
                all_skills=self.skills,
                mode="llm",
            )

        if tool_name == "list_skills":
            if not response_text:
                names = ", ".join(s.name for s in self.skills) or "(none)"
                response_text = f"Available skills: {names}"
            return RoutingResult(
                selected_skill=None,
                response=response_text,
                all_skills=self.skills,
                mode="llm",
            )

        # Default: select_skill
        skill_name = args.get("skill_name", "")
        selected = self._find_skill_by_name(skill_name)
        return RoutingResult(
            selected_skill=selected,
            response=response_text,
            all_skills=self.skills,
            mode="llm",
        )

    # ------------------------------------------------------------------
    # Keyword-based routing (fallback when no API key is set)
    # ------------------------------------------------------------------

    def _route_via_keywords(self, user_message: str) -> RoutingResult:
        """Simple keyword matching as a zero-dependency fallback."""
        msg_lower = user_message.lower()
        best_skill: Skill | None = None
        best_score = 0

        for skill in self.skills:
            score = self._keyword_score(skill, msg_lower)
            if score > best_score:
                best_score = score
                best_skill = skill

        if best_skill:
            response = (
                f"[Skill: {best_skill.name}] "
                f"Matched skill '{best_skill.name}' — {best_skill.description}"
            )
        else:
            response = "No matching skill found. I'll try to help directly."

        return RoutingResult(
            selected_skill=best_skill,
            response=response,
            all_skills=self.skills,
            mode="keyword",
        )

    @staticmethod
    def _keyword_score(skill: Skill, message: str) -> int:
        """Score a skill against a message using simple keyword overlap."""
        score = 0
        # Exact skill name mention
        if skill.name.lower() in message:
            score += 10

        # Keywords from description
        desc_words = set(re.findall(r"[a-z]{3,}", skill.description.lower()))
        msg_words = set(re.findall(r"[a-z]{3,}", message))
        overlap = desc_words & msg_words
        score += len(overlap) * 2

        # Keywords from body
        body_words = set(re.findall(r"[a-z]{4,}", skill.body.lower()))
        body_overlap = body_words & msg_words
        score += len(body_overlap)

        return score

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_skill_by_name(self, name: str) -> Skill | None:
        if not name:
            return None
        name_lower = name.lower().strip()
        for skill in self.skills:
            if skill.name.lower() == name_lower:
                return skill
        return None

    def _create_skill_from_args(self, args: dict[str, str]) -> Skill | None:
        skill_name = str(args.get("skill_name", "")).strip().lower()
        if not re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", skill_name):
            return None

        description = str(args.get("description", "")).strip()
        body = str(args.get("body", "")).strip()
        if not description or not body:
            return None

        skill_dir = Path(self.workspace_dir) / skill_name
        if skill_dir.exists() and not skill_dir.is_dir():
            return None
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        if skill_path.exists():
            existing = self._find_skill_by_name(skill_name)
            if existing is not None:
                return existing
            parsed = _parse_skill(str(skill_path))
            if parsed is not None:
                self.skills.append(parsed)
                self._system_prompt = build_system_prompt(
                    self.skills, workspace_dir=self.workspace_dir,
                )
            return parsed

        skill_path.write_text(
            "\n".join([
                "---",
                f"name: {skill_name}",
                f'description: "{description}"',
                "---",
                "",
                body,
                "",
            ]),
            encoding="utf-8",
        )

        created = Skill(
            name=skill_name,
            description=description,
            file_path=str(skill_path),
            body=body,
        )
        self.skills.append(created)
        self.manager._skills[skill_name] = created
        self._system_prompt = build_system_prompt(
            self.skills, workspace_dir=self.workspace_dir,
        )
        return created

    # ------------------------------------------------------------------
    # Skill management (list, update, delete)
    # ------------------------------------------------------------------

    def list_skills(self) -> list[dict[str, str]]:
        """Return a summary of all loaded skills."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "emoji": s.emoji,
                "eligible": str(s.is_eligible()),
                "file_path": s.file_path,
            }
            for s in self.skills
        ]

    def update_skill(
        self,
        name: str,
        *,
        description: str | None = None,
        body: str | None = None,
        emoji: str | None = None,
    ) -> Skill | None:
        """Update an existing skill and rebuild the prompt."""
        updated = self.manager.update(name, description=description, body=body, emoji=emoji)
        if updated is None:
            return None
        # Sync the router's skills list
        for i, s in enumerate(self.skills):
            if s.name == name:
                self.skills[i] = updated
                break
        self._system_prompt = build_system_prompt(
            self.skills, workspace_dir=self.workspace_dir,
        )
        return updated

    def delete_skill(self, name: str) -> bool:
        """Delete a skill and rebuild the prompt."""
        if not self.manager.delete(name):
            return False
        self.skills = [s for s in self.skills if s.name != name]
        self._system_prompt = build_system_prompt(
            self.skills, workspace_dir=self.workspace_dir,
        )
        return True

    # ------------------------------------------------------------------
    # Skill execution
    # ------------------------------------------------------------------

    @staticmethod
    def extract_commands(skill: Skill) -> list[str]:
        """Extract shell commands from fenced code blocks in a skill body."""
        commands: list[str] = []
        in_block = False
        is_shell = False
        current: list[str] = []

        for line in skill.body.splitlines():
            stripped = line.strip()
            if stripped.startswith("```") and not in_block:
                lang = stripped[3:].strip().lower()
                is_shell = lang in ("bash", "sh", "shell", "zsh", "")
                in_block = True
                current = []
            elif stripped == "```" and in_block:
                if is_shell and current:
                    commands.extend(current)
                in_block = False
                is_shell = False
                current = []
            elif in_block and is_shell:
                # Skip comment-only lines
                if stripped and not stripped.startswith("#"):
                    current.append(line.rstrip())
        return commands

    def execute_skill(
        self,
        skill: Skill,
        *,
        command_index: int = 0,
        timeout: int = 30,
    ) -> ExecutionResult:
        """Execute a shell command from a skill's code blocks.

        Runs the command at *command_index* from the skill's extracted commands.
        """
        commands = self.extract_commands(skill)
        if not commands:
            return ExecutionResult(
                skill=skill,
                command="",
                stdout="",
                stderr="No executable commands found in skill body.",
                returncode=1,
            )
        if command_index >= len(commands):
            return ExecutionResult(
                skill=skill,
                command="",
                stdout="",
                stderr=f"Command index {command_index} out of range (skill has {len(commands)} commands).",
                returncode=1,
            )

        cmd = commands[command_index]
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.workspace_dir,
            )
            return ExecutionResult(
                skill=skill,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                skill=skill,
                command=cmd,
                stdout="",
                stderr=f"Command timed out after {timeout}s.",
                returncode=124,
            )
        except OSError as exc:
            return ExecutionResult(
                skill=skill,
                command=cmd,
                stdout="",
                stderr=str(exc),
                returncode=1,
            )
