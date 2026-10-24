"""Comprehensive automated test suite for RBAC hierarchy, self-lockout, and semantic search."""

import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import _create_access_token
from app.state import get_db

class TestRBACHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = get_db()
        cls.student_token = _create_access_token(
            user_id="std_2024101001",
            email="2024101001@student.system",
            role="student",
        )
        cls.student_headers = {"Authorization": f"Bearer {cls.student_token}"}

        cls.college_admin_token = _create_access_token(
            user_id="usr_sanaa_dean_cit",
            email="dean.cit@su.edu.ye",
            role="college_admin",
        )
        cls.college_admin_headers = {"Authorization": f"Bearer {cls.college_admin_token}"}

        cls.ministry_admin_token = _create_access_token(
            user_id="usr_mohesr_admin",
            email="admin@mohesr.gov.ye",
            role="ministry_admin",
        )
        cls.ministry_admin_headers = {"Authorization": f"Bearer {cls.ministry_admin_token}"}

    def test_student_restricted_endpoints(self):
        # Scan endpoints
        res = self.client.post("/api/plagiarism/upload-scan", headers=self.student_headers)
        self.assertEqual(res.status_code, 403)

        # Compare endpoints
        res = self.client.post("/api/plagiarism/compare-projects", json={"project_a_id": "1", "project_b_id": "2"}, headers=self.student_headers)
        self.assertEqual(res.status_code, 403)

        # Deep scan endpoints
        res = self.client.post("/api/plagiarism/deep-scan", json={"query_project_id": "1", "target_project_ids": ["2"]}, headers=self.student_headers)
        self.assertEqual(res.status_code, 403)

        # History endpoints
        res = self.client.get("/api/plagiarism/history", headers=self.student_headers)
        self.assertEqual(res.status_code, 403)

        # Settings
        res = self.client.put("/api/settings", json={"settings": {}}, headers=self.student_headers)
        self.assertEqual(res.status_code, 403)

        # Dashboard stats
        res = self.client.get("/api/dashboard/stats", headers=self.student_headers)
        self.assertEqual(res.status_code, 403)

        # Team mutations
        res = self.client.post("/api/teams", json={"name": "Hacked Team"}, headers=self.student_headers)
        self.assertEqual(res.status_code, 403)

        # User management
        res = self.client.get("/api/users", headers=self.student_headers)
        self.assertEqual(res.status_code, 403)
        res = self.client.post("/api/users", json={"name": "Attacker", "role": "ministry_admin"}, headers=self.student_headers)
        self.assertEqual(res.status_code, 403)

    def test_student_allowed_scoped_endpoints(self):
        res = self.client.get("/api/teams", headers=self.student_headers)
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/api/plagiarism/projects", headers=self.student_headers)
        self.assertEqual(res.status_code, 200)

    def test_semantic_proposal_search(self):
        res = self.client.post(
            "/api/plagiarism/projects/semantic-search",
            json={"query": "Artificial Intelligence surveillance and computer vision", "top_k": 5},
            headers=self.student_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("projects", data)

    def test_delegation_hierarchy_and_scope(self):
        # College admin elevating to ministry_admin
        res = self.client.post(
            "/api/users",
            json={"name": "Unauthorized Admin", "email": "fake.admin@ministry.gov", "password": "pass", "role": "ministry_admin"},
            headers=self.college_admin_headers
        )
        self.assertEqual(res.status_code, 403)

        # College admin elevating to university_admin
        res = self.client.post(
            "/api/users",
            json={"name": "Unauthorized Uni Admin", "email": "fake.uni@ministry.gov", "password": "pass", "role": "university_admin"},
            headers=self.college_admin_headers
        )
        self.assertEqual(res.status_code, 403)

        # College admin creating user for another college
        res = self.client.post(
            "/api/users",
            json={"name": "Cross College Faculty", "email": "cross.college@cs.edu", "password": "pass", "role": "faculty", "college_id": "diff_college_999"},
            headers=self.college_admin_headers
        )
        self.assertEqual(res.status_code, 403)

    def test_self_lockout_and_self_deletion(self):
        # College admin modifying own role
        res = self.client.put(
            "/api/users/usr_sanaa_dean_cit",
            json={"role": "student"},
            headers=self.college_admin_headers
        )
        self.assertEqual(res.status_code, 403)

        # Ministry admin modifying own role
        res = self.client.put(
            "/api/users/usr_mohesr_admin",
            json={"role": "faculty"},
            headers=self.ministry_admin_headers
        )
        self.assertEqual(res.status_code, 403)

        # Admin deleting own account
        res = self.client.delete("/api/users/usr_mohesr_admin", headers=self.ministry_admin_headers)
        self.assertEqual(res.status_code, 400)

    def test_short_query_hybrid_semantic_search(self):
        # Short 1-word query: "robotics" should not return 0 due to 0.72 floor
        res = self.client.post(
            "/api/plagiarism/projects/semantic-search",
            json={"query": "robotics", "top_k": 5},
            headers=self.student_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["total_found"], 0)
        self.assertGreater(data["projects"][0]["similarity_percent"], 15.0)

    def test_supervisor_one_time_submission_workflow(self):
        # 1. Setup a test team and assign student
        import uuid
        test_team_id = f"test_team_{uuid.uuid4().hex[:8]}"
        created_project_ids = []
        orig_student = self.db.get_student_by_id("std_2024101001")
        orig_team_id = orig_student.get("team_id") if orig_student else "team_sanaa_ai_1"

        try:
            self.db.create_team(test_team_id, "Autonomous Robotics Squad", "col_sanaa_cit")
            self.db.add_team_member(test_team_id, "std_2024101001")

            # 2. Initially submission_allowed is False -> student submit fails 403
            submit_payload = {
                "title": "Quadrotor SLAM in GPS-Denied Environments",
                "abstract": "This graduation project explores autonomous LiDAR and visual SLAM for quadrotor drones.",
            }
            res = self.client.post(
                "/api/plagiarism/projects/student-submit",
                json=submit_payload,
                headers=self.student_headers,
            )
            self.assertEqual(res.status_code, 403)

            # 3. Faculty grants 1-time submission token
            faculty_token = _create_access_token(
                user_id="usr_sanaa_fac_ammar",
                email="dr.ammar@su.edu.ye",
                role="faculty",
            )
            res = self.client.post(
                f"/api/teams/{test_team_id}/toggle-submission",
                json={"allowed": True},
                headers={"Authorization": f"Bearer {faculty_token}"},
            )
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()["submission_allowed"])

            # 4. Student submits proposal -> 200 OK, project created with pending_review
            res = self.client.post(
                "/api/plagiarism/projects/student-submit",
                json=submit_payload,
                headers=self.student_headers,
            )
            self.assertEqual(res.status_code, 200)
            created_project = res.json()
            created_project_ids.append(created_project["id"])
            self.assertEqual(created_project["status"], "pending_review")
            self.assertEqual(created_project["title"], submit_payload["title"])

            # 5. Token is now consumed! Second submission attempt is blocked
            res = self.client.post(
                "/api/plagiarism/projects/student-submit",
                json=submit_payload,
                headers=self.student_headers,
            )
            self.assertEqual(res.status_code, 403)

            # 6. Faculty reviews and rejects with revision request + reopen
            res = self.client.post(
                f"/api/plagiarism/projects/{created_project['id']}/review",
                json={
                    "action": "reject",
                    "notes": "Please expand on the sensor fusion Kalman filter methodology.",
                    "reopen_submission": True,
                },
                headers={"Authorization": f"Bearer {faculty_token}"},
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "rejected")

            # 7. Team submission is reopened! Student submits revised proposal -> 200 OK
            res = self.client.post(
                "/api/plagiarism/projects/student-submit",
                json={
                    "title": "Quadrotor SLAM with Extended Kalman Filter",
                    "abstract": "Updated proposal detailing EKF sensor fusion with IMU and stereoscopic vision.",
                },
                headers=self.student_headers,
            )
            self.assertEqual(res.status_code, 200)
            created_project_ids.append(res.json()["id"])

            # 8. Faculty approves proposal
            res = self.client.post(
                f"/api/plagiarism/projects/{res.json()['id']}/review",
                json={"action": "approve", "notes": "Approved by academic committee."},
                headers={"Authorization": f"Bearer {faculty_token}"},
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "approved")

        finally:
            # Clean up test team and test projects
            try:
                self.db.delete_team(test_team_id)
            except Exception:
                pass
            for pid in created_project_ids:
                try:
                    self.db.delete_project(pid)
                except Exception:
                    pass
            # Restore Ahmed back to his original team
            if orig_team_id:
                try:
                    self.db.add_team_member(orig_team_id, "std_2024101001")
                except Exception:
                    pass

    def test_direct_pair_comparison_semantic_and_paths(self):
        # 1. Direct file upload pair comparison
        files = {
            "file_a": ("doc_a.txt", b"This is a technical research paper on neural network architectures and transformer self-attention mechanisms in computer vision.", "text/plain"),
            "file_b": ("doc_b.txt", b"A study on deep learning transformer models and self-attention algorithms for automated image analysis.", "text/plain"),
        }
        res = self.client.post(
            "/api/plagiarism/compare-direct-files",
            files=files,
            headers=self.college_admin_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("similarity", data)
        self.assertIn("semantic_score", data)
        self.assertGreater(data["semantic_score"], 40.0)

    def test_institutional_scoping_and_cross_university_isolation(self):
        # 1. Login with real credentials for Dean of Ibb Engineering & IT
        res = self.client.post("/api/auth/login", json={"email": "dean.eng@univibb.edu.ye", "password": "Dean@2026"})
        self.assertEqual(res.status_code, 200)
        ibb_dean_token = res.json()["token"]
        ibb_headers = {"Authorization": f"Bearer {ibb_dean_token}"}

        # 2. Query /api/teams as Dean of Ibb Eng & IT -> Only Ibb Cloud Pioneers (col_ibb_eng)
        res = self.client.get("/api/teams", headers=ibb_headers)
        self.assertEqual(res.status_code, 200)
        teams = res.json()["teams"]
        team_names = [t["name"] for t in teams]
        self.assertTrue(any("الحوسبة السحابية" in name or "Ibb Cloud Pioneers" in name for name in team_names))
        # Ensure Sana'a and Thamar teams are INVISIBLE
        self.assertFalse(any("الذكاء الاصطناعي" in name for name in team_names))
        self.assertFalse(any("ذمار" in name for name in team_names))

        # 3. Query /api/users as Dean of Ibb Eng & IT -> Only col_ibb_eng users
        res = self.client.get("/api/users", headers=ibb_headers)
        self.assertEqual(res.status_code, 200)
        users = res.json()["users"]
        user_emails = [u["email"] for u in users]
        self.assertIn("dr.khaled@univibb.edu.ye", user_emails)
        self.assertNotIn("dr.ammar@su.edu.ye", user_emails)
        self.assertNotIn("dr.fatima@tu.edu.ye", user_emails)

        # 4. Dean of Ibb attempts to create team for Sana'a -> 403 Forbidden
        res = self.client.post("/api/teams", json={"name": "Hacked Sana Team", "college_id": "col_sanaa_cit"}, headers=ibb_headers)
        self.assertEqual(res.status_code, 403)

        # 5. Login as Dean of Sana'a Computer & IT
        res = self.client.post("/api/auth/login", json={"email": "dean.cit@su.edu.ye", "password": "Dean@2026"})
        self.assertEqual(res.status_code, 200)
        sanaa_cit_token = res.json()["token"]
        sanaa_cit_headers = {"Authorization": f"Bearer {sanaa_cit_token}"}

        # Query /api/teams -> Sees Sana'a AI Visionaries, does NOT see Sana'a Embedded Systems (Faculty of Engineering)
        res = self.client.get("/api/teams", headers=sanaa_cit_headers)
        self.assertEqual(res.status_code, 200)
        sanaa_teams = res.json()["teams"]
        sanaa_team_names = [t["name"] for t in sanaa_teams]
        self.assertTrue(any("الذكاء الاصطناعي" in name for name in sanaa_team_names))
        self.assertFalse(any("النظم المدمجة" in name for name in sanaa_team_names))

        # 6. Login as University Admin of Sana'a (Rector)
        res = self.client.post("/api/auth/login", json={"email": "rector@su.edu.ye", "password": "Sanaa@2026"})
        self.assertEqual(res.status_code, 200)
        rector_token = res.json()["token"]
        rector_headers = {"Authorization": f"Bearer {rector_token}"}

        # Query /api/teams -> Sees BOTH Computer & IT and Engineering teams in Sana'a, does NOT see Ibb or Thamar
        res = self.client.get("/api/teams", headers=rector_headers)
        self.assertEqual(res.status_code, 200)
        rector_teams = res.json()["teams"]
        rector_team_names = [t["name"] for t in rector_teams]
        self.assertTrue(any("الذكاء الاصطناعي" in name for name in rector_team_names))
        self.assertTrue(any("النظم المدمجة" in name for name in rector_team_names))
        self.assertFalse(any("الحوسبة السحابية" in name for name in rector_team_names))
        self.assertFalse(any("ذمار" in name for name in rector_team_names))

        # 7. Login as Ministry Admin -> Sees all 5 teams nationwide
        res = self.client.post("/api/auth/login", json={"email": "admin@mohesr.gov.ye", "password": "Ministry@2026"})
        self.assertEqual(res.status_code, 200)
        min_token = res.json()["token"]
        min_headers = {"Authorization": f"Bearer {min_token}"}

        res = self.client.get("/api/teams", headers=min_headers)
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.json()["teams"]), 5)


if __name__ == "__main__":
    unittest.main()
