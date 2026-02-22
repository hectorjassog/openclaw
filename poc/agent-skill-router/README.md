# OpenClaw Agent Skill Router — Python POC

A proof-of-concept implementation of OpenClaw's agent skill routing system in Python.

This POC demonstrates how OpenClaw takes user input and translates it into a skill (or set of skills) by mirroring the real architecture:

1. **Skill Discovery** — Load `SKILL.md` files (YAML frontmatter + Markdown body) from a skills directory
2. **Eligibility Filtering** — Check binary/env requirements before including a skill
3. **System Prompt Construction** — Inject the skills catalog into the LLM's system prompt
4. **LLM-based Routing** — The model reads the skills list and selects the best match
5. **Keyword Fallback** — Simple keyword scoring when no LLM API key is available

## How It Maps to OpenClaw

| Python POC | OpenClaw (TypeScript) | Purpose |
|---|---|---|
| `skill_loader.py` | `src/agents/skills/workspace.ts` | Discover and parse SKILL.md files |
| `skill_loader._parse_frontmatter()` | `src/agents/skills/frontmatter.ts` | Extract YAML metadata from markdown |
| `skill_loader.Skill.is_eligible()` | `src/agents/skills/config.ts` → `shouldIncludeSkill()` | Check binary/env requirements |
| `system_prompt.py` | `src/agents/system-prompt.ts` | Build the full system prompt |
| `system_prompt.format_skills_for_prompt()` | `formatSkillsForPrompt()` (pi-coding-agent) | Render skills as a prompt block |
| `system_prompt.build_skills_section()` | `buildSkillsSection()` | Add routing instructions for the LLM |
| `router.py` → `SkillRouter` | `src/agents/pi-embedded-runner/` | The agent loop: prompt + LLM + tool calls |

## Quick Start

```bash
cd poc/agent-skill-router

# Install dependencies
pip install -r requirements.txt

# Run with keyword fallback (no API key needed)
python demo.py

# Run with LLM routing
OPENAI_API_KEY=sk-... python demo.py

# Show the generated system prompt
python demo.py --show-prompt

# Load OpenClaw's bundled skills too
python demo.py --bundled-skills ../../skills
```

## Example Session

```
OpenClaw Agent Skill Router (Python POC)
  Mode:   keyword
  Skills: 4 loaded
    - 🌤️ weather: Get current weather and forecasts...
    - 🐙 github: GitHub operations via gh CLI...
    - 🧾 summarize: Summarize or extract text from URLs...
    - 💻 coding: Code editing, refactoring, debugging...

Type a message (or "quit" to exit):

You> What's the weather in Tokyo?

  Skill:  🌤️ weather
  Mode:   keyword
  Response: [Skill: weather] Matched skill 'weather' — Get current weather...

You> Open a PR for the login fix

  Skill:  🐙 github
  Mode:   keyword
  Response: [Skill: github] Matched skill 'github' — GitHub operations via gh CLI...
```

## Architecture

```
User Message
     │
     ▼
┌─────────────┐
│ SkillRouter │
│  .route()   │
└──────┬──────┘
       │
       ├── Has API key? ──► LLM Mode
       │                     │
       │                     ▼
       │              ┌──────────────┐
       │              │ System Prompt│ ◄── Skills catalog injected
       │              │  + User Msg  │
       │              └──────┬───────┘
       │                     │
       │                     ▼
       │              ┌──────────────┐
       │              │  LLM (GPT)   │ ──► select_skill tool call
       │              └──────┬───────┘
       │                     │
       │                     ▼
       │              RoutingResult(skill, response)
       │
       └── No API key? ──► Keyword Mode
                            │
                            ▼
                     Score each skill by
                     keyword overlap with
                     the user message
                            │
                            ▼
                     RoutingResult(skill, response)
```

## SKILL.md Format

Skills are defined as Markdown files with YAML frontmatter:

```markdown
---
name: weather
description: "Get current weather and forecasts..."
emoji: "🌤️"
requires:
  bins:
    - curl
---

# Weather Skill

Instructions for the agent to follow when this skill is activated...
```

## Running Tests

```bash
pip install -r requirements.txt
python -m pytest test_agent.py -v
```
