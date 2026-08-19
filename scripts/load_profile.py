"""
load_profile.py

Purpose: load master_profile.json, check it's filled in properly, and print
a quick summary. This is intentionally simple - it's step 1 of the job
search agent, and doubles as a refresher on core Python.

Concepts touched on (comments below point out where):
  - opening/reading files
  - the json module (parsing JSON into Python dicts/lists)
  - functions and return values
  - exception handling (try/except)
  - list comprehensions
  - f-strings

Run it with:
    python scripts/load_profile.py
"""

import json
import sys
from pathlib import Path


def load_profile(path: str) -> dict:
    """
    Read a JSON file from disk and return it as a Python dict.

    Path objects and open() are the standard way to do file I/O in Python.
    json.load() parses a file directly; json.loads() would parse a string.
    """
    file_path = Path(path)

    if not file_path.exists():
        # Raising a clear, specific exception is better than letting Python
        # throw a generic FileNotFoundError with a less helpful message.
        raise FileNotFoundError(
            f"No profile found at '{path}'. "
            "Copy master_profile.template.json to master_profile.json and fill it in first."
        )

    with open(file_path, "r", encoding="utf-8") as f:
        # 'with' automatically closes the file when the block ends,
        # even if an error happens inside it.
        data = json.load(f)

    return data


def find_unfilled_fields(profile: dict) -> list[str]:
    """
    Walk the profile and flag any values that still contain the literal
    string 'REPLACE' - meaning the template placeholder wasn't filled in.

    This is a simple recursive function: it calls itself on nested
    dicts/lists, which is how you handle arbitrarily nested JSON data.
    """
    unfilled = []

    def _walk(value, path):
        if isinstance(value, dict):
            for key, val in value.items():
                _walk(val, f"{path}.{key}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                _walk(item, f"{path}[{i}]")
        elif isinstance(value, str) and "REPLACE" in value:
            unfilled.append(path)

    _walk(profile, "profile")
    return unfilled


def print_summary(profile: dict) -> None:
    """Print a quick human-readable summary of the loaded profile."""
    name = profile.get("personal", {}).get("full_name", "Unknown")
    num_experience = len(profile.get("experience", []))
    num_projects = len(profile.get("projects", []))

    # List comprehension: build a list of skill strings from a nested dict.
    all_skills = [
        skill
        for skill_list in profile.get("skills", {}).values()
        for skill in skill_list
    ]

    print(f"Profile loaded for: {name}")
    print(f"  Experience entries: {num_experience}")
    print(f"  Project entries:    {num_projects}")
    print(f"  Total skills listed: {len(all_skills)}")


def main():
    # Default to the real profile file; fall back to the template if the
    # real one doesn't exist yet, just so this script is runnable immediately.
    profile_path = "profile/master_profile.json"

    try:
        profile = load_profile(profile_path)
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        sys.exit(1)

    unfilled = find_unfilled_fields(profile)
    if unfilled:
        print(f"⚠️  Found {len(unfilled)} unfilled field(s):")
        for field in unfilled:
            print(f"   - {field}")
        print()

    print_summary(profile)


if __name__ == "__main__":
    # This guard means the script only runs main() when executed directly,
    # not when imported as a module elsewhere (useful later when this file
    # gets imported by the tailoring script).
    main()
