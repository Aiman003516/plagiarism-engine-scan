from playwright.sync_api import sync_playwright
import time
import os

os.makedirs("test_screenshots", exist_ok=True)

with sync_playwright() as p:
    # Use the local system Chrome instead of the downloaded chromium
    browser = p.chromium.launch(headless=True, channel="chrome")
    context = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = context.new_page()

    print("1. Navigating to Home Page...")
    page.goto("http://localhost:3000")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    page.screenshot(path="test_screenshots/1_home_default.png")

    print("2. Testing Dark Mode Toggle...")
    try:
        # Toggle usually has the class or text for dark mode. Let's just click the button with 'Mode'
        page.get_by_role("button").filter(has_text="Mode").click()
        time.sleep(1)
        page.screenshot(path="test_screenshots/2_home_toggled.png")
    except Exception as e:
        print("Could not click theme toggle:", e)

    print("3. Navigating to Login Page...")
    page.goto("http://localhost:3000/login")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.screenshot(path="test_screenshots/3_login_page.png")

    print("4. Attempting Login...")
    try:
        page.fill("input[type='email']", "admin2@test.com")
        page.fill("input[type='password']", "p")
        page.get_by_role("button").click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        page.screenshot(path="test_screenshots/4_after_login.png")
    except Exception as e:
        print("Login failed:", e)

    print("5. Checking Protected Route (Users)...")
    page.goto("http://localhost:3000/users")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    page.screenshot(path="test_screenshots/5_users_page.png")

    browser.close()
    print("Done. Screenshots saved to test_screenshots/")
