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
            user_id="demo_student",
            email="20240001@student.edu",
            role="student",
        )
        cls.student_headers = {"Authorization": f"Bearer {cls.student_token}"}

        cls.college_admin_token = _create_access_token(
            user_id="demo_college_admin",
            email="dean@engineering.edu",
            role="college_admin",
        )
        cls.college_admin_headers = {"Authorization": f"Bearer {cls.college_admin_token}"}

        cls.ministry_admin_token = _create_access_token(
            user_id="user_admin_smoke",
            email="admin@ministry.gov",
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
            "/api/users/demo_college_admin",
            json={"role": "student"},
            headers=self.college_admin_headers
        )
        self.assertEqual(res.status_code, 403)

        # Ministry admin modifying own role
        res = self.client.put(
            "/api/users/user_admin_smoke",
            json={"role": "faculty"},
            headers=self.ministry_admin_headers
        )
        self.assertEqual(res.status_code, 403)

        # Admin deleting own account
        res = self.client.delete("/api/users/user_admin_smoke", headers=self.ministry_admin_headers)
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
