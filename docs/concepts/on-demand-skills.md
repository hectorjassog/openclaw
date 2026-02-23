---
title: "On-Demand Skill Creation"
summary: "How OpenClaw identifies unmet needs and creates skills on demand"
---

# On-Demand Skill Creation

OpenClaw can **detect when no existing skill matches a user request** and
**create a new skill on the fly**. The newly created skill is immediately
available for the current session and all future sessions. This page explains
every component of that system.

## High-Level Flow

```
User message
    │
    ▼
┌──────────────────────────────┐
│  System prompt with skills   │  ← skill catalog injected
│  catalog + routing rules     │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  LLM reasoning               │
│  "Does any skill apply?"     │
└──────────┬───────────────────┘
           │
     ┌─────┴─────┐
     │            │
  match?       no match?
     │            │
     ▼            ▼
select_skill   create_skill
     │            │
     │      ┌─────┴──────────────────┐
     │      │ 1. Validate name       │
     │      │ 2. Write SKILL.md      │
     │      │ 3. Parse into Skill    │
     │      │ 4. Add to registry     │
     │      │ 5. Rebuild prompt      │
     │      └─────┬──────────────────┘
     │            │
     ▼            ▼
  RoutingResult (skill + response)
```

## Components

### 1. Skill Discovery and Loading

Skills are Markdown files with YAML frontmatter that describe a capability.
OpenClaw loads them from multiple directories with a defined precedence order.

**File format** (`SKILL.md`):

```markdown
---
name: weather
description: "Get current weather and forecasts for any location."
emoji: "🌤️"
requires:
  bins:
    - curl
---

# Weather Skill

Instructions the agent follows when this skill activates...
```

**Loading sources** (lowest → highest precedence):

1. Extra directories (`skills.load.extraDirs`)
2. Plugin skills
3. Bundled skills (shipped with the install)
4. Managed skills (`~/.openclaw/skills`)
5. Agent personal skills (`~/.agents/skills`)
6. Agent project skills (`<workspace>/.agents/skills`)
7. Workspace skills (`<workspace>/skills`) — **highest**

**Eligibility filtering** happens at load time. A skill is eligible when:

- Required binaries exist on `PATH` (`requires.bins`)
- At least one binary from `requires.anyBins` exists
- Required environment variables are set (`requires.env`)
- Required config paths are truthy (`requires.config`)
- OS matches (`os` list, if specified)

See [Skills](/tools/skills) and [Skills Config](/tools/skills-config) for
the full configuration reference.

### 2. System Prompt Construction

Once skills are loaded and filtered, OpenClaw injects a compact catalog into
the agent system prompt. This is the mechanism that enables on-demand creation:
the LLM sees the skill list and the routing rules, and decides whether to
select an existing skill or create a new one.

**Prompt structure:**

```
You are a personal assistant running inside OpenClaw.

## Tooling
[available tools: read, write, exec, web_search, web_fetch]

## Skills (mandatory)
Before replying: scan <available_skills> <description> entries.
- If exactly one skill clearly applies: select it, read its SKILL.md, follow it.
- If multiple could apply: choose the most specific one, then read/follow it.
- If none clearly apply but the request is specific and actionable: create a new skill.
- If none clearly apply and the request is vague/general: do not use any skill.

<available_skills>
- 🌤️ weather: Get current weather and forecasts...
  location: ~/skills/weather/SKILL.md
- 🐙 github: GitHub operations via gh CLI...
  location: ~/skills/github/SKILL.md
</available_skills>

## Workspace
Your working directory is: /home/user/project
```

**Key design principles:**

- **Progressive disclosure**: only skill names and descriptions are in the
  prompt. The full SKILL.md body is loaded only after the LLM selects a skill.
  This keeps the context window efficient.
- **Routing rules are mandatory**: the `## Skills (mandatory)` heading tells
  the model it must evaluate the skills list before responding.
- **Creation trigger**: the rule "if none clearly apply but the request is
  specific and actionable: create a new skill" is what enables on-demand
  creation.

### 3. Tool Definitions

The LLM is given two tools via function calling:

**`select_skill`** — pick an existing skill:

```json
{
  "name": "select_skill",
  "parameters": {
    "skill_name": "Name of the selected skill (or empty if none)",
    "response": "Response to the user following skill instructions"
  }
}
```

**`create_skill`** — create a brand new skill:

```json
{
  "name": "create_skill",
  "parameters": {
    "skill_name": "short-hyphenated-name",
    "description": "One-line description of what the skill does",
    "body": "Full SKILL.md body (Markdown instructions)",
    "response": "Response to the user after creation"
  }
}
```

When the LLM determines no existing skill fits but the request is actionable,
it calls `create_skill` instead of `select_skill`. The agent loop intercepts
this tool call and executes the creation flow.

### 4. Skill Creation Flow

When the agent calls `create_skill`, the following steps execute:

1. **Validate the name**: must match `[a-z0-9]([a-z0-9-]*[a-z0-9])?` (lowercase
   alphanumeric with hyphens, no leading/trailing hyphens).
2. **Create the directory**: `<workspace>/skills/<skill_name>/`.
3. **Write `SKILL.md`**: YAML frontmatter (name + description) + Markdown body.
4. **Parse into a Skill object**: the file is immediately parsed back into the
   in-memory skill registry.
5. **Update the skill list**: the new skill is appended to the router's skills
   array.
6. **Rebuild the system prompt**: the prompt is regenerated to include the new
   skill so that subsequent turns can select it.
7. **Return the skill**: the created skill and the LLM's response are returned
   to the user.

**Idempotency**: if a skill directory already exists, the system loads the
existing skill instead of overwriting it.

### 5. Skill Registry (In-Memory)

The skill registry is the in-memory list of `Skill` objects that the router
maintains. It is:

- **Initialized** when the router starts (from disk).
- **Appended to** when `create_skill` executes.
- **Used to rebuild** the system prompt after every creation.
- **Persisted** via the filesystem (the `SKILL.md` file on disk).

This means created skills survive across sessions because they exist as files.
The next time the agent starts, it discovers them during the normal skill
loading pass.

### 6. Keyword Fallback (No LLM)

When no LLM API key is available, the router falls back to keyword-based
scoring:

1. Exact skill name mention in the message → +10 points.
2. Keyword overlap with the skill description → +2 points per word.
3. Keyword overlap with the skill body → +1 point per word.
4. The highest-scoring skill is selected.

This mode does **not** support on-demand creation (it requires LLM reasoning
to decide when a new skill is needed). It is useful for testing and
environments without API access.

## Architecture Mapping

The on-demand creation system is implemented differently in the production
TypeScript codebase and the Python proof-of-concept, but the architecture is
the same:

| Component | Production (TypeScript) | POC (Python) |
|---|---|---|
| Skill parsing | `src/agents/skills/frontmatter.ts` | `skill_loader._parse_frontmatter()` |
| Skill loading | `src/agents/skills/workspace.ts` | `skill_loader.load_skills()` |
| Eligibility | `src/agents/skills/config.ts` | `Skill.is_eligible()` |
| Prompt building | `src/agents/system-prompt.ts` | `system_prompt.build_system_prompt()` |
| Agent loop | `src/agents/pi-embedded-runner/` | `router.SkillRouter` |
| Skill catalog | `formatSkillsForPrompt()` | `format_skills_for_prompt()` |
| On-demand creation | Planned | `router._create_skill_from_args()` |

## Skill Lifecycle

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Discovery   │ ──► │  Eligibility  │ ──► │   Prompt     │
│  (load from  │     │  (check bins, │     │ (inject into │
│   disk)      │     │   env, OS)    │     │  system msg) │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                │
                              ┌─────────────────┴────────┐
                              │                          │
                         select_skill              create_skill
                              │                          │
                              ▼                          ▼
                    ┌──────────────┐        ┌──────────────────┐
                    │ Follow skill │        │ Write SKILL.md   │
                    │ instructions │        │ Update registry   │
                    └──────────────┘        │ Rebuild prompt   │
                                            └────────┬─────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │  Persisted on    │
                                            │  disk for future │
                                            │  sessions        │
                                            └──────────────────┘
```

## Security Considerations

- **Name validation**: skill names are strictly validated to prevent path
  traversal attacks (e.g., `../bad` is rejected).
- **No symlinks**: the skill loader rejects symlinks (production only).
- **Treat created skills as untrusted**: review auto-generated SKILL.md files
  before relying on them in sensitive environments.
- **Sandboxing**: created skills follow the same sandbox rules as any other
  skill. See [Sandboxing](/gateway/sandboxing).

## Related Documentation

- [Skills](/tools/skills) — full skills reference (locations, gating, config)
- [Skills Config](/tools/skills-config) — configuration schema
- [Creating Skills](/tools/creating-skills) — manual skill creation guide
- [System Prompt](/concepts/system-prompt) — how the system prompt is built
- [Agent Loop](/concepts/agent-loop) — the agent reasoning cycle
