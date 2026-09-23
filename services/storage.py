"""JSON persistence for a local, single-process hackathon demo."""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit
from uuid import uuid4

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_LOCK = RLock()


def _collection_path(collection):
    if not isinstance(collection, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", collection):
        raise ValueError("Invalid collection name.")
    return DATA_DIR / f"{collection}.json"


def load_records(collection):
    path = _collection_path(collection)
    with DATA_LOCK:
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as file:
            records = json.load(file)
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError(f"{path.name} must contain a JSON list of objects.")
    return records


def save_records(collection, records):
    path = _collection_path(collection)
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError("Records must be a list of objects.")
    # Serialize before touching disk: invalid values cannot corrupt the saved file.
    payload = json.dumps(records, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    with DATA_LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=DATA_DIR,
                                             prefix=f".{collection}-", suffix=".tmp",
                                             delete=False) as file:
                temporary = Path(file.name)
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


def add_record(collection, values):
    with DATA_LOCK:
        records = load_records(collection)
        record = {**values, "id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat()}
        records.append(record)
        save_records(collection, records)
        return record


def update_record(collection, record_id, values):
    with DATA_LOCK:
        records = load_records(collection)
        for record in records:
            if record["id"] == record_id:
                record.update({key: value for key, value in values.items()
                               if key not in {"id", "created_at"}})
                record["updated_at"] = datetime.now(timezone.utc).isoformat()
                save_records(collection, records)
                return record
    raise ValueError("Record not found.")


def validate_url(value):
    """Validate an optional public web link without fetching its contents."""
    if not isinstance(value, str):
        raise ValueError("Use a valid http:// or https:// URL.")
    value = value.strip()
    if not value:
        return ""
    try:
        parts = urlsplit(value)
        valid = (parts.scheme in {"http", "https"} and parts.hostname
                 and not parts.username and not parts.password
                 and not any(character.isspace() for character in value))
        parts.port  # Reject malformed port numbers as well.
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Use a valid http:// or https:// URL.")
    return value


def submit_proposal(task_id, values):
    cleaned = dict(values)
    for field in ("team_name", "solution_idea", "plan", "estimated_time"):
        value = cleaned.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Team name, solution idea, plan, and estimated time are required.")
        cleaned[field] = value.strip()
    cleaned["prototype_url"] = validate_url(cleaned.get("prototype_url", ""))
    with DATA_LOCK:
        if not any(task["id"] == task_id for task in load_records("tasks")):
            raise ValueError("This task no longer exists.")
        teams = load_records("teams")
        name = cleaned["team_name"]
        team = next((team for team in teams if team["name"].casefold() == name.casefold()), None)
        if team is None:
            team = add_record("teams", {"name": name})
        return add_record("proposals", {**cleaned, "team_name": team["name"],
                                       "team_id": team["id"], "task_id": task_id, "status": "Pending"})


def review_proposal(proposal_id, status):
    if status not in ("Accepted", "Rejected"):
        raise ValueError("Choose Accepted or Rejected.")
    with DATA_LOCK:
        proposals = load_records("proposals")
        for proposal in proposals:
            if proposal["id"] == proposal_id:
                if status == "Rejected" and proposal.get("status") == "Accepted":
                    engagement = next((record for record in load_records("engagements")
                                       if record.get("team_id") == proposal.get("team_id")
                                       and record.get("task_id") == proposal.get("task_id")), None)
                    if engagement and (engagement.get("milestones") or engagement.get("delivery")
                                       or engagement.get("review")):
                        raise ValueError("Work has already started. Review its delivery in the workspace.")
                proposal["status"] = status
                save_records("proposals", proposals)
                return proposal
    raise ValueError("Proposal not found.")
