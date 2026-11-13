"""Dependency-free validation for an Engineering Method plugin checkout."""

from __future__ import annotations

import collections.abc
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


COMMON_IDENTITY_FIELDS = ("name", "version", "description", "author", "license", "keywords")
COMMON_REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "third-party/sources.lock.json",
)
CODEX_REQUIRED_INTERFACE_FIELDS = {
    "displayName": str,
    "shortDescription": str,
    "longDescription": str,
    "developerName": str,
    "category": str,
    "capabilities": list,
    "defaultPrompt": list,
    "brandColor": str,
    "screenshots": list,
}
SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(?:0|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*|[1-9][0-9]*)(?:\.(?:0|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*|[1-9][0-9]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
BRACKETED_PLACEHOLDER = re.compile(r"\[(?:TODO|TBD|TASK|FIXME)(?::[^\]]*)?\]", re.IGNORECASE)
SCAFFOLD_PHRASES = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        "TODO" + r":\s*replace this placeholder",
        "TODO" + r":\s*add implementation",
    )
)
EXCLUDED_SCAN_PARTS = {".git", "__pycache__", ".engineering-method"}
SKILL_FRONTMATTER_FIELDS = frozenset({"name", "description"})
PLAIN_SCALAR_START_INDICATORS = frozenset("-?:,[]{}#&*!|>@`")
DOUBLE_QUOTED_SCALAR = re.compile(
    r'^"(?:[^"\\\r\n]|\\(?:["\\/bfnrt]|u[0-9A-Fa-f]{4}))*"$'
)
SINGLE_QUOTED_SCALAR = re.compile(r"^'(?:[^'\r\n]|'')*'$")
SKILL_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
YAML_AMBIGUOUS_PLAIN_SCALARS = frozenset(
    {
        "~",
        "null",
        "true",
        "false",
        "yes",
        "no",
        "on",
        "off",
        ".nan",
        ".inf",
        "+.inf",
        "-.inf",
    }
)
YAML_NUMERIC_PLAIN_SCALAR = re.compile(
    r"^[+-]?(?:(?:[0-9][0-9_]*)(?:\.[0-9_]*)?(?:[eE][+-]?[0-9_]+)?|"
    r"\.[0-9_]+(?:[eE][+-]?[0-9_]+)?|0[xX][0-9A-Fa-f_]+|0[oO][0-7_]+|0[bB][01_]+)$"
)
YAML_DATE_LIKE_PLAIN_SCALAR = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[Tt \t].*)?$")
PLAIN_SCALAR_COMMENT_OR_MAPPING = re.compile(r"(?:[ \t]#|:[ \t])")
PLAIN_DESCRIPTION = re.compile(r"^[A-Za-z][A-Za-z0-9 .()/'\"-]*$")
MARKDOWN_LINK = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _error(path: str, message: str) -> str:
    return f"ERROR {path}: {message}"


def _load_json(root: Path, relative: str, errors: list[str]) -> dict[str, object] | None:
    path = root / relative
    if not path.is_file():
        errors.append(_error(relative, "file is required"))
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append(_error(relative, "invalid JSON"))
        return None
    if not isinstance(value, dict):
        errors.append(_error(relative, "must contain a JSON object"))
        return None
    return value


def _validate_identity(
    relative: str, manifest: dict[str, object], errors: list[str]
) -> None:
    for field in COMMON_IDENTITY_FIELDS:
        if field not in manifest:
            errors.append(_error(relative, f"{field} is required"))
    name = manifest.get("name")
    if "name" in manifest and (not isinstance(name, str) or not name):
        errors.append(_error(relative, "name must be a non-empty string"))
    version = manifest.get("version")
    if "version" in manifest and (not isinstance(version, str) or not SEMVER.fullmatch(version)):
        errors.append(_error(relative, "version must be strict semver"))
    if "description" in manifest and (
        not isinstance(manifest["description"], str) or not manifest["description"]
    ):
        errors.append(_error(relative, "description must be a non-empty string"))
    author = manifest.get("author")
    if "author" in manifest and (
        not isinstance(author, dict)
        or not isinstance(author.get("name"), str)
        or not author["name"]
    ):
        errors.append(_error(relative, "author.name must be a non-empty string"))
    if "license" in manifest and (not isinstance(manifest["license"], str) or not manifest["license"]):
        errors.append(_error(relative, "license must be a non-empty string"))
    if "keywords" in manifest and (
        not isinstance(manifest["keywords"], list)
        or not all(isinstance(keyword, str) and keyword for keyword in manifest["keywords"])
    ):
        errors.append(_error(relative, "keywords must be a list of non-empty strings"))


def _validate_codex_manifest(
    root: Path, relative: str, manifest: dict[str, object], errors: list[str]
) -> None:
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        errors.append(_error(relative, "interface must be an object"))
        interface = {}
    skills = manifest.get("skills")
    if "skills" not in manifest:
        errors.append(_error(relative, "skills is required"))
    elif not isinstance(skills, str) or not skills:
        errors.append(_error(relative, "skills must be a non-empty string"))
    elif skills != "./skills/":
        errors.append(_error(relative, "skills must be exactly ./skills/"))
    for field, expected_type in CODEX_REQUIRED_INTERFACE_FIELDS.items():
        value = interface.get(field)
        if field not in interface:
            errors.append(_error(relative, f"{field} is required"))
        elif not isinstance(value, expected_type) or (isinstance(value, str) and not value):
            errors.append(_error(relative, f"{field} must be a non-empty {expected_type.__name__}"))

    for field in ("capabilities", "defaultPrompt"):
        value = interface.get(field)
        if isinstance(value, list) and not all(isinstance(item, str) and item for item in value):
            errors.append(_error(relative, f"{field} must be a list of non-empty strings"))
    brand_color = interface.get("brandColor")
    if isinstance(brand_color, str) and not re.fullmatch(r"#[0-9A-Fa-f]{6}", brand_color):
        errors.append(_error(relative, "brandColor must be a six-digit hex color"))

    for field in ("hooks", "apps", "mcpServers"):
        if field in manifest:
            errors.append(_error(relative, f"{field} is not supported without a component"))

    for field in ("skills", "agents", "commands"):
        if field not in manifest:
            continue
        component = manifest[field]
        if not isinstance(component, str) or not component:
            continue
        component_path = (root / component).resolve()
        try:
            component_path.relative_to(root.resolve())
        except ValueError:
            errors.append(_error(relative, f"{field} must stay within the repository"))
            continue
        if not component_path.is_dir():
            errors.append(_error(relative, f"{field} path {_relative(root, component_path)} is required"))


def _parse_supported_frontmatter_scalar(field: str, value: str) -> str | None:
    """Resolve the narrow, dependency-free string subset used by skill metadata.

    Supported values are non-empty plain strings, JSON-style double-quoted
    strings, and YAML single-quoted strings. Unquoted descriptions must begin
    with an ASCII letter and use only conservative text characters; values
    needing YAML structural, comment, tag, or anchor indicators must be
    quoted. Plain values that YAML might resolve as null, booleans, numbers,
    or dates are also intentionally unsupported.
    """
    if not value:
        return None
    if value.startswith('"'):
        if not DOUBLE_QUOTED_SCALAR.fullmatch(value):
            return None
        try:
            resolved = json.loads(value)
        except json.JSONDecodeError:
            return None
        return resolved if isinstance(resolved, str) and resolved.strip() else None
    if value.startswith("'"):
        if not SINGLE_QUOTED_SCALAR.fullmatch(value):
            return None
        resolved = value[1:-1].replace("''", "'")
        return resolved if resolved.strip() else None
    if (
        value[0] in PLAIN_SCALAR_START_INDICATORS
        or value.endswith(":")
        or PLAIN_SCALAR_COMMENT_OR_MAPPING.search(value)
        or value.lower() in YAML_AMBIGUOUS_PLAIN_SCALARS
        or YAML_NUMERIC_PLAIN_SCALAR.fullmatch(value)
        or YAML_DATE_LIKE_PLAIN_SCALAR.fullmatch(value)
        or (field == "description" and not PLAIN_DESCRIPTION.fullmatch(value))
    ):
        return None
    return value


def _validate_skill_frontmatter(root: Path, errors: list[str]) -> None:
    skills_root = root / "skills"
    if not skills_root.is_dir():
        return
    for path in sorted(skills_root.rglob("SKILL.md")):
        relative = _relative(root, path)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            errors.append(_error(relative, "must be valid UTF-8 text"))
            continue
        if not content.startswith("---\n"):
            errors.append(_error(relative, "YAML frontmatter is required"))
            continue
        closing = content.find("\n---\n", 4)
        if closing == -1:
            errors.append(_error(relative, "YAML frontmatter must be closed"))
            continue
        fields: set[str] = set()
        for line in content[4:closing].splitlines():
            if not line.strip():
                continue
            key, separator, value = line.partition(":")
            if not separator or key not in SKILL_FRONTMATTER_FIELDS or key in fields:
                errors.append(
                    _error(relative, "frontmatter supports only unique name and description scalars")
                )
                continue
            fields.add(key)
            scalar = _parse_supported_frontmatter_scalar(key, value.strip())
            if scalar is None:
                errors.append(_error(relative, f"frontmatter {key} must be a supported scalar"))
            elif key == "name" and not SKILL_NAME.fullmatch(scalar):
                errors.append(_error(relative, "frontmatter name must be lowercase hyphen-case"))
        for field in SKILL_FRONTMATTER_FIELDS:
            if field not in fields:
                errors.append(_error(relative, f"frontmatter {field} is required"))


def _validate_project_backlog_contract(root: Path, errors: list[str]) -> None:
    relative = "skills/project-backlog/SKILL.md"
    path = root / relative
    if not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    description_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
    description = (
        _parse_supported_frontmatter_scalar("description", description_match.group(1).strip())
        if description_match is not None
        else None
    )
    lowered_description = description.lower() if description is not None else ""
    if not (
        "implementation methodology" in lowered_description
        and ("never" in lowered_description or "not " in lowered_description)
    ):
        errors.append(
            _error(relative, "description must exclude implementation methodology selection")
        )
    lowered_content = content.lower()
    required_script_links = {
        "../../scripts/project-state",
        "../../scripts/backlog-to-issues",
        "../../scripts/refresh-issue-cache",
        "../../scripts/continuity-state",
    }
    script_links = {
        target.strip().strip("<>").split("#", 1)[0]
        for target in MARKDOWN_LINK.findall(content)
        if target.strip().strip("<>").split("#", 1)[0].startswith("../../scripts/")
    }
    has_target_relative_command = re.search(
        r"(?m)^\s*scripts/(?:project-state|backlog-to-issues|refresh-issue-cache|continuity-state)\b",
        content,
    )
    if (
        script_links != required_script_links
        or "skill.md" not in lowered_content
        or "relative" not in lowered_content
        or "absolute path" not in lowered_content
        or "target repository" not in lowered_content
        or "cwd" not in lowered_content
        or has_target_relative_command is not None
    ):
        errors.append(
            _error(
                relative,
                "bundled script links must resolve from the skill directory and run with the target repository cwd",
            )
        )


def _validate_skill_resources(root: Path, errors: list[str]) -> None:
    """Validate local Markdown links from skills as installed-relative resources."""
    skills_root = root / "skills"
    if not skills_root.is_dir():
        return
    resolved_root = root.resolve()
    for path in sorted(skills_root.rglob("*.md")):
        relative = _relative(root, path)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw_target in MARKDOWN_LINK.findall(content):
            target = raw_target.strip().strip("<>")
            target = target.split("#", 1)[0]
            if not target or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            target = unquote(target)
            candidate = (path.parent / target).resolve()
            try:
                candidate.relative_to(resolved_root)
            except ValueError:
                errors.append(
                    _error(relative, f"bundled resource {target} must stay within the repository")
                )
                continue
            if not candidate.is_file():
                errors.append(_error(relative, f"bundled resource {target} is required"))


def _validate_locked_destinations(
    root: Path, lock: dict[str, object], errors: list[str]
) -> None:
    """Validate repository-contained provenance facts without upstream checkouts."""
    sources = lock.get("sources")
    if not isinstance(sources, list):
        errors.append(_error("third-party/sources.lock.json", "sources must be a list"))
        return
    resolved_root = root.resolve()
    destinations: set[str] = set()
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("files"), list):
            errors.append(_error("third-party/sources.lock.json", "each source must have a files list"))
            continue
        for mapping in source["files"]:
            if not isinstance(mapping, dict):
                errors.append(_error("third-party/sources.lock.json", "file mappings must be objects"))
                continue
            source_hash = mapping.get("source_sha256")
            if not isinstance(source_hash, str) or not SHA256.fullmatch(source_hash):
                errors.append(_error("third-party/sources.lock.json", "source_sha256 must be lowercase SHA-256"))
            if mapping.get("modification_status") != "adapted":
                continue
            destination = mapping.get("destination_path")
            destination_hash = mapping.get("destination_sha256")
            if not isinstance(destination, str) or not destination:
                errors.append(_error("third-party/sources.lock.json", "adapted destination_path is required"))
                continue
            if destination in destinations:
                errors.append(_error("third-party/sources.lock.json", f"duplicate destination {destination}"))
                continue
            destinations.add(destination)
            candidate = (root / destination).resolve()
            try:
                candidate.relative_to(resolved_root)
            except ValueError:
                errors.append(_error("third-party/sources.lock.json", f"destination {destination} must stay within the repository"))
                continue
            if not candidate.is_file():
                errors.append(_error("third-party/sources.lock.json", f"destination {destination} is required"))
                continue
            if not isinstance(destination_hash, str) or not SHA256.fullmatch(destination_hash):
                errors.append(_error("third-party/sources.lock.json", f"destination_sha256 is required for {destination}"))
                continue
            actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual != destination_hash:
                errors.append(_error("third-party/sources.lock.json", f"destination hash mismatch for {destination}"))


def _is_excluded_scan_path(relative: Path) -> bool:
    return any(part in EXCLUDED_SCAN_PARTS for part in relative.parts) or relative.parts[:2] == (
        "tests",
        "fixtures",
    )


def _validate_unfinished_markers(root: Path, errors: list[str]) -> None:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root)
        if _is_excluded_scan_path(relative_path):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        marker = BRACKETED_PLACEHOLDER.search(content)
        if marker is None:
            marker = next(
                (phrase.search(content) for phrase in SCAFFOLD_PHRASES if phrase.search(content)), None
            )
        if marker is not None:
            errors.append(
                _error(_relative(root, path), f"unfinished marker '{marker.group(0)}'")
            )


def _validate_platform_boundary(root: Path, errors: list[str]) -> None:
    host_syntax = re.compile(
        r"\bgpt-\d[\w.-]*|\bclaude-(?:fable|opus|sonnet|haiku)[\w.-]*|"
        r"\bcollaboration\.[a-z_]+|\b(?:spawn_agent|followup_task|send_message|wait_agent|"
        r"interrupt_agent|list_agents)\b|`Agent`|\bCLAUDE_PLUGIN_ROOT\b"
    )
    for tree in ("skills", "templates", "shared/policies"):
        for path in sorted((root / tree).rglob("*")):
            if not path.is_file() or path.suffix not in (".md", ".json", ".yaml", ".yml"):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                errors.append(_error(_relative(root, path), "cannot read neutral resource"))
                continue
            if host_syntax.search(content):
                errors.append(_error(_relative(root, path), "host syntax and model IDs belong in shared/platform adapters"))


def _validate_marketplaces(root: Path, name: object, errors: list[str]) -> None:
    for relative, host in ((".agents/plugins/marketplace.json", "codex"),
                           (".claude-plugin/marketplace.json", "claude")):
        data = _load_json(root, relative, errors)
        if data is None:
            continue
        if data.get("name") != name:
            errors.append(_error(relative, "marketplace name must match plugin identity"))
        plugins = data.get("plugins")
        if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
            errors.append(_error(relative, "plugins must contain exactly one plugin object"))
            continue
        entry = plugins[0]
        if entry.get("name") != name:
            errors.append(_error(relative, "entry name must match plugin identity"))
        expected_source = {"source": "local", "path": "./"} if host == "codex" else "./"
        if entry.get("source") != expected_source:
            errors.append(_error(relative, "source must resolve to the local repository root ./"))
        if host == "codex":
            policy = entry.get("policy")
            if not isinstance(policy, dict) or policy.get("installation") not in (
                "NOT_AVAILABLE", "AVAILABLE", "INSTALLED_BY_DEFAULT"
            ) or policy.get("authentication") not in ("ON_INSTALL", "ON_USE"):
                errors.append(_error(relative, "policy requires valid installation and authentication"))
            if not isinstance(entry.get("category"), str) or not entry["category"].strip():
                errors.append(_error(relative, "category is required"))
        else:
            owner = data.get("owner")
            if not isinstance(owner, dict) or not isinstance(owner.get("name"), str) or not owner["name"].strip():
                errors.append(_error(relative, "owner.name is required"))


def _core_integrity(root: Path, errors: list[str]) -> None:
    try:
        from .method_core import check, contained, safe_name
    except ImportError:
        from method_core import check, contained, safe_name
    if (root / "method-core.json").is_file():
        try:
            manifest = json.loads((root / "method-core.json").read_text())
            names = manifest["exports"]
            if manifest.get("schema_version") != 1 or manifest.get("name") != "method-core" or not isinstance(names,list) or not names or len(names) != len(set(names)):
                raise ValueError("invalid core export inventory")
            for name in names:
                if not contained(root,safe_name(name)).is_file():
                    raise ValueError(f"missing core export: {name}")
        except (OSError,ValueError,TypeError,KeyError) as error:
            errors.append(_error("method-core.json",str(error)))
    if (root / "method.json").is_file():
        try:
            check(root)
        except (OSError,ValueError,TypeError,KeyError) as error:
            errors.append(_error("method-core.lock.json",str(error)))
        try:
            profile = json.loads((root / "method.json").read_text())
            own = profile["method_skills"]
            if not isinstance(own,list) or not own or len(own) != len(set(own)) or not all(isinstance(n,str) and SKILL_NAME.fullmatch(n) for n in own):
                raise ValueError("invalid method skill inventory")
            bundled = {p.parent.name for p in (root / "skills").glob("*/SKILL.md")}
            locked = json.loads((root / "method-core.lock.json").read_text())
            shared = {item["path"].split("/")[1] for item in locked["files"] if re.fullmatch(r"skills/[^/]+/SKILL.md",item["path"])}
            if bundled != set(own) | shared or set(own) & shared:
                raise ValueError("method skills disagree with owned and shared inventories")
        except (OSError,ValueError,TypeError,KeyError) as error:
            errors.append(_error("method.json",str(error)))


def validate_repository(root: Path) -> list[str]:
    """Return sorted validation errors, or an empty list."""
    root = root.resolve()
    errors: list[str] = []
    _core_integrity(root, errors)
    if (root / "method-core.json").is_file() and not (root / "method.json").exists():
        _validate_skill_frontmatter(root, errors)
        _validate_project_backlog_contract(root, errors)
        _validate_skill_resources(root, errors)
        _validate_platform_boundary(root, errors)
        if (root / "third-party/sources.lock.json").is_file():
            lock = _load_json(root, "third-party/sources.lock.json", errors)
            if lock is not None: _validate_locked_destinations(root,lock,errors)
        else:
            errors.append(_error("third-party/sources.lock.json","file is required"))
        return sorted(errors)
    codex_relative = ".codex-plugin/plugin.json"
    claude_relative = ".claude-plugin/plugin.json"
    codex = _load_json(root, codex_relative, errors)
    claude = _load_json(root, claude_relative, errors)
    for relative in COMMON_REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(_error(relative, "file is required"))
    lock: dict[str, object] | None = None
    if (root / "third-party/sources.lock.json").is_file():
        lock = _load_json(root, "third-party/sources.lock.json", errors)
    if codex is not None:
        _validate_identity(codex_relative, codex, errors)
        _validate_codex_manifest(root, codex_relative, codex, errors)
    if claude is not None:
        _validate_identity(claude_relative, claude, errors)
    if codex is not None and claude is not None:
        for field in (field for field in COMMON_IDENTITY_FIELDS if field != "author"):
            if field in codex and field in claude and codex[field] != claude[field]:
                errors.append(_error(claude_relative, f"{field} must match .codex-plugin/plugin.json"))
        codex_author = codex.get("author")
        claude_author = claude.get("author")
        if (
            isinstance(codex_author, dict)
            and isinstance(claude_author, dict)
            and codex_author.get("name") != claude_author.get("name")
        ):
            errors.append(_error(claude_relative, "author.name must match .codex-plugin/plugin.json"))
    _validate_skill_frontmatter(root, errors)
    _validate_project_backlog_contract(root, errors)
    _validate_skill_resources(root, errors)
    _validate_marketplaces(root, codex.get("name") if codex else "engineering-method", errors)
    _validate_platform_boundary(root, errors)
    if lock is not None:
        _validate_locked_destinations(root, lock, errors)
    core_provenance = root / "third-party/core-sources.lock.json"
    if core_provenance.is_file():
        core_lock = _load_json(root,"third-party/core-sources.lock.json",errors)
        if core_lock is not None: _validate_locked_destinations(root,core_lock,errors)
    _validate_unfinished_markers(root, errors)
    return sorted(errors)


def main(argv: collections.abc.Sequence[str] | None = None) -> int:
    """Validate argv[0] or the current directory and return a process code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = Path(arguments[0]) if arguments else Path.cwd()
    errors = validate_repository(root)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
