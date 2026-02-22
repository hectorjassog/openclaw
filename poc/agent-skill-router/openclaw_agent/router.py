"""
Skill router — sends user input through the LLM with the skills-injected system prompt.

This is the core of the POC: it demonstrates how OpenClaw routes user messages
to the appropriate skill via the LLM's own reasoning.

Supports two modes:
1. **LLM mode** (default): uses OpenAI-compatible API to route via a real model
2. **Keyword mode** (fallback): simple keyword matching when no API key is available
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .skill_loader import Skill
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

        # Ask the model to return structured JSON with the skill selection
        tool_def = {
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
        }

        completion = client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=[tool_def],
            tool_choice={"type": "function", "function": {"name": "select_skill"}},
        )

        choice = completion.choices[0]

        # Extract tool call result
        if choice.message.tool_calls:
            call = choice.message.tool_calls[0]
            try:
                args = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                args = {"skill_name": "", "response": choice.message.content or ""}

            skill_name = args.get("skill_name", "")
            response_text = args.get("response", "")
        else:
            skill_name = ""
            response_text = choice.message.content or ""

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
