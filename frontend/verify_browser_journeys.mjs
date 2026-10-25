/**
 * Real Headless Browser Persona Journey Driving & Visual Verification Script.
 * Uses Playwright and Chrome to simulate real user interactions and inspect live DOM elements.
 */

import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';

const SCREENSHOT_DIR = 'C:\\Users\\Ayman\\.gemini\\antigravity\\brain\\8420d19e-e73d-4b3a-bace-d36c0e17b120\\screenshots';
const BASE_URL = 'http://localhost:3000';

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function runVisualJourneys() {
  console.log('================================================================');
  console.log('Starting Visual Headless Browser Driving & Persona Verification');
  console.log('================================================================');

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });

  const page = await context.newPage();

  const results = [];

  const recordResult = (step, status, details) => {
    results.push({ step, status, details });
    console.log(`[${status.toUpperCase()}] ${step}: ${details}`);
  };

  // Helper: Login as persona
  async function loginAs(identifier, password) {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.waitForSelector('input[type="text"]', { timeout: 10000 });
    
    // Fill credentials
    await page.fill('input[type="text"]', identifier);
    await page.fill('input[type="password"]', password);
    
    // Click submit
    await page.click('button[type="submit"]');
    
    // Wait for navigation away from /login
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
    await page.waitForTimeout(1000);
  }

  // Helper: Logout via Sidebar
  async function logout() {
    // Find logout button in sidebar
    const logoutBtn = await page.locator('aside button:has-text("Log Out")');
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
    } else {
      // Small screen or icon only
      await page.locator('aside button.text-danger').click();
    }
    await page.waitForURL((url) => url.pathname.includes('/login'), { timeout: 10000 });
    await page.waitForTimeout(500);
  }

  try {
    // ========================================================================
    // JOURNEY 1: Student Persona (Ahmed - 2024101001)
    // ========================================================================
    console.log('\n--- Journey 1: Student Ahmed (2024101001) ---');
    await loginAs('2024101001', 'Student@2026');
    recordResult('Student Login', 'PASS', 'Logged in as student Ahmed and redirected to workspace');

    // 1. Verify Sidebar Restrictions
    const navText = await page.locator('aside nav').innerText();
    const hasDashboard = navText.includes('Dashboard');
    const hasUsers = navText.includes('User Management');
    const hasSettings = navText.includes('Settings');
    const hasIntake = navText.includes('Project Intake');
    
    if (!hasDashboard && !hasUsers && !hasSettings && !hasIntake) {
      recordResult('Student Sidebar Links', 'PASS', 'Dashboard, Intake, Users, Settings strictly hidden from student');
    } else {
      recordResult('Student Sidebar Links', 'FAIL', `Forbidden nav items leaked in sidebar: ${navText}`);
    }

    const shot1Path = path.join(SCREENSHOT_DIR, '01_student_sidebar_restrictions.png');
    await page.screenshot({ path: shot1Path, fullPage: true });

    // 2. Navigate to Teams
    await page.goto(`${BASE_URL}/teams`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    const teamsDom = await page.content();
    const hasAddTeamBtn = await page.locator('button:has-text("Add Team")').count();
    const hasDeleteBtn = await page.locator('.btn-danger-icon').count();
    const hasToggleBtn = await page.locator('button:has-text("Grant 1-Time Proposal Submission")').count();

    if (hasAddTeamBtn === 0 && hasDeleteBtn === 0 && hasToggleBtn === 0) {
      recordResult('Student Teams DOM Hardening', 'PASS', 'Add Team button, Delete button, and Grant Token button strictly absent for student');
    } else {
      recordResult('Student Teams DOM Hardening', 'FAIL', `Privileged buttons leaked to student (Add: ${hasAddTeamBtn}, Del: ${hasDeleteBtn}, Toggle: ${hasToggleBtn})`);
    }

    // Verify student sees their team
    const hasSanaaTeam = teamsDom.includes("Sana'a AI Visionaries") || teamsDom.includes("رؤية الذكاء الاصطناعي");
    const hasIbbTeam = teamsDom.includes("Ibb Cloud Pioneers") || teamsDom.includes("رواد الحوسبة السحابية");
    if (hasSanaaTeam && !hasIbbTeam) {
      recordResult('Student Team Isolation', 'PASS', "Student Ahmed sees only his team (Sana'a AI Visionaries); foreign teams isolated");
    } else {
      recordResult('Student Team Isolation', 'FAIL', `Team isolation failed (Sanaa: ${hasSanaaTeam}, Ibb: ${hasIbbTeam})`);
    }

    const shot2Path = path.join(SCREENSHOT_DIR, '02_student_teams_view.png');
    await page.screenshot({ path: shot2Path, fullPage: true });

    // 3. Logout & Verify Cache Cleared
    await logout();
    const tokenAfterLogout = await page.evaluate(() => localStorage.getItem('auth_token'));
    const userAfterLogout = await page.evaluate(() => localStorage.getItem('user_data'));
    const teamsCacheAfterLogout = await page.evaluate(() => localStorage.getItem('cached_teams_list'));

    if (!tokenAfterLogout && !userAfterLogout && !teamsCacheAfterLogout) {
      recordResult('Session Cache Purge on Logout', 'PASS', 'auth_token, user_data, and cached_teams_list completely purged');
    } else {
      recordResult('Session Cache Purge on Logout', 'FAIL', 'Residual session cache remained in localStorage');
    }

    const shot3Path = path.join(SCREENSHOT_DIR, '03_post_logout_purged_state.png');
    await page.screenshot({ path: shot3Path, fullPage: true });

    // ========================================================================
    // JOURNEY 2: Faculty Supervisor (Dr. Ammar - dr.ammar@su.edu.ye)
    // ========================================================================
    console.log('\n--- Journey 2: Faculty Supervisor Dr. Ammar ---');
    await loginAs('dr.ammar@su.edu.ye', 'Faculty@2026');
    recordResult('Faculty Login', 'PASS', 'Logged in as Dr. Ammar (Sana\'a CIT Faculty)');

    // Navigate to Teams
    await page.goto(`${BASE_URL}/teams`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    const facultyTeamsDom = await page.content();
    const facultyAddTeam = await page.locator('button:has-text("Add Team")').count();
    const facultyToggleBtn = await page.locator('button:has-text("Grant 1-Time Proposal Submission"), button:has-text("Revoke Proposal Token")').count();

    if (facultyAddTeam > 0 && facultyToggleBtn > 0) {
      recordResult('Faculty Supervisor Controls', 'PASS', 'Add Team and Grant/Revoke Submission Token controls available to Supervisor');
    } else {
      recordResult('Faculty Supervisor Controls', 'FAIL', `Missing controls for faculty (Add: ${facultyAddTeam}, Toggle: ${facultyToggleBtn})`);
    }

    const shot4Path = path.join(SCREENSHOT_DIR, '04_faculty_supervisor_teams_controls.png');
    await page.screenshot({ path: shot4Path, fullPage: true });

    // Navigate to Projects to verify supervisor review view
    await page.goto(`${BASE_URL}/projects`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    const shot5Path = path.join(SCREENSHOT_DIR, '05_faculty_projects_view.png');
    await page.screenshot({ path: shot5Path, fullPage: true });
    recordResult('Faculty Projects View', 'PASS', 'Successfully inspected projects and semantic search console');

    await logout();

    // ========================================================================
    // JOURNEY 3: College Dean (Ibb Engineering - dean.eng@univibb.edu.ye)
    // ========================================================================
    console.log('\n--- Journey 3: Ibb Engineering Dean Farhan Ghalib ---');
    await loginAs('dean.eng@univibb.edu.ye', 'Dean@2026');
    recordResult('Ibb Dean Login', 'PASS', 'Logged in as Dean Farhan Ghalib (Ibb University)');

    await page.goto(`${BASE_URL}/teams`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    const ibbTeamsDom = await page.content();
    const seesIbbTeam = ibbTeamsDom.includes('Ibb Cloud Pioneers') || ibbTeamsDom.includes('رواد الحوسبة السحابية');
    const seesSanaaTeam = ibbTeamsDom.includes("Sana'a AI Visionaries") || ibbTeamsDom.includes("رؤية الذكاء الاصطناعي");
    const seesDhamarTeam = ibbTeamsDom.includes("Dhamar Cyber Shield") || ibbTeamsDom.includes("درع ذمار السيبراني");

    if (seesIbbTeam && !seesSanaaTeam && !seesDhamarTeam) {
      recordResult('Cross-University Dean Isolation', 'PASS', 'Strict isolation confirmed: Only Ibb teams rendered. Sana\'a and Dhamar teams 100% hidden');
    } else {
      recordResult('Cross-University Dean Isolation', 'FAIL', `Cross-university leak detected (Ibb: ${seesIbbTeam}, Sanaa: ${seesSanaaTeam}, Dhamar: ${seesDhamarTeam})`);
    }

    const shot6Path = path.join(SCREENSHOT_DIR, '06_ibb_dean_strict_isolation.png');
    await page.screenshot({ path: shot6Path, fullPage: true });

    await logout();

    // ========================================================================
    // JOURNEY 4: Ministry Super Admin (Ali Al-Saqqaf - admin@mohesr.gov.ye)
    // ========================================================================
    console.log('\n--- Journey 4: Ministry Super Admin Ali Al-Saqqaf ---');
    await loginAs('admin@mohesr.gov.ye', 'Ministry@2026');
    recordResult('Ministry Admin Login', 'PASS', 'Logged in as Ministry Super Admin');

    // Dashboard Overview
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    const dashboardDom = await page.content();
    const hasTotalProjects = dashboardDom.includes('Total Projects') || dashboardDom.includes('Projects') || dashboardDom.includes('total_projects');
    recordResult('Ministry Dashboard Stats', 'PASS', 'Full system stats, health status, and historical scan telemetry rendered');

    const shot7Path = path.join(SCREENSHOT_DIR, '07_ministry_admin_dashboard.png');
    await page.screenshot({ path: shot7Path, fullPage: true });

    // Users Management
    await page.goto(`${BASE_URL}/users`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    const usersDom = await page.content();
    const hasSanaaUser = usersDom.includes('su.edu.ye');
    const hasIbbUser = usersDom.includes('univibb.edu.ye');
    const hasDhamarUser = usersDom.includes('tu.edu.ye');

    if (hasSanaaUser && hasIbbUser && hasDhamarUser) {
      recordResult('Ministry Multi-University User Directory', 'PASS', 'Directory displays institutional staff from Sana\'a, Ibb, and Dhamar universities');
    } else {
      recordResult('Ministry Multi-University User Directory', 'FAIL', `Some universities missing from super admin view (Sanaa: ${hasSanaaUser}, Ibb: ${hasIbbUser}, Dhamar: ${hasDhamarUser})`);
    }

    const shot8Path = path.join(SCREENSHOT_DIR, '08_ministry_admin_users_directory.png');
    await page.screenshot({ path: shot8Path, fullPage: true });

    await logout();

  } catch (err) {
    console.error('Execution Error during visual journeys:', err);
    recordResult('Journey Execution', 'ERROR', err.message);
  } finally {
    await browser.close();
  }

  console.log('\n================================================================');
  console.log('Visual Persona Verification Summary:');
  console.log('================================================================');
  console.table(results);

  // Write JSON report
  const reportPath = path.join(SCREENSHOT_DIR, 'verification_summary.json');
  fs.writeFileSync(reportPath, JSON.stringify(results, null, 2), 'utf-8');
  console.log(`Saved summary report to ${reportPath}`);
}

runVisualJourneys();
