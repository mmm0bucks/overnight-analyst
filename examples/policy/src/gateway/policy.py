"""Политика доступа ночного агента: можно ли роли выполнить действие.

Правила лежат в config/policy/rules.toml. Решение принимается так:
1. Правила [[rule]] проверяются по порядку, срабатывает последнее подходящее.
   Первое правило запрещает всё, поэтому без явного разрешения ответ "deny".
2. Затем [[hard_deny]]. Если подошло хоть одно, ответ "deny",
   что бы ни разрешили правила выше (К12: защитный слой только запрещает).
3. Ночью владельца нет, поэтому "ask" превращается в "queue":
   запрос уходит в очередь, эта ветка работы останавливается (К16).

Ответ: "allow", "ask", "queue" или "deny".
"""
import fnmatch
import tomllib


def load_rules(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def rule_matches(rule, action, resource, role, flags):
    if not fnmatch.fnmatchcase(action, rule["action"]):
        return False
    if not fnmatch.fnmatchcase(resource, rule.get("resource", "*")):
        return False
    roles = rule.get("roles", ["*"])
    if "*" not in roles and role not in roles:
        return False
    flag = rule.get("when")
    if flag and flag not in flags:
        return False
    return True


def decide(rules, action, resource, role, profile, flags=()):
    if profile == "off":
        return "deny"

    effect = "deny"
    for rule in rules.get("rule", []):
        if rule_matches(rule, action, resource, role, flags):
            effect = rule["effect"]

    for rule in rules.get("hard_deny", []):
        if rule_matches(rule, action, resource, role, flags):
            return "deny"

    if effect == "ask" and profile == "night":
        return "queue"
    return effect
