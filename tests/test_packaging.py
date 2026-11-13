from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("plugin_verify", ROOT / "packaging/verify.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class PackagingTest(unittest.TestCase):
    def test_source_tree_is_valid_and_binary_free(self) -> None:
        self.assertEqual(VERIFY.verify(ROOT / "plugin", require_binary=False), [])

    def test_repository_and_plugin_carry_the_same_license(self) -> None:
        for filename in ("LICENSE", "NOTICE", "AUTHORS.md"):
            with self.subTest(filename=filename):
                self.assertEqual(
                    (ROOT / filename).read_bytes(), (ROOT / "plugin" / filename).read_bytes()
                )

    def test_marketplaces_point_only_at_plugin_subtree(self) -> None:
        claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual(claude["plugins"][0]["source"], "./plugin")
        self.assertEqual(claude["plugins"][0]["author"], {"name": "Nikolai Lugovskoi"})
        self.assertEqual(
            codex["plugins"][0]["source"], {"source": "local", "path": "./plugin"}
        )


if __name__ == "__main__":
    unittest.main()
