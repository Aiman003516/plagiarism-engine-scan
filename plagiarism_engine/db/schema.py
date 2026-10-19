"""Schema creation / migration for all tables."""




class SchemaMixin:
    """Schema creation / migration for all tables. Mixed into SystemDBStore."""

    def _init_schema(self):
        """Initializes relational tables for projects, research papers, files, scan audit reports, and fingerprint index."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()

            if self.mode == "postgresql":
                # 1. Probe whether pgvector C extension is installed on this PostgreSQL server
                self.has_pgvector = False
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    conn.commit()
                    self.has_pgvector = True
                except Exception:
                    conn.rollback()
                    self.has_pgvector = False

                embedding_col_type = "VECTOR(1024)" if self.has_pgvector else "TEXT"

                cur.execute(f"""
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
                    embedding {embedding_col_type},
                    embedding_binary BIT(1024),
                    embedding_model TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS scan_reports (
                    id VARCHAR(255) PRIMARY KEY,
                    query_id VARCHAR(255) NOT NULL,
                    target_id VARCHAR(255) NOT NULL,
                    similarity_score FLOAT NOT NULL,
                    winnowing_score FLOAT,
                    semantic_score FLOAT,
                    fusion_score FLOAT,
                    alpha FLOAT,
                    verdict VARCHAR(50),
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
                CREATE INDEX IF NOT EXISTS idx_fp_composite ON fingerprint_index(fingerprint_hash, file_type, project_id);

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
                conn.commit()

                # Expand existing tables with new metadata & vector/fusion columns (safe for existing DBs)
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
                    # Phase 6/7: Vector and Hybrid Fusion columns
                    f"ALTER TABLE project_files ADD COLUMN IF NOT EXISTS embedding {embedding_col_type};",
                    "ALTER TABLE project_files ADD COLUMN IF NOT EXISTS embedding_binary BIT(1024);",
                    "ALTER TABLE project_files ADD COLUMN IF NOT EXISTS embedding_model TEXT;",
                    "ALTER TABLE scan_reports ADD COLUMN IF NOT EXISTS winnowing_score FLOAT;",
                    "ALTER TABLE scan_reports ADD COLUMN IF NOT EXISTS semantic_score FLOAT;",
                    "ALTER TABLE scan_reports ADD COLUMN IF NOT EXISTS fusion_score FLOAT;",
                    "ALTER TABLE scan_reports ADD COLUMN IF NOT EXISTS alpha FLOAT;",
                    "ALTER TABLE scan_reports ADD COLUMN IF NOT EXISTS verdict VARCHAR(50);",
                    "CREATE INDEX IF NOT EXISTS idx_pf_embedded ON project_files (file_type, embedding_model) WHERE embedding_binary IS NOT NULL;",
                    "CREATE INDEX IF NOT EXISTS idx_fp_composite ON fingerprint_index(fingerprint_hash, file_type, project_id);",
                    "CREATE INDEX IF NOT EXISTS idx_scan_reports_target_id ON scan_reports(target_id);",
                    "CREATE INDEX IF NOT EXISTS idx_students_team_id ON students(team_id);",
                    "CREATE INDEX IF NOT EXISTS idx_students_college_id ON students(college_id);",
                    "CREATE INDEX IF NOT EXISTS idx_projects_team_id ON projects(team_id);",
                    "CREATE INDEX IF NOT EXISTS idx_projects_student_id ON projects(student_id);",
                    "CREATE INDEX IF NOT EXISTS idx_users_college_id ON users(college_id);",
                ]
                for stmt in alter_statements:
                    try:
                        cur.execute(stmt)
                        conn.commit()
                    except Exception:
                        conn.rollback()

                # Upgrade BIT(768) -> BIT(1024) if an earlier schema created 768-bit column
                try:
                    cur.execute("""
                        SELECT character_maximum_length
                        FROM information_schema.columns
                        WHERE table_name = 'project_files' AND column_name = 'embedding_binary';
                    """)
                    row = cur.fetchone()
                    bit_len = (row['character_maximum_length'] if isinstance(row, dict) or hasattr(row, 'keys') else row[0]) if row else None
                    if bit_len is not None and int(bit_len) != 1024:
                        cur.execute("ALTER TABLE project_files ALTER COLUMN embedding_binary TYPE BIT(1024) USING NULL;")
                        conn.commit()
                except Exception:
                    conn.rollback()

                if self.has_pgvector:
                    try:
                        cur.execute("""
                            CREATE INDEX IF NOT EXISTS idx_files_embedding
                                ON project_files USING hnsw (embedding vector_cosine_ops)
                                WITH (m = 16, ef_construction = 64);
                        """)
                        conn.commit()
                    except Exception:
                        conn.rollback()

                self._init_default_settings(cur)
                conn.commit()

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
                    embedding TEXT,
                    embedding_binary TEXT,
                    embedding_model TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS scan_reports (
                    id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    winnowing_score REAL,
                    semantic_score REAL,
                    fusion_score REAL,
                    alpha REAL,
                    verdict TEXT,
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
                CREATE INDEX IF NOT EXISTS idx_fp_composite ON fingerprint_index(fingerprint_hash, file_type, project_id);

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

                # Expand tables with new metadata & vector/fusion columns (safe for existing DBs)
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
                    # Phase 6/7: Vector and Hybrid Fusion columns
                    "ALTER TABLE project_files ADD COLUMN embedding TEXT;",
                    "ALTER TABLE project_files ADD COLUMN embedding_binary TEXT;",
                    "ALTER TABLE project_files ADD COLUMN embedding_model TEXT;",
                    "ALTER TABLE scan_reports ADD COLUMN winnowing_score REAL;",
                    "ALTER TABLE scan_reports ADD COLUMN semantic_score REAL;",
                    "ALTER TABLE scan_reports ADD COLUMN fusion_score REAL;",
                    "ALTER TABLE scan_reports ADD COLUMN alpha REAL;",
                    "ALTER TABLE scan_reports ADD COLUMN verdict TEXT;",
                    "CREATE INDEX IF NOT EXISTS idx_pf_embedded ON project_files (file_type, embedding_model);",
                    "CREATE INDEX IF NOT EXISTS idx_fp_composite ON fingerprint_index (fingerprint_hash, file_type, project_id);",
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

