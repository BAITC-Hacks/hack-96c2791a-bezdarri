"""Run with: python -m streamlit run app.py"""

from urllib.parse import urlparse

import streamlit as st

from services.scoring import FIELDS, calculate_readiness
from services.storage import add_record, load_records, review_proposal, submit_proposal

st.set_page_config(page_title="TaskForge", page_icon="🛠️", layout="wide")


def show_readiness(task):
    result = calculate_readiness(task)
    st.metric("Readiness score", f"{result['score']}/100", result["level"], delta_color="off")
    st.progress(result["score"] / 100)
    st.table(result["breakdown"])
    if result["missing"]:
        st.warning("Missing information: " + ", ".join(result["missing"]))
        st.markdown("**Suggestions for increasing the score**")
        for suggestion in result["suggestions"]:
            st.write("• " + suggestion)
    else:
        st.success("All readiness fields are filled in. Review the detail with the business contact.")
    return result


def create_task():
    st.header("Create Task")
    st.caption("Readiness measures completion, not quality. Each non-empty field earns its points; context and need earn 10 each. A title is required to publish.")
    task = {"title": st.text_input("Title").strip()}
    labels = {"data_materials": "Data/materials", "contact": "Contact/interaction format"}
    for key in ("context", "need", "users", "data_materials", "constraints", "expected_result", "success_criteria", "contact"):
        task[key] = st.text_area(labels.get(key, key.replace("_", " ").capitalize())).strip()
    result = show_readiness(task)
    if st.button("Publish task", type="primary"):
        if not task["title"]:
            st.error("Enter a title before publishing.")
        else:
            add_record("tasks", {**task, "readiness_score": result["score"], "readiness_level": result["level"]})
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
    tasks = sorted(load_records("tasks"), key=lambda task: calculate_readiness(task)["score"], reverse=True)
    tasks = [task for task in tasks if level == "All" or calculate_readiness(task)["level"] == level]
    if not tasks:
        st.info("No published tasks match this filter.")
    for task in tasks:
        result = calculate_readiness(task)
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
