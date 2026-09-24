from playwright.sync_api import sync_playwright
import time
import os

os.makedirs("full_test_screens", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    context = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = context.new_page()

    print("1. Logging in...")
    page.goto("http://localhost:3000/login")
    page.fill("input[type='email']", "admin2@test.com")
    page.fill("input[type='password']", "p")
    # Click the login button (finding by generic button type)
    page.locator("button[type='submit']").click()
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    print("2. Project Intake (Upload) - Root Page")
    page.goto("http://localhost:3000/")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    
    # Upload the dummy zip file
    try:
        # page.set_input_files("input[type='file']", "dummy_project_dir")
        # Take screenshot immediately to catch any loading/spinner state
        time.sleep(0.5)
        page.screenshot(path="full_test_screens/01_uploading_spinner.png")
        # Wait for the backend to extract, winnow, and insert into DB
        time.sleep(4)
        page.screenshot(path="full_test_screens/02_upload_success.png")
    except Exception as e:
        print("Upload failed:", e)

    print("3. Plagiarism Scanner (List Page)")
    page.goto("http://localhost:3000/scan")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    page.screenshot(path="full_test_screens/03_scan_list.png")

    print("4. Selecting Project & Running Deep Scan")
    try:
        # Click the first row/project that appears in the table
        page.locator("tbody tr").first.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        page.screenshot(path="full_test_screens/04_project_analysis_view.png")

        # Find the Deep Scan button (might be Arabic or English)
        # We will look for any button containing 'Scan' or 'فحص'
        deep_scan_btn = page.locator("button", has_text="Scan")
        if deep_scan_btn.count() == 0:
            deep_scan_btn = page.locator("button", has_text="فحص عميق")
        
        if deep_scan_btn.count() > 0:
            deep_scan_btn.first.click()
            time.sleep(0.5) # Catch the spinner
            page.screenshot(path="full_test_screens/05_deep_scan_spinner.png")
            
            # Wait for ML models to finish processing (might take 5-10s)
            time.sleep(8)
            page.screenshot(path="full_test_screens/06_deep_scan_results.png")
        else:
            print("Could not find Deep Scan button.")
            page.screenshot(path="full_test_screens/06_no_deep_scan_btn.png")
    except Exception as e:
        print("Project selection failed:", e)

    print("5. Viewing Dashboard")
    page.goto("http://localhost:3000/dashboard")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    page.screenshot(path="full_test_screens/07_dashboard.png")

    print("6. Viewing Settings")
    page.goto("http://localhost:3000/settings")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    page.screenshot(path="full_test_screens/08_settings.png")

    browser.close()
    print("Full workflow test complete.")
