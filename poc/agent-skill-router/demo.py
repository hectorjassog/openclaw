#!/usr/bin/env python3
"""
Interactive demo of the OpenClaw agent skill router.

Usage:
    python demo.py                          # keyword mode (no API key needed)
    OPENAI_API_KEY=sk-... python demo.py    # LLM mode (uses OpenAI API)
    python demo.py --skills-dir ./skills    # custom skills directory
    python demo.py --show-prompt            # print the system prompt and exit

Also loads OpenClaw's bundled skills from ../../skills/ when present,
so you can see the full catalog in action.

Management commands (available in the interactive loop):
    /skills              — list all loaded skills
    /info <name>         — show details of a skill
    /create              — interactively create a new skill
    /update <name>       — update a skill's description or body
    /delete <name>       — delete a skill
    /exec <name> [n]     — execute command n (default 0) from a skill
    /prompt              — print the current system prompt
    /reload              — reload skills from disk
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running from the poc directory without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from openclaw_agent import SkillRouter, load_skills


def _print_skill_table(router: SkillRouter) -> None:
    """Print a compact table of all loaded skills."""
    skills = router.list_skills()
    if not skills:
        print("  (no skills loaded)")
        return
    for s in skills:
        emoji = f"{s['emoji']} " if s['emoji'] else "  "
        eligible = "✓" if s["eligible"] == "True" else "✗"
        print(f"  {emoji}{s['name']:20s} [{eligible}] {s['description'][:60]}")


def _handle_command(cmd: str, router: SkillRouter) -> bool:
    """Handle a slash command. Returns True if handled."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if command == "/skills":
        print("\nLoaded skills:")
        _print_skill_table(router)
        print()
        return True

    if command == "/info":
        if not rest:
            print("  Usage: /info <skill-name>\n")
            return True
        skill = router._find_skill_by_name(rest)
        if not skill:
            print(f"  Skill '{rest}' not found.\n")
            return True
        emoji = f" {skill.emoji}" if skill.emoji else ""
        print(f"\n  {skill.name}{emoji}")
        print(f"  Description: {skill.description}")
        print(f"  File: {skill.file_path}")
        print(f"  Eligible: {skill.is_eligible()}")
        cmds = SkillRouter.extract_commands(skill)
        if cmds:
            print(f"  Commands ({len(cmds)}):")
            for i, c in enumerate(cmds):
                print(f"    [{i}] {c}")
        print(f"\n  --- Body ---\n{skill.body}\n  --- End ---\n")
        return True

    if command == "/create":
        name = input("  Skill name: ").strip().lower()
        desc = input("  Description: ").strip()
        emoji = input("  Emoji (optional): ").strip()
        print("  Body (end with a blank line):")
        body_lines: list[str] = []
        while True:
            line = input("  ")
            if not line:
                break
            body_lines.append(line)
        body = "\n".join(body_lines)
        created = router._create_skill_from_args({
            "skill_name": name,
            "description": desc,
            "body": body,
        })
        if created:
            print(f"\n  ✓ Created skill '{created.name}'\n")
        else:
            print("\n  ✗ Failed to create skill (invalid name or already exists)\n")
        return True

    if command == "/update":
        if not rest:
            print("  Usage: /update <skill-name>\n")
            return True
        skill = router._find_skill_by_name(rest)
        if not skill:
            print(f"  Skill '{rest}' not found.\n")
            return True
        print(f"  Updating '{skill.name}' (press Enter to keep current value)")
        new_desc = input(f"  Description [{skill.description[:50]}]: ").strip() or None
        new_body = None
        change_body = input("  Change body? (y/N): ").strip().lower()
        if change_body == "y":
            print("  New body (end with a blank line):")
            body_lines = []
            while True:
                line = input("  ")
                if not line:
                    break
                body_lines.append(line)
            new_body = "\n".join(body_lines)
        updated = router.update_skill(rest, description=new_desc, body=new_body)
        if updated:
            print(f"\n  ✓ Updated skill '{updated.name}'\n")
        else:
            print("\n  ✗ Failed to update skill\n")
        return True

    if command == "/delete":
        if not rest:
            print("  Usage: /delete <skill-name>\n")
            return True
        confirm = input(f"  Delete skill '{rest}'? (y/N): ").strip().lower()
        if confirm == "y":
            deleted = router.delete_skill(rest)
            print(f"\n  {'✓ Deleted' if deleted else '✗ Not found'} skill '{rest}'\n")
        else:
            print("  Cancelled.\n")
        return True

    if command == "/exec":
        exec_parts = rest.split(maxsplit=1)
        if not exec_parts:
            print("  Usage: /exec <skill-name> [command-index]\n")
            return True
        skill_name = exec_parts[0]
        cmd_idx = int(exec_parts[1]) if len(exec_parts) > 1 else 0
        skill = router._find_skill_by_name(skill_name)
        if not skill:
            print(f"  Skill '{skill_name}' not found.\n")
            return True
        print(f"  Executing command [{cmd_idx}] from skill '{skill_name}'...")
        result = router.execute_skill(skill, command_index=cmd_idx)
        if result.success:
            print(f"  ✓ Command: {result.command}")
            if result.stdout:
                print(f"  Output:\n{result.stdout}")
        else:
            print(f"  ✗ Command: {result.command}")
            if result.stderr:
                print(f"  Error: {result.stderr}")
        print()
        return True

    if command == "/prompt":
        print(f"\n{router.system_prompt}\n")
        return True

    if command == "/reload":
        router.manager.reload()
        router.skills = router.manager.skills
        router._system_prompt = router.system_prompt  # rebuild
        print(f"  Reloaded {len(router.skills)} skills.\n")
        return True

    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenClaw Agent Skill Router — Python POC",
    )
    parser.add_argument(
        "--skills-dir",
        default=os.path.join(os.path.dirname(__file__), "skills"),
        help="Path to directory containing SKILL.md files (default: ./skills)",
    )
    parser.add_argument(
        "--bundled-skills",
        default=os.path.join(os.path.dirname(__file__), "..", "..", "skills"),
        help="Path to OpenClaw's bundled skills directory",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Model name for LLM routing (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the system prompt and exit",
    )
    parser.add_argument(
        "--check-eligible",
        action="store_true",
        help="Only include skills whose requirements are satisfied",
    )
    args = parser.parse_args()

    # Load skills from the POC skills dir + optionally the bundled OpenClaw skills
    dirs = [args.skills_dir]
    bundled = os.path.normpath(args.bundled_skills)
    if os.path.isdir(bundled) and bundled != os.path.normpath(args.skills_dir):
        dirs.append(bundled)

    skills = load_skills(*dirs, check_eligible=args.check_eligible)

    if not skills:
        print("No skills found. Check --skills-dir path.", file=sys.stderr)
        sys.exit(1)

    router = SkillRouter(skills, model=args.model, workspace_dir=args.skills_dir)

    # Show prompt mode
    if args.show_prompt:
        print(router.system_prompt)
        return

    # Print header
    mode = "LLM" if router.api_key else "keyword"
    print(f"OpenClaw Agent Skill Router (Python POC)")
    print(f"  Mode:   {mode}" + (f" ({args.model})" if mode == "LLM" else ""))
    print(f"  Skills: {len(skills)} loaded")
    for skill in skills:
        emoji = f"{skill.emoji} " if skill.emoji else ""
        desc = skill.description[:70] + ("..." if len(skill.description) > 70 else "")
        print(f"    - {emoji}{skill.name}: {desc}")
    print()
    print('Type a message (or "quit" to exit). Use /skills, /create, /exec, /info, etc.')
    print()

    # Interactive loop
    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        # Handle management commands
        if user_input.startswith("/"):
            if _handle_command(user_input, router):
                continue

        result = router.route(user_input)

        if result.selected_skill:
            emoji = f"{result.selected_skill.emoji} " if result.selected_skill.emoji else ""
            print(f"\n  Skill:  {emoji}{result.selected_skill.name}")
            if result.created:
                print(f"  Action: created new skill")
        else:
            print("\n  Skill:  (none)")
        print(f"  Mode:   {result.mode}")
        print(f"  Response: {result.response}")
        print()


if __name__ == "__main__":
    main()
