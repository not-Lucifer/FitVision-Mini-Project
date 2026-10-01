import streamlit as st
import os
import time
import pandas as pd
from services.auth.login_wall import render_login_wall
from services.state.session_defaults import initial_session_defaults
from services.config.workout_config import EXERCISE_OPTIONS
from html import escape
from services.ui.style_loader import load_css, inject_webrtc_styles
from services.ui.scoreboard import (
    scoreboard_html,
    coach_note_html,
    history_html,
    exercise_colors,
    exercise_label,
)
from services.persistence.exercise_repository import init_db
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from services.vision.exercise_video_processor import VideoProcessorClass, warm_up_pose_model
from services.tracking.metrics import sync_metrics_update
from services.persistence.exercise_repository import get_users_exercises
from groq import Groq
from streamlit.errors import StreamlitSecretNotFoundError
from services.coaching.llm import LLMCoach
from services.coaching.tts import TextToSpeech
from services.coaching.voice_pipeline import VoicePipeline, autoplay_audio


def get_setting(name):
    """Read a setting from the environment, falling back to Streamlit secrets."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        if name in st.secrets:
            return st.secrets[name]
    except StreamlitSecretNotFoundError:
        pass
    return ""


def get_ice_servers():
    """Build ICE servers with optional authenticated deployment relay."""
    ice_servers = [
        {"urls": ["stun:stun.l.google.com:19302"]},
        {
            "urls": [
                "turn:openrelay.metered.ca:80",
                "turn:openrelay.metered.ca:443?transport=tcp",
            ],
            "username": "openrelayproject",
            "credential": "openrelayproject",
        },
    ]

    turn_urls = get_setting("TURN_URLS") or get_setting("TURN_URL")
    turn_username = get_setting("TURN_USERNAME")
    turn_password = get_setting("TURN_PASSWORD")

    if turn_urls and turn_username and turn_password:
        ice_servers.append({
            "urls": [url.strip() for url in turn_urls.split(",") if url.strip()],
            "username": turn_username,
            "credential": turn_password,
        })

    return ice_servers


@st.fragment(run_every="500ms")
def render_live_workout():
    ice_servers = get_ice_servers()
    context = webrtc_streamer(
        key="exercise-analysis",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=VideoProcessorClass,
        rtc_configuration={"iceServers": ice_servers},
        media_stream_constraints={
            "video": True,
            "audio": False
        },
        async_processing=True
    )
    sync_metrics_update(context)
    inject_webrtc_styles()


@st.fragment(run_every="500ms")
def render_scoreboard():
    st.markdown(scoreboard_html(st.session_state), unsafe_allow_html=True)


def render_top_bar():
    username = escape(st.session_state.get("username") or "")
    st.markdown(
        f"""
        <header class="top-bar">
            <p class="brand">Apna AI Coach</p>
            <p class="who">Signed in as <strong>{username}</strong></p>
        </header>
        """,
        unsafe_allow_html=True,
    )


def start_workout(plan_exercise, plan_sets, plan_reps):
    warm_up_pose_model()
    st.session_state.exercise_type = plan_exercise
    st.session_state.target_sets = int(plan_sets)
    st.session_state.reps_per_set = int(plan_reps)
    st.session_state.reps = 0
    st.session_state.sets_completed = 0
    st.session_state.current_set_reps = 0
    st.session_state.camera_live = False
    st.session_state.pose_detected = True
    st.session_state.workout_started = True
    st.session_state.set_cycle_started_at = time.time()
    st.session_state.last_saved_sets_completed = 0

    if st.session_state.voice_pipeline:
        result = st.session_state.voice_pipeline.process_event(
            event="workout_started",
            exercise=plan_exercise,
            metrics={}
        )

        if result:
            st.session_state.audio_to_play, st.session_state.coach_feedback = result

    st.session_state.last_notified_sets_completed = 0
    st.session_state.last_notified_workout_complete = False


def end_workout():
    st.session_state.workout_started = False

    if st.session_state.voice_pipeline:
        result = st.session_state.voice_pipeline.process_event(
            event="workout_completed",
            exercise=st.session_state.get("exercise_type"),
            metrics={}
        )
        if result:
            st.session_state.audio_to_play, st.session_state.coach_feedback = result


def render_setup():
    # Tint the start button with the chosen exercise's colour (set before the widget renders).
    fill, on_fill = exercise_colors(st.session_state.get("plan_exercise"))
    st.markdown(
        '<h2 class="section-title">Choose an exercise</h2>'
        f"<style>.st-key-start_session_button button{{--ex:{fill};--on-ex:{on_fill}}}</style>",
        unsafe_allow_html=True,
    )

    with st.container(key="exercise-picker"):
        plan_exercise = st.pills(
            "Exercise",
            options=EXERCISE_OPTIONS,
            format_func=exercise_label,
            key="plan_exercise",
            label_visibility="collapsed",
        )

    sets_col, reps_col, start_col = st.columns([1, 1, 1.4], vertical_alignment="bottom")

    with sets_col:
        plan_sets = st.number_input("Sets", min_value=1, max_value=50, key="plan_sets", step=1)

    with reps_col:
        plan_reps = st.number_input("Reps per set", min_value=1, max_value=50, key="plan_reps", step=1)

    with start_col:
        start_session_button = st.button(
            "Start workout",
            type="primary",
            width="stretch",
            key="start_session_button",
            disabled=not plan_exercise,
        )

    if plan_exercise:
        hint = "Stand 2–3 metres from the camera so your whole body is in the frame."
    else:
        hint = "Choose an exercise to start."

    st.markdown(f'<p class="setup-hint">{hint}</p>', unsafe_allow_html=True)

    if start_session_button and plan_exercise:
        start_workout(plan_exercise, plan_sets, plan_reps)
        st.rerun()


def render_workout():
    camera_col, panel_col = st.columns([3, 2], gap="large")

    with camera_col:
        render_live_workout()

    with panel_col:
        with st.container(key="scoreboard"):
            render_scoreboard()

        if st.button("End workout", key="end_session_button", width="stretch"):
            end_workout()
            st.rerun()


def format_duration(seconds):
    minutes, secs = divmod(int(round(seconds or 0)), 60)
    return f"{minutes}:{secs:02d}"


def render_history():
    user_id = st.session_state.get("user_id", 0)

    if not isinstance(user_id, int):
        return

    history_rows = get_users_exercises(user_id)

    arr = [
        {
            "Exercise": row['exercise_name'],
            "Reps": row['reps'],
            "Sets": row['sets'],
            "Time (sec)": row['time'],
            "Date": row['created_at']
        }
        for row in history_rows
    ]

    df = pd.DataFrame(arr)

    if df.empty:
        st.markdown(
            '<div class="history-empty"><h2 class="section-title">No workouts yet</h2>'
            '<p>Each set you finish is saved here. Start one from the Workout tab.</p></div>',
            unsafe_allow_html=True,
        )
        return

    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    agg_df = df.groupby(["Date", "Exercise"]).agg({
        "Reps": 'sum',
        "Sets": "sum",
        "Time (sec)": "sum"
    }).reset_index().sort_values(["Date", "Exercise"], ascending=[False, True])

    rows = [
        {
            "date": pd.Timestamp(record["Date"]).strftime("%d %b %Y"),
            "exercise": record["Exercise"],
            "sets": int(record["Sets"]),
            "reps": int(record["Reps"]),
            "time": format_duration(record["Time (sec)"]),
        }
        for record in agg_df.to_dict("records")
    ]

    st.markdown(history_html(rows), unsafe_allow_html=True)


def main():
    st.set_page_config(
        page_icon="🏋️‍♀️",
        page_title="Apna AI Coach",
        initial_sidebar_state="collapsed",
        layout="wide"
    )

    load_css(os.path.join(os.getcwd(), "static", "style.css"))

    init_db()

    if not render_login_wall():
        return

    initial_session_defaults()

    if "voice_pipeline" not in st.session_state:
        try:
            api_key = get_setting("GROQ_API_KEY")

            if not api_key:
                st.session_state.voice_pipeline = None
            else:
                groq_client = Groq(api_key=api_key)
                llm_coach = LLMCoach(groq_client)
                tts = TextToSpeech()
                st.session_state.voice_pipeline = VoicePipeline(llm_coach, tts)
        except Exception:
            st.session_state.voice_pipeline = None

    render_top_bar()

    audio_to_play = st.session_state.pop("audio_to_play", None)
    if audio_to_play:
        autoplay_audio(audio_to_play)

    workout_tab, history_tab = st.tabs(["Workout", "History"])

    with workout_tab:
        if st.session_state.get("coach_feedback"):
            st.markdown(coach_note_html(st.session_state.coach_feedback), unsafe_allow_html=True)

        if st.session_state.get("workout_started", False):
            render_workout()
        else:
            render_setup()

    with history_tab:
        render_history()


if __name__ == "__main__":
    main()
