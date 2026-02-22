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
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running from the poc directory without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from openclaw_agent import SkillRouter, load_skills


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
    print('Type a message (or "quit" to exit):')
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

        result = router.route(user_input)

        if result.selected_skill:
            emoji = f"{result.selected_skill.emoji} " if result.selected_skill.emoji else ""
            print(f"\n  Skill:  {emoji}{result.selected_skill.name}")
        else:
            print("\n  Skill:  (none)")
        print(f"  Mode:   {result.mode}")
        print(f"  Response: {result.response}")
        print()


if __name__ == "__main__":
    main()
