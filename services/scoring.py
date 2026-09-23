"""Transparent completion-based readiness scoring; no AI required."""

FIELDS = [
    ("context", "Context", 10, "Describe the business situation and current process."),
    ("need", "Need", 10, "Explain the problem and why it matters."),
    ("data_materials", "Data/materials", 20, "List available datasets, documents, or examples and how to access them."),
    ("expected_result", "Expected result", 15, "Name the deliverable students should produce."),
    ("success_criteria", "Success criteria", 15, "Define measurable criteria for a successful result."),
    ("constraints", "Constraints", 10, "Specify the deadline, budget, tools, and privacy limits."),
    ("users", "Users", 10, "Identify who will use the result and their needs."),
    ("contact", "Business contact", 10, "Provide a contact and explain how students can ask questions."),
]


def readiness_level(score):
    if score < 40:
        return "Draft"
    if score < 70:
        return "Working"
    if score < 90:
        return "Ready"
    return "Priority"


def calculate_readiness(task):
    breakdown = []
    missing = []
    suggestions = []
    for key, label, weight, suggestion in FIELDS:
        points = weight if task.get(key, "").strip() else 0
        breakdown.append({"Category": label, "Points": points, "Maximum": weight})
        if not points:
            missing.append(label)
            suggestions.append(f"{suggestion} (+{weight} points)")
    # Present the combined category with the requested 20-point weighting.
    breakdown = [{"Category": "Context and need", "Points": sum(row["Points"] for row in breakdown[:2]), "Maximum": 20}] + breakdown[2:]
    score = sum(row["Points"] for row in breakdown)
    return {"score": score, "level": readiness_level(score), "breakdown": breakdown,
            "missing": missing, "suggestions": suggestions}
