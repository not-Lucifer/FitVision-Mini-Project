import streamlit as st
import os
import time
import pandas as pd
from services.auth.login_wall import render_login_wall
from services.state.session_defaults import initial_session_defaults
from services.config.workout_config import EXERCISE_OPTIONS
from services.ui.style_loader import load_css, inject_local_font, inject_webrtc_styles
from services.ui.scoreboard import scoreboard_html, coach_note_html
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


def render_empty_state():
    st.markdown(
        """
        <section class="empty-state">
            <h2>Set up your workout</h2>
            <ol>
                <li>Pick an exercise, sets and reps in the sidebar.</li>
                <li>Press <strong>Start workout</strong>, then <strong>Start</strong> under the video.</li>
                <li>Step back 2&ndash;3 metres so your whole body is in the frame.</li>
            </ol>
            <p>Reps are counted from your pose, and every finished set is saved to your history.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def format_duration(seconds):
    minutes, secs = divmod(int(round(seconds or 0)), 60)
    return f"{minutes}:{secs:02d}"


def render_history():
    st.markdown("### Workout history")

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
            '<p class="history-empty">No workouts saved yet. Each set you finish shows up here.</p>',
            unsafe_allow_html=True,
        )
        return

    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    agg_df = df.groupby(["Date", "Exercise"]).agg({
        "Reps": 'sum',
        "Sets": "sum",
        "Time (sec)": "sum"
    }).reset_index().sort_values(["Date", "Exercise"], ascending=[False, True])

    agg_df["Date"] = pd.to_datetime(agg_df["Date"]).dt.strftime("%d %b %Y")
    agg_df["Time"] = agg_df.pop("Time (sec)").map(format_duration)
    agg_df = agg_df.set_index("Date")

    st.table(agg_df, border="horizontal")


def main():
    st.set_page_config(
        page_icon="🏋️‍♀️",
        page_title="AI Real-time GYM Coach",
        initial_sidebar_state="expanded",
        layout="wide"
    )

    load_css(os.path.join(os.getcwd(), "static", "style.css"))
    inject_local_font(os.path.join(os.getcwd(), "static", "AdobeClean.otf"), "AdobeClean")

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

    workout_started = st.session_state.get("workout_started", False)

    with st.sidebar:
        st.title("🏋️‍♂️ Apna AI Coach")

        if st.session_state.username:
            st.caption(f"Signed in as {st.session_state.username}")

        st.subheader("Workout plan")

        if not workout_started:
            plan_exercise = st.selectbox("Exercise", options=EXERCISE_OPTIONS, key="plan_exercise")

            plan_sets = st.number_input("Sets", min_value=1, max_value=50, key="plan_sets", step=1)

            plan_reps = st.number_input("Reps per set", min_value=1, max_value=50, key="plan_reps", step=1)

            start_session_button = st.button(
                "Start workout", type="primary", width="stretch", key="start_session_button"
            )

            if start_session_button:
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
                st.rerun()
        else:
            exercise = st.session_state.get("exercise_type")
            sets = st.session_state.get("target_sets")
            reps = st.session_state.get("reps_per_set")

            st.markdown(f"**{exercise}**  \n{sets} sets of {reps} reps")

            end_session_button = st.button("End workout", key="end_session_button", width="stretch")

            if end_session_button:
                st.session_state.workout_started = False

                if st.session_state.voice_pipeline:
                    result = st.session_state.voice_pipeline.process_event(
                        event="workout_completed",
                        exercise=exercise,
                        metrics={}
                    )
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result

                st.rerun()

    st.title("AI Real-time GYM Coach")
    st.markdown(
        '<p class="app-subtitle">Real-time pose detection with proactive AI voice coaching</p>',
        unsafe_allow_html=True,
    )

    audio_to_play = st.session_state.pop("audio_to_play", None)
    if audio_to_play:
        autoplay_audio(audio_to_play)

    if st.session_state.get("coach_feedback"):
        st.markdown(coach_note_html(st.session_state.coach_feedback), unsafe_allow_html=True)

    if not workout_started:
        render_empty_state()
    else:
        camera_col, scoreboard_col = st.columns([3, 2], gap="large")

        with camera_col:
            render_live_workout()

        with scoreboard_col:
            with st.container(key="scoreboard"):
                render_scoreboard()

    render_history()


if __name__ == "__main__":
    main()
