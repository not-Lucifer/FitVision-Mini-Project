import sqlite3
from services.persistence import exercise_repository as repo


def test_add_exercise_merges_same_day_entries(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(repo, "_get_connection", lambda: conn)

    repo.init_db()
    user = repo.get_or_create_user("tester")

    repo.add_exercise(user["id"], "Squats", 10, 1, 30)
    repo.add_exercise(user["id"], "Squats", 10, 1, 25)
    repo.add_exercise(user["id"], "Lunges", 8, 1, 20)

    rows = {row["exercise_name"]: row for row in repo.get_users_exercises(user["id"])}

    assert len(rows) == 2
    assert rows["Squats"]["reps"] == 20
    assert rows["Squats"]["sets"] == 2
    assert rows["Squats"]["time"] == 55
    assert rows["Lunges"]["reps"] == 8
