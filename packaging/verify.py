#!/usr/bin/env python3
"""Validate plugin source or an assembled plugin directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_METADATA = {
    "homepage": "https://tendboat.com/",
    "repository": "https://github.com/tendboat/tendboat-agent-plugin",
    "license": "Apache-2.0",
}
EXPECTED_AUTHOR = {"name": "Nikolai Lugovskoi"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def verify(plugin: Path, require_binary: bool) -> list[str]:
    errors: list[str] = []
    lock = read_json(ROOT / "tendboat.lock.json")
    manifests = {
        "agent": plugin / "plugin.json",
        "codex": plugin / ".codex-plugin/plugin.json",
        "claude": plugin / ".claude-plugin/plugin.json",
        "mcp-agent": plugin / "mcp.json",
        "mcp-claude": plugin / ".mcp.json",
    }
    parsed: dict[str, dict] = {}
    for name, path in manifests.items():
        try:
            parsed[name] = read_json(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
    versions = {
        parsed[name].get("version")
        for name in ("agent", "codex", "claude")
        if name in parsed
    }
    if versions != {lock["plugin_version"]}:
        errors.append(f"manifest versions {sorted(map(str, versions))} != lock {lock['plugin_version']}")
    for name in ("agent", "codex", "claude"):
        for key, expected in EXPECTED_METADATA.items():
            if parsed.get(name, {}).get(key) != expected:
                errors.append(f"{name}: {key} does not match canonical metadata")
    for name in ("agent", "claude"):
        if parsed.get(name, {}).get("author") != EXPECTED_AUTHOR:
            errors.append(f"{name}: author does not match canonical metadata")
    if parsed.get("codex", {}).get("interface", {}).get("developerName") != EXPECTED_AUTHOR["name"]:
        errors.append("codex: developerName does not match canonical metadata")
    if parsed.get("agent", {}).get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
        errors.append("plugin/plugin.json does not declare the Agent Plugins schema")
    agent_server = parsed.get("mcp-agent", {}).get("mcpServers", {}).get("tendboat", {})
    if agent_server.get("command") != "./bin/tendboat" or agent_server.get("args", [])[:2] != ["mcp", "--plugin"]:
        errors.append("agent MCP command is not ./bin/tendboat mcp --plugin")
    claude_server = parsed.get("mcp-claude", {}).get("mcpServers", {}).get("tendboat", {})
    if claude_server.get("command") != "${CLAUDE_PLUGIN_ROOT}/bin/tendboat":
        errors.append("Claude MCP command does not use CLAUDE_PLUGIN_ROOT")
    skill = plugin / "skills/tendboat/SKILL.md"
    if not skill.is_file() or sha256(skill) != lock["skill_sha256"]:
        errors.append("generated skill checksum does not match tendboat.lock.json")
    license_file = plugin / "LICENSE"
    if not license_file.is_file() or sha256(license_file) != lock["license_sha256"]:
        errors.append("Apache-2.0 LICENSE checksum does not match tendboat.lock.json")
    for attribution_file in ("NOTICE", "AUTHORS.md"):
        if not (plugin / attribution_file).is_file():
            errors.append(f"plugin is missing {attribution_file}")
    binary = plugin / "bin/tendboat"
    if require_binary:
        if not binary.is_file() or not os.access(binary, os.X_OK):
            errors.append("assembled plugin has no executable bin/tendboat")
        elif sha256(binary) != lock["binary_sha256"]:
            errors.append("assembled binary checksum does not match tendboat.lock.json")
    elif binary.exists():
        errors.append("source repository must not contain plugin/bin/tendboat")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-root", type=Path, default=ROOT / "plugin")
    parser.add_argument("--require-binary", action="store_true")
    args = parser.parse_args()
    errors = verify(args.plugin_root.resolve(), args.require_binary)
    print(f"plugin={args.plugin_root} errors={len(errors)}")
    for error in errors:
        print(error)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
