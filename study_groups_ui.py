"""Streamlit pages for creating and collaborating in local study groups."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from study_groups import (
    DEFAULT_UPLOAD_DIR,
    add_file,
    add_goal,
    add_message,
    add_note,
    create_group,
    get_group,
    join_group,
    list_groups,
    read_shared_file,
    schedule_meeting,
    update_goal_progress,
    update_meeting,
)


def render_study_groups(output_dir: Path, history_path: Path) -> None:
    st.subheader("Study Groups")
    st.caption("Create a group or join with its code. Groups on this demo share the app's local storage.")
    display_name = st.text_input(
        "Your name in groups",
        value=st.session_state.get("group_display_name", "Student"),
        key="group_display_name_input",
    )
    if display_name.strip():
        st.session_state["group_display_name"] = display_name.strip()

    create_tab, join_tab = st.tabs(["Create a group", "Join a group"])
    with create_tab:
        with st.form("create_group_form"):
            group_name = st.text_input("Group name", placeholder="e.g. Biology revision team")
            create_submitted = st.form_submit_button("Create group", type="primary")
        if create_submitted:
            try:
                group = create_group(group_name, display_name)
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state["active_group_code"] = group["code"]
                st.rerun()

    with join_tab:
        with st.form("join_group_form"):
            invite_code = st.text_input("Group invite code", placeholder="8-character code")
            join_submitted = st.form_submit_button("Join group")
        if join_submitted:
            try:
                group = join_group(invite_code, display_name)
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state["active_group_code"] = group["code"]
                st.rerun()

    groups = list_groups()
    if not groups:
        st.info("Create a study group or enter an invite code to join one.")
        return

    group_codes = [group["code"] for group in groups]
    if st.session_state.get("active_group_code") not in group_codes:
        st.session_state["active_group_code"] = group_codes[0]
    group_labels = {
        group["code"]: f"{group['name']} · {group['code']}"
        for group in groups
    }
    selected_code = st.selectbox(
        "Your groups",
        group_codes,
        format_func=lambda code: group_labels[code],
        key="active_group_code",
    )
    group = get_group(selected_code)
    if group is None:
        st.warning("This group is no longer available.")
        return

    st.markdown(f"### {group['name']}")
    st.caption("Invite teammates with this group code:")
    st.code(group["code"], language=None)
    member_names = [member["name"] for member in group["members"]]
    member_columns = st.columns([1, 3])
    member_columns[0].metric("Members", len(member_names))
    member_columns[1].write("**Study team:** " + ", ".join(member_names))

    sessions_tab, materials_tab, discussion_tab, goals_tab = st.tabs(
        ["Sessions", "Shared materials", "Discussion", "Goals & progress"]
    )
    with sessions_tab:
        _render_sessions(group, display_name)
    with materials_tab:
        _render_materials(group, display_name, output_dir, history_path)
    with discussion_tab:
        _render_discussion(group, display_name)
    with goals_tab:
        _render_goals(group, display_name)


def _render_sessions(group: dict[str, Any], display_name: str) -> None:
    st.markdown("#### Schedule a study session")
    with st.form(f"schedule_{group['code']}"):
        topic = st.text_input("Session topic", placeholder="e.g. Review cell respiration")
        meeting_date = st.date_input("Date", value=date.today())
        meeting_time = st.time_input("Start time", value=time(16, 0))
        duration = st.slider("Duration (minutes)", 15, 240, 60, step=15)
        agenda = st.text_area("Agenda", placeholder="What will the group work on?")
        submitted = st.form_submit_button("Schedule session", type="primary")
    if submitted:
        starts_at = datetime.combine(meeting_date, meeting_time, tzinfo=timezone.utc).isoformat()
        try:
            schedule_meeting(group["code"], topic, starts_at, duration, agenda, display_name)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Study session scheduled.")
            st.rerun()

    st.markdown("#### Upcoming and past sessions")
    if not group["meetings"]:
        st.caption("Your group has no scheduled sessions yet.")
    for meeting in sorted(group["meetings"], key=lambda item: item["starts_at"]):
        with st.expander(f"{meeting['topic']} · {meeting['starts_at'][:16]} · {meeting['status'].title()}"):
            st.write(f"**Organizer:** {meeting['organizer']} · **Duration:** {meeting['duration_minutes']} minutes")
            if meeting["agenda"]:
                st.write(meeting["agenda"])
            if meeting["status"] == "scheduled":
                reschedule_tab, complete_tab = st.tabs(["Reschedule", "Manage"])
                with reschedule_tab:
                    try:
                        current_start = datetime.fromisoformat(meeting["starts_at"])
                    except ValueError:
                        current_start = datetime.now(timezone.utc)
                    with st.form(f"reschedule_{meeting['meeting_id']}"):
                        new_date = st.date_input(
                            "New date", current_start.date(), key=f"meeting_date_{meeting['meeting_id']}"
                        )
                        new_time = st.time_input(
                            "New time", current_start.time().replace(tzinfo=None),
                            key=f"meeting_time_{meeting['meeting_id']}",
                        )
                        reschedule = st.form_submit_button("Save new time")
                    if reschedule:
                        new_start = datetime.combine(new_date, new_time, tzinfo=timezone.utc).isoformat()
                        update_meeting(group["code"], meeting["meeting_id"], starts_at=new_start)
                        st.rerun()
                with complete_tab:
                    complete_col, cancel_col = st.columns(2)
                    if complete_col.button("Mark completed", key=f"complete_{meeting['meeting_id']}"):
                        update_meeting(group["code"], meeting["meeting_id"], status="completed")
                        st.rerun()
                    if cancel_col.button("Cancel session", key=f"cancel_{meeting['meeting_id']}"):
                        update_meeting(group["code"], meeting["meeting_id"], status="cancelled")
                        st.rerun()


def _render_materials(
    group: dict[str, Any],
    display_name: str,
    output_dir: Path,
    history_path: Path,
) -> None:
    st.markdown("#### Share a note")
    with st.form(f"share_note_{group['code']}"):
        note_title = st.text_input("Note title", placeholder="e.g. Chapter 4 summary")
        note_content = st.text_area("Note content", height=130)
        note_submitted = st.form_submit_button("Share note")
    if note_submitted:
        try:
            add_note(group["code"], note_title, note_content, display_name)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Note shared with the group.")
            st.rerun()

    uploaded = st.file_uploader(
        "Share a document or study material",
        type=["md", "txt", "pdf", "doc", "docx", "ppt", "pptx"],
        key=f"upload_{group['code']}",
        help="Maximum size 10 MB. Saved to this app's local group storage.",
    )
    if uploaded and st.button("Add uploaded material", key=f"add_upload_{group['code']}"):
        try:
            add_file(group["code"], uploaded.name, uploaded.getvalue(), display_name)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Material shared.")
            st.rerun()

    study_result = st.session_state.get("study_crew_result")
    if study_result:
        result_context = study_result["context"]
        st.write(f"Share your latest study pack: **{result_context['subject']} · {result_context['topic']}**")
        if st.button("Share latest study pack", key=f"share_pack_{group['code']}"):
            try:
                add_note(
                    group["code"],
                    f"{result_context['subject']} - {result_context['topic']} study pack",
                    study_result["report"],
                    display_name,
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("Study pack shared with the group.")
                st.rerun()

    st.markdown("#### Group library")
    if not group["materials"]:
        st.caption("No shared materials yet.")
    for material in group["materials"]:
        with st.container(border=True):
            st.markdown(f"**{material['title']}** · shared by {material['author']} · {material['created_at'][:10]}")
            if material["kind"] == "note":
                st.markdown(material["content"])
                st.download_button(
                    "Download note",
                    material["content"],
                    file_name=f"{material['title']}.md",
                    mime="text/markdown",
                    key=f"download_note_{material['material_id']}",
                )
            else:
                upload_dir = Path(__file__).resolve().parent / "outputs" / "group_uploads"
                file_content = read_shared_file(material, upload_dir)
                if file_content is None:
                    st.warning("This shared file is missing or unavailable.")
                else:
                    st.download_button(
                        f"Download {material['title']}",
                        file_content,
                        file_name=material["title"],
                        key=f"download_file_{material['material_id']}",
                    )


def _render_discussion(group: dict[str, Any], display_name: str) -> None:
    st.markdown("#### Discuss a topic")
    with st.form(f"discussion_{group['code']}"):
        message = st.text_area("Message", placeholder="Share an explanation, question, or study tip.")
        posted = st.form_submit_button("Post to group", type="primary")
    if posted:
        try:
            add_message(group["code"], display_name, message)
        except ValueError as error:
            st.error(str(error))
        else:
            st.rerun()

    st.markdown("#### Group discussion")
    if not group["messages"]:
        st.caption("Start the discussion with a question or an explanation for a teammate.")
    for item in group["messages"]:
        with st.chat_message("user", avatar="👤"):
            st.caption(f"{item['author']} · {item['created_at'][:16]}")
            st.write(item["content"])


def _render_goals(group: dict[str, Any], display_name: str) -> None:
    st.markdown("#### Set a learning goal")
    with st.form(f"goal_{group['code']}"):
        title = st.text_input("Goal", placeholder="e.g. Complete 20 practice problems")
        target = st.date_input("Target date", value=date.today())
        created = st.form_submit_button("Add goal")
    if created:
        try:
            add_goal(group["code"], display_name, title, target.isoformat())
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Goal added. Your teammates can track and encourage progress.")
            st.rerun()

    st.markdown("#### Team progress")
    if not group["goals"]:
        st.caption("Your group's goals will appear here.")
    members = [member["name"] for member in group["members"]]
    for goal in group["goals"]:
        st.markdown(f"**{goal['title']}** · {goal['member']} · target {goal['target_date']}")
        st.progress(goal["progress"], text=f"{goal['progress']}% complete")
        if goal["cheers"]:
            st.caption("Peer support: " + ", ".join(goal["cheers"]))
        controls = st.columns([3, 1, 1])
        new_progress = controls[0].slider(
            f"Update {goal['title']} progress",
            0,
            100,
            goal["progress"],
            step=5,
            key=f"progress_{goal['goal_id']}",
        )
        if controls[1].button("Save", key=f"save_goal_{goal['goal_id']}"):
            update_goal_progress(group["code"], goal["goal_id"], new_progress)
            st.rerun()
        cheer_from = next(
            (member for member in members if member.casefold() != display_name.casefold()),
            display_name,
        )
        if controls[2].button("Cheer", key=f"cheer_goal_{goal['goal_id']}"):
            update_goal_progress(
                group["code"], goal["goal_id"], goal["progress"], cheer_from=cheer_from
            )
            st.rerun()
