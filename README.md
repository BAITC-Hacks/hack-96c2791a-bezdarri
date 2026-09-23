 HEAD
# TaskForge

A beginner-friendly Streamlit hackathon MVP that turns vague business problems into structured student tasks, with optional OpenAI-assisted drafting and quality scoring. Python and JSON persistence; no authentication, database, or Docker.

## Run locally

Requires Python 3.10 or newer. From the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On macOS/Linux, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.
Before starting, edit your local `.env` and set `OPENAI_API_KEY` to your own key. Do not overwrite an existing `.env`. It is ignored by Git. Never put the key in the UI or source code. `OPENAI_MODEL` defaults to `gpt-4o-mini`; use a model available to your account that supports Responses API structured outputs. Calls require API access and billing. Existing environment variables take precedence over `.env`.

Open http://localhost:8501. Stop the server with Ctrl+C. Catalog, proposals, manual reviews, and manual task creation still work without a key. AI actions show a safe configuration error until a key is configured.

## Demo flow

1. **Create Task:** Enter a vague description and click **Analyze with AI**. Review the initial quality score, evidence-based explanations, suggestions, and at least three clarification questions. Answer questions and click **Update task with answers**. The updated editable card and score change appear. You can edit every field and click **Reanalyze edited card**; edits invalidate the previous assessment for publishing. Review the facts, tick the confirmation box, then explicitly **Publish task**. A title is required; low-scoring briefs can still be published. Clicking Analyze with AI again starts a fresh draft from the description.
2. **Catalog:** Browse tasks ordered by score, highest first, or filter by level. Expand a task and submit a team name, solution idea, plan, estimated time, and optional HTTP(S) prototype URL. Existing team names are matched without case sensitivity; new names create team records. Proposals start as Pending.
3. **Business Dashboard:** Review proposals under their tasks and manually Accept or Reject each one. Decisions persist and can be changed. Multiple acceptances are allowed; the application never automatically chooses a team or rejects other proposals.

Five fictional tasks span all four readiness levels, and five fictional teams are included. Contact addresses use `.example`; referenced sample materials are illustrative and are not bundled. Proposals start empty so you can demonstrate the whole flow.

## Readiness scoring

AI evaluates quality and completeness using the rubric below. Vague mentions receive low credit; specific, actionable information earns more. Each category includes awarded points, its maximum, an explanation, and an improvement suggestion. Missing categories earn zero. Context and need each account for up to 10 points. The title does not contribute to readiness. AI scores are subjective and may vary between calls; improvement is never forced.

| Category | Points |
| --- | ---: |
| Context and need | 20 |
| Data/materials | 20 |
| Expected result | 15 |
| Success criteria | 15 |
| Constraints | 10 |
| Users | 10 |
| Business contact/interaction format | 10 |

Levels: **Draft** 0–39, **Working** 40–69, **Ready** 70–89, **Priority** 90–100. Published AI assessments, including breakdowns, are saved with the task. The catalog uses these saved scores for display, sorting, and filtering, with all levels visible by default. Browsing, publishing, and proposal decisions do not call AI.

Existing seed tasks and tasks created without AI retain the original completion checklist, explicitly labeled **Completion checklist (not AI quality scoring)**. They are not silently converted into AI assessments.

## AI behavior and validation

The integration uses the [OpenAI Responses API with Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). The description, current card, and submitted answers are sent only when an AI button is clicked, with response storage disabled (`store=False`). No API key is included in prompts, JSON records, or UI messages. Errors use fixed messages and do not display raw provider responses.

AI may summarize and paraphrase supplied information, including the title, but must not introduce new factual claims. Unknowns stay blank, are listed as missing, and receive clarification questions (at least three when three or more fields need clarification). Local validation rejects obvious unsupported email addresses, URLs, and numeric facts while allowing ordinary rewording. These checks do not establish semantic truth or catch every unsupported claim, so the prompt forbids invention and the business must review and confirm the facts.

Validation also checks exact categories and maxima, integer scores within bounds, zero points for absent categories, score arithmetic, readiness level, question count, and missing-field coverage. Invalid/incomplete responses, refusals, and API failures preserve the previous draft. Reanalysis of manual edits must return that exact card unchanged. The initial and previous scores are held in session state; drafts survive sidebar navigation but are not saved across a server restart or new browser session.

## Project structure

```text
app.py                 # Sidebar navigation and three pages
requirements.txt       # Streamlit, OpenAI SDK, python-dotenv
.env.example           # API key and model configuration template
.gitignore
README.md
data/
  tasks.json           # Published tasks
  teams.json           # Seed teams and newly submitted team names
  proposals.json       # Proposals and manual review status
services/
  __init__.py
  scoring.py           # Checklist weights, levels, and suggestions
  ai.py                # Structured API call, grounding and rubric validation
  storage.py           # JSON reads, writes, and record operations
```

Data paths are relative to the project, independent of the working directory. Writes replace each file atomically to reduce partial-write risk. Invalid JSON produces an error instead of silently replacing existing data. This local demo is intended for one server and sequential use; it does not coordinate simultaneous writers. With no authentication, every visitor can access the dashboard, so use synthetic information only.

## Verify the MVP

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use temporary copies of JSON files and mock HTTP responses through the real OpenAI SDK; no key, API charges, or external requests are required. They cover the original manual flow and the complete AI draft → questions → answers → improved score → manual edits → reanalysis → confirmation → publication → catalog → proposal → Accept/Reject scenario, plus malformed responses and API failures. Mock tests verify the integration and state transitions, not live model output quality.

For a live smoke test after configuring your key, enter: "We run an online clothing store and many customers abandon their carts. We want students to help us understand why." Verify unknown data, metrics, constraints, and contact stay empty. Answer questions with actual specifics (for example, available anonymized CSV data, a deadline, a deliverable, a measurable criterion, and a contact format), reanalyze, review the score explanation, and publish only after confirming the facts. Then submit a proposal in Catalog and manually review it in Business Dashboard.
4a055f2 (Complete AI analysis and clarification flow)
