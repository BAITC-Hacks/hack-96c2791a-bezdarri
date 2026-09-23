"""Run with: python -m streamlit run app.py"""

from urllib.parse import urlparse
import logging

import streamlit as st

from services.ai import AIError, TASK_KEYS, analyze_task
from services.scoring import FIELDS, task_readiness
from services.storage import add_record, load_records, review_proposal, submit_proposal

st.set_page_config(page_title="TaskForge", page_icon="🛠️", layout="wide")

# Temporary local diagnostics: state transitions only, never prompts or credentials.
logger = logging.getLogger("taskforge.ui")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False


def show_readiness(task):
    result = task_readiness(task)
    st.caption(result["source"])
    st.metric("Readiness score", f"{result['score']}/100", result["level"], delta_color="off")
    st.progress(result["score"] / 100)
    st.table(result["breakdown"])
    if result["missing"]:
        st.warning("Missing information: " + ", ".join(result["missing"]))
        st.markdown("**Suggestions for increasing the score**")
        for suggestion in result["suggestions"]:
            st.write("• " + suggestion)
    elif not task.get("ai_analysis"):
        st.success("All readiness fields are filled in. Review the detail with the business contact.")
    return result


def save_card_edit(key):
    st.session_state.draft[key] = st.session_state[f"card_{key}"].strip()
    st.session_state.confirm_publish = False


def run_analysis(mode):
    """Save results before spinner cleanup can yield to a queued widget rerun."""
    state = st.session_state
    logger.info("Analyze button triggered: mode=%s", mode)
    description = state.get("business_description", "").strip()
    if mode == "draft" and not description:
        state.ai_error = "Enter a business problem first."
        return
    answers = list(state.get("answer_history", []))
    if mode == "clarify":
        new_answers = [{**q, "answer": state.get(f"answer_{state.analysis_version}_{i}", "").strip()}
                       for i, q in enumerate(state.analysis["questions"])]
        new_answers = [answer for answer in new_answers if answer["answer"]]
        if not new_answers:
            state.ai_error = "Answer at least one clarification question first."
            return
        answers.extend(new_answers)
    source_description = description if mode == "draft" else state.get("analyzed_description", "")
    current_card = None if mode == "draft" else dict(state.draft)
    # Capture a session-owned object before the API call. Mutating this object does
    # not yield to Streamlit, unlike accessing st.session_state after the call.
    job = {"mode": mode, "description": description, "answers": answers}
    state.analysis_job = job
    with st.spinner("Analyzing the business brief…"):
        try:
            result = analyze_task(source_description, [] if mode == "draft" else answers, current_card, mode)
        except AIError as error:
            job["error"] = str(error)
            logger.info("Analysis failed; preserving current draft and prior result")
        else:
            job["result"] = result
            logger.info("Result stored in session_state job: questions=%s score=%s",
                        len(result["questions"]), result["scoring"]["total_score"])


def apply_analysis_result():
    """Apply a completed request once, before any editable widgets are rendered."""
    state = st.session_state
    job = state.get("analysis_job", {})
    if "error" in job:
        state.ai_error = job["error"]
        state.analysis_job = {}
        return
    if "result" not in job:
        return
    result, mode = job["result"], job["mode"]
    previous = state.get("analysis")
    state.previous_score = previous["scoring"]["total_score"] if previous and mode != "draft" else None
    state.analysis = result
    state.draft = dict(result["task"])
    state.answer_history = [] if mode == "draft" else job["answers"]
    if mode == "draft":
        state.analyzed_description = job["description"]
    state.analysis_version = state.get("analysis_version", 0) + 1
    state.confirm_publish = False
    state.ai_error = None
    state.analysis_job = {}
    logger.info("Result stored in session_state: version=%s questions=%s score=%s",
                state.analysis_version, len(result["questions"]), result["scoring"]["total_score"])


def create_task():
    st.header("Create Task")
    state = st.session_state
    if "draft" not in state:
        state.draft = {key: "" for key in TASK_KEYS}
    apply_analysis_result()
    st.subheader("Quick AI draft")
    st.caption("Describe the problem in your own words. AI uses only supplied facts; unknowns stay blank. Review every field before publishing.")
    # Keep the draft across sidebar navigation; widget state alone is discarded by Streamlit.
    if "business_description" not in state:
        state.business_description = state.get("saved_description", "")
    st.text_area("Business problem", key="business_description", placeholder="We run an online clothing store and many customers abandon their carts…",
                 on_change=lambda: state.update(saved_description=state.business_description))
    st.button("Analyze with AI", key="analyze", on_click=run_analysis, args=("draft",))
    if state.get("ai_error"):
        st.error(state.ai_error)
    analysis = state.get("analysis")
    logger.info("Rendering section reached: analysis_present=%s", analysis is not None)
    if analysis:
        st.subheader("Clarification questions")
        with st.form(f"clarifications_{state.analysis_version}"):
            for i, question in enumerate(analysis["questions"]):
                st.text_area(question["question"], key=f"answer_{state.analysis_version}_{i}")
            st.form_submit_button("Update task with answers", on_click=run_analysis, args=("clarify",))
    st.subheader("Editable task card")
    labels = {"title": "Title", "data_materials": "Data/materials", "contact": "Contact/interaction format"}
    for key in ("title", "context", "need", "users", "data_materials", "constraints", "expected_result", "success_criteria", "contact"):
        state[f"card_{key}"] = state.draft[key]
        widget = st.text_input if key == "title" else st.text_area
        widget(labels.get(key, key.replace("_", " ").capitalize()), key=f"card_{key}",
               on_change=save_card_edit, args=(key,))
    task = dict(state.draft)
    st.button("Reanalyze edited card", key="rescore", on_click=run_analysis, args=("rescore",))
    stale = bool(analysis and task != analysis["task"])
    if analysis:
        if state.get("previous_score") is not None:
            before, after = state.previous_score, analysis["scoring"]["total_score"]
            st.metric("Readiness improvement" if not stale else "Last assessed improvement", f"{before} → {after}", f"{after - before:+d} points")
        if stale:
            st.warning("The card has changed. The assessment below is for the previous version. Reanalyze the edited card before publishing.")
        result = show_readiness({**analysis["task"], "ai_analysis": analysis})
        confirmed = st.checkbox("I reviewed the task card and confirm its business facts.", key="confirm_publish")
    else:
        st.caption("You can also create a task manually. Until AI analysis succeeds, this is a completion checklist, not a quality score.")
        result = show_readiness(task)
        confirmed = True
    if st.button("Publish task", key="publish", type="primary", disabled=stale or not confirmed):
        if not task["title"]:
            st.error("Enter a title before publishing.")
        else:
            values = {**task, "readiness_score": result["score"], "readiness_level": result["level"]}
            if analysis:
                values["ai_analysis"] = analysis
            add_record("tasks", values)
            st.success("Task published. Open Catalog to view it.")


def proposal_form(task_id):
    with st.form(f"proposal_{task_id}", clear_on_submit=False):
        st.subheader("Submit a team proposal")
        values = {
            "team_name": st.text_input("Team name"),
            "solution_idea": st.text_area("Solution idea"),
            "plan": st.text_area("Plan"),
            "estimated_time": st.text_input("Estimated time", placeholder="e.g. 2 weeks, 20 hours"),
            "prototype_url": st.text_input("Prototype URL (optional)", placeholder="https://example.com/demo"),
        }
        submitted = st.form_submit_button("Submit proposal")
    if submitted:
        values = {key: value.strip() for key, value in values.items()}
        if any(not values[key] for key in ("team_name", "solution_idea", "plan", "estimated_time")):
            st.error("Fill in team name, solution idea, plan, and estimated time.")
            return
        url = urlparse(values["prototype_url"])
        if values["prototype_url"] and (url.scheme not in ("http", "https") or not url.netloc):
            st.error("Prototype URL must be a valid http:// or https:// link.")
            return
        submit_proposal(task_id, values)
        st.success("Proposal submitted as Pending. The business will review it manually.")


def catalog():
    st.header("Catalog")
    level = st.selectbox("Readiness level", ["All", "Draft", "Working", "Ready", "Priority"])
    tasks = sorted(load_records("tasks"), key=lambda task: task_readiness(task)["score"], reverse=True)
    tasks = [task for task in tasks if level == "All" or task_readiness(task)["level"] == level]
    if not tasks:
        st.info("No published tasks match this filter.")
    for task in tasks:
        result = task_readiness(task)
        with st.expander(f"{task['title']} — {result['score']}/100 · {result['level']}"):
            for key, label, _, _ in FIELDS:
                st.markdown(f"**{label}**")
                st.write(task.get(key) or "Not provided")
            show_readiness(task)
            proposal_form(task["id"])
    teams = load_records("teams")
    with st.expander(f"Student teams ({len(teams)})"):
        for team in teams:
            st.write(team["name"])
        st.caption("Use an existing team name or enter a new one when submitting a proposal.")


def dashboard():
    st.header("Business Dashboard")
    st.caption("Every decision is manual. Accepting a proposal does not reject or select any other team. You can change a decision using the buttons below.")
    tasks = load_records("tasks")
    proposals = load_records("proposals")
    if not tasks:
        st.info("Publish a task to start receiving proposals.")
    for task in tasks:
        st.subheader(task["title"])
        matches = [proposal for proposal in proposals if proposal["task_id"] == task["id"]]
        if not matches:
            st.info("No proposals yet.")
        for proposal in matches:
            with st.container(border=True):
                st.markdown(f"**{proposal['team_name']} · {proposal['status']}**")
                for key, label in (("solution_idea", "Solution idea"), ("plan", "Plan"), ("estimated_time", "Estimated time"), ("prototype_url", "Prototype URL")):
                    st.markdown(f"**{label}**")
                    st.write(proposal.get(key) or "Not provided")
                accept, reject = st.columns(2)
                if accept.button("Accept", key=f"accept_{proposal['id']}", disabled=proposal["status"] == "Accepted"):
                    review_proposal(proposal["id"], "Accepted")
                    st.rerun()
                if reject.button("Reject", key=f"reject_{proposal['id']}", disabled=proposal["status"] == "Rejected"):
                    review_proposal(proposal["id"], "Rejected")
                    st.rerun()


st.title("TaskForge")
st.write("Turn business problems into student-ready tasks.")
page = st.sidebar.radio("Navigation", ["Create Task", "Catalog", "Business Dashboard"])
st.sidebar.caption("Draft: 0–39 · Working: 40–69 · Ready: 70–89 · Priority: 90–100")
try:
    {"Create Task": create_task, "Catalog": catalog, "Business Dashboard": dashboard}[page]()
except (OSError, ValueError) as error:
    st.error(f"Could not read or save the app data: {error}. Check the JSON files and folder permissions, then retry.")
