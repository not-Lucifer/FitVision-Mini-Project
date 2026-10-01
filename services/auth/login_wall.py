import streamlit as st
from services.persistence.exercise_repository import get_or_create_user


def render_login_wall():
    if st.session_state.get("user_id") is not None:
        return True
    
    with st.container(key="login"):
        st.title("🏋️‍♂️ AI Real-time GYM Coach")
        st.markdown(
            '<p class="app-subtitle">Enter your name to load your workout history. '
            'A new name starts a fresh history.</p>',
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False, border=False):
            username = st.text_input("Your name", placeholder="e.g. princekhunt")
            submit_button = st.form_submit_button("Continue", type="primary", width="stretch")

    if submit_button:
        username = username.strip()

        if not username:
            st.error("Enter a name to continue.")
            return False
        
        user = get_or_create_user(username)
    
        st.session_state["user_id"] = user["id"]
        st.session_state["username"] = user["username"]

        st.rerun()

    return False