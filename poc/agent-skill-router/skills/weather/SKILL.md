---
name: weather
description: "Get current weather and forecasts. Use when: user asks about weather, temperature, or forecasts for any location."
emoji: "🌤️"
requires:
  bins:
    - curl
---

# Weather Skill

Get current weather conditions and forecasts via wttr.in.

## When to Use

- "What's the weather?"
- "Will it rain today/tomorrow?"
- "Temperature in [city]"

## Commands

```bash
curl "wttr.in/London?format=3"
curl "wttr.in/London?0"
```
