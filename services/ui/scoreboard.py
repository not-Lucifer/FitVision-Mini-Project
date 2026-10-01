from html import escape


# Competition kettlebell colours, one per exercise: (fill, text on fill)
EXERCISE_COLORS = {
    "Squats": ("#FFC21A", "#17153A"),
    "Push-ups": ("#2F6BFF", "#FFFFFF"),
    "Biceps Curls (Dumbbell)": ("#FF4F9A", "#17153A"),
    "Shoulder Press": ("#7C4DFF", "#FFFFFF"),
    "Lunges": ("#FF7A1A", "#17153A"),
}

EXERCISE_LABELS = {
    "Squats": "Squats",
    "Push-ups": "Push-ups",
    "Biceps Curls (Dumbbell)": "Biceps curls",
    "Shoulder Press": "Shoulder press",
    "Lunges": "Lunges",
}

# Checks shown under the counter for each exercise: (label, session key, kind)
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

# Detector statuses that need the user's attention
ISSUE_STATUSES = {
    "TOO HIGH",
    "Slight Bend",
    "Poor Form",
    "SAGGING",
    "PIKED UP",
    "ELBOW DRIFTING",
    "SWINGING",
    "Slight Arch",
    "Excessive Arch",
    "OFF BALANCE",
}


def exercise_label(exercise):
    return EXERCISE_LABELS.get(exercise, exercise or "")


def exercise_colors(exercise):
    return EXERCISE_COLORS.get(exercise, ("#17153A", "#FFFFFF"))


def _status_text(value):
    text = str(value)
    if text == "N/A":
        return "Waiting"
    return text[:1].upper() + text[1:].lower()


def _metric_row(label, value, kind):
    if kind == "angle":
        shown = f"{value}°" if value else "–"
        return f'<div class="wp-row"><dt>{escape(label)}</dt><dd>{escape(shown)}</dd></div>'

    if str(value) in ISSUE_STATUSES:
        shown = f'<span class="wp-issue">{escape(_status_text(value))}</span>'
    elif str(value) == "N/A":
        shown = f'<span class="wp-idle">{escape(_status_text(value))}</span>'
    else:
        shown = escape(_status_text(value))

    return f'<div class="wp-row"><dt>{escape(label)}</dt><dd>{shown}</dd></div>'


def _set_track(target_sets, sets_completed, current_set_reps, reps_per_set):
    segments = []
    for index in range(target_sets):
        if index < sets_completed:
            fill = 100
        elif index == sets_completed:
            fill = round(100 * current_set_reps / reps_per_set)
        else:
            fill = 0
        segments.append(f'<span class="wp-seg"><span style="width:{fill}%"></span></span>')

    label = f"{min(sets_completed, target_sets)} of {target_sets} sets done"
    return f'<div class="wp-sets" role="img" aria-label="{label}">{"".join(segments)}</div>'


def _camera_note(camera_live, pose_detected, workout_done, target_sets):
    if workout_done:
        return f'<p class="wp-note">All {target_sets} sets done. End the workout when you are ready.</p>'
    if not camera_live:
        return '<p class="wp-note">Press <strong>Start</strong> under the video to turn on your camera.</p>'
    if not pose_detected:
        return (
            '<p class="wp-note"><span class="wp-issue">Can’t see you</span> '
            'Step back until your whole body is in the frame.</p>'
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
        count_of = f"/{reps_per_set}"
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

    track = (
        _set_track(target_sets, sets_completed, current_set_reps, reps_per_set)
        if has_plan else ""
    )
    note = _camera_note(
        state.get("camera_live", False),
        state.get("pose_detected", True),
        workout_done,
        target_sets,
    )
    fill, on_fill = exercise_colors(exercise)

    return f"""
<section class="workout-panel" style="--ex:{fill};--on-ex:{on_fill}" aria-label="Workout progress">
  <header class="wp-head">
    <h2>{escape(exercise_label(exercise))}</h2>
    <p>{escape(set_label)}</p>
  </header>
  <div class="wp-count" aria-live="polite">
    <span class="wp-number{pulse}">{count}</span><span class="wp-of">{escape(count_of)}</span>
  </div>
  {track}
  <dl class="wp-checks">{rows}</dl>
  {note}
</section>
"""


def coach_note_html(text):
    return (
        '<aside class="coach-note" aria-label="Coach">'
        f'<p class="coach-name">Coach</p><p>{escape(text)}</p></aside>'
    )


def history_html(rows):
    body = "".join(
        f"""<tr>
  <td>{escape(row["date"])}</td>
  <td><span class="hx-dot" style="--ex:{exercise_colors(row["exercise"])[0]}"></span>{escape(exercise_label(row["exercise"]))}</td>
  <td class="num">{row["sets"]}</td>
  <td class="num">{row["reps"]}</td>
  <td class="num">{escape(row["time"])}</td>
</tr>"""
        for row in rows
    )
    return f"""
<table class="history">
  <thead><tr><th>Date</th><th>Exercise</th><th class="num">Sets</th><th class="num">Reps</th><th class="num">Time</th></tr></thead>
  <tbody>{body}</tbody>
</table>
"""
