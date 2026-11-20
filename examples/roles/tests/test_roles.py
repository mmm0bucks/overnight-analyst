"""Тесты проверки ролей. Запуск: python -m unittest discover -s tests"""
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "gateway"))
sys.path.insert(0, str(ROOT / "src" / "orchestrator"))

import check_roles  # noqa: E402
import policy  # noqa: E402


def first_existing(*names):
    for name in names:
        if (ROOT / name).exists():
            return ROOT / name
    raise FileNotFoundError(names)


RULES_PATH = first_existing("config/policy/rules.toml", "config/policy/rules.example.toml")
TOOLS_PATH = first_existing("config/tools.toml", "config/tools.example.toml")


def load_tools():
    with open(TOOLS_PATH, "rb") as f:
        return tomllib.load(f)["tools"]


class RolesTest(unittest.TestCase):
    def test_roles_match_policy_and_tools(self):
        problems = check_roles.find_problems(ROOT / "agents", policy.load_rules(RULES_PATH), load_tools())
        self.assertEqual(problems, [])

    def test_untrusted_role_with_kernel_is_caught(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copy(ROOT / "agents" / "scout.md", tmp / "scout.md")
            text = (tmp / "scout.md").read_text(encoding="utf-8").replace("kernel: none", "kernel: read")
            (tmp / "scout.md").write_text(text, encoding="utf-8")
            problems = check_roles.find_problems(tmp, policy.load_rules(RULES_PATH), load_tools())
            self.assertTrue(any("К9" in p for p in problems))
        finally:
            shutil.rmtree(tmp)


    def test_tool_forbidden_by_policy_is_caught(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copy(ROOT / "agents" / "analyst.md", tmp / "analyst.md")
            text = (tmp / "analyst.md").read_text(encoding="utf-8").replace("tools: [", "tools: [wiki_read, ", 1)
            (tmp / "analyst.md").write_text(text, encoding="utf-8")
            problems = check_roles.find_problems(tmp, policy.load_rules(RULES_PATH), load_tools())
            self.assertTrue(any("wiki_read" in p for p in problems))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
