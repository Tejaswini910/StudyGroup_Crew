"""Streamlit interface for the LangChain study group crew."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from study_history import load_history, record_quiz_attempt, record_session
from study_pipeline import PROFILES, render_report, run_study_session, score_quiz
from study_groups_ui import render_study_groups


PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"
HISTORY_PATH = OUTPUT_DIR / "study_history.json"


st.set_page_config(page_title="Study Group Crew", page_icon="📚", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #090c10; color: #f5f7fa; }
    [data-testid="stHeader"] { background: transparent; }
    .main .block-container { max-width: 980px; padding-top: 1.5rem; padding-bottom: 3rem; }
    .crew-hero {
        padding: 28px 32px;
        margin-bottom: 26px;
        color: #f7f9fc;
        background: linear-gradient(115deg, #0d151d 0%, #13304a 100%);
        border-radius: 16px;
        border: 1px solid #1d3850;
    }
    .crew-hero h1 { margin: 0; font-size: 2rem; line-height: 1.15; }
    .crew-hero p { margin: 8px 0 0; color: #b8c8d8; font-size: 1rem; }
    .section-heading { margin: 20px 0 12px; font-size: 1.25rem; font-weight: 700; }
    .agent-tile {
        min-height: 142px;
        padding: 18px;
        margin-bottom: 14px;
        background: #202326;
        border: 1px solid #2c3035;
        border-radius: 10px;
    }
    .agent-number { color: #a8c9e8; font-size: .85rem; font-weight: 700; }
    .agent-tile h3 { margin: 7px 0; font-size: 1.15rem; }
    .agent-tile p { margin: 0; color: #c1c6cb; line-height: 1.5; }
    .materials {
        padding: 20px 22px;
        margin: 8px 0 22px;
        border: 1px solid #30353a;
        border-radius: 12px;
        background: #0d1013;
    }
    .materials h2 { margin: 0 0 14px; font-size: 1.25rem; }
    .material-row { display: flex; gap: 14px; align-items: center; padding: 9px 0; }
    .material-copy strong { display: block; font-size: 1.05rem; }
    .material-copy small { color: #b1b8c0; }
    .material-status { margin-left: auto; color: #7f8993; font-size: 1.2rem; }
    .material-status.ready { color: #29c779; }
    @media (max-width: 640px) {
        .main .block-container { padding-left: 1rem; padding-right: 1rem; }
        .crew-hero { padding: 22px 20px; }
        .crew-hero h1 { font-size: 1.7rem; }
        .agent-tile { min-height: 0; }
    }
    </style>
    <header class="crew-hero">
      <h1>Study Group Crew</h1>
      <p>Your collaborative learning team</p>
    </header>
    """,
    unsafe_allow_html=True,
)

workspace = st.radio(
    "Workspace",
    ["Study Session", "Study Groups"],
    horizontal=True,
    label_visibility="collapsed",
    key="workspace_page",
)
if workspace == "Study Groups":
    render_study_groups(OUTPUT_DIR, HISTORY_PATH)
    st.stop()

st.markdown('<div class="section-heading">BUILD A STUDY SESSION</div>', unsafe_allow_html=True)
subject_options = [
    "Computer Science", "Mathematics", "Biology", "Physics", "Chemistry",
    "History", "Literature", "Geography", "Other",
]
subject_choice = st.selectbox("Subject", subject_options)
subject = st.text_input("Enter your subject") if subject_choice == "Other" else subject_choice
topic = st.text_input(
    "Topic or syllabus unit",
    placeholder="e.g. Neural networks, quadratic equations, cell division",
    help="Enter any topic; add syllabus text below for course-specific context.",
)
syllabus = st.text_area(
    "Paste syllabus or class material (optional)",
    placeholder="Paste relevant learning outcomes, chapter notes, or syllabus sections here.",
    height=110,
)
quiz_count = st.slider("Quiz questions", min_value=3, max_value=10, value=5)
run_button = st.button(
    "Build my study materials",
    type="primary",
    disabled=not subject.strip() or not topic.strip(),
)
model_name = os.getenv("OLLAMA_MODEL", "").strip()
ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
st.caption(
    f"Ollama model configured: `{model_name}`. Start Ollama at `{ollama_url}` to use it; no API key is needed."
    if model_name
    else "No model configured: source-grounded fallback is active. Ollama is optional and needs no API key."
)

if run_button:
    with st.spinner("The agents are sharing research and checking the quiz..."):
        try:
            context = run_study_session(subject, topic, syllabus, quiz_count)
            report = render_report(context)
            session_report_path = OUTPUT_DIR / "study_reports" / f"{context['session_id']}.md"
            latest_report_path = OUTPUT_DIR / "study_group_output.md"
            session_report_path.parent.mkdir(parents=True, exist_ok=True)
            session_report_path.write_text(report, encoding="utf-8")
            latest_report_path.write_text(report, encoding="utf-8")
            record_session(HISTORY_PATH, context, session_report_path)
            st.session_state["study_crew_result"] = {
                "context": context,
                "report": report,
                "report_path": str(session_report_path),
            }
        except ValueError as error:
            st.error(str(error))

result = st.session_state.get("study_crew_result")
ready = result is not None

st.markdown('<div class="section-heading">Your AI study team</div>', unsafe_allow_html=True)
agent_descriptions = {
    "Topic Researcher": "Finds key facts and concepts from linked sources.",
    "Study Explainer": "Turns the findings into clear, concise study notes.",
    "Quiz Maker": "Builds multiple-choice practice questions.",
    "Fact-Checker": "Checks claims and answer keys against the sources.",
}
agent_roles = ("Topic Researcher", "Study Explainer", "Quiz Maker", "Fact-Checker")
if "selected_agent" not in st.session_state:
    st.session_state["selected_agent"] = "Topic Researcher"

agent_columns = st.columns(2)
for index, role in enumerate(agent_roles):
    profile = next(profile for profile in PROFILES if profile.role == role)
    with agent_columns[index % 2]:
        st.markdown(
            f'<article class="agent-tile"><span class="agent-number">{index + 1} / AGENT</span>'
            f'<h3>{role}</h3><p>{agent_descriptions[role]}</p></article>',
            unsafe_allow_html=True,
        )
        if st.button(
            f"Open {role}",
            key=f"open_agent_{index}",
            type="primary" if st.session_state["selected_agent"] == role else "secondary",
            use_container_width=True,
        ):
            st.session_state["selected_agent"] = role

status_class = "ready" if ready else ""
status_mark = "✓" if ready else "○"
st.markdown(
    f"""
    <section class="materials">
      <h2>Generated study materials</h2>
      <div class="material-row"><span>▤</span><div class="material-copy"><strong>Study notes</strong>
        <small>Key concepts and source-backed explanations</small></div>
        <span class="material-status {status_class}">{status_mark}</span></div>
      <div class="material-row"><span>☷</span><div class="material-copy"><strong>Practice quiz</strong>
        <small>Questions, options, and answer feedback</small></div>
        <span class="material-status {status_class}">{status_mark}</span></div>
      <div class="material-row"><span>⇩</span><div class="material-copy"><strong>Downloadable output</strong>
        <small>Saved as outputs/study_group_output.md</small></div>
        <span class="material-status {status_class}">{status_mark}</span></div>
    </section>
    """,
    unsafe_allow_html=True,
)

if not ready:
    st.info("Choose a subject, enter a topic, and build your first study pack.")
    selected_profile = next(
        profile for profile in PROFILES if profile.role == st.session_state["selected_agent"]
    )
    st.subheader(f"{selected_profile.role} workspace")
    st.write(f"**Goal:** {selected_profile.goal}")
    st.write(f"**Backstory:** {selected_profile.backstory}")
    st.caption("Run a study session to give this agent research and course content to work on.")
else:
    context = result["context"]
    st.caption(
        f"Saved report: `{result['report_path']}` · "
        f"Fact-check: {'PASS' if context['fact_check_passed'] else 'REVIEW'} · "
        f"Tools: {len(context['tool_log'])}"
    )
    metric_columns = st.columns(4)
    metric_columns[0].metric("Subject", context["subject"])
    metric_columns[1].metric("Sources", len(context["sources"]))
    metric_columns[2].metric("Quiz questions", len(context["questions"]))
    metric_columns[3].metric("Fact-check", "PASS" if context["fact_check_passed"] else "REVIEW")
    st.caption(f"Generation mode: {context['generation_mode']}")

    if context["warnings"] or context["generation_warnings"]:
        with st.expander("Research and generation notes"):
            for warning in context["warnings"] + context["generation_warnings"]:
                st.warning(warning)

    selected_agent = st.session_state["selected_agent"]
    selected_profile = next(profile for profile in PROFILES if profile.role == selected_agent)
    st.subheader(f"{selected_agent} workspace")
    st.caption(selected_profile.goal)

    if selected_agent == "Topic Researcher":
        st.markdown(f"### {context['topic']} in {context['subject']}")
        st.write("Research sources and syllabus matches gathered for this topic:")
        for source in context["sources"]:
            title = f"[{source['source_id']}] {source['title']}"
            if source.get("url"):
                st.markdown(f"**[{title}]({source['url']})** · {source['source_type']}")
            else:
                st.markdown(f"**{title}** · {source['source_type']}")
            st.write(source["summary"])
        if context.get("syllabus_search_note"):
            st.caption(context["syllabus_search_note"])
        st.markdown("**Research actions**")
        for tool_call in context["tool_log"][:2]:
            st.markdown(f"- `{tool_call}`")

    elif selected_agent == "Study Explainer":
        st.markdown(context["notes"])
        syllabus_sources = [source for source in context["sources"] if source["source_type"] == "User syllabus"]
        if syllabus_sources:
            with st.expander("Course-specific syllabus context"):
                for source in syllabus_sources:
                    st.markdown(f"**{source['source_id']}** {source['summary']}")

    elif selected_agent == "Quiz Maker":
        st.write("Answer every question, then submit once to see your score and explanations.")
        existing_attempt = context.get("quiz_attempt")
        with st.form(f"quiz_form_{context['session_id']}"):
            selected_answers = {}
            for question in context["questions"]:
                selected_answers[question["question_id"]] = st.radio(
                    f"{question['question_id']}. {question['question']}",
                    question["options"],
                    index=None,
                    key=f"answer_{context['session_id']}_{question['question_id']}",
                )
            submitted = st.form_submit_button("Submit quiz", type="primary")

        if submitted:
            try:
                attempt = score_quiz(context["questions"], selected_answers)
            except ValueError as error:
                st.warning(str(error))
            else:
                attempt["attempted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                context["quiz_attempt"] = attempt
                record_quiz_attempt(HISTORY_PATH, context["session_id"], attempt)
                result["report"] = render_report(context)
                Path(result["report_path"]).write_text(result["report"], encoding="utf-8")
                (OUTPUT_DIR / "study_group_output.md").write_text(result["report"], encoding="utf-8")
                existing_attempt = attempt

        if existing_attempt:
            st.metric("Most recent score", f"{existing_attempt['score']} / {existing_attempt['total']}")
            for item in existing_attempt["results"]:
                if item["correct"]:
                    st.success(f"{item['question_id']}: Correct")
                else:
                    st.error(f"{item['question_id']}: Review this answer")
                st.write(f"**Correct answer:** {item['answer']}")
                st.write(f"**Why:** {item['explanation']}")
                st.caption("Evidence: " + ", ".join(item["source_ids"]))

    else:
        check = context["fact_check"]
        st.metric("Structural validation", "PASS" if check["passed"] else "REVIEW")
        st.write(context["fact_check_scope"])
        st.markdown("**Checks**")
        st.markdown(
            f"- {'PASS' if check['notes_cite_known_sources'] else 'FAIL'}: study notes cite known source IDs"
        )
        st.markdown(
            f"- {'PASS' if check['quiz_items_have_valid_keys_explanations_and_citations'] else 'FAIL'}: quiz keys, explanations, and citations"
        )
        for question_check in check["quiz_item_checks"]:
            st.markdown(
                f"- {'PASS' if question_check['passed'] else 'FAIL'}: "
                f"{question_check['question_id']} answer and citation check"
            )
        with st.expander("Agent handoffs"):
            for handoff in context["handoffs"]:
                st.markdown(f"- {handoff}")
            st.markdown("**LangChain tools used**")
            for tool_call in context["tool_log"]:
                st.markdown(f"- `{tool_call}`")

    st.download_button(
        "Download this study pack",
        data=result["report"],
        file_name=f"{context['subject']}_{context['topic']}_study_pack.md".replace(" ", "_"),
        mime="text/markdown",
        type="primary",
        key=f"download_{context['session_id']}",
    )

st.subheader("Study history")
history = load_history(HISTORY_PATH)
if not history:
    st.caption("Your saved sessions and quiz scores will appear here.")
else:
    for history_item in history:
        with st.expander(
            f"{history_item['subject']} · {history_item['topic']} · {history_item['created_at'][:10]}"
        ):
            st.write(
                f"{history_item['source_count']} sources · {history_item['quiz_count']} questions · "
                f"Fact-check: {'PASS' if history_item['fact_check_passed'] else 'REVIEW'} · "
                f"Mode: {history_item['generation_mode']}"
            )
            attempts = history_item.get("attempts", [])
            if attempts:
                st.write("Quiz scores: " + ", ".join(f"{item['score']}/{item['total']}" for item in attempts))
            past_report = Path(history_item["report_path"])
            if past_report.is_file():
                st.download_button(
                    "Download this past study pack",
                    data=past_report.read_bytes(),
                    file_name=past_report.name,
                    mime="text/markdown",
                    key=f"history_download_{history_item['session_id']}",
                )

if history:
    st.download_button(
        "Download study history (JSON)",
        data=json.dumps(history, indent=2, ensure_ascii=False),
        file_name="study_history.json",
        mime="application/json",
        key="download_history_json",
    )
