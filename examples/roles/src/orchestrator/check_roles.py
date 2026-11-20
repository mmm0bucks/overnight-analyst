"""Проверка ролей: файлы agents/*.md согласованы с политикой и списком инструментов.

    python src/orchestrator/check_roles.py      код выхода 0 — роли в порядке

Ловит ошибки вида «роли дали инструмент, который политика ей запрещает»
или «роль читает чужой текст и при этом имеет kernel».
"""
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
import policy  # noqa: E402

REQUIRED_FIELDS = ["name", "description", "untrusted_input", "kernel", "tools", "writes",
                   "max_steps", "max_minutes", "profile", "output"]
KERNEL_VALUES = {"none", "read", "read_write_by_hash"}
PROFILE_VALUES = {"low", "high"}


def read_front_matter(path):
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    block = text.split("---")[1]
    fields = {}
    for line in block.strip().splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = [item.strip() for item in value[1:-1].split(",") if item.strip()]
        fields[key.strip()] = value
    return fields


def find_problems(agents_dir, rules, tools):
    problems = []
    files = sorted(Path(agents_dir).glob("*.md"))
    if not files:
        return [f"нет файлов ролей в {agents_dir}"]

    for path in files:
        role = read_front_matter(path)
        name = role.get("name", "")
        where = path.name

        for field in REQUIRED_FIELDS:
            if field not in role:
                problems.append(f"{where}: нет поля {field}")
        if name and path.stem != name:
            problems.append(f"{where}: имя файла не совпадает с name")
        if role.get("kernel") not in KERNEL_VALUES:
            problems.append(f"{where}: kernel должен быть none, read или read_write_by_hash")
        if role.get("profile") not in PROFILE_VALUES:
            problems.append(f"{where}: profile должен быть low или high")

        untrusted = role.get("untrusted_input") == "true"
        if untrusted and role.get("kernel") != "none":
            problems.append(f"{where}: роль читает чужой текст, kernel должен быть none (К9)")

        for tool in role.get("tools", []):
            spec = tools.get(tool)
            if spec is None:
                problems.append(f"{where}: инструмента {tool} нет в config/tools.toml")
                continue
            if spec.get("untrusted") and not untrusted:
                problems.append(f"{where}: {tool} даёт чужой текст, а untrusted_input: false")
            resource = "runs/x" if "{path}" in spec.get("resource", "") else "*"
            decision = policy.decide(rules, spec["action"], resource, name, "day")
            if decision == "deny":
                problems.append(f"{where}: политика запрещает роли {tool} ({spec['action']})")
    return problems


def main():
    rules = policy.load_rules("config/policy/rules.toml")
    with open("config/tools.toml", "rb") as f:
        tools = tomllib.load(f)["tools"]
    problems = find_problems("agents", rules, tools)
    if problems:
        print("роли не прошли проверку", file=sys.stderr)
        for p in problems:
            print(" -", p, file=sys.stderr)
        return 1
    print("роли в порядке")
    return 0


if __name__ == "__main__":
    sys.exit(main())
