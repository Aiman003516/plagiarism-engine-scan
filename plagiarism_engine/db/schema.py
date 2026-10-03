"""Schema creation / migration for all tables."""




class SchemaMixin:
    """Schema creation / migration for all tables. Mixed into SystemDBStore."""

    def _init_schema(self):
        """Initializes relational tables for projects, research papers, files, scan audit reports, and fingerprint index."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()

            if self.mode == "postgresql":
                cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    status VARCHAR(50) DEFAULT 'approved',
                    student_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS papers (
                    id VARCHAR(255) PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    author VARCHAR(255),
                    keywords TEXT,
                    extracted_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS project_files (
                    id VARCHAR(255) PRIMARY KEY,
                    project_id VARCHAR(255) REFERENCES projects(id) ON DELETE CASCADE,
                    relative_path TEXT NOT NULL,
                    file_type VARCHAR(50),
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS scan_reports (
                    id VARCHAR(255) PRIMARY KEY,
                    query_id VARCHAR(255) NOT NULL,
                    target_id VARCHAR(255) NOT NULL,
                    similarity_score FLOAT NOT NULL,
                    match_type VARCHAR(50) NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS fingerprint_index (
                    id SERIAL PRIMARY KEY,
                    fingerprint_hash BIGINT NOT NULL,
                    file_path TEXT NOT NULL,
                    project_id VARCHAR(255) NOT NULL,
                    file_type VARCHAR(50) NOT NULL,
                    position INTEGER DEFAULT 0,
                    UNIQUE(fingerprint_hash, file_path, project_id)
                );
                CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
                CREATE INDEX IF NOT EXISTS idx_projects_created ON projects(created_at);
                CREATE INDEX IF NOT EXISTS idx_scan_reports_query_id ON scan_reports(query_id);
                CREATE INDEX IF NOT EXISTS idx_project_files_project_id ON project_files(project_id);
                CREATE INDEX IF NOT EXISTS idx_fp_hash ON fingerprint_index(fingerprint_hash);
                CREATE INDEX IF NOT EXISTS idx_fp_project ON fingerprint_index(project_id);

                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role VARCHAR(50) NOT NULL DEFAULT 'college_admin',
                    college_id VARCHAR(255),
                    requires_password_change BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS students (
                    id VARCHAR(255) PRIMARY KEY,
                    enrollment_number VARCHAR(100) UNIQUE NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    password_hash TEXT,
                    requires_password_change BOOLEAN DEFAULT TRUE,
                    college_id VARCHAR(255),
                    team_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                CREATE INDEX IF NOT EXISTS idx_students_enrollment ON students(enrollment_number);
                CREATE TABLE IF NOT EXISTS teams (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    college_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_teams_college ON teams(college_id);
                CREATE TABLE IF NOT EXISTS settings (
                    key VARCHAR(255) PRIMARY KEY,
                    value TEXT
                );
                """)

                # Expand projects table with new metadata columns (safe for existing DBs)
                alter_statements = [
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS title VARCHAR(500);",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS abstract TEXT;",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS team_id VARCHAR(255);",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS department VARCHAR(255);",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS year INTEGER;",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS university VARCHAR(255);",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'approved';",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS student_id VARCHAR(255);",
                    # RBAC upgrade: students authenticate with enrollment_number + password
                    "ALTER TABLE students ADD COLUMN IF NOT EXISTS password_hash TEXT;",
                    "ALTER TABLE students ADD COLUMN IF NOT EXISTS requires_password_change BOOLEAN DEFAULT TRUE;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS requires_password_change BOOLEAN DEFAULT FALSE;",
                ]
                for stmt in alter_statements:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        pass

                self._init_default_settings(cur)

            else:
                cur.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT DEFAULT 'approved',
                    student_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS papers (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    author TEXT,
                    keywords TEXT,
                    extracted_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS project_files (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    relative_path TEXT NOT NULL,
                    file_type TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS scan_reports (
                    id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    match_type TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS fingerprint_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint_hash INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    position INTEGER DEFAULT 0,
                    UNIQUE(fingerprint_hash, file_path, project_id)
                );
                CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
                CREATE INDEX IF NOT EXISTS idx_projects_created ON projects(created_at);
                CREATE INDEX IF NOT EXISTS idx_scan_reports_query_id ON scan_reports(query_id);
                CREATE INDEX IF NOT EXISTS idx_project_files_project_id ON project_files(project_id);
                CREATE INDEX IF NOT EXISTS idx_fp_hash ON fingerprint_index(fingerprint_hash);
                CREATE INDEX IF NOT EXISTS idx_fp_project ON fingerprint_index(project_id);

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'college_admin',
                    college_id TEXT,
                    requires_password_change BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS students (
                    id TEXT PRIMARY KEY,
                    enrollment_number TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    password_hash TEXT,
                    requires_password_change BOOLEAN DEFAULT 1,
                    college_id TEXT,
                    team_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                CREATE INDEX IF NOT EXISTS idx_students_enrollment ON students(enrollment_number);
                CREATE TABLE IF NOT EXISTS teams (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    college_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_teams_college ON teams(college_id);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """)

                # Expand projects table with new metadata columns (safe for existing DBs)
                alter_statements = [
                    "ALTER TABLE projects ADD COLUMN title TEXT;",
                    "ALTER TABLE projects ADD COLUMN abstract TEXT;",
                    "ALTER TABLE projects ADD COLUMN team_id TEXT;",
                    "ALTER TABLE projects ADD COLUMN department TEXT;",
                    "ALTER TABLE projects ADD COLUMN year INTEGER;",
                    "ALTER TABLE projects ADD COLUMN university TEXT;",
                    "ALTER TABLE projects ADD COLUMN status TEXT DEFAULT 'approved';",
                    "ALTER TABLE projects ADD COLUMN student_id TEXT;",
                    # RBAC upgrade: students authenticate with enrollment_number + password
                    "ALTER TABLE students ADD COLUMN password_hash TEXT;",
                    "ALTER TABLE students ADD COLUMN requires_password_change BOOLEAN DEFAULT 1;",
                    "ALTER TABLE users ADD COLUMN requires_password_change BOOLEAN DEFAULT 0;",
                ]
                for stmt in alter_statements:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        pass

                self._init_default_settings(cur)

            conn.commit()
        finally:
            conn.close()
