"""Проверка политики перед стартом агента (К11, К12).

Скрипт запуска вызывает эту проверку первой. Код выхода не 0 — харнесс не запускается.

    python src/orchestrator/check_policy.py            проверить
    python src/orchestrator/check_policy.py --approve  утвердить текущий файл (делает только владелец)

Утверждение записывает хеш файла правил. Если файл потом изменится,
хеш не совпадёт и агент не стартует, пока владелец не утвердит заново.
"""
import hashlib
import sys
import tomllib
from pathlib import Path

RULES_PATH = Path("config/policy/rules.toml")
HASH_PATH = Path("config/policy/rules.sha256")

EFFECTS = {"allow", "ask", "deny"}

# Эти запреты обязаны быть в [[hard_deny]]. Без них политика не принимается.
REQUIRED_HARD_DENY = {
    "external.write",   # трекер, вики, почта, мессенджеры (К2)
    "package.install",  # ничего стороннего (К3)
    "git.push",         # push делает только владелец (К2)
    "file.write",       # запись в config/, constitution.md, agents/, tools/ (К11)
    "kernel.*",         # сессия, читавшая чужой текст, не запускает код (К9)
    "web.search",       # сессия с внутренними данными не ходит в веб (К1, К9)
}


def find_problems(rules_path=RULES_PATH, hash_path=HASH_PATH):
    rules_path, hash_path = Path(rules_path), Path(hash_path)
    if not rules_path.exists():
        return [f"нет файла политики: {rules_path}"]

    problems = []
    data = rules_path.read_bytes()

    approved_hash = hash_path.read_text().strip() if hash_path.exists() else ""
    if approved_hash != hashlib.sha256(data).hexdigest():
        problems.append("файл политики не утверждён владельцем или изменён после утверждения")

    try:
        rules = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return problems + [f"файл политики не читается: {e}"]

    rule_list = rules.get("rule", [])
    hard_deny = rules.get("hard_deny", [])

    if not rule_list:
        problems.append("нет ни одного правила [[rule]]")
    else:
        first = rule_list[0]
        deny_all = (
            first.get("action") == "*"
            and first.get("resource", "*") == "*"
            and first.get("roles", ["*"]) == ["*"]
            and not first.get("when")
            and first.get("effect") == "deny"
        )
        if not deny_all:
            problems.append("первое правило должно запрещать всё: action = \"*\", effect = \"deny\"")

    for n, rule in enumerate(rule_list, start=1):
        if "action" not in rule:
            problems.append(f"[[rule]] №{n}: нет action")
        if rule.get("effect") not in EFFECTS:
            problems.append(f"[[rule]] №{n}: effect должен быть allow, ask или deny")

    for n, rule in enumerate(hard_deny, start=1):
        if "action" not in rule:
            problems.append(f"[[hard_deny]] №{n}: нет action")
        if "effect" in rule:
            problems.append(f"[[hard_deny]] №{n}: effect не нужен, это всегда запрет")

    present = {rule.get("action") for rule in hard_deny}
    for action in sorted(REQUIRED_HARD_DENY - present):
        problems.append(f"в [[hard_deny]] нет обязательного запрета: {action}")

    return problems


def approve(rules_path=RULES_PATH, hash_path=HASH_PATH):
    digest = hashlib.sha256(Path(rules_path).read_bytes()).hexdigest()
    Path(hash_path).write_text(digest + "\n")
    return digest


def main():
    if "--approve" in sys.argv:
        print("политика утверждена, хеш:", approve())
        return 0

    problems = find_problems()
    if problems:
        print("агент не запускается: политика не прошла проверку", file=sys.stderr)
        for p in problems:
            print(" -", p, file=sys.stderr)
        return 1

    print("политика в порядке")
    return 0


if __name__ == "__main__":
    sys.exit(main())
