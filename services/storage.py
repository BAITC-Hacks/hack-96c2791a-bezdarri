"""Atomic JSON storage, serialized within one Streamlit server process."""
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

from services.scoring import TASK_KEYS, TOPICS, has_value, task_readiness

DATA_DIR = Path(os.environ.get("TASKFORGE_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
LOCK = threading.RLock()
COLLECTIONS = {"tasks", "teams", "proposals", "drafts"}
REVIEW_XP = {1: -20, 2: -10, 3: 0, 4: 20, 5: 40}


def now():
    return datetime.now(timezone.utc).isoformat()


def load_records(collection):
    if collection not in COLLECTIONS:
        raise ValueError("Неизвестная коллекция.")
    path = DATA_DIR / f"{collection}.json"
    with LOCK:
        if not path.exists():
            return []
        records = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise ValueError(f"{path.name}: ожидается список объектов.")
        return records


def save_records(collection, records):
    if collection not in COLLECTIONS:
        raise ValueError("Неизвестная коллекция.")
    with LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / f"{collection}.json"
        temporary = path.with_suffix(f".{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            # Windows indexers can briefly hold a recently read JSON file.
            for attempt in range(6):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            temporary.unlink(missing_ok=True)


def add_record(collection, values):
    with LOCK:
        records = load_records(collection)
        record = {**values, "id": str(uuid4()), "created_at": now()}
        records.append(record)
        save_records(collection, records)
        return record


def valid_url(value):
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.hostname) and not parsed.username and not any(c.isspace() for c in value)
    except ValueError:
        return False


def publish_task(values, confirmed=False, task_id=None):
    if not confirmed:
        raise ValueError("Перед публикацией подтвердите карточку.")
    if not has_value(values.get("title")):
        raise ValueError("Укажите название задачи.")
    if values.get("topic") not in TOPICS:
        raise ValueError("Выберите тему задачи.")
    task = {k: str(values.get(k, "")).strip() for k in TASK_KEYS}
    task.update({k: values.get(k, default) for k, default in (("topic", "AI"), ("required_skills", []), ("original_description", ""), ("owner", "Demo Business"))})
    task["confirmed_fields"] = [k for k in values.get("confirmed_fields", []) if k in TASK_KEYS and has_value(task.get(k))]
    task.update(published=True, confirmed_at=now(), updated_at=now())
    score = task_readiness(task)
    task.update(readiness_score=score["score"], readiness_level=score["level"])
    with LOCK:
        if not task_id:
            return add_record("tasks", task)
        rows = load_records("tasks")
        old = next((r for r in rows if r["id"] == task_id), None)
        if not old:
            raise ValueError("Задача не найдена.")
        old.update(task)
        save_records("tasks", rows)
        return old


def save_team(name, interests, skills, team_id=None):
    name = name.strip()
    if not name:
        raise ValueError("Укажите название команды.")
    with LOCK:
        teams = load_records("teams")
        duplicate = next((t for t in teams if t["name"].casefold() == name.casefold() and t["id"] != team_id), None)
        if duplicate:
            raise ValueError("Такое название уже занято. Выберите существующий профиль.")
        values = {"name": name, "interests": interests, "skills": list(dict.fromkeys(s.strip() for s in skills if s.strip()))}
        if not team_id:
            return add_record("teams", values)
        team = next((t for t in teams if t["id"] == team_id), None)
        if not team:
            raise ValueError("Команда не найдена.")
        team.update(values)
        save_records("teams", teams)
        return team


def submit_proposal(task_id, values):
    for key in ("team_id", "solution_idea", "plan", "estimated_time", "definition_of_done"):
        if not has_value(values.get(key)):
            raise ValueError("Заполните идею, план, срок и понимание готового результата.")
    url = values.get("prototype_url", "").strip()
    if url and not valid_url(url):
        raise ValueError("Ссылка должна начинаться с http:// или https:// и содержать адрес сайта.")
    with LOCK:
        task = next((t for t in load_records("tasks") if t["id"] == task_id and t.get("published", True)), None)
        team = next((t for t in load_records("teams") if t["id"] == values["team_id"]), None)
        if not task or not team:
            raise ValueError("Задача или команда не найдена.")
        fields = {k: values.get(k, "").strip() for k in ("solution_idea", "plan", "estimated_time", "definition_of_done", "prototype_url")}
        return add_record("proposals", {**fields, "team_name": team["name"], "team_id": team["id"], "task_id": task_id, "status": "Pending", "milestones": [], "submission": None, "review": None, "agreement": {"expected_result": task.get("expected_result", ""), "success_criteria": task.get("success_criteria", "")}})


def _change_proposal(proposal_id, change):
    with LOCK:
        rows = load_records("proposals")
        proposal = next((p for p in rows if p["id"] == proposal_id), None)
        if not proposal:
            raise ValueError("Предложение не найдено.")
        change(proposal)
        save_records("proposals", rows)
        return proposal


def review_proposal(proposal_id, status):
    if status not in ("Accepted", "Rejected"):
        raise ValueError("Выберите Accepted или Rejected.")
    def change(p):
        if p.get("milestones") or p.get("submission") or p.get("review"):
            raise ValueError("Работа уже началась; решение нельзя изменить задним числом.")
        p["status"] = status
        p["decided_at"] = now()
        if status == "Accepted":
            task = next(t for t in load_records("tasks") if t["id"] == p["task_id"])
            p["agreement"] = {k: task.get(k, "") for k in ("expected_result", "success_criteria")}
    return _change_proposal(proposal_id, change)


def confirm_milestone(proposal_id, description, evidence):
    if not has_value(description) or not has_value(evidence):
        raise ValueError("Опишите этап и подтверждение фактического результата.")
    def change(p):
        if p["status"] != "Accepted" or p.get("review"):
            raise ValueError("Этап доступен только выбранной команде до итогового отзыва.")
        # Cap per team/task, even if the same team has multiple accepted proposals.
        siblings = [r for r in load_records("proposals") if r["task_id"] == p["task_id"] and r["team_id"] == p["team_id"]]
        if sum(len(r.get("milestones", [])) for r in siblings) >= 2:
            raise ValueError("За одну задачу команде можно подтвердить не более двух этапов.")
        if any(m["description"].strip().casefold() == description.strip().casefold() for r in siblings for m in r.get("milestones", [])):
            raise ValueError("Этот этап уже подтверждён.")
        p.setdefault("milestones", []).append({"description": description.strip(), "evidence": evidence.strip(), "xp": 10, "at": now()})
    return _change_proposal(proposal_id, change)


def submit_result(proposal_id, summary, url=""):
    if not has_value(summary):
        raise ValueError("Опишите сданный результат.")
    if url and not valid_url(url):
        raise ValueError("Некорректная ссылка на результат.")
    def change(p):
        if p["status"] != "Accepted" or p.get("review"):
            raise ValueError("Сдать результат может выбранная команда до итогового отзыва.")
        p["submission"] = {"summary": summary.strip(), "url": url.strip(), "at": now()}
    return _change_proposal(proposal_id, change)


def leave_review(proposal_id, rating, comment):
    if type(rating) is not int or rating not in REVIEW_XP:
        raise ValueError("Оценка должна быть от 1 до 5.")
    if not has_value(comment):
        raise ValueError("Оставьте итоговый отзыв; при 1–2 ★ укажите причину относительно согласованных критериев.")
    def change(p):
        if p["status"] != "Accepted" or not p.get("submission"):
            raise ValueError("Отзыв доступен только после сдачи результата выбранной командой.")
        siblings = [r for r in load_records("proposals") if r["task_id"] == p["task_id"] and r["team_id"] == p["team_id"]]
        if any(r.get("review") for r in siblings):
            raise ValueError("Для этой команды по задаче уже оставлен итоговый отзыв.")
        p["review"] = {"rating": rating, "comment": comment.strip(), "xp": REVIEW_XP[rating], "at": now()}
    return _change_proposal(proposal_id, change)


def team_stats(team_id):
    proposals = [p for p in load_records("proposals") if p["team_id"] == team_id]
    events, reviews = [], []
    for p in proposals:
        events.extend(p.get("milestones", []))
        if p.get("review"):
            reviews.append({**p["review"], "task_id": p["task_id"]})
            events.append(p["review"])
    balance = 0
    for event in sorted(events, key=lambda e: e["at"]):
        balance = max(0, balance + event["xp"])
    return {"xp": balance, "average": round(sum(r["rating"] for r in reviews) / len(reviews), 1) if reviews else None, "completed": len({r["task_id"] for r in reviews}), "reviews": reviews, "milestones": sum(len(p.get("milestones", [])) for p in proposals), "submitted": len({p["task_id"] for p in proposals if p.get("submission")})}
