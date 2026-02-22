# OpenClaw Agent Skill Router — Python POC

A proof-of-concept implementation of OpenClaw's agent skill routing system in Python.

This POC demonstrates how OpenClaw takes user input and translates it into a skill (or set of skills) by mirroring the real architecture:

1. **Skill Discovery** — Load `SKILL.md` files (YAML frontmatter + Markdown body) from a skills directory
2. **Eligibility Filtering** — Check binary/env requirements before including a skill
3. **System Prompt Construction** — Inject the skills catalog into the LLM's system prompt
4. **LLM-based Routing** — The model reads the skills list and selects the best match
5. **On-Demand Skill Creation** — When no skill matches, the LLM creates a new one on the fly
6. **Skill Management** — List, update, and delete skills through LLM tools or CLI commands
7. **Skill Execution** — Run shell commands extracted from skill code blocks
8. **Keyword Fallback** — Simple keyword scoring when no LLM API key is available

## How It Maps to OpenClaw

| Python POC | OpenClaw (TypeScript) | Purpose |
|---|---|---|
| `skill_loader.py` | `src/agents/skills/workspace.ts` | Discover and parse SKILL.md files |
| `skill_loader._parse_frontmatter()` | `src/agents/skills/frontmatter.ts` | Extract YAML metadata from markdown |
| `skill_loader.Skill.is_eligible()` | `src/agents/skills/config.ts` → `shouldIncludeSkill()` | Check binary/env requirements |
| `skill_manager.py` | `src/agents/skills/workspace.ts` (CRUD) | Create, update, delete skills |
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

## Interactive Commands

When running the demo interactively, these slash commands are available:

| Command | Description |
|---|---|
| `/skills` | List all loaded skills with eligibility status |
| `/info <name>` | Show full details of a skill (body, commands, file path) |
| `/create` | Interactively create a new skill |
| `/update <name>` | Update a skill's description or body |
| `/delete <name>` | Delete a skill from disk |
| `/exec <name> [n]` | Execute command `n` (default: 0) from a skill's code blocks |
| `/prompt` | Print the current system prompt |
| `/reload` | Reload skills from disk |

## Example Session

```
OpenClaw Agent Skill Router (Python POC)
  Mode:   keyword
  Skills: 4 loaded
    - 🌤️ weather: Get current weather and forecasts...
    - 🐙 github: GitHub operations via gh CLI...
    - 🧾 summarize: Summarize or extract text from URLs...
    - 💻 coding: Code editing, refactoring, debugging...

Type a message (or "quit" to exit). Use /skills, /create, /exec, /info, etc.

You> What's the weather in Tokyo?

  Skill:  🌤️ weather
  Mode:   keyword
  Response: [Skill: weather] Matched skill 'weather' — Get current weather...

You> /skills

Loaded skills:
  🌤️ weather              [✓] Get current weather and forecasts...
  🐙 github               [✗] GitHub operations via gh CLI...
  🧾 summarize            [✗] Summarize or extract text from URLs...
  💻 coding               [✓] Code editing, refactoring, debugging...

You> /exec weather 0
  Executing command [0] from skill 'weather'...
  ✓ Command: curl "wttr.in/London?format=3"
  Output:
  London: ⛅️ +12°C
```

## On-Demand Skill Creation

When no existing skill matches a request, the LLM can create a new skill:

1. The LLM calls the `create_skill` tool with a name, description, and body
2. The router validates the name, writes a `SKILL.md` to disk, and adds it to the registry
3. The system prompt is rebuilt to include the new skill
4. The new skill is immediately usable in subsequent turns

This flow is also available via the `/create` interactive command.

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
       │              │  LLM (GPT)   │ ──► Tool calls:
       │              └──────┬───────┘     - select_skill
       │                     │             - create_skill
       │                     │             - update_skill
       │                     │             - delete_skill
       │                     │             - list_skills
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

## Commands

```bash
curl "wttr.in/London?format=3"
```
```

## Running Tests

```bash
pip install -r requirements.txt
python -m pytest test_agent.py -v
```

## Documentation

For a detailed explanation of how the on-demand skill creation system works, see
[On-Demand Skill Creation](../../docs/concepts/on-demand-skills.md).
