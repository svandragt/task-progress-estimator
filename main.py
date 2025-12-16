import json
from pathlib import Path
from typing import Dict, Any, List
from uuid import uuid4

import pandas as pd
import streamlit as st
from streamlit_local_storage import LocalStorage

DEFAULT_STATE: Dict[str, Any] = {
    "global_velocity": 1.8,   # story points / day
    "tasks": {}               # id -> task
}

STORAGE_KEY = "task_progress_state"


def get_local_storage(key_suffix="default"):
    """Initialize LocalStorage instance with unique key."""
    return LocalStorage(key=f"local_storage_{key_suffix}")


def load_state() -> Dict[str, Any]:
    """Load state from browser local storage."""
    localS = get_local_storage(key_suffix="load")
    stored_data = localS.getItem(STORAGE_KEY)
    if stored_data:
        try:
            return json.loads(stored_data)
        except Exception:
            pass
    return DEFAULT_STATE.copy()

def save_state(state: Dict[str, Any]) -> None:
    """Save state to browser local storage."""
    localS = get_local_storage(key_suffix="save")
    localS.setItem(STORAGE_KEY, json.dumps(state))

def ensure_session_state():
    if "app_state" not in st.session_state:
        st.session_state.app_state = load_state()

def new_task(title: str) -> Dict[str, Any]:
    return {
        "id": str(uuid4()),
        "title": title.strip() or "Untitled Task",
        "planned_points": 3.0,  # story points planned for this task
        "days_worked": 0.0,            # cumulative log
        "velocity_override": None,     # optional per-task velocity
        "criteria": [],  # list of dicts: {text, points, done}
    }

def criteria_to_df(criteria: List[Dict[str, Any]]) -> pd.DataFrame:
    if not criteria:
        return pd.DataFrame(
            [{"Criteria": "", "Points": 1.0, "Done": False}]
        )
    return pd.DataFrame([
        {"Criteria": c.get("text", ""),
         "Points": float(c.get("points", 0)),
         "Done": bool(c.get("done", False))}
        for c in criteria
    ])

def df_to_criteria(df: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = []
    for _, row in df.iterrows():
        text = str(row.get("Criteria", "")).strip()
        points = float(row.get("Points", 0) or 0)
        done = bool(row.get("Done", False))
        if text or points:  # keep non-empty rows
            rows.append({"text": text, "points": points, "done": done})
    return rows

def compute_points(criteria: List[Dict[str, Any]]):
    total = sum(c["points"] for c in criteria)
    completed = sum(c["points"] for c in criteria if c["done"])
    incomplete = total - completed
    return total, completed, incomplete

def main():
    st.set_page_config(page_title="Task Progress Estimator", layout="wide")
    ensure_session_state()
    state = st.session_state.app_state

    st.header("Task Progress Estimator !")

    with st.sidebar:
        st.header("Settings")
        state["global_velocity"] = st.number_input(
            "Global velocity (SP/day)",
            min_value=0.1, step=0.1, value=float(state.get("global_velocity", 3.0))
        )

        st.markdown("---")
        st.subheader("Add Task")

        def create_task_from_input():
            new_title = st.session_state.get("new_task_title", "")
            if new_title.strip():
                t = new_task(new_title)
                state["tasks"][t["id"]] = t
                save_state(state)
                st.session_state.new_task_title = ""

        new_title = st.text_input("Task title", key="new_task_title", on_change=create_task_from_input)
        if st.button("Create task", type="primary"):
            if not new_title.strip():
                st.toast("Please enter a title.", icon="⚠️")

        st.markdown("---")
        if st.button("Save now"):
            save_state(state)
            st.toast("Saved to browser storage.", icon="💾")

        st.caption("💡 Data is stored in your browser's local storage")

    task_ids_sorted = sorted(
        state["tasks"].keys(),
        key=lambda tid: state["tasks"][tid]["title"].lower()
    )

    if not task_ids_sorted:
        st.info("No tasks yet. Use the sidebar to create your first task.")
        save_state(state)
        return

    tabs = st.tabs([state["tasks"][tid]["title"] for tid in task_ids_sorted])

    changed = False

    for tid, tab in zip(task_ids_sorted, tabs):
        task = state["tasks"][tid]
        with tab:
            # Top row: title, delete
            col_title, col_delete = st.columns([5,1])
            with col_title:
                new_task_title = st.text_input(
                    "Title",
                    value=task["title"],
                    key=f"title_{tid}"
                )
                if new_task_title != task["title"]:
                    task["title"] = new_task_title
                    changed = True
            with col_delete:
                if st.button("Delete task", key=f"del_{tid}"):
                    del state["tasks"][tid]
                    save_state(state)
                    st.rerun()

            # Capacity & logging
            col_plan, col_logged, col_add = st.columns([1.1, 1.1, 1.3])
            with col_plan:
                planned_points = st.number_input(
                    "Planned story points",
                    min_value=0.0, step=0.5,
                    value=float(task.get("planned_points", 3.0)),
                    key=f"planned_{tid}"
                )
                if planned_points != task.get("planned_points", 3.0):
                    task["planned_points"] = planned_points
                    changed = True

            with col_logged:
                st.metric("Days worked", f'{task.get("days_worked", 0.0):.2f}')
                add_days = st.select_slider(
                    "Quick log",
                    options=[0.25, 0.5, 0.75, 1.0],
                    value=0.5,
                    key=f"quicklog_{tid}"
                )
                if st.button("Log work", key=f"log_{tid}"):
                    task["days_worked"] = float(task.get("days_worked", 0.0)) + float(add_days)
                    changed = True
                    save_state(state)
                    st.toast(f"Added {add_days} day(s).", icon="🕒")
                    st.rerun()

            with col_add:
                st.caption("Set per-task velocity (optional):")
                vel_override = st.number_input(
                    "Velocity override (SP/day)",
                    min_value=0.0, step=0.1,
                    value=float(task.get("velocity_override") or 0.0),
                    key=f"vel_{tid}"
                )
                # Treat 0 as None (no override)
                effective_override = None if vel_override <= 0 else vel_override
                if effective_override != task.get("velocity_override"):
                    task["velocity_override"] = effective_override
                    changed = True

            st.markdown("### Acceptance Criteria")
            df = criteria_to_df(task.get("criteria", []))
            edited = st.data_editor(
                df,
                key=f"editor_{tid}",
                width='stretch',
                num_rows="dynamic",
                column_config={
                    "Criteria": st.column_config.TextColumn("Criteria", width="medium", required=False),
                    "Points": st.column_config.NumberColumn("Points", min_value=0.0, step=0.5, required=True),
                    "Done": st.column_config.CheckboxColumn("Done"),
                },
            )
            new_criteria = df_to_criteria(edited)
            if new_criteria != task.get("criteria", []):
                task["criteria"] = new_criteria
                changed = True

            # Metrics
            total_sp, done_sp, incomplete_sp = compute_points(task["criteria"])
            velocity = task.get("velocity_override") or state["global_velocity"]
            required_days = (incomplete_sp / velocity) if velocity > 0 else float("inf")
            planned_days = (task.get("planned_points", 3.0) / velocity) if velocity > 0 else 0.0
            time_left = max(0.0, planned_days - task["days_worked"])

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total SP", f"{total_sp:.2f}")
            m2.metric("Completed SP", f"{done_sp:.2f}")
            m3.metric("Incomplete SP", f"{incomplete_sp:.2f}")
            m4.metric("Required days (at velocity)", f"{required_days:.2f}")

            # Guidance and warning
            if velocity <= 0:
                st.warning("Velocity is 0. Set a positive velocity to estimate remaining days.")
            else:
                if time_left < required_days:
                    st.error(
                        f"Risk: remaining time ({time_left:.2f} days) < required ({required_days:.2f} days)."
                    )
                else:
                    st.success(
                        f"On track: remaining time ({time_left:.2f} days) ≥ required ({required_days:.2f} days)."
                    )

            st.caption(
                "Planned days = planned story points × velocity. "
                "Remaining time = planned days – days worked. "
                "Required days = incomplete story points ÷ velocity (SP/day)."
            )

    # Auto-save on any change
    if changed:
        save_state(state)
        st.toast("Changes saved.", icon="💾")

if __name__ == "__main__":
    main()
