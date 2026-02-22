---
name: github
description: "GitHub operations via gh CLI: issues, PRs, CI runs, code review, API queries. Use when checking PR status, creating issues, or viewing CI logs."
emoji: "🐙"
requires:
  bins:
    - gh
---

# GitHub Skill

Use the `gh` CLI to interact with GitHub repositories, issues, PRs, and CI.

## When to Use

- Checking PR status, reviews, or merge readiness
- Viewing CI/workflow run status and logs
- Creating, closing, or commenting on issues

## Commands

```bash
gh pr list --repo owner/repo
gh issue list --repo owner/repo --state open
gh run list --repo owner/repo --limit 10
```
