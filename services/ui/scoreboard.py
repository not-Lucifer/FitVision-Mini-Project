from html import escape


# Metrics shown under the counter for each exercise: (label, session key, kind)
SCOREBOARD_METRICS = {
    "Squats": [
        ("Depth", "depth_status", "status"),
        ("Knee angle", "knee_angle", "angle"),
        ("Back angle", "back_angle", "angle"),
    ],
    "Push-ups": [
        ("Body line", "body_alignment", "status"),
        ("Hips", "hip_status", "status"),
        ("Elbow angle", "elbow_angle", "angle"),
    ],
    "Biceps Curls (Dumbbell)": [
        ("Torso swing", "swing_status", "status"),
        ("Elbow position", "shoulder_status", "status"),
        ("Elbow angle", "elbow_angle", "angle"),
    ],
    "Shoulder Press": [
        ("Lower back", "back_arch_status", "status"),
        ("Arm extension", "extension_status", "status"),
        ("Elbow angle", "elbow_angle", "angle"),
    ],
    "Lunges": [
        ("Balance", "balance_status", "status"),
        ("Front knee angle", "front_knee_angle", "angle"),
        ("Torso angle", "torso_angle", "angle"),
    ],
}

# Detector status -> tone. Tones map to plate colours in style.css.
STATUS_TONES = {
    "GOOD DEPTH": "good",
    "TOO HIGH": "warn",
    "Straight": "good",
    "Slight Bend": "warn",
    "Poor Form": "bad",
    "LEVEL": "good",
    "SAGGING": "bad",
    "PIKED UP": "warn",
    "STABLE": "good",
    "ELBOW DRIFTING": "warn",
    "NO SWING": "good",
    "SWINGING": "bad",
    "FULL EXTENSION": "good",
    "Neutral": "good",
    "Slight Arch": "warn",
    "Excessive Arch": "bad",
    "BALANCED": "good",
    "OFF BALANCE": "bad",
}


def _status_text(value):
    text = str(value)
    if text == "N/A":
        return "Waiting"
    return text[:1].upper() + text[1:].lower()


def _metric_row(label, value, kind):
    if kind == "angle":
        shown = f"{value}°" if value else "–"
        return (
            f'<div class="sb-row"><dt>{escape(label)}</dt>'
            f'<dd class="sb-angle">{escape(shown)}</dd></div>'
        )

    tone = STATUS_TONES.get(str(value), "idle")
    return (
        f'<div class="sb-row"><dt>{escape(label)}</dt>'
        f'<dd class="sb-status tone-{tone}"><span class="sb-dot" aria-hidden="true"></span>'
        f'{escape(_status_text(value))}</dd></div>'
    )


def _plates(target_sets, sets_completed, workout_done):
    plates = []
    for index in range(target_sets):
        if index < sets_completed:
            state = "done"
        elif index == sets_completed and not workout_done:
            state = "current"
        else:
            state = "upcoming"
        plates.append(f'<span class="sb-plate plate-{state}"></span>')

    label = f"{min(sets_completed, target_sets)} of {target_sets} sets done"
    return f'<div class="sb-plates" role="img" aria-label="{label}">{"".join(plates)}</div>'


def _camera_note(camera_live, pose_detected, workout_done, target_sets):
    if workout_done:
        return (
            '<p class="sb-note tone-good">'
            f'All {target_sets} sets done. End the workout when you are ready.</p>'
        )
    if not camera_live:
        return '<p class="sb-note">Press <strong>Start</strong> under the video to turn on your camera.</p>'
    if not pose_detected:
        return (
            '<p class="sb-note tone-warn">Can’t see you. Step back until your whole body is in the frame.</p>'
        )
    return ""


def scoreboard_html(state):
    exercise = state.get("exercise_type") or ""
    total_reps = int(state.get("reps") or 0)
    reps_per_set = int(state.get("reps_per_set") or 0)
    target_sets = int(state.get("target_sets") or 0)
    sets_completed = int(state.get("sets_completed") or 0)
    current_set_reps = int(state.get("current_set_reps") or 0)
    has_plan = reps_per_set > 0 and target_sets > 0
    workout_done = has_plan and sets_completed >= target_sets

    if has_plan:
        count = reps_per_set if workout_done else current_set_reps
        count_of = f"of {reps_per_set}"
        set_label = (
            "Workout done" if workout_done
            else f"Set {sets_completed + 1} of {target_sets}"
        )
    else:
        count = total_reps
        count_of = "reps"
        set_label = "Free session"

    # Alternating the animation name restarts the pulse only when the count changes.
    pulse = f" pulse-{total_reps % 2}" if total_reps else ""

    rows = "".join(
        _metric_row(label, state.get(key, 0 if kind == "angle" else "N/A"), kind)
        for label, key, kind in SCOREBOARD_METRICS.get(exercise, [])
    )

    plates = _plates(target_sets, sets_completed, workout_done) if has_plan else ""
    note = _camera_note(
        state.get("camera_live", False),
        state.get("pose_detected", True),
        workout_done,
        target_sets,
    )

    return f"""
<section class="scoreboard" aria-label="Workout progress">
  <header class="sb-head">
    <h2>{escape(exercise)}</h2>
    <p>{escape(set_label)}</p>
  </header>
  <div class="sb-count" aria-live="polite">
    <span class="sb-number{pulse}">{count}</span>
    <span class="sb-of">{escape(count_of)}</span>
  </div>
  {plates}
  <dl class="sb-metrics">{rows}</dl>
  {note}
</section>
"""


def coach_note_html(text):
    return (
        '<aside class="coach-note" aria-label="Coach">'
        f'<p class="coach-name">Coach</p><p>{escape(text)}</p></aside>'
    )
