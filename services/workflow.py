"""Independent team deliveries and an auditable XP ledger for the local demo.

An engagement belongs to a (team, task) pair, rather than a proposal. Submitting
another proposal therefore cannot reset milestones or earn a second review.
All changes to an engagement and its XP events are one atomic JSON write.
"""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from services import storage

REVIEW_XP = {1: -20, 2: -10, 3: 0, 4: 20, 5: 40}
MILESTONE_XP = 10
MAX_MILESTONES = 2


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, label, maximum=12000):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required.")
    if len(value.strip()) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters.")
    return value.strip()


def _context(proposal_id, require_accepted=True):
    proposal = next((row for row in storage.load_records("proposals")
                     if row["id"] == proposal_id), None)
    if proposal is None:
        raise ValueError("Proposal not found.")
    if require_accepted and proposal.get("status") != "Accepted":
        raise ValueError("The business must accept this proposal before work can begin.")
    task = next((row for row in storage.load_records("tasks")
                 if row["id"] == proposal["task_id"]), None)
    team = next((row for row in storage.load_records("teams")
                 if row["id"] == proposal["team_id"]), None)
    if task is None or team is None:
        raise ValueError("The task or team no longer exists.")
    return proposal, task


def _engagement(records, proposal, task):
    existing = next((row for row in records
                     if row["team_id"] == proposal["team_id"]
                     and row["task_id"] == proposal["task_id"]), None)
    if existing is not None:
        return existing
    record = {
        "id": str(uuid4()), "proposal_id": proposal["id"],
        "team_id": proposal["team_id"], "task_id": proposal["task_id"],
        "status": "In progress", "milestones": [], "delivery": None,
        "delivery_history": [], "review": None, "events": [],
        # The basis agreed when work starts stays visible after task edits.
        "success_criteria": task.get("success_criteria", ""),
        "expected_result": task.get("expected_result", ""),
        "definition_of_done": proposal.get("definition_of_done", ""),
        "created_at": _now(),
    }
    records.append(record)
    return record


def get_engagement(proposal_id):
    """Read work without writing merely because someone opened a page."""
    with storage.DATA_LOCK:
        proposal, task = _context(proposal_id, require_accepted=False)
        return _engagement(storage.load_records("engagements"), proposal, task)


def _working(record):
    if record.get("review") or record["status"] in {"Accepted", "Completed"}:
        raise ValueError("This delivery has already been accepted; its work is locked.")
    if record["status"] == "Delivery submitted":
        raise ValueError("Wait for the business to accept the delivery or request a revision.")


def _persist(records, record):
    record["updated_at"] = _now()
    storage.save_records("engagements", records)
    return deepcopy(record)


def submit_milestone(proposal_id, title, evidence):
    title = _text(title, "Milestone title", 200)
    evidence = _text(evidence, "Evidence of completed work")
    with storage.DATA_LOCK:
        proposal, task = _context(proposal_id)
        records = storage.load_records("engagements")
        record = _engagement(records, proposal, task)
        _working(record)
        if any(row["title"] == title and row["evidence"] == evidence
               for row in record["milestones"]):
            return record
        if len(record["milestones"]) >= MAX_MILESTONES:
            raise ValueError("A team can submit at most two milestones for one task.")
        record["milestones"].append({"id": str(uuid4()), "title": title,
                                     "evidence": evidence, "status": "Submitted",
                                     "created_at": _now()})
        return _persist(records, record)


def _ledger(records, team_id):
    events = []
    for record in records:
        if record["team_id"] != team_id:
            continue
        for event in record.get("events", []):
            events.append({**event, "task_id": record["task_id"],
                           "proposal_id": record["proposal_id"]})
    # A monotonic sequence captures the order committed under the data lock,
    # including events whose wall clock timestamps happen to be identical.
    events.sort(key=lambda event: (event.get("sequence", 0), event["created_at"], event["id"]))
    balance = 0
    for event in events:
        event["xp_before"] = balance
        balance = max(0, balance + event["xp_delta"])
        event["xp_after"] = balance
        event["xp_applied"] = balance - event["xp_before"]
    return events


def _add_event(records, record, kind, xp_delta, **details):
    sequence = 1 + max((event.get("sequence", 0) for row in records
                        for event in row.get("events", [])), default=0)
    event = {"id": str(uuid4()), "kind": kind, "xp_delta": xp_delta,
             "created_at": _now(), "sequence": sequence, **details}
    record["events"].append(event)
    return _ledger(records, record["team_id"])[-1]


def confirm_milestone(proposal_id, milestone_id):
    with storage.DATA_LOCK:
        proposal, task = _context(proposal_id)
        records = storage.load_records("engagements")
        record = _engagement(records, proposal, task)
        milestone = next((row for row in record["milestones"]
                          if row["id"] == milestone_id), None)
        if milestone is None:
            raise ValueError("Milestone not found for this team and task.")
        if milestone["status"] == "Confirmed":
            return record
        if record.get("review"):
            raise ValueError("This task has already received its final review.")
        if sum(row["status"] == "Confirmed" for row in record["milestones"]) >= MAX_MILESTONES:
            raise ValueError("Only two milestones can earn XP for one task.")
        milestone["status"] = "Confirmed"
        milestone["confirmed_at"] = _now()
        _add_event(records, record, "milestone", MILESTONE_XP,
                   milestone_id=milestone_id, title=milestone["title"])
        return _persist(records, record)


def submit_delivery(proposal_id, summary, url=""):
    summary = _text(summary, "Delivery summary")
    url = storage.validate_url(url)
    with storage.DATA_LOCK:
        proposal, task = _context(proposal_id)
        records = storage.load_records("engagements")
        record = _engagement(records, proposal, task)
        existing = record.get("delivery")
        if (existing and existing["status"] == "Submitted"
                and existing["summary"] == summary and existing["url"] == url):
            return record
        _working(record)
        version = 1
        if existing:
            version = existing.get("version", 1) + 1
            record.setdefault("delivery_history", []).append(deepcopy(existing))
        record["delivery"] = {"summary": summary, "url": url, "status": "Submitted",
                               "submitted_at": _now(), "version": version}
        record["status"] = "Delivery submitted"
        return _persist(records, record)


def request_revision(proposal_id, feedback):
    feedback = _text(feedback, "Revision feedback")
    with storage.DATA_LOCK:
        proposal, task = _context(proposal_id)
        records = storage.load_records("engagements")
        record = _engagement(records, proposal, task)
        delivery = record.get("delivery")
        if delivery and delivery["status"] == "Revision requested" and delivery.get("feedback") == feedback:
            return record
        if not delivery or delivery["status"] != "Submitted" or record.get("review"):
            raise ValueError("Only a submitted delivery can be returned for revision.")
        delivery["status"] = "Revision requested"
        delivery["feedback"] = feedback
        delivery["revision_requested_at"] = _now()
        record["status"] = "Revision requested"
        return _persist(records, record)


def accept_delivery(proposal_id):
    with storage.DATA_LOCK:
        proposal, task = _context(proposal_id)
        records = storage.load_records("engagements")
        record = _engagement(records, proposal, task)
        delivery = record.get("delivery")
        if delivery and delivery["status"] == "Accepted":
            return record
        if not delivery or delivery["status"] != "Submitted":
            raise ValueError("A submitted delivery is required before acceptance.")
        delivery["status"] = "Accepted"
        delivery["accepted_at"] = _now()
        record["status"] = "Accepted"
        return _persist(records, record)


def leave_review(proposal_id, rating, comment, criterion_feedback=""):
    if isinstance(rating, bool) or not isinstance(rating, int) or rating not in REVIEW_XP:
        raise ValueError("Choose a rating from 1 to 5 stars.")
    comment = _text(comment, "Review comment")
    if not isinstance(criterion_feedback, str):
        raise ValueError("Criterion feedback must be text.")
    criterion_feedback = criterion_feedback.strip()
    if rating <= 2:
        criterion_feedback = _text(criterion_feedback, "Explain which agreed criterion was not met")
    with storage.DATA_LOCK:
        proposal, task = _context(proposal_id)
        records = storage.load_records("engagements")
        record = _engagement(records, proposal, task)
        existing = record.get("review")
        if existing:
            if (existing["rating"] == rating and existing["comment"] == comment
                    and existing.get("criterion_feedback", "") == criterion_feedback):
                return record
            raise ValueError("Only one final review is allowed for each team and task.")
        if not record.get("delivery") or record["delivery"]["status"] != "Accepted":
            raise ValueError("Accept the team's final delivery before leaving a review.")
        event = _add_event(records, record, "review", REVIEW_XP[rating], rating=rating,
                           title=f"Final review: {rating}/5")
        record["review"] = {"rating": rating, "comment": comment,
                             "criterion_feedback": criterion_feedback,
                             "created_at": event["created_at"], "event_id": event["id"],
                             "xp_delta": REVIEW_XP[rating], "xp_applied": event["xp_applied"]}
        record["status"] = "Completed"
        return _persist(records, record)


def _team_stats(team_id, records, tasks, proposals):
    ledger = _ledger(records, team_id)
    for event in ledger:
        event["task_title"] = tasks.get(event["task_id"], {}).get("title", "Archived task")
    reviews = []
    completed_projects = []
    completed = set()
    for record in records:
        if record["team_id"] != team_id:
            continue
        delivery = record.get("delivery") or {}
        if delivery.get("status") == "Accepted":
            completed.add(record["task_id"])
            completed_projects.append({
                "task_id": record["task_id"],
                "task_title": tasks.get(record["task_id"], {}).get("title", "Archived task"),
                "summary": delivery.get("summary", ""), "url": delivery.get("url", ""),
                "accepted_at": delivery.get("accepted_at", ""),
                "review": deepcopy(record.get("review")),
                "success_criteria": record.get("success_criteria", ""),
            })
        if record.get("review"):
            reviews.append({**record["review"], "task_id": record["task_id"],
                            "task_title": tasks.get(record["task_id"], {}).get("title", "Archived task"),
                            "summary": delivery.get("summary", ""), "url": delivery.get("url", ""),
                            "success_criteria": record.get("success_criteria", "")})
    reviews.sort(key=lambda row: row["created_at"], reverse=True)
    completed_projects.sort(key=lambda row: row["accepted_at"], reverse=True)
    active = {row["task_id"] for row in proposals
              if row.get("team_id") == team_id and row.get("status") == "Accepted"} - completed
    return {"team_id": team_id, "xp": ledger[-1]["xp_after"] if ledger else 0,
            "average_rating": round(sum(row["rating"] for row in reviews) / len(reviews), 2) if reviews else None,
            "completed_tasks": len(completed), "review_count": len(reviews),
            "confirmed_milestones": sum(event["kind"] == "milestone" for event in ledger),
            "active_tasks": len(active), "reviews": reviews, "ledger": ledger,
            "completed_projects": completed_projects}


def team_stats(team_id):
    with storage.DATA_LOCK:
        if not any(row["id"] == team_id for row in storage.load_records("teams")):
            raise ValueError("Team not found.")
        return _team_stats(team_id, storage.load_records("engagements"),
                           {row["id"]: row for row in storage.load_records("tasks")},
                           storage.load_records("proposals"))


def leaderboard():
    with storage.DATA_LOCK:
        records = storage.load_records("engagements")
        tasks = {row["id"]: row for row in storage.load_records("tasks")}
        proposals = storage.load_records("proposals")
        teams = [{**team, **_team_stats(team["id"], records, tasks, proposals)}
                 for team in storage.load_records("teams")]
    return sorted(teams, key=lambda row: (-row["xp"], -row["completed_tasks"], row["name"].casefold()))


def _tags(values, label):
    if isinstance(values, str):
        values = values.split(",")
    if not isinstance(values, (list, tuple)) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"{label} must be a list or comma-separated text.")
    result = []
    seen = set()
    for value in values:
        value = value.strip()
        if value and value.casefold() not in seen:
            if len(value) > 60:
                raise ValueError(f"Each {label.lower()} entry must be at most 60 characters.")
            result.append(value)
            seen.add(value.casefold())
    if len(result) > 20:
        raise ValueError(f"Use at most 20 {label.lower()} entries.")
    return result


def update_team_profile(team_id, about, skills, interests):
    if not isinstance(about, str) or len(about.strip()) > 3000:
        raise ValueError("Team description must be text of at most 3000 characters.")
    return storage.update_record("teams", team_id, {
        "about": about.strip(), "skills": _tags(skills, "Skills"),
        "interests": _tags(interests, "Interests"),
    })
