import time
import requests
import sys

BASE_URL = "http://127.0.0.0:8000/api"
if len(sys.argv) > 1 and sys.argv[1] == 'local':
    BASE_URL = "http://localhost:8000/api"

print("Waiting for server to start...")
for i in range(20):
    try:
        requests.get("http://localhost:8000/api/plagiarism/projects")
        print("Server is up!")
        break
    except:
        time.sleep(2)
else:
    print("Server failed to start within 40 seconds.")
    sys.exit(1)

results = []

def run_test(name, func):
    try:
        func()
        results.append(f"âœ… {name}")
    except Exception as e:
        results.append(f"âŒ {name}: {str(e)}")

# Test 1: Register
def test_register():
    res = requests.post(f"{BASE_URL}/auth/register", json={
        "name": "Admin Tester",
        "email": "admin@test.com",
        "password": "testpassword123",
        "role": "ministry_admin"
    })
    # If already exists, that's fine, we'll login
    if res.status_code not in [200, 400]:
        raise Exception(f"Status {res.status_code}: {res.text}")

run_test("Auth: Register", test_register)

# Test 2: Login
jwt_token = None
def test_login():
    global jwt_token
    res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@test.com",
        "password": "testpassword123"
    })
    if res.status_code != 200:
        raise Exception(f"Status {res.status_code}: {res.text}")
    data = res.json()
    jwt_token = data.get("access_token")
    if not jwt_token:
        raise Exception("No token received")

run_test("Auth: Login & JWT Issue", test_login)

HEADERS = {"Authorization": f"Bearer {jwt_token}"} if jwt_token else {}

# Test 3: Get Me
def test_get_me():
    res = requests.get(f"{BASE_URL}/auth/me", headers=HEADERS)
    if res.status_code != 200:
        raise Exception(f"Status {res.status_code}: {res.text}")

if jwt_token:
    run_test("Auth: Verify Identity (GET /me)", test_get_me)

# Test 4: Dashboard Stats
def test_dashboard():
    res = requests.get(f"{BASE_URL}/dashboard/stats", headers=HEADERS)
    if res.status_code != 200:
        raise Exception(f"Status {res.status_code}: {res.text}")

if jwt_token:
    run_test("API: Dashboard Stats", test_dashboard)

# Test 5: Teams
def test_teams():
    res = requests.get(f"{BASE_URL}/teams", headers=HEADERS)
    if res.status_code != 200:
        raise Exception(f"Status {res.status_code}: {res.text}")

if jwt_token:
    run_test("API: List Teams", test_teams)

# Test 6: Settings
def test_settings():
    res = requests.get(f"{BASE_URL}/settings", headers=HEADERS)
    if res.status_code != 200:
        raise Exception(f"Status {res.status_code}: {res.text}")

if jwt_token:
    run_test("API: Load Settings", test_settings)

print("\n--- SMOKE TEST RESULTS ---")
for r in results:
    print(r)
