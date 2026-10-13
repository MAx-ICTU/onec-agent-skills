#!/usr/bin/env python3
"""Isolated copy and negative packaging checks; no Codex or 1C execution."""

import contextlib
import hashlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

from check_files import ROOT, SKILLS, check, check_skill_portability


def hashes(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


class PackagingChecks(unittest.TestCase):
    def setUp(self):
        self.original = hashes(ROOT)
        self.temp = tempfile.TemporaryDirectory(prefix="onec-packaging-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)

    def tearDown(self):
        self.assertEqual(hashes(ROOT), self.original, "Checks must preserve source files")

    def test_each_folder_copies_without_repository(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                # Separate project: none of the sibling skills/docs/examples is present.
                target = self.workspace / name / ".agents/skills" / name
                shutil.copytree(ROOT / "skills" / name, target)
                self.assertEqual(hashes(target), hashes(ROOT / "skills" / name))
                self.assertEqual(check_skill_portability(target), [])
        self.assertTrue((self.workspace / "onec-query-review/.agents/skills/onec-query-review"
                         / "references/query-pitfalls.md").is_file())

    def copy_project(self):
        target = self.workspace / "project"
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns("__pycache__", ".git", ".venv"))
        return target

    def assert_check_fails(self, root, message):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(check(root), 1)
        self.assertIn(message, stderr.getvalue())

    def test_existing_repository_file_is_not_a_portable_dependency(self):
        root = self.copy_project()
        skill = root / "skills/onec-refactor/SKILL.md"
        with skill.open("a", encoding="utf-8") as out:
            out.write("\n[Existing outside file](../../README.md)\n")
        self.assertTrue((skill.parent / "../../README.md").is_file())
        self.assert_check_fails(root, "outside skill folder")

    def test_reference_link_encoded_escape_and_absolute_path(self):
        root = self.copy_project()
        skill = root / "skills/onec-refactor/SKILL.md"
        for link in ("[outside]: ../../README.md", "[outside](%2e%2e/%2e%2e/README.md)",
                     f"[outside](<{(root / 'README.md').as_posix()}>)"):
            with self.subTest(link=link):
                original = skill.read_bytes()
                skill.write_text(original.decode("utf-8") + "\n" + link + "\n", encoding="utf-8")
                self.assert_check_fails(root, "outside skill folder")
                skill.write_bytes(original)

    def test_missing_reference_and_empty_description(self):
        root = self.copy_project()
        (root / "skills/onec-query-review/references/query-pitfalls.md").unlink()
        self.assert_check_fails(root, "missing skill resource")
        skill = root / "skills/onec-refactor/SKILL.md"
        lines = skill.read_text(encoding="utf-8").splitlines()
        skill.write_text("\n".join('description: ""' if line.startswith("description:") else line
                                    for line in lines) + "\n", encoding="utf-8")
        self.assert_check_fails(root, "invalid description")

    def test_ui_resource_cannot_escape_folder(self):
        root = self.copy_project()
        metadata = root / "skills/onec-refactor/agents/openai.yaml"
        # UI resource paths are relative to the skill root, not agents/.
        metadata.write_text('interface:\n  icon_small: "../../README.md"\n', encoding="utf-8")
        self.assert_check_fails(root, "outside skill folder")


if __name__ == "__main__":
    print("PACKAGING CHECKS ONLY: file copies, links and metadata; no CLI/IDE/1C execution.", flush=True)
    unittest.main(verbosity=2)
