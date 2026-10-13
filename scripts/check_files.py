#!/usr/bin/env python3
"""Ссылки, переносимость, UTF-8 и комплектность. Это не BSL-анализатор."""

import argparse
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("onec-refactor", "onec-debug", "onec-query-review")


def markdown_targets(content):
    """Inline/reference links and quoted HTML resources; not a Markdown renderer."""
    for pattern in (r'\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)',
                    r'^\s*\[[^\]]+\]:\s*(?:<([^>]+)>|(\S+))',
                    r'(?:href|src)=[\"\']([^\"\']+)[\"\']'):
        for match in re.finditer(pattern, content, re.M):
            yield next(value for value in match.groups() if value is not None)


def local_target(target):
    if target.startswith(("#", "//")):
        return None
    # A drive letter and file: URI are machine dependencies, not web sources.
    if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
        if not re.match(r"(?:file:|[a-z]:[\\/])", target, re.I):
            return None
    return unquote(target.split("#", 1)[0].split("?", 1)[0])


def check_skill_portability(folder):
    """Check a single copied folder without requiring the repository beside it."""
    folder = folder.resolve()
    errors = []

    def resource(origin, target, base):
        local = local_target(target)
        if not local:
            return
        label = origin.relative_to(folder)
        resolved = (base / local).resolve()
        if local.lower().startswith("file:") or not resolved.is_relative_to(folder):
            errors.append(f"{label}: target outside skill folder: {target}")
        elif not resolved.exists():
            errors.append(f"{label}: missing skill resource: {target}")

    for path in sorted(folder.rglob("*")):
        if not path.resolve().is_relative_to(folder):
            errors.append(f"{path.relative_to(folder)}: symlink outside skill folder")
            continue
        if path.is_file() and path.suffix == ".md":
            try:
                for target in markdown_targets(path.read_text(encoding="utf-8")):
                    resource(path, target, path.parent)
            except UnicodeError as exc:
                errors.append(f"{path.relative_to(folder)}: not UTF-8: {exc}")
    metadata = folder / "agents/openai.yaml"
    if metadata.is_file():
        try:
            fields = yaml.safe_load(metadata.read_text(encoding="utf-8"))
            interface = fields.get("interface", {}) if isinstance(fields, dict) else None
            if not isinstance(interface, dict):
                errors.append("agents/openai.yaml: expected interface mapping")
            else:
                for key in ("icon_small", "icon_large"):
                    target = interface.get(key)
                    if target is not None:
                        if not isinstance(target, str):
                            errors.append(f"agents/openai.yaml: invalid {key}")
                        else:
                            resource(metadata, target, folder)
        except (UnicodeError, yaml.YAMLError) as exc:
            errors.append(f"agents/openai.yaml: invalid YAML: {exc}")
    return errors


def check(root, validator=None):
    errors = []
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(p in {".git", "__pycache__", ".venv"} for p in path.parts):
            continue
        if path.suffix not in {".md", ".bsl", ".query", ".json", ".yaml", ".py", ".txt", ".yml"}:
            continue
        count += 1
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            errors.append(f"{path.relative_to(root)}: not UTF-8: {exc}")
            continue
        if content.startswith("\ufeff"):
            errors.append(f"{path.relative_to(root)}: unexpected BOM")
        if path.suffix == ".md":
            for target in markdown_targets(content):
                local = local_target(target)
                if local and not (path.parent / local).exists():
                    errors.append(f"{path.relative_to(root)}: missing local target {local}")
    for name in SKILLS:
        folder = root / "skills" / name
        errors.extend(f"{name}/{error}" for error in check_skill_portability(folder))
        path = folder / "SKILL.md"
        if not path.exists():
            errors.append(f"Missing {path}")
            continue
        content = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", content, re.S)
        if not match:
            errors.append(f"{name}: missing frontmatter")
            continue
        try:
            fields = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            errors.append(f"{name}: invalid YAML: {exc}")
            continue
        if not isinstance(fields, dict) or fields.get("name") != name:
            errors.append(f"{name}: frontmatter name mismatch")
            continue
        description = fields.get("description")
        if not isinstance(description, str) or not description.strip() or len(description) > 1024:
            errors.append(f"{name}: invalid description")
        if "[TODO:" in content:
            errors.append(f"{name}: unfinished scaffold")
        if validator:
            result = subprocess.run([sys.executable, "-X", "utf8", str(validator), str(folder)],
                                    text=True, encoding="utf-8", capture_output=True)
            print(f"skill-creator/{name}: {result.stdout.strip()}")
            if result.returncode:
                errors.append(f"{name}: external validator failed: {result.stderr.strip()}")
    print(f"Checked {count} text files; {len(SKILLS)} skill manifests and portable folders; {len(errors)} errors.")
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-validator", type=Path,
                        help="Path to quick_validate.py supplied with skill-creator (optional)")
    args = parser.parse_args()
    if args.skill_validator and not args.skill_validator.is_file():
        parser.error("--skill-validator must be an existing file")
    return check(ROOT, args.skill_validator)


if __name__ == "__main__":
    sys.exit(main())
