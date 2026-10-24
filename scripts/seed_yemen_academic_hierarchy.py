"""
seed_yemen_academic_hierarchy.py
Clean reset & multi-university institutional hierarchy seeding for Yemeni academic institutions.
Preserves existing indexed benchmark projects and fingerprints while establishing clean
jurisdictional separation across universities, colleges, departments, staff, and students.
"""

import os
import sys
import uuid
import json
import bcrypt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plagiarism_engine.db import SystemDBStore
from plagiarism_engine.db.helpers import decompress_text


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed_hierarchy():
    print("=" * 70)
    print("🎓 Seeding Yemeni Multi-University Academic Hierarchy")
    print("=" * 70)

    db = SystemDBStore()
    conn = db._get_connection()
    cur = conn.cursor()

    try:
        # ---------------------------------------------------------------------
        # 1. Safe Detach & Decompress Existing Benchmark Projects
        # ---------------------------------------------------------------------
        print("\n[Step 1] Preserving benchmark projects and cleaning detached references...")
        cur.execute("""
            UPDATE projects 
            SET student_id = NULL, 
                team_id = NULL, 
                university_id = NULL, 
                college_id = NULL, 
                department_id = NULL
            WHERE student_id IS NOT NULL OR team_id IS NOT NULL;
        """)

        # Clean compressed or binary abstracts in projects
        cur.execute("SELECT id, name, title, abstract FROM projects;")
        projects = cur.fetchall()
        for p in projects:
            pid, pname, ptitle, pabs = p[0], p[1], p[2], p[3] or ""
            new_abs = pabs
            if pabs.startswith("eJy"):
                new_abs = decompress_text(pabs)
                print(f"   🔧 Decompressed Zlib abstract for '{pname}' ({len(new_abs)} chars)")
            elif pabs.startswith("%PDF"):
                new_abs = (
                    "Smart campus edge computing surveillance architecture utilizing lightweight "
                    "deep convolutional networks and TinyML for automated real-time incident detection."
                )
                print(f"   🔧 Sanitized binary PDF abstract for '{pname}'")

            if new_abs != pabs:
                cur.execute("UPDATE projects SET abstract = %s WHERE id = %s;", (new_abs, pid))

        # ---------------------------------------------------------------------
        # 2. Purge Old Users, Students, Teams & Hierarchy
        # ---------------------------------------------------------------------
        print("\n[Step 2] Safely purging old test users, students, teams, and departments...")
        cur.execute("DELETE FROM students;")
        cur.execute("DELETE FROM teams;")
        cur.execute("DELETE FROM users;")
        cur.execute("DELETE FROM departments;")
        cur.execute("DELETE FROM colleges;")
        cur.execute("DELETE FROM universities;")
        print("   ✅ Old test data purged successfully.")

        # ---------------------------------------------------------------------
        # 3. Insert Universities
        # ---------------------------------------------------------------------
        print("\n[Step 3] Seeding Universities...")
        universities = [
            ("uni_sanaa", "جامعة صنعاء - Sana'a University", "UOS"),
            ("uni_ibb", "جامعة إب - Ibb University", "UOI"),
            ("uni_dhamar", "جامعة ذمار - Thamar University", "UOT"),
        ]
        for uid, uname, ucode in universities:
            cur.execute("""
                INSERT INTO universities (id, name, code)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, code = EXCLUDED.code;
            """, (uid, uname, ucode))
            print(f"   🏛️  {uname} ({ucode})")

        # ---------------------------------------------------------------------
        # 4. Insert Colleges
        # ---------------------------------------------------------------------
        print("\n[Step 4] Seeding Colleges...")
        colleges = [
            ("col_sanaa_cit", "uni_sanaa", "كلية الحاسوب وتكنولوجيا المعلومات - Faculty of Computer & IT"),
            ("col_sanaa_eng", "uni_sanaa", "كلية الهندسة - Faculty of Engineering"),
            ("col_ibb_eng", "uni_ibb", "كلية الهندسة وتكنولوجيا المعلومات - Faculty of Engineering & IT"),
            ("col_ibb_sci", "uni_ibb", "كلية العلوم - Faculty of Science"),
            ("col_dhamar_cs", "uni_dhamar", "كلية الحاسوب ونظم المعلومات - Faculty of Computer Science & IS"),
        ]
        for cid, cuid, cname in colleges:
            cur.execute("""
                INSERT INTO colleges (id, university_id, name)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET university_id = EXCLUDED.university_id, name = EXCLUDED.name;
            """, (cid, cuid, cname))
            print(f"   🏢  {cname} [Parent: {cuid}]")

        # ---------------------------------------------------------------------
        # 5. Insert Departments
        # ---------------------------------------------------------------------
        print("\n[Step 5] Seeding Departments...")
        departments = [
            ("dept_sanaa_ai", "col_sanaa_cit", "الذكاء الاصطناعي - Artificial Intelligence"),
            ("dept_sanaa_swe", "col_sanaa_cit", "هندسة البرمجيات - Software Engineering"),
            ("dept_sanaa_ce", "col_sanaa_eng", "هندسة الحاسوب - Computer Engineering"),
            ("dept_ibb_it", "col_ibb_eng", "تقنية المعلومات - Information Technology"),
            ("dept_ibb_math_cs", "col_ibb_sci", "الرياضيات والحاسوب - Mathematics & Computer Science"),
            ("dept_dhamar_cyber", "col_dhamar_cs", "الأمن السيبراني والشبكات - Cybersecurity & Networks"),
        ]
        for did, dcid, dname in departments:
            cur.execute("""
                INSERT INTO departments (id, college_id, name)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET college_id = EXCLUDED.college_id, name = EXCLUDED.name;
            """, (did, dcid, dname))
            print(f"   📂  {dname} [College: {dcid}]")

        # ---------------------------------------------------------------------
        # 6. Insert Staff & Administrative Users
        # ---------------------------------------------------------------------
        print("\n[Step 6] Seeding Administrative & Faculty Users...")
        users = [
            # Ministry Admin (Super Admin)
            {
                "id": "usr_mohesr_admin",
                "name": "م. علي السقاف (Ali Al-Saqqaf)",
                "email": "admin@mohesr.gov.ye",
                "password": hash_password("Ministry@2026"),
                "role": "ministry_admin",
                "university_id": None,
                "college_id": None,
                "department_id": None,
            },
            # Sana'a University Admin
            {
                "id": "usr_sanaa_rector",
                "name": "أ.د. القاسم عباس (Prof. Al-Qasim Abbas)",
                "email": "rector@su.edu.ye",
                "password": hash_password("Sanaa@2026"),
                "role": "university_admin",
                "university_id": "uni_sanaa",
                "college_id": None,
                "department_id": None,
            },
            # Deans Sana'a
            {
                "id": "usr_sanaa_dean_cit",
                "name": "د. فضل باعلوي (Dr. Fadhl Ba-Alawi)",
                "email": "dean.cit@su.edu.ye",
                "password": hash_password("Dean@2026"),
                "role": "college_admin",
                "university_id": "uni_sanaa",
                "college_id": "col_sanaa_cit",
                "department_id": None,
            },
            {
                "id": "usr_sanaa_dean_eng",
                "name": "أ.د. محمد البخيتي (Prof. Mohammed Al-Bukhaiti)",
                "email": "dean.eng@su.edu.ye",
                "password": hash_password("Dean@2026"),
                "role": "college_admin",
                "university_id": "uni_sanaa",
                "college_id": "col_sanaa_eng",
                "department_id": None,
            },
            # Faculty Sana'a
            {
                "id": "usr_sanaa_fac_ammar",
                "name": "د. عمار زاهر (Dr. Ammar Zaher)",
                "email": "dr.ammar@su.edu.ye",
                "password": hash_password("Faculty@2026"),
                "role": "faculty",
                "university_id": "uni_sanaa",
                "college_id": "col_sanaa_cit",
                "department_id": "dept_sanaa_ai",
            },
            {
                "id": "usr_sanaa_fac_nabil",
                "name": "د. نبيل العريقي (Dr. Nabil Al-Ariqi)",
                "email": "dr.nabil@su.edu.ye",
                "password": hash_password("Faculty@2026"),
                "role": "faculty",
                "university_id": "uni_sanaa",
                "college_id": "col_sanaa_cit",
                "department_id": "dept_sanaa_swe",
            },
            {
                "id": "usr_sanaa_fac_tariq",
                "name": "د. طارق المجيدي (Dr. Tariq Al-Majidi)",
                "email": "dr.tariq@su.edu.ye",
                "password": hash_password("Faculty@2026"),
                "role": "faculty",
                "university_id": "uni_sanaa",
                "college_id": "col_sanaa_eng",
                "department_id": "dept_sanaa_ce",
            },
            # Ibb University Admin
            {
                "id": "usr_ibb_rector",
                "name": "أ.د. نصر الحجيلي (Prof. Nasr Al-Hujaili)",
                "email": "rector@univibb.edu.ye",
                "password": hash_password("Ibb@2026"),
                "role": "university_admin",
                "university_id": "uni_ibb",
                "college_id": None,
                "department_id": None,
            },
            # Deans Ibb
            {
                "id": "usr_ibb_dean_eng",
                "name": "د. فرحان غالب (Dr. Farhan Ghalib)",
                "email": "dean.eng@univibb.edu.ye",
                "password": hash_password("Dean@2026"),
                "role": "college_admin",
                "university_id": "uni_ibb",
                "college_id": "col_ibb_eng",
                "department_id": None,
            },
            {
                "id": "usr_ibb_dean_sci",
                "name": "د. علي الوادعي (Dr. Ali Al-Wadei)",
                "email": "dean.sci@univibb.edu.ye",
                "password": hash_password("Dean@2026"),
                "role": "college_admin",
                "university_id": "uni_ibb",
                "college_id": "col_ibb_sci",
                "department_id": None,
            },
            # Faculty Ibb
            {
                "id": "usr_ibb_fac_khaled",
                "name": "د. خالد الصلاحي (Dr. Khaled Al-Salahi)",
                "email": "dr.khaled@univibb.edu.ye",
                "password": hash_password("Faculty@2026"),
                "role": "faculty",
                "university_id": "uni_ibb",
                "college_id": "col_ibb_eng",
                "department_id": "dept_ibb_it",
            },
            {
                "id": "usr_ibb_fac_samira",
                "name": "د. سميرة الشوافي (Dr. Samira Al-Shawafi)",
                "email": "dr.samira@univibb.edu.ye",
                "password": hash_password("Faculty@2026"),
                "role": "faculty",
                "university_id": "uni_ibb",
                "college_id": "col_ibb_sci",
                "department_id": "dept_ibb_math_cs",
            },
            # Thamar University Admin
            {
                "id": "usr_dhamar_rector",
                "name": "أ.د. محمد الحيفي (Prof. Mohammed Al-Haifi)",
                "email": "rector@tu.edu.ye",
                "password": hash_password("Dhamar@2026"),
                "role": "university_admin",
                "university_id": "uni_dhamar",
                "college_id": None,
                "department_id": None,
            },
            # Dean Thamar
            {
                "id": "usr_dhamar_dean_cs",
                "name": "د. بشير المقالح (Dr. Basheer Al-Maqaleh)",
                "email": "dean.cs@tu.edu.ye",
                "password": hash_password("Dean@2026"),
                "role": "college_admin",
                "university_id": "uni_dhamar",
                "college_id": "col_dhamar_cs",
                "department_id": None,
            },
            # Faculty Thamar
            {
                "id": "usr_dhamar_fac_fatima",
                "name": "د. فاطمة الغشم (Dr. Fatima Al-Ghashm)",
                "email": "dr.fatima@tu.edu.ye",
                "password": hash_password("Faculty@2026"),
                "role": "faculty",
                "university_id": "uni_dhamar",
                "college_id": "col_dhamar_cs",
                "department_id": "dept_dhamar_cyber",
            },
        ]

        for u in users:
            cur.execute("""
                INSERT INTO users (id, name, email, password_hash, role, university_id, college_id, department_id, requires_password_change)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE)
                ON CONFLICT (id) DO UPDATE SET 
                    name = EXCLUDED.name,
                    email = EXCLUDED.email,
                    password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role,
                    university_id = EXCLUDED.university_id,
                    college_id = EXCLUDED.college_id,
                    department_id = EXCLUDED.department_id,
                    requires_password_change = FALSE;
            """, (u["id"], u["name"], u["email"], u["password"], u["role"], u["university_id"], u["college_id"], u["department_id"]))
            print(f"   👤 {u['name']} ({u['email']}) -> {u['role']}")

        # ---------------------------------------------------------------------
        # 7. Insert Student Teams
        # ---------------------------------------------------------------------
        print("\n[Step 7] Seeding Teams...")
        teams = [
            ("team_sanaa_ai_1", "فريق رؤية الذكاء الاصطناعي (Sana'a AI Visionaries)", "col_sanaa_cit"),
            ("team_sanaa_eng_1", "فريق هندسة النظم المدمجة (Embedded Systems Core)", "col_sanaa_eng"),
            ("team_ibb_it_1", "رواد الحوسبة السحابية (Ibb Cloud Pioneers)", "col_ibb_eng"),
            ("team_ibb_sci_1", "مجموعة التشفير التطبيقي (Applied Cryptography Group)", "col_ibb_sci"),
            ("team_dhamar_cs_1", "درع ذمار السيبراني (Dhamar Cyber Shield)", "col_dhamar_cs"),
        ]
        for tid, tname, tcid in teams:
            cur.execute("""
                INSERT INTO teams (id, name, college_id, submission_allowed)
                VALUES (%s, %s, %s, FALSE)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, college_id = EXCLUDED.college_id, submission_allowed = FALSE;
            """, (tid, tname, tcid))
            print(f"   👥 {tname} [College: {tcid}]")

        # ---------------------------------------------------------------------
        # 8. Insert Students
        # ---------------------------------------------------------------------
        print("\n[Step 8] Seeding Students...")
        students = [
            # Sana'a University - CIT
            {
                "id": "std_2024101001",
                "enrollment_number": "2024101001",
                "name": "أحمد الحمادي (Ahmed Al-Hammadi)",
                "email": "2024101001@student.system",
                "password": hash_password("Student@2026"),
                "university_id": "uni_sanaa",
                "college_id": "col_sanaa_cit",
                "department_id": "dept_sanaa_ai",
                "team_id": "team_sanaa_ai_1",
            },
            {
                "id": "std_2024101002",
                "enrollment_number": "2024101002",
                "name": "سارة الزبيري (Sarah Al-Zubairi)",
                "email": "2024101002@student.system",
                "password": hash_password("Student@2026"),
                "university_id": "uni_sanaa",
                "college_id": "col_sanaa_cit",
                "department_id": "dept_sanaa_ai",
                "team_id": "team_sanaa_ai_1",
            },
            # Sana'a University - Eng
            {
                "id": "std_2024102001",
                "enrollment_number": "2024102001",
                "name": "يحيى المتوكل (Yahya Al-Mutawakkil)",
                "email": "2024102001@student.system",
                "password": hash_password("Student@2026"),
                "university_id": "uni_sanaa",
                "college_id": "col_sanaa_eng",
                "department_id": "dept_sanaa_ce",
                "team_id": "team_sanaa_eng_1",
            },
            {
                "id": "std_2024102002",
                "enrollment_number": "2024102002",
                "name": "ريم الشامي (Reem Al-Shami)",
                "email": "2024102002@student.system",
                "password": hash_password("Student@2026"),
                "university_id": "uni_sanaa",
                "college_id": "col_sanaa_eng",
                "department_id": "dept_sanaa_ce",
                "team_id": "team_sanaa_eng_1",
            },
            # Ibb University - Eng & IT
            {
                "id": "std_2024201001",
                "enrollment_number": "2024201001",
                "name": "حسام المليكي (Hussam Al-Maliki)",
                "email": "2024201001@student.system",
                "password": hash_password("Student@2026"),
                "university_id": "uni_ibb",
                "college_id": "col_ibb_eng",
                "department_id": "dept_ibb_it",
                "team_id": "team_ibb_it_1",
            },
            {
                "id": "std_2024201002",
                "enrollment_number": "2024201002",
                "name": "مروة الأهدل (Marwa Al-Ahdal)",
                "email": "2024201002@student.system",
                "password": hash_password("Student@2026"),
                "university_id": "uni_ibb",
                "college_id": "col_ibb_eng",
                "department_id": "dept_ibb_it",
                "team_id": "team_ibb_it_1",
            },
            # Ibb University - Science
            {
                "id": "std_2024202001",
                "enrollment_number": "2024202001",
                "name": "ماجد القاضي (Majed Al-Qadi)",
                "email": "2024202001@student.system",
                "password": hash_password("Student@2026"),
                "university_id": "uni_ibb",
                "college_id": "col_ibb_sci",
                "department_id": "dept_ibb_math_cs",
                "team_id": "team_ibb_sci_1",
            },
            # Thamar University - CS & IS
            {
                "id": "std_2024301001",
                "enrollment_number": "2024301001",
                "name": "أسامة الورقي (Osama Al-Waraqi)",
                "email": "2024301001@student.system",
                "password": hash_password("Student@2026"),
                "university_id": "uni_dhamar",
                "college_id": "col_dhamar_cs",
                "department_id": "dept_dhamar_cyber",
                "team_id": "team_dhamar_cs_1",
            },
            {
                "id": "std_2024301002",
                "enrollment_number": "2024301002",
                "name": "هند العنسي (Hind Al-Ansi)",
                "email": "2024301002@student.system",
                "password": hash_password("Student@2026"),
                "university_id": "uni_dhamar",
                "college_id": "col_dhamar_cs",
                "department_id": "dept_dhamar_cyber",
                "team_id": "team_dhamar_cs_1",
            },
        ]

        for s in students:
            # 1. Insert into students table
            cur.execute("""
                INSERT INTO students (id, enrollment_number, name, password_hash, requires_password_change, university_id, college_id, department_id, team_id)
                VALUES (%s, %s, %s, %s, FALSE, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    enrollment_number = EXCLUDED.enrollment_number,
                    name = EXCLUDED.name,
                    password_hash = EXCLUDED.password_hash,
                    requires_password_change = FALSE,
                    university_id = EXCLUDED.university_id,
                    college_id = EXCLUDED.college_id,
                    department_id = EXCLUDED.department_id,
                    team_id = EXCLUDED.team_id;
            """, (s["id"], s["enrollment_number"], s["name"], s["password"], s["university_id"], s["college_id"], s["department_id"], s["team_id"]))

            # 2. Insert into users table so students can login seamlessly
            cur.execute("""
                INSERT INTO users (id, name, email, password_hash, role, university_id, college_id, department_id, requires_password_change)
                VALUES (%s, %s, %s, %s, 'student', %s, %s, %s, FALSE)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    email = EXCLUDED.email,
                    password_hash = EXCLUDED.password_hash,
                    role = 'student',
                    university_id = EXCLUDED.university_id,
                    college_id = EXCLUDED.college_id,
                    department_id = EXCLUDED.department_id,
                    requires_password_change = FALSE;
            """, (s["id"], s["name"], s["enrollment_number"], s["password"], s["university_id"], s["college_id"], s["department_id"]))
            print(f"   🎓 Student {s['name']} (ID: {s['enrollment_number']}) -> Team: {s['team_id']}")

        conn.commit()
        print("\n" + "=" * 70)
        print("✅ YEMENI ACADEMIC HIERARCHY SEEDED SUCCESSFULLY!")
        print("=" * 70)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Seeding failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    seed_hierarchy()
