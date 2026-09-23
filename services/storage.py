"""JSON persistence for a local, single-process hackathon demo."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_records(collection):
    path = DATA_DIR / f"{collection}.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        records = json.load(file)
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError(f"{path.name} must contain a JSON list of objects.")
    return records


def save_records(collection, records):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{collection}.json"
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2, ensure_ascii=False)
        file.write("\n")
    os.replace(temporary, path)


def add_record(collection, values):
    records = load_records(collection)
    record = {**values, "id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat()}
    records.append(record)
    save_records(collection, records)
    return record


def submit_proposal(task_id, values):
    if not any(task["id"] == task_id for task in load_records("tasks")):
        raise ValueError("This task no longer exists.")
    teams = load_records("teams")
    name = values["team_name"].strip()
    team = next((team for team in teams if team["name"].casefold() == name.casefold()), None)
    if team is None:
        team = add_record("teams", {"name": name})
    return add_record("proposals", {**values, "team_name": team["name"],
                                   "team_id": team["id"], "task_id": task_id, "status": "Pending"})


def review_proposal(proposal_id, status):
    if status not in ("Accepted", "Rejected"):
        raise ValueError("Choose Accepted or Rejected.")
    proposals = load_records("proposals")
    for proposal in proposals:
        if proposal["id"] == proposal_id:
            proposal["status"] = status
            save_records("proposals", proposals)
            return
    raise ValueError("Proposal not found.")
