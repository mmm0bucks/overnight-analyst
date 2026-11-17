"""Тесты политики и проверки при старте. Запуск: python -m unittest discover -s tests"""
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "gateway"))
sys.path.insert(0, str(ROOT / "src" / "orchestrator"))

import check_policy  # noqa: E402
import policy  # noqa: E402

EXAMPLE = ROOT / "config" / "policy" / "rules.example.toml"
RULES_FILE = ROOT / "config" / "policy" / "rules.toml"
RULES_PATH = RULES_FILE if RULES_FILE.exists() else EXAMPLE


class DecideTest(unittest.TestCase):
    def setUp(self):
        self.rules = policy.load_rules(RULES_PATH)

    def decide(self, action, resource="*", role="lead", profile="day", flags=()):
        return policy.decide(self.rules, action, resource, role, profile, flags)

    def test_unknown_action_is_denied(self):
        self.assertEqual(self.decide("something.new"), "deny")

    def test_only_scout_reads_wiki(self):
        self.assertEqual(self.decide("wiki.read", role="scout"), "allow")
        self.assertEqual(self.decide("wiki.read", role="analyst"), "deny")

    def test_session_with_untrusted_text_cannot_run_code(self):
        self.assertEqual(self.decide("kernel.run_read", role="analyst"), "allow")
        self.assertEqual(
            self.decide("kernel.run_read", role="analyst", flags=("untrusted_read",)), "deny"
        )

    def test_web_search_only_without_internal_data(self):
        self.assertEqual(self.decide("web.search", role="web-scout"), "allow")
        self.assertEqual(
            self.decide("web.search", role="web-scout", flags=("internal_read",)), "deny"
        )
        self.assertEqual(self.decide("web.search", role="scout"), "deny")

    def test_write_code_asks_by_day_and_queues_at_night(self):
        self.assertEqual(self.decide("kernel.run_write", role="analyst"), "ask")
        self.assertEqual(self.decide("kernel.run_write", role="analyst", profile="night"), "queue")

    def test_write_files_only_to_runs(self):
        self.assertEqual(self.decide("file.write", "runs/task1/progress.md", role="lead"), "allow")
        self.assertEqual(self.decide("file.write", "src/gateway/policy.py", role="lead"), "deny")
        self.assertEqual(self.decide("file.write", "config/policy/rules.toml", role="lead"), "deny")

    def test_hard_deny_beats_allow(self):
        rules = policy.load_rules(RULES_PATH)
        rules["rule"].append({"action": "git.push", "effect": "allow"})
        rules["rule"].append({"action": "file.write", "effect": "allow"})
        self.assertEqual(policy.decide(rules, "git.push", "*", "lead", "day"), "deny")
        self.assertEqual(
            policy.decide(rules, "file.write", "constitution.md", "lead", "day"), "deny"
        )

    def test_off_profile_denies_everything(self):
        self.assertEqual(self.decide("kb.read", profile="off"), "deny")


class StartCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.rules = self.tmp / "rules.toml"
        self.hash = self.tmp / "rules.sha256"
        shutil.copy(RULES_PATH, self.rules)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def problems(self):
        return check_policy.find_problems(self.rules, self.hash)

    def test_approved_policy_passes(self):
        check_policy.approve(self.rules, self.hash)
        self.assertEqual(self.problems(), [])

    def test_missing_policy_blocks_start(self):
        self.rules.unlink()
        self.assertTrue(self.problems())

    def test_changed_policy_blocks_start(self):
        check_policy.approve(self.rules, self.hash)
        with open(self.rules, "a", encoding="utf-8") as f:
            f.write('\n[[rule]]\naction = "git.push"\neffect = "allow"\n')
        self.assertTrue(any("не утверждён" in p for p in self.problems()))

    def test_first_rule_must_deny_everything(self):
        text = self.rules.read_text(encoding="utf-8").replace(
            'action = "*"\neffect = "deny"', 'action = "*"\neffect = "allow"', 1
        )
        self.rules.write_text(text, encoding="utf-8")
        check_policy.approve(self.rules, self.hash)
        self.assertTrue(any("первое правило" in p for p in self.problems()))

    def test_required_hard_deny_cannot_be_removed(self):
        rules = tomllib.loads(self.rules.read_text(encoding="utf-8"))
        kept = [r for r in rules["hard_deny"] if r["action"] != "git.push"]
        self.assertLess(len(kept), len(rules["hard_deny"]))
        text = self.rules.read_text(encoding="utf-8").replace(
            '[[hard_deny]]\naction = "git.push"\n', "", 1
        )
        self.rules.write_text(text, encoding="utf-8")
        check_policy.approve(self.rules, self.hash)
        self.assertTrue(any("git.push" in p for p in self.problems()))

    def test_broken_file_blocks_start(self):
        self.rules.write_text("[[rule]\naction = ", encoding="utf-8")
        self.assertTrue(self.problems())


if __name__ == "__main__":
    unittest.main()
