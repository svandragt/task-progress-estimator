import json
import time
from typing import Dict, Any, List
from uuid import uuid4

import pandas as pd
import streamlit as st
from streamlit_local_storage import LocalStorage

DEFAULT_STATE: Dict[str, Any] = {
    "global_velocity": 1.8,  # story points / day
    "tasks": {},  # id -> task
}

STORAGE_KEY = "task_progress_state"

# Add a single instance of LocalStorage in session state


def get_local_storage() -> LocalStorage:
    """Return a single, stable LocalStorage component instance."""
    if "local_storage" not in st.session_state:
        st.session_state.local_storage = LocalStorage(key="task_progress_local_storage")
    return st.session_state.local_storage


def load_state() -> Dict[str, Any]:
    """Load state from browser local storage."""
    try:
        ls = get_local_storage()
        stored_data = ls.getItem(STORAGE_KEY)
        if stored_data:
            return json.loads(stored_data)
    except Exception:
        pass
    return DEFAULT_STATE.copy()


def save_state(state: Dict[str, Any]) -> None:
    """Save state to browser local storage."""
    try:
        ls = get_local_storage()
        ls.setItem(STORAGE_KEY, json.dumps(state))
        st.session_state._last_saved_at = time.time()
    except Exception:
        # Silently fail - storage may not be available in some environments
        pass

    # Wait a moment to ensure save completes before any rerun
    time.sleep(0.2)


def ensure_session_state():
    if "app_state" not in st.session_state:
        st.session_state.app_state = load_state()
    if "velocity_last_changed" not in st.session_state:
        st.session_state.velocity_last_changed = None
    if "velocity_pending_save" not in st.session_state:
        st.session_state.velocity_pending_save = False
    if "_toast_after_rerun" not in st.session_state:
        st.session_state._toast_after_rerun = None
    if "need_rerun" not in st.session_state:
        st.session_state.need_rerun = False


def new_task(title: str) -> Dict[str, Any]:
    return {
        "id": str(uuid4()),
        "title": title.strip() or "Untitled Task",
        "planned_points": 3.0,  # story points planned for this task
        "days_worked": 0.0,  # cumulative log
        "velocity_override": None,  # optional per-task velocity
        "criteria": [],  # list of dicts: {text, points, done}
    }


def criteria_to_df(criteria: List[Dict[str, Any]]) -> pd.DataFrame:
    if not criteria:
        return pd.DataFrame([{"Criteria": "", "Points": 1.0, "Done": False}])
    return pd.DataFrame(
        [
            {
                "Criteria": c.get("text", ""),
                "Points": float(c.get("points", 0)),
                "Done": bool(c.get("done", False)),
            }
            for c in criteria
        ]
    )


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

    def _rename_task(tid: str) -> None:
        """Apply a title edit and immediately rerun so tab labels refresh."""
        task = state["tasks"][tid]
        proposed = (
            str(st.session_state.get(f"title_{tid}", "")).strip() or "Untitled Task"
        )

        existing_titles = {
            t["title"] for t_id, t in state["tasks"].items() if t_id != tid
        }
        if proposed in existing_titles:
            st.warning(
                f"⚠️ Another task named '{proposed}' already exists. Choose a different name."
            )
            st.session_state[f"title_{tid}"] = task["title"]
            return

        if proposed != task["title"]:
            task["title"] = proposed
            save_state(state)
            st.session_state.need_rerun = True

    # show any deferred toast at the start of the run (after rerun)
    if st.session_state._toast_after_rerun:
        st.toast(st.session_state._toast_after_rerun, icon="🕒")
        st.session_state._toast_after_rerun = None

    st.header("Task Progress Estimator")

    with st.sidebar:
        st.header("Settings")

        current_velocity = st.number_input(
            "Global velocity (SP/day)",
            min_value=0.1,
            step=0.1,
            value=float(state.get("global_velocity", DEFAULT_STATE["global_velocity"])),
            key="global_velocity_input",
        )

        # Update state and mark for debounced save if velocity changed
        if current_velocity != state.get("global_velocity"):
            state["global_velocity"] = current_velocity
            st.session_state.velocity_last_changed = time.time()
            st.session_state.velocity_pending_save = True

        st.markdown("---")
        st.subheader("Add Task")

        with st.form("create_task_form", clear_on_submit=True):
            new_title = st.text_input("Task title", key="new_task_title")
            submitted = st.form_submit_button("Create task", type="primary")

        if submitted:
            if not new_title.strip():
                st.toast("Please enter a title.", icon="⚠️")
            else:
                normalized_title = new_title.strip()
                existing_titles = [task["title"] for task in state["tasks"].values()]

                if normalized_title in existing_titles:
                    st.toast(f"Task '{normalized_title}' already exists!", icon="⚠️")
                else:
                    t = new_task(normalized_title)
                    state["tasks"][t["id"]] = t
                    save_state(state)
                    st.rerun()

        st.caption("💡 Data is stored in your browser's local storage")

    task_ids_sorted = sorted(
        state["tasks"].keys(), key=lambda tid: state["tasks"][tid]["title"].lower()
    )

    if not task_ids_sorted:
        st.info("No tasks yet. Use the sidebar to create your first task.")
        save_state(state)
        return

    tabs = st.tabs([state["tasks"][tid]["title"] for tid in task_ids_sorted])

    changed = False
    need_rerun = False

    for tid, tab in zip(task_ids_sorted, tabs):
        task = state["tasks"][tid]
        with tab:
            with st.container():
                col_title, col_delete = st.columns([5, 1])
                with col_title:
                    st.text_input(
                        "Title",
                        value=task["title"],
                        key=f"title_{tid}",
                        on_change=_rename_task,
                        args=(tid,),
                    )
                with col_delete:
                    if st.button("Delete task", key=f"del_{tid}"):
                        del state["tasks"][tid]
                        save_state(state)
                        need_rerun = True

            # Capacity & logging
            col_plan, col_logged, col_add = st.columns([1.1, 1.1, 1.3])
            with col_plan:
                planned_points = st.number_input(
                    "Planned story points",
                    min_value=0.0,
                    step=0.5,
                    value=float(task.get("planned_points", 3.0)),
                    key=f"planned_{tid}",
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
                    key=f"quicklog_{tid}",
                )
                if st.button("Log work", key=f"log_{tid}"):
                    task["days_worked"] = float(task.get("days_worked", 0.0)) + float(
                        add_days
                    )
                    changed = True
                    save_state(state)
                    st.rerun()

            with col_add:
                st.caption("Set per-task velocity (optional):")
                vel_override = st.number_input(
                    "Velocity override (SP/day)",
                    min_value=0.0,
                    step=0.1,
                    value=float(task.get("velocity_override") or 0.0),
                    key=f"vel_{tid}",
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
                width="stretch",
                num_rows="dynamic",
                column_config={
                    "Criteria": st.column_config.TextColumn(
                        "Criteria", width="medium", required=False
                    ),
                    "Points": st.column_config.NumberColumn(
                        "Points", min_value=0.0, step=0.5, required=True
                    ),
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
            planned_days = (
                (task.get("planned_points", 3.0) / velocity) if velocity > 0 else 0.0
            )
            remaining_time = max(0.0, planned_days - task["days_worked"])

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Planned days", f"{planned_days:.2f}")
            m2.metric("Remaining time", f"{remaining_time:.2f}")
            m3.metric("Required days", f"{required_days:.2f}")
            m4.metric("Days worked", f"{task['days_worked']:.2f}")

            # Guidance and warning
            if velocity <= 0:
                st.warning(
                    "Velocity is 0. Set a positive velocity to estimate remaining days."
                )
            else:
                if remaining_time < required_days:
                    st.error(
                        f"Risk: remaining time ({remaining_time:.2f} days) < required ({required_days:.2f} days)."
                    )
                else:
                    st.success(
                        f"On track: remaining time ({remaining_time:.2f} days) ≥ required ({required_days:.2f} days)."
                    )

            st.caption(
                "Planned days = planned story points ÷ velocity (SP/day). "
                "Remaining time = planned days – days worked. "
                "Required days = incomplete story points ÷ velocity (SP/day)."
            )

    # Auto-save on any change
    if changed:
        save_state(state)

    # Handle debounced velocity save
    if st.session_state.velocity_pending_save:
        if st.session_state.velocity_last_changed is not None:
            elapsed = time.time() - st.session_state.velocity_last_changed
            if elapsed >= 1.0:  # 1 second debounce
                save_state(state)
                st.session_state.velocity_pending_save = False
                st.session_state.velocity_last_changed = None
            else:
                # Trigger rerun to check again
                time.sleep(0.1)
                st.rerun()

    if need_rerun or st.session_state.need_rerun:
        st.session_state.need_rerun = False
        st.rerun()


if __name__ == "__main__":
    main()
