# Tendboat Agent Plugin

Host packaging for the Tendboat MCP executable and generated analysis skill. The
same source tree supports Codex Agent Plugins and Claude Code plugins.

The source tree intentionally excludes `plugin/bin/tendboat`. Assembly accepts a
standalone Tendboat executable, verifies it against `tendboat.lock.json`, validates the
generated skill and all manifests, and creates a self-contained deterministic
archive.

```bash
python3 packaging/verify.py
python3 packaging/assemble.py \
  --tendboat-binary /path/to/tendboat \
  --output dist/tendboat-agent-plugin-0.4.0.tar.gz
```

Or use:

```bash
make check
make package TENDBOAT_BINARY=/path/to/tendboat
```

The resulting archive contains the executable, skill, manifests, and MCP launch
configuration required at runtime.

## Layout

```text
plugin/                 installable host package
  bin/tendboat              inserted only during assembly
  skills/tendboat/SKILL.md  generated analysis contract
  plugin.json           Agent Plugins manifest
  mcp.json              Agent Plugins MCP configuration
  .claude-plugin/       Claude Code manifest
  .mcp.json             Claude Code MCP configuration
packaging/              validation and deterministic assembly
tests/                  local packaging checks
tendboat.lock.json          version and artifact checksums
```

`packaging/verify.py` accepts either the binary-free source layout or an
assembled layout containing the locked executable. `packaging/assemble.py`
normalizes archive ownership and timestamps so identical inputs produce
identical bytes.

## Project links

- Homepage: https://tendboat.com/
- Source: https://github.com/tendboat/tendboat-agent-plugin
- Issues: https://github.com/tendboat/tendboat-agent-plugin/issues

## License

Tendboat Agent Plugin is licensed under the Apache License, Version 2.0. See
[`LICENSE`](LICENSE). Self-contained plugin packages carry the same license as
`plugin/LICENSE`.
