"""Exercise native local plugin loading with empty, disposable host homes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile

try:
    from .process_control import run_bounded
except ImportError:
    from process_control import run_bounded


def isolated_environment(directory: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}}
    for key, name in (("HOME", "home"), ("CODEX_HOME", "codex"),
                      ("CLAUDE_CONFIG_DIR", "claude"), ("XDG_CONFIG_HOME", "xdg")):
        path = directory / name
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env["DISABLE_AUTOUPDATER"] = "1"
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return env


def run_native(command, cwd, env, timeout):
    try:
        result = run_bounded(command, cwd=cwd, env=env, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"native command unavailable or timed out: {command[0]} ({type(error).__name__})") from error
    if result.returncode:
        raise ValueError(f"native command failed ({result.returncode}): {' '.join(command[:3])}")
    return result.stdout


def extract_package(package: Path, destination: Path) -> Path:
    with zipfile.ZipFile(package) as archive:
        roots = {PurePosixPath(m.filename).parts[0] for m in archive.infolist() if m.filename}
        if len(roots) != 1:
            raise ValueError("package must contain one root")
        name = roots.pop()
        if not re.fullmatch(r"[a-z][a-z0-9-]*",name):
            raise ValueError("invalid package root")
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or path.parts[0] != name or mode & 0o170000 == 0o120000:
                raise ValueError("unsafe archive member")
        archive.extractall(destination)
        for member in archive.infolist():
            if not member.is_dir():
                (destination / member.filename).chmod((member.external_attr >> 16) & 0o777 or 0o644)
    return destination / name


def assert_installed(payload: str, host: str, name: str = "engineering-method") -> None:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"{host} returned malformed plugin inventory") from error
    identity = name + "@" + name
    if host == "Codex":
        entries = parsed.get("installed") if isinstance(parsed, dict) else None
        valid = isinstance(entries, list) and any(
            isinstance(entry, dict) and entry.get("pluginId") == identity
            and entry.get("name") == name and entry.get("marketplaceName") == name
            and entry.get("installed") is True and entry.get("enabled") is True
            for entry in entries)
    elif host == "Claude":
        # Claude's installed inventory has no installed boolean. A cache path
        # containing its actual plugin manifest is the native installation proof.
        valid = isinstance(parsed, list) and any(
            isinstance(entry, dict) and entry.get("id") == identity and entry.get("enabled") is True
            and isinstance(entry.get("installPath"), str) and Path(entry["installPath"]).is_absolute()
            and (Path(entry["installPath"]) / ".claude-plugin/plugin.json").is_file()
            for entry in parsed)
    else:
        raise ValueError("unknown native host inventory")
    if not valid:
        raise ValueError(f"{host} inventory did not show the installed plugin")


def clean_install(package: Path, timeout: int = 60) -> dict:
    with tempfile.TemporaryDirectory(prefix="em-clean-install-") as directory:
        temporary = Path(directory)
        root = extract_package(package, temporary / "package")
        name = json.loads((root / ".codex-plugin/plugin.json").read_text())["name"]
        identity = name + "@" + name
        env = isolated_environment(temporary / "configuration")
        commands = []
        def run(command):
            output = run_native(command, temporary, env, timeout)
            commands.append(command)
            return output
        run(["claude", "plugin", "validate", "--strict", str(root)])
        run(["claude", "plugin", "marketplace", "add", str(root)])
        run(["claude", "plugin", "install", identity])
        assert_installed(run(["claude", "plugin", "list", "--json"]), "Claude", name)
        details = run(["claude", "plugin", "details", identity])
        if name not in details:
            raise ValueError("Claude did not load the plugin inventory")
        run(["codex", "plugin", "marketplace", "add", str(root), "--json"])
        run(["codex", "plugin", "add", identity, "--json"])
        assert_installed(run(["codex", "plugin", "list", "--marketplace", name, "--json"]), "Codex", name)
        return {"status": "passed", "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
                "commands": commands, "credentials_used": False, "live_model_requests": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        result = clean_install(args.package.resolve(), args.timeout)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        result = {"status": "failed", "error": str(error)}
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    print(output, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
