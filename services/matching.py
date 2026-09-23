"""Explanatory recommendations. They never gate access or make a decision."""
import re

def interpretations(description):
    text = description.casefold()
    if any(word in text for word in ("отзыв", "review", "feedback")):
        return [
            ("Обзор для руководителя", "Дашборд с темами и тональностью отзывов для принятия решений."),
            ("Помощь с ответами", "Черновики ответов на отзывы, которые сотрудник проверяет перед отправкой."),
            ("Срочные сигналы", "Уведомления ответственному сотруднику о негативных отзывах для быстрого реагирования."),
        ]
    if any(word in text for word in ("продаж", "склад", "запас", "waste", "sales")):
        return [("Понять причины", "Отчёт с причинами потерь и рекомендациями для руководителя."),
                ("Планировать", "Прототип прогноза спроса с проверкой на исторических данных."),
                ("Управлять процессом", "Инструмент контроля операций и уведомлений для сотрудников.")]
    return [("Увидеть картину", "Аналитический отчёт или дашборд для принятия решений."),
            ("Помочь сотруднику", "Интерактивный помощник с проверкой ответа человеком."),
            ("Автоматизировать шаг", "Прототип автоматизации повторяющегося шага с ручным контролем.")]

ALIASES = {"ml": "machine learning", "ии": "ai", "javascript": "js", "react.js": "react", "реакт": "react", "питон": "python"}
def normalized(value):
    value = value.strip().casefold()
    return ALIASES.get(value, value)

def skill_match(task, team):
    required = list(dict.fromkeys(task.get("required_skills", [])))
    owned = {normalized(s) for s in team.get("skills", [])}
    matched = [s for s in required if normalized(s) in owned]
    return {"percent": round(100 * len(matched) / len(required)) if required else None, "matched": matched, "missing": [s for s in required if s not in matched]}

SIGNALS = {
    "уведомления": ("уведом", "alert", "сроч", "notify"),
    "отчёт": ("отчёт", "отчет", "report", "еженедель"),
    "дашборд": ("дашборд", "dashboard"),
    "ответы клиентам": ("ответ", "reply", "response"),
    "прогноз": ("прогноз", "forecast", "predict"),
}
def expectation_check(task, proposal):
    expected = " ".join(task.get(k, "") for k in ("expected_result", "success_criteria"))
    offered = proposal.get("definition_of_done", "")
    if not expected.strip() or not offered.strip():
        return {"message": "Недостаточно сведений для сравнения. Уточните ожидаемый результат и критерии.", "missing": [], "common": []}
    def tags(text):
        return {tag for tag, words in SIGNALS.items() if any(word in text.casefold() for word in words)}
    business, team = tags(expected), tags(offered)
    missing = sorted(business - team)
    return {"message": "Возможное расхождение: команда не упомянула " + ", ".join(missing) + ". Обсудите это до выбора." if missing else "Явных расхождений по ключевым словам не найдено. Это не подтверждение соответствия: сравните критерии вручную.", "missing": missing, "common": sorted(business & team)}

def task_markdown(task):
    from services.scoring import FIELDS, task_readiness
    score = task_readiness(task)
    lines = [f"# {task['title']}", "", f"{score['score']}/100 · {score['level']} · {task.get('topic', '')}", ""]
    for key, label, *_ in FIELDS:
        lines += [f"## {label}", task.get(key) or "Не указано", ""]
    return "\n".join(lines)
