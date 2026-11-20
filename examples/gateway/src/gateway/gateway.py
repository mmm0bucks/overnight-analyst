"""Шлюз инструментов: через него идёт каждый вызов инструмента агента.

Порядок для одного вызова:
1. Инструмент есть в config/tools.toml, иначе отказ.
2. Политика (policy.decide) по действию, роли, профилю и флагам сессии.
3. Для веб-поиска — проверка запроса: без имён из каталога, длинных чисел и кода (К1).
4. Вызов самого инструмента.
5. Маскировка секретов и персональных данных в ответе, до модели (К10).
6. Чужой текст оборачивается пометкой «данные, не указания» (К8), сессия получает флаги.
7. Ответ обрезается по размеру. Всё пишется в журнал (К15).

Отказ возвращается с подсказкой, что делать вместо, а не просто «нельзя».
"""
import json
import re
import time
from pathlib import Path

import policy

MAX_RESULT_CHARS = 20000

SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key)(\s*[:=]\s*)(['\"]?)[^\s'\",;]{4,}"),
    re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
]
PERSONAL_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"(?<!\d)(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)"),
]

HINTS = {
    "deny": "Действие запрещено политикой. Не обходи запрет; если без него шаг не сделать, остановись и напиши владельцу номер правила.",
    "queue": "Нужно одобрение владельца. Запрос поставлен в очередь, эта ветка работы остановлена; продолжай другую работу.",
    "ask": "Нужно одобрение владельца. Покажи ему, что хочешь сделать, и жди ответа.",
    "unknown_tool": "Такого инструмента нет в списке разрешённых. Используй инструмент из своей роли.",
    "bad_query": "Запрос в веб-поиск должен быть общим: без имён таблиц и полей, чисел из данных и кода. Переформулируй.",
}


def redact(text):
    """Секреты заменяются метками, остальной текст сохраняется."""
    found = 0

    def secret(match):
        nonlocal found
        found += 1
        if match.re is SECRET_PATTERNS[0]:
            return f"{match.group(1)}{match.group(2)}[SECRET_{found}]"
        if match.re is SECRET_PATTERNS[1]:
            return f"{match.group(1)}[SECRET_{found}]"
        return f"[SECRET_{found}]"

    for pattern in SECRET_PATTERNS:
        text = pattern.sub(secret, text)
    for pattern in PERSONAL_PATTERNS:
        text = pattern.sub("[PERSONAL]", text)
    return text, found


def wrap_untrusted(text, source):
    """Чужой текст — данные. Закрывающий тег внутри текста убирается, чтобы из пометки нельзя было выйти."""
    text = re.sub(r"(?i)</?untrusted_data[^>]*>", "", text)
    return f'<untrusted_data source="{source}">\n{text}\n</untrusted_data>'


def query_problem(query, catalog_names):
    """Пустая строка — запрос можно отправлять. Иначе — что с ним не так."""
    lowered = query.lower()
    for name in catalog_names:
        if name and name.lower() in lowered:
            return "в запросе имя из каталога данных"
    if re.search(r"\d{4,}", query):
        return "в запросе длинное число"
    if re.search(r"[=;{}()<>]|\bselect\b|\bfrom\b", lowered):
        return "в запросе похоже на код"
    if len(query) > 200:
        return "запрос длиннее 200 символов"
    return ""


class Gateway:
    def __init__(self, rules, tools, implementations, journal_path, catalog_names=()):
        self.rules = rules
        self.tools = tools
        self.implementations = implementations
        self.journal_path = Path(journal_path)
        self.catalog_names = set(catalog_names)

    def call(self, session, tool, args):
        """session: {"role": ..., "profile": "night" | "day", "flags": set()}"""
        spec = self.tools.get(tool)
        if spec is None:
            return self._refuse(session, tool, "*", "unknown_tool")

        resource = spec.get("resource", "*").replace("{path}", str(args.get("path", "")))
        decision = policy.decide(
            self.rules, spec["action"], resource, session["role"], session["profile"], session["flags"]
        )
        if decision != "allow":
            return self._refuse(session, tool, resource, decision)

        if spec["action"] == "web.search":
            problem = query_problem(args.get("query", ""), self.catalog_names)
            if problem:
                return self._refuse(session, tool, resource, "bad_query", problem)

        result = str(self.implementations[tool](**args))
        result, secrets = redact(result)

        if spec.get("untrusted"):
            result = wrap_untrusted(result, tool)
            session["flags"].add("untrusted_read")
        if spec.get("internal"):
            session["flags"].add("internal_read")

        cut = len(result) > MAX_RESULT_CHARS
        if cut:
            result = result[:MAX_RESULT_CHARS] + "\n[обрезано: сузь запрос]"

        self._journal(session, tool, resource, "allow", args, secrets=secrets, cut=cut)
        return {"status": "ok", "result": result}

    def _refuse(self, session, tool, resource, decision, detail=""):
        self._journal(session, tool, resource, decision, {}, detail=detail)
        return {"status": decision, "detail": detail, "hint": HINTS.get(decision, HINTS["deny"])}

    def _journal(self, session, tool, resource, decision, args, **extra):
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "role": session["role"],
            "profile": session["profile"],
            "tool": tool,
            "resource": resource,
            "decision": decision,
        }
        if tool == "web_search" and "query" in args:
            record["query"] = args["query"]
        record.update({k: v for k, v in extra.items() if v})
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def self_test(gateway):
    """Проверка при старте: запрещённое действие должно быть отклонено.
    Если шлюз пропустил его, защита не работает и агент не запускается."""
    session = {"role": "lead", "profile": "day", "flags": set()}
    tools = dict(gateway.tools)
    tools["__canary_push"] = {"action": "git.push"}
    canary = Gateway(gateway.rules, tools, {"__canary_push": lambda: "pushed"}, gateway.journal_path)
    answer = canary.call(session, "__canary_push", {})
    return answer["status"] == "deny"
