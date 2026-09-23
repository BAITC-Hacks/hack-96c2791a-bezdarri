"""Deterministic, evidence-confirmed readiness. AI never awards catalog points."""
import re

FIELDS = [
    ("context", "Контекст", 10, "Опишите текущий процесс и ситуацию."),
    ("need", "Потребность", 10, "Объясните проблему и необходимое изменение."),
    ("data_materials", "Данные", 20, "Укажите материалы, источник и порядок доступа."),
    ("expected_result", "Ожидаемый результат", 15, "Назовите конкретный результат работы команды."),
    ("success_criteria", "Критерии успеха", 15, "Укажите измеримый способ приёмки результата."),
    ("constraints", "Ограничения", 10, "Укажите сроки, технологии, доступы или другие границы."),
    ("users", "Пользователи", 10, "Укажите, кто будет пользоваться решением."),
    ("contact", "Контакт", 5, "Укажите контакт представителя бизнеса."),
    ("interaction_format", "Обратная связь", 5, "Укажите формат консультаций и порядок обратной связи."),
]
TASK_KEYS = ["title"] + [row[0] for row in FIELDS]
TOPICS = ["AI", "Web", "Data", "Automation"]
UNKNOWN = {"", "not provided", "not specified", "unknown", "n/a", "none", "no data", "нет данных", "не знаю", "пока не знаю", "не указано", "нет", "tbd", "-", "?"}


def has_value(value):
    return isinstance(value, str) and value.strip().casefold().rstrip(".!?") not in UNKNOWN and bool(re.search(r"\w", value))


def readiness_level(score):
    return "Draft" if score < 40 else "Workable" if score < 70 else "Ready" if score < 90 else "Priority"


def calculate_readiness(task):
    confirmed = set(task.get("confirmed_fields", []))
    rows, missing, suggestions = [], [], []
    for key, label, weight, tip in FIELDS:
        filled = has_value(task.get(key))
        points = weight if filled and key in confirmed else 0
        rows.append({"Категория": label, "Баллы": points, "Максимум": weight})
        if not points:
            missing.append(label)
            action = tip if not filled else f"Подтвердите поле «{label}»."
            suggestions.append(f"+{weight} · {action}")
    rows = [{"Категория": "Контекст и потребность", "Баллы": sum(r["Баллы"] for r in rows[:2]), "Максимум": 20}] + rows[2:-2] + [{"Категория": "Связь с бизнесом", "Баллы": sum(r["Баллы"] for r in rows[-2:]), "Максимум": 10}]
    score = sum(row["Баллы"] for row in rows)
    return {"score": score, "level": readiness_level(score), "breakdown": rows, "missing": missing, "suggestions": suggestions, "source": "Баллы за заполненные и подтверждённые поля · единая шкала для всех задач"}


def task_readiness(task):
    return calculate_readiness(task)
