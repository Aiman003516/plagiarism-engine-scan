"""
Automated Persona Journeys & Multi-Role Permission Lifecycle Verification.
Simulates real human workflows across Ministry Admin, University Admin, College Deans,
Faculty Supervisors, and Students.
"""

import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.state import get_db


class TestPersonaJourneys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = get_db()

    def _login(self, login_id: str, password: str = "Student@2026") -> tuple[str, dict]:
        """Helper to login any user or student and return (token, headers)."""
        res = self.client.post("/api/auth/login", json={"email": login_id, "password": password})
        self.assertEqual(res.status_code, 200, f"Login failed for {login_id}: {res.text}")
        token = res.json()["token"]
        return token, {"Authorization": f"Bearer {token}"}

    def test_story1_academic_proposal_lifecycle_and_one_time_token(self):
        """
        Story 1: Complete Proposal Lifecycle across Roles
        1. Supervisor Dr. Ammar (Sana'a CIT) grants 1-time token to Team Sana'a AI.
        2. Student Lead Ahmed submits proposal -> token consumed (locked).
        3. Ahmed attempts 2nd submission -> blocked with 403.
        4. Teammate Sarah logs in -> views the proposal (teammate visibility).
        5. Sarah attempts to mutate/edit proposal -> blocked with 403.
        6. Supervisor Dr. Ammar reviews proposal -> rejects with notes & re-opens token.
        7. Ahmed sees rejection status + notes, and token re-opened.
        8. Ahmed submits revised proposal.
        9. Supervisor approves proposal -> status becomes 'approved'.
        10. Ahmed attempts to edit approved proposal -> blocked with 403.
        """
        # 1. Login as Dr. Ammar (Faculty supervisor)
        _, sup_headers = self._login("dr.ammar@su.edu.ye", "Faculty@2026")
        
        # Grant submission token to Team Sana'a AI
        res = self.client.put("/api/teams/team_sanaa_ai_1", json={"submission_allowed": True}, headers=sup_headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["submission_allowed"])

        # 2. Login as Student Ahmed
        _, ahmed_headers = self._login("2024101001", "Student@2026")
        
        test_project_id = None
        revised_id = None
        try:
            # Submit Proposal
            res = self.client.post("/api/plagiarism/projects/student-submit", json={
                "title": "Autonomous Quadrotor Navigation via SLAM",
                "abstract": "A deep visual SLAM architecture running real-time on drone hardware.",
                "department": "Artificial Intelligence",
                "year": 2026,
            }, headers=ahmed_headers)
            self.assertEqual(res.status_code, 200, res.text)
            project_data = res.json()
            test_project_id = project_data["id"]
            self.assertEqual(project_data["status"], "pending_review")

            # Verify token was consumed
            res_team = self.client.get("/api/teams/team_sanaa_ai_1", headers=sup_headers)
            self.assertEqual(res_team.status_code, 200)
            self.assertFalse(res_team.json()["submission_allowed"], "Token should be locked after submission")

            # 3. Ahmed attempts second submission -> Must be 403
            res_second = self.client.post("/api/plagiarism/projects/student-submit", json={
                "title": "Duplicate Second Proposal",
                "abstract": "This should be blocked because submission_allowed is false.",
            }, headers=ahmed_headers)
            self.assertEqual(res_second.status_code, 403, "Student must be blocked from second submission without token")

            # 4. Teammate Sarah logs in and checks proposal visibility
            _, sarah_headers = self._login("2024101002", "Student@2026")
            res_sarah_projs = self.client.get("/api/plagiarism/projects", headers=sarah_headers)
            self.assertEqual(res_sarah_projs.status_code, 200)
            sarah_proj_ids = [p["id"] for p in res_sarah_projs.json()["projects"]]
            self.assertIn(test_project_id, sarah_proj_ids, "Teammate must see their team's submitted proposal")

            # 5. Sarah attempts to update/mutate proposal -> Must be 403
            res_sarah_edit = self.client.put(f"/api/plagiarism/projects/{test_project_id}", json={
                "status": "approved",  # forging approval
            }, headers=sarah_headers)
            self.assertEqual(res_sarah_edit.status_code, 403)

            # 6. Supervisor Dr. Ammar reviews proposal -> Rejects with feedback notes and reopens token
            res_review = self.client.post(f"/api/plagiarism/projects/{test_project_id}/review", json={
                "action": "reject",
                "notes": "Please include comparative benchmarks with ORB-SLAM3 in the methodology.",
                "reopen_submission": True,
            }, headers=sup_headers)
            self.assertEqual(res_review.status_code, 200)
            self.assertEqual(res_review.json()["status"], "rejected")

            # 7. Ahmed logs in and views review notes
            res_ahmed_projs = self.client.get("/api/plagiarism/projects", headers=ahmed_headers)
            self.assertEqual(res_ahmed_projs.status_code, 200)
            ahmed_proj = next((p for p in res_ahmed_projs.json()["projects"] if p["id"] == test_project_id), None)
            self.assertIsNotNone(ahmed_proj)
            self.assertEqual(ahmed_proj["status"], "rejected")
            self.assertEqual(ahmed_proj["review_notes"], "Please include comparative benchmarks with ORB-SLAM3 in the methodology.")

            # Verify token re-opened
            res_team_reopened = self.client.get("/api/teams/team_sanaa_ai_1", headers=sup_headers)
            self.assertTrue(res_team_reopened.json()["submission_allowed"])

            # 8. Ahmed submits revised proposal
            res_revised = self.client.post("/api/plagiarism/projects/student-submit", json={
                "title": "Autonomous Quadrotor Navigation via SLAM with ORB-SLAM3 Benchmarks",
                "abstract": "A deep visual SLAM architecture with ORB-SLAM3 comparative benchmarks.",
                "department": "Artificial Intelligence",
                "year": 2026,
            }, headers=ahmed_headers)
            self.assertEqual(res_revised.status_code, 200)
            revised_id = res_revised.json()["id"]

            # 9. Supervisor approves revised proposal
            res_approve = self.client.post(f"/api/plagiarism/projects/{revised_id}/review", json={
                "action": "approve",
                "notes": "Benchmarks added. Approved for semester defense.",
            }, headers=sup_headers)
            self.assertEqual(res_approve.status_code, 200)
            self.assertEqual(res_approve.json()["status"], "approved")

            # 10. Ahmed attempts to edit approved proposal -> Must be 403
            res_edit_approved = self.client.put(f"/api/plagiarism/projects/{revised_id}", json={
                "title": "Tampered Title After Approval",
            }, headers=ahmed_headers)
            self.assertEqual(res_edit_approved.status_code, 403)

        finally:
            if test_project_id:
                self.db.delete_project(test_project_id)
            if revised_id:
                self.db.delete_project(revised_id)
            # Restore submission allowed to False
            self.client.put("/api/teams/team_sanaa_ai_1", json={"submission_allowed": False}, headers=sup_headers)

    def test_story2_strict_cross_university_isolation(self):
        """
        Story 2: Strict Multi-University Isolation
        Dean of Ibb Engineering (Farhan Ghalib) must be completely isolated from Sana'a and Dhamar:
        - Cannot see Sana'a or Dhamar teams.
        - Cannot read, update, or remove members from Sana'a teams (403).
        - Cannot create users outside Ibb University (403).
        """
        _, ibb_dean_headers = self._login("dean.eng@univibb.edu.ye", "Dean@2026")

        # 1. Inspect teams: only Ibb Cloud Pioneers should be visible
        res = self.client.get("/api/teams", headers=ibb_dean_headers)
        self.assertEqual(res.status_code, 200)
        teams = res.json()["teams"]
        team_ids = [t["id"] for t in teams]
        self.assertIn("team_ibb_it_1", team_ids)
        self.assertNotIn("team_sanaa_ai_1", team_ids)
        self.assertNotIn("team_dhamar_cs_1", team_ids)

        # 2. Direct ID access to Sana'a team -> Must be 403
        res_direct = self.client.get("/api/teams/team_sanaa_ai_1", headers=ibb_dean_headers)
        self.assertEqual(res_direct.status_code, 403)

        # 3. Direct update of Sana'a team -> Must be 403
        res_update = self.client.put("/api/teams/team_sanaa_ai_1", json={"name": "Hacked Name"}, headers=ibb_dean_headers)
        self.assertEqual(res_update.status_code, 403)

        # 4. Remove member from Sana'a team -> Must be 403
        res_remove = self.client.delete("/api/teams/team_sanaa_ai_1/members/std_2024101001", headers=ibb_dean_headers)
        self.assertEqual(res_remove.status_code, 403)

        # 5. Create user in Sana'a University -> Must be 403
        res_user = self.client.post("/api/users", json={
            "name": "Rogue Faculty",
            "email": "rogue@su.edu.ye",
            "password": "Password@2026",
            "role": "faculty",
            "university_id": "uni_sanaa",
            "college_id": "col_sanaa_cit",
        }, headers=ibb_dean_headers)
        self.assertEqual(res_user.status_code, 403)

    def test_story3_cross_college_isolation_same_university(self):
        """
        Story 3: College Boundary Isolation inside Same University
        Dean of Sana'a Engineering cannot inspect or review proposals/teams of Sana'a CIT.
        """
        _, eng_dean_headers = self._login("dean.eng@su.edu.ye", "Dean@2026")

        # 1. Teams query: only Engineering teams visible
        res = self.client.get("/api/teams", headers=eng_dean_headers)
        self.assertEqual(res.status_code, 200)
        team_ids = [t["id"] for t in res.json()["teams"]]
        self.assertIn("team_sanaa_eng_1", team_ids)
        self.assertNotIn("team_sanaa_ai_1", team_ids)

        # 2. Attempt to toggle submission on CIT team -> Must be 403
        res_toggle = self.client.put("/api/teams/team_sanaa_ai_1", json={"submission_allowed": True}, headers=eng_dean_headers)
        self.assertEqual(res_toggle.status_code, 403)

    def test_story4_student_security_boundaries_and_anti_exfiltration(self):
        """
        Story 4: Complete Student Security Hardening
        Verifies that students are blocked from all operational, scan, and administrative endpoints.
        """
        _, student_headers = self._login("2024101001", "Student@2026")

        # 1. Blocked from starting scans
        res_upload = self.client.post("/api/plagiarism/upload-scan", data={"project_name": "hack"}, headers=student_headers)
        self.assertEqual(res_upload.status_code, 403)

        res_git = self.client.post("/api/plagiarism/git-scan", json={"repo_url": "https://github.com/test/repo"}, headers=student_headers)
        self.assertEqual(res_git.status_code, 403)

        # 2. Blocked from admin stats & settings
        res_stats = self.client.get("/api/dashboard/stats", headers=student_headers)
        self.assertEqual(res_stats.status_code, 403)

        res_users = self.client.get("/api/users", headers=student_headers)
        self.assertEqual(res_users.status_code, 403)

        res_settings = self.client.get("/api/settings", headers=student_headers)
        self.assertEqual(res_settings.status_code, 403)

        # 3. Blocked from downloading full code of foreign projects
        projs = self.db.get_all_projects(limit=10)
        foreign_proj = next((p for p in projs if p.get("team_id") != "team_sanaa_ai_1" and p.get("student_id") != "std_2024101001"), None)
        if foreign_proj:
            foreign_id = foreign_proj["id"]
            res_code = self.client.get(f"/api/plagiarism/projects/{foreign_id}/files?include_content=true", headers=student_headers)
            self.assertEqual(res_code.status_code, 403, "Students must not exfiltrate source code of projects not submitted by their team")

    def test_story5_ministry_super_admin_full_visibility(self):
        """
        Story 5: Ministry Super Admin Global Oversight
        Ministry Admin Ali Al-Saqqaf has full non-restricted view across all universities.
        """
        _, ministry_headers = self._login("admin@mohesr.gov.ye", "Ministry@2026")

        # 1. Full dashboard stats
        res_stats = self.client.get("/api/dashboard/stats", headers=ministry_headers)
        self.assertEqual(res_stats.status_code, 200)
        self.assertIn("total_projects", res_stats.json())

        # 2. Teams across all 3 universities
        res_teams = self.client.get("/api/teams", headers=ministry_headers)
        self.assertEqual(res_teams.status_code, 200)
        team_ids = [t["id"] for t in res_teams.json()["teams"]]
        self.assertIn("team_sanaa_ai_1", team_ids)
        self.assertIn("team_ibb_it_1", team_ids)
        self.assertIn("team_dhamar_cs_1", team_ids)

        # 3. Users across all institutions
        res_users = self.client.get("/api/users", headers=ministry_headers)
        self.assertEqual(res_users.status_code, 200)
        self.assertGreater(len(res_users.json()["users"]), 10)


if __name__ == "__main__":
    unittest.main()
