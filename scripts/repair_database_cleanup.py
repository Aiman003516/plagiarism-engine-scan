"""Repair database state: restore student Ahmed to team_sanaa_ai_1 and clean up test projects."""

import sys
sys.stdout.reconfigure(encoding='utf-8')

from plagiarism_engine.db import store

conn = store._get_connection()
try:
    cur = conn.cursor()
    # 1. Restore student Ahmed
    cur.execute("UPDATE students SET team_id = %s WHERE id = %s;", ("team_sanaa_ai_1", "std_2024101001"))
    print(f"Updated student team_id: {cur.rowcount} row(s)")

    # 2. Clean up test projects
    cur.execute("DELETE FROM projects WHERE title LIKE %s;", ("%Quadrotor%",))
    print(f"Deleted test projects: {cur.rowcount} row(s)")

    # 3. Clean up test teams
    cur.execute("DELETE FROM teams WHERE id LIKE %s;", ("test_team_%",))
    print(f"Deleted test teams: {cur.rowcount} row(s)")

    conn.commit()
    print("Database state successfully repaired.")
finally:
    conn.close()
