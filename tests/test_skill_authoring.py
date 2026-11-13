"""Skill files follow the published skill authoring limits.

The limits come from Anthropic's skill authoring guidance: a name of at most 64
lowercase letters, digits and hyphens without a reserved word; a description of
at most 1,024 characters in the third person without XML tags; a SKILL.md body
under 500 lines; forward slashes in paths; and a contents list at the top of
every reference file longer than 100 lines, so that a partial read still shows
its scope. The frontmatter keys are the ones every host accepts.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
RESERVED = ("anthropic", "claude")
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_BODY_LINES = 500
CONTENTS_ABOVE_LINES = 100
CONTENTS_WITHIN_LINES = 40
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
LINK = re.compile(r"\[[^\]]*\]\(<?([^)>#\s]+)[^)]*\)")
CONTENTS = re.compile(r"^#{1,3}\s*(Contents|Table of contents)\s*$", re.I | re.M)
NOT_THIRD_PERSON = re.compile(r"\b(I|we|you|your|my|our)\b")


def skill_files() -> list[Path]:
    return sorted(ROOT.glob("skills/*/SKILL.md"))


def split(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    if match is None:
        return {}, text
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if line[:1] in (" ", "\t", "#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key.strip()] = value
    return fields, text[match.end():]


def linked_markdown(path: Path) -> set[Path]:
    found = set()
    for target in LINK.findall(path.read_text(encoding="utf-8", errors="ignore")):
        if "://" in target or target.startswith("mailto:"):
            continue
        resolved = (path.parent / target).resolve()
        if resolved.suffix == ".md" and resolved.is_file() and ROOT in resolved.parents:
            found.add(resolved)
    return found


def reference_files() -> set[Path]:
    """Markdown a skill can be sent to: the shared and skill directories, and links two levels deep."""
    found = {p.resolve() for base in ("shared", "skills") for p in (ROOT / base).rglob("*.md")}
    for skill in skill_files():
        first = linked_markdown(skill)
        found |= first
        for path in first:
            found |= linked_markdown(path)
    return {p for p in found if p.name != "SKILL.md"}


class SkillAuthoringTests(unittest.TestCase):
    def test_there_are_skills_to_check(self) -> None:
        self.assertTrue(skill_files())

    def test_frontmatter_names_the_skill_within_the_limits(self) -> None:
        for path in skill_files():
            with self.subTest(skill=path.parent.name):
                fields, _ = split(path)
                self.assertTrue(set(fields) <= PORTABLE_KEYS, sorted(set(fields) - PORTABLE_KEYS))
                name = fields.get("name", "")
                self.assertEqual(path.parent.name, name)
                self.assertLessEqual(len(name), MAX_NAME)
                self.assertRegex(name, rf"\A{NAME.pattern}\Z")
                self.assertFalse([word for word in RESERVED if word in name])

    def test_description_is_bounded_plain_and_in_the_third_person(self) -> None:
        for path in skill_files():
            with self.subTest(skill=path.parent.name):
                description = split(path)[0].get("description", "")
                self.assertTrue(description.strip())
                self.assertLessEqual(len(description), MAX_DESCRIPTION)
                self.assertNotRegex(description, r"[<>]")
                self.assertEqual([], NOT_THIRD_PERSON.findall(description))

    def test_body_stays_under_the_line_limit(self) -> None:
        for path in skill_files():
            with self.subTest(skill=path.parent.name):
                self.assertLess(len(split(path)[1].splitlines()), MAX_BODY_LINES)

    def test_links_use_forward_slashes(self) -> None:
        for path in skill_files():
            with self.subTest(skill=path.parent.name):
                targets = LINK.findall(path.read_text(encoding="utf-8"))
                self.assertEqual([], [target for target in targets if "\\" in target])

    def test_long_reference_files_open_with_a_contents_list(self) -> None:
        missing = []
        for path in sorted(reference_files()):
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) > CONTENTS_ABOVE_LINES and not CONTENTS.search("\n".join(lines[:CONTENTS_WITHIN_LINES])):
                missing.append(f"{path.relative_to(ROOT)} ({len(lines)} lines)")
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
