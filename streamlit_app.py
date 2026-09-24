import streamlit as st
import requests
import time

# --- CONFIGURATION ---
API_URL = "http://localhost:8000"
st.set_page_config(page_title="Plagiarism Engine UI", layout="wide", page_icon="🔬")

# --- SESSION STATE ---
if "token" not in st.session_state:
    st.session_state.token = None

# --- AUTHENTICATION ---
def login(email, password):
    try:
        r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
        if r.status_code == 200:
            st.session_state.token = r.json().get("token")
            st.success("Login successful!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.error("Login failed. Check your credentials.")
    except Exception as e:
        st.error(f"Could not connect to FastAPI Backend: {e}")

if not st.session_state.token:
    # --- LOGIN PAGE ---
    st.title("🔐 Plagiarism Engine - Login")
    st.write("This Streamlit UI connects directly to your local FastAPI backend.")
    
    with st.form("login_form"):
        email = st.text_input("Email", "admin2@test.com")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In")
        if submitted:
            login(email, password)
else:
    # --- MAIN APP (AUTHENTICATED) ---
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    
    # Sidebar
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to:", ["Dashboard", "Project Intake", "Scanner"])
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state.token = None
        st.rerun()

    # 1. DASHBOARD
    if page == "Dashboard":
        st.title("📊 Dashboard")
        st.write("Live stats pulled from your FastAPI backend.")
        
        r = requests.get(f"{API_URL}/api/dashboard/stats", headers=headers)
        if r.status_code == 200:
            stats = r.json()
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Projects", stats.get("total_projects", 0))
            col2.metric("Total Users", stats.get("total_users", 0))
            col3.metric("Pending Scans", stats.get("pending_scans", 0))
            col4.metric("Completed Scans", stats.get("completed_scans", 0))
        else:
            st.warning("Could not fetch dashboard stats. Check backend logs.")

    # 2. PROJECT INTAKE (UPLOAD)
    elif page == "Project Intake":
        st.title("📤 Project Intake")
        st.info("Upload standard `.zip` files here. Streamlit handles this seamlessly compared to the React dropzone.")
        
        project_name = st.text_input("Project Name (Required)")
        uploaded_file = st.file_uploader("Upload ZIP File", type=["zip"])
        
        if st.button("Upload & Process", type="primary"):
            if not uploaded_file or not project_name:
                st.error("Please provide both a project name and a ZIP file.")
            else:
                # Beautiful Stateful Feedback Example
                with st.status("Uploading and Processing...", expanded=True) as status:
                    st.write("🚀 Sending file to FastAPI backend...")
                    
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/zip")}
                    data = {"project_name": project_name}
                    
                    # POST to backend
                    r = requests.post(f"{API_URL}/api/plagiarism/upload-zip-stream", headers=headers, files=files, data=data)
                    
                    if r.status_code == 200:
                        st.write("✅ File extracted and winnowed.")
                        st.write("✅ Embeddings generated.")
                        status.update(label="Upload Complete! Project Indexed.", state="complete", expanded=False)
                        st.balloons()
                    else:
                        status.update(label="Upload Failed", state="error")
                        st.error(f"Backend Error: {r.text}")

    # 3. SCANNER
    elif page == "Scanner":
        st.title("🔬 Plagiarism Scanner")
        
        # Try fetching projects
        try:
            r = requests.get(f"{API_URL}/api/plagiarism/projects", headers=headers)
            if r.status_code == 200:
                projects = r.json().get('projects', [])
                if not projects:
                    st.info("No projects in the database. Go to Project Intake to upload one.")
                else:
                    # Create a dictionary of project name -> ID
                    proj_dict = {f"{p.get('project_name', 'Unnamed')} (ID: {p.get('id', 'N/A')})": p.get("id") for p in projects}
                    
                    st.subheader("Select a Project to Analyze")
                    selected_name = st.selectbox("Available Projects", list(proj_dict.keys()))
                    selected_id = proj_dict[selected_name]
                    
                    if st.button("Run Deep Scan 🧠", type="primary"):
                        # Stateful UX Feedback for scanning
                        with st.status("Running ML Deep Scan...", expanded=True) as status:
                            st.write("📡 Loading UniXcoder models into memory...")
                            time.sleep(1.5)
                            st.write("🔍 Cross-referencing syntax trees...")
                            time.sleep(1.5)
                            st.write("📊 Calculating similarity scores...")
                            
                            r = requests.post(f"{API_URL}/api/plagiarism/scan", headers=headers, json={"target": str(selected_id)})
                            if r.status_code == 200:
                                status.update(label="Analysis Finished!", state="complete", expanded=False)
                                st.success("Deep Scan completed successfully.")
                                st.json(r.json())
                            else:
                                status.update(label="Scan Failed", state="error")
                                st.error(r.text)
            else:
                st.error("Failed to fetch projects list from the backend.")
        except Exception as e:
            st.error(f"Could not connect to backend: {e}")
