import sys
sys.stdout.reconfigure(encoding='utf-8')
from app.state import get_db

db = get_db()
conn = db._get_connection()
cur = conn.cursor()

print("=== USERS ===")
cur.execute("SELECT id, name, email, role, college_id, university_id, requires_password_change FROM users ORDER BY role, name;")
for r in cur.fetchall():
    print(dict(r) if hasattr(r, 'keys') else r)

print("\n=== STUDENTS ===")
cur.execute("SELECT id, name, enrollment_number, college_id, university_id, team_id, requires_password_change FROM students ORDER BY enrollment_number;")
for r in cur.fetchall():
    print(dict(r) if hasattr(r, 'keys') else r)

print("\n=== TEAMS ===")
cur.execute("SELECT id, name, college_id, submission_allowed FROM teams ORDER BY name;")
for r in cur.fetchall():
    print(dict(r) if hasattr(r, 'keys') else r)

conn.close()
