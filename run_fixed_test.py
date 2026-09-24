from playwright.sync_api import sync_playwright
import time
import os
os.makedirs('full_test_screens', exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='chrome')
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    
    # 1. Login
    page.goto('http://localhost:3000/login')
    page.fill('input[type=\'email\']', 'admin2@test.com')
    page.fill('input[type=\'password\']', 'p')
    # Use exact match for the submit button
    page.locator('button[type=\'submit\']').click()
    page.wait_for_load_state('networkidle')
    time.sleep(2)
    
    # 3. Scanner Page
    page.goto('http://localhost:3000/scan')
    page.wait_for_load_state('networkidle')
    time.sleep(2)
    page.screenshot(path='full_test_screens/03_scan_list.png')
    
    # Click the first link that has an href containing '/scan/'
    try:
        page.locator('a[href*=\'/scan/\']').first.click()
        page.wait_for_load_state('networkidle')
        time.sleep(2)
        page.screenshot(path='full_test_screens/04_project_analysis_view.png')
        
        # Click Deep Scan button
        page.locator('button', has_text='Scan').click(timeout=3000)
        time.sleep(0.5)
        page.screenshot(path='full_test_screens/05_deep_scan_spinner.png')
        time.sleep(8)
        page.screenshot(path='full_test_screens/06_deep_scan_results.png')
    except Exception as e:
        print('Deep Scan failed:', e)
        page.screenshot(path='full_test_screens/04_error.png')
        
    browser.close()
    print('Done.')
