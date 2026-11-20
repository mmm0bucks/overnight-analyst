"""Проверки перед стартом агента. Скрипт запуска вызывает их первыми.
Код выхода не 0 — харнесс не запускается (угроза «защита тихо выключена»).

    python src/orchestrator/start_checks.py

Что проверяется:
1. Политика на месте, утверждена владельцем и не ослаблена (check_policy).
2. Шлюз отклоняет запрещённое действие (gateway.self_test).
3. Роли согласованы с политикой и списком инструментов (check_roles).
"""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "gateway"))
sys.path.insert(0, str(ROOT / "src" / "orchestrator"))

import check_policy  # noqa: E402
import check_roles  # noqa: E402
import gateway  # noqa: E402
import policy  # noqa: E402


def find_problems():
    problems = check_policy.find_problems()
    if problems:
        return problems

    rules = policy.load_rules(check_policy.RULES_PATH)
    with open("config/tools.toml", "rb") as f:
        tools = tomllib.load(f)["tools"]

    gw = gateway.Gateway(rules, tools, {}, "runs/start_checks.jsonl")
    if not gateway.self_test(gw):
        problems.append("шлюз пропустил запрещённое действие")

    problems += check_roles.find_problems("agents", rules, tools)
    return problems


def main():
    problems = find_problems()
    if problems:
        print("агент не запускается:", file=sys.stderr)
        for p in problems:
            print(" -", p, file=sys.stderr)
        return 1
    print("проверки перед стартом пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
