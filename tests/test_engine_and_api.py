"""
Comprehensive automated test suite for the Plagiarism Detection Engine.
Compatible with both standard-library `unittest` (`python -m unittest discover -s tests -v`)
and `pytest` (`pytest tests/test_engine_and_api.py`).

Covers:
1. Arabic NLP preprocessing, stop-word filtering, language detection, and RTL PDF fix
2. Winnowing fingerprinting (code, English text, Arabic text, small-file exact bypass)
3. StorageService (LocalStorage CRUD + path traversal security)
4. SystemDBStore (SQLite & PostgreSQL 18.4 pooling, schema migration, boolean flags, zlib fallback)
5. PgVectorStore & VectorStore (Option 1 1024-dim zero-padding, BIT(1024) 2-Step Rescoring)
6. Adaptive Hybrid Fusion Scorer (alpha rules for code, text, Arabic, PDF, small files)
7. End-to-end Intake + Analysis + FastAPI endpoints (auth, PDF upload-scan, scan, deep-scan, compare)
"""

import os
import tempfile
import unittest
import uuid
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from plagiarism_engine.arabic_preprocessor import (
    normalize_arabic,
    tokenize_arabic,
    detect_language,
)
from plagiarism_engine.text_detector import normalize_arabic_text
from plagiarism_engine.extractor import FileExtractor
from plagiarism_engine.winnowing import WinnowingEngine
from plagiarism_engine.fusion_scorer import compute_fusion_score
from plagiarism_engine.storage.local_storage import LocalStorage
from plagiarism_engine.db import SystemDBStore, compress_text
from plagiarism_engine.vectors.pgvector_store import PgVectorStore


# ===========================================================================
# 1. Arabic Preprocessing & PDF Direction Tests
# ===========================================================================

def test_arabic_normalization_unification():
    raw = "إِنَّ الذَّكَاءَ الاصْطِنَاعِيَّ فِي الجَامِعَاتِ اليَمَنِيَّةِ يَسْعَى إِلَى تَحْقِيقِ الجَوْدَةِ"
    norm1 = normalize_arabic(raw)
    norm2 = normalize_arabic_text(raw)
    assert norm1 == norm2
    # Check diacritics and tatweel removed, hamzas -> ا, teh marbuta -> ه, alef maqsura -> ي
    assert "إ" not in norm1
    assert "أ" not in norm1
    assert "ة" not in norm1
    assert "ى" not in norm1
    assert "ـ" not in norm1


def test_arabic_stop_words_filtered_after_normalization():
    text = "في من على إلى عن هذا هذه أن إن أو إذا أمام الذكاء الاصطناعي وتعلم الالة"
    tokens = tokenize_arabic(text)
    # Stop words with hamza/alef maqsura (إلى, على, أن, إن, أو, إذا, أمام) must be removed
    for stop in ("في", "من", "علي", "الي", "ان", "او", "اذا", "امام"):
        assert stop not in tokens
    assert "الذكاء" in tokens
    assert "الاصطناعي" in tokens


def test_language_detection():
    ar = "تعتبر خوارزميات كشف الانتحال العلمي في النصوص العربية من أهم التطبيقات الحديثة"
    en = "Plagiarism detection algorithms combine lexical fingerprinting with semantic embeddings."
    mixed = "This system supports الذكاء الاصطناعي and semantic search للغة العربية"
    assert detect_language(ar) == "arabic"
    assert detect_language(en) == "english"
    assert detect_language(mixed) == "mixed"
    assert detect_language("12345 !@#") == "unknown"


def test_arabic_pdf_reversed_detection_and_fix():
    # Visual RTL extraction produces words ending in 'لا' instead of starting with 'ال'
    reversed_line = "ةرهاقلا ةعماج يف يملعلا ثحبلا Python 2026"
    assert FileExtractor._is_arabic_reversed(reversed_line) is True
    fixed = FileExtractor._fix_arabic_direction(reversed_line)
    assert "البحث العلمي في جامعة القاهرة" in fixed
    # Embedded LTR English/numeric tokens must not be reversed to 'nohtyP' or '6202'
    assert "Python" in fixed
    assert "2026" in fixed


# ===========================================================================
# 2. Winnowing Fingerprinting Tests
# ===========================================================================

def test_winnowing_code_variable_renaming_invariance():
    engine = WinnowingEngine(k=15, w=5)
    code_a = """
def calculate_fibonacci_sequence(limit_count):
    sequence = [0, 1]
    for idx in range(2, limit_count):
        next_val = sequence[idx - 1] + sequence[idx - 2]
        sequence.append(next_val)
    return sequence
"""
    code_b = """
def compute_fib_numbers(max_elements):
    arr = [0, 1]
    for i in range(2, max_elements):
        val = arr[i - 1] + arr[i - 2]
        arr.append(val)
    return arr
"""
    fp_a = {h for h, _ in engine.compute_code_fingerprints(code_a, "fib_a.py")}
    fp_b = {h for h, _ in engine.compute_code_fingerprints(code_b, "fib_b.py")}
    assert len(fp_a) > 0
    assert engine.jaccard_similarity(fp_a, fp_b) == 1.0


def test_winnowing_small_file_arabic_diacritics_invariance():
    engine = WinnowingEngine(k=50, w=10)
    small_ar_1 = "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ البَحْثُ العِلْمِيُّ فِي الذَّكَاءِ الاصْطِنَاعِيِّ"
    small_ar_2 = "بسم الله الرحمن الرحيم البحث العلمي في الذكاء الاصطناعي"
    fp_1 = engine.compute_text_fingerprints(small_ar_1)
    fp_2 = engine.compute_text_fingerprints(small_ar_2)
    assert len(fp_1) == 1
    assert fp_1 == fp_2


# ===========================================================================
# 3. LocalStorage CRUD & Path Traversal Security Tests
# ===========================================================================

def test_local_storage_crud_and_security():
    with tempfile.TemporaryDirectory() as tmp:
        storage_dir = Path(tmp) / "storage"
        storage = LocalStorage(base_dir=str(storage_dir))

        storage.save_file("proj1/src/main.py", b"print('hello')")
        assert storage.file_exists("proj1/src/main.py")
        assert storage.read_file("proj1/src/main.py") == b"print('hello')"
        assert "proj1/src/main.py" in storage.list_files("proj1")

        # Path traversal attempts must raise ValueError
        raised_parent = False
        try:
            storage.save_file("../../evil.py", b"bad")
        except ValueError:
            raised_parent = True
        assert raised_parent

        # Sibling folder with matching prefix (e.g. storage_evil) must also be blocked
        raised_sibling = False
        try:
            storage.save_file("../storage_evil/hack.txt", b"bad")
        except ValueError:
            raised_sibling = True
        assert raised_sibling

        storage.delete_directory("proj1")
        assert not storage.file_exists("proj1/src/main.py")


# ===========================================================================
# 4. SystemDBStore (SQLite & PostgreSQL) Tests
# ===========================================================================

def test_sqlite_store_and_legacy_zlib_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "test_system.sqlite"
        db = SystemDBStore(pg_connection_string="postgresql://invalid:5432/none", sqlite_db_path=str(db_file))
        assert db.mode == "sqlite"

        # Student boolean creation and update
        db.create_student("stu_1", "2026001", "Aiman Student", "hash123", requires_password_change=True)
        stu = db.get_user_or_student_by_login("2026001")
        assert stu is not None
        assert stu["requires_password_change"] == 1
        db.update_student("stu_1", requires_password_change=False)
        stu2 = db.get_user_or_student_by_login("2026001")
        assert stu2["requires_password_change"] == 0

        # Legacy zlib content fallback when file is not on disk in StorageService
        conn = db._get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO projects (id, name) VALUES (?, ?);", ("legacy_proj", "legacy_proj"))
        cur.execute(
            "INSERT INTO project_files (id, project_id, relative_path, file_type, content) VALUES (?, ?, ?, ?, ?);",
            ("legacy_proj::old.py", "legacy_proj", "old.py", "code", compress_text("def legacy(): return 42")),
        )
        conn.commit()
        conn.close()

        files = db.get_project_files("legacy_proj")
        assert len(files) == 1
        assert files[0]["content"] == "def legacy(): return 42"

        targeted = db.get_files_by_paths("other_proj", ["old.py"], target_project_id="legacy_proj")
        assert len(targeted) == 1
        assert targeted[0]["content"] == "def legacy(): return 42"


def test_postgresql_pooling_and_2step_rescoring():
    db = SystemDBStore()
    if db.mode != "postgresql":
        raise unittest.SkipTest("Local PostgreSQL server not active")

    # Verify pooled connection close works repeatedly without AttributeError
    for _ in range(5):
        conn = db._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        assert cur.fetchone()[0] == 1
        conn.close()

    # Verify student boolean handling in PostgreSQL
    test_sid = f"test_stu_{uuid.uuid4().hex[:8]}"
    test_enum = f"ENR_{uuid.uuid4().hex[:8]}"
    p1 = f"test_pg_proj_a_{uuid.uuid4().hex[:6]}"
    p2 = f"test_pg_proj_b_{uuid.uuid4().hex[:6]}"
    try:
        db.create_student(test_sid, test_enum, "PG Test Student", "hash_pg", requires_password_change=True)
        login_rec = db.get_user_or_student_by_login(test_enum)
        assert login_rec is not None
        assert login_rec["requires_password_change"] == 1
        db.update_student(test_sid, requires_password_change=False)
        login_rec_after = db.get_user_or_student_by_login(test_enum)
        assert login_rec_after["requires_password_change"] == 0

        # Test Option 1 (768-dim zero-padded to 1024-dim) + PostgreSQL BIT(1024) 2-Step Rescoring
        db.save_project(p1, p1, [{"relative_path": "algo.py", "file_type": "code", "content": "def f(x): return x + 1"}])
        db.save_project(p2, p2, [{"relative_path": "algo_copy.py", "file_type": "code", "content": "def g(y): return y + 1"}])

        pg_vstore = PgVectorStore(db_store=db)
        rng = np.random.default_rng(42)
        vec_768 = rng.standard_normal(768).astype("float32")
        vec_768 /= np.linalg.norm(vec_768)
        # Near-identical 768-dim vector
        vec_768_near = vec_768 + 0.02 * rng.standard_normal(768).astype("float32")
        vec_768_near /= np.linalg.norm(vec_768_near)

        c1 = pg_vstore.store_embeddings_batch(p1, [(f"{p1}::algo.py", vec_768, "code")])
        c2 = pg_vstore.store_embeddings_batch(p2, [(f"{p2}::algo_copy.py", vec_768_near, "code")])
        assert c1 == 1 and c2 == 1
        assert pg_vstore.count_project_vectors(p1) == 1
        assert pg_vstore.count_project_vectors(p2) == 1

        matches = pg_vstore.search_bulk(p1, top_k=5)
        p2_matches = [m for m in matches if m["matched_project_id"] == p2]
        assert len(p2_matches) == 1
        hit = p2_matches[0]
        assert hit["target_project"] == p2
        assert hit["target_file"] == "algo_copy.py"
        expected_cos = float(np.dot(vec_768, vec_768_near))
        assert abs(hit["similarity_raw"] - expected_cos) < 1e-3
        # Synthetic rows carry embedding_model = None -> floor 0.0 -> calibrated == raw
        assert hit["embedding_model"] is None
        assert abs(hit["similarity"] - expected_cos) < 1e-3

        pair_sim = pg_vstore.get_pair_similarity(p1, "algo.py", p2, "algo_copy.py")
        assert abs(pair_sim - expected_cos) < 1e-3
        pair_raw = pg_vstore.get_pair_similarity(p1, "algo.py", p2, "algo_copy.py", raw=True)
        assert abs(pair_raw - expected_cos) < 1e-3
    finally:
        db.delete_project(p1)
        db.delete_project(p2)
        conn = db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM students WHERE id = %s;", (test_sid,))
            conn.commit()
        finally:
            conn.close()


# ===========================================================================
# 5. Adaptive Hybrid Fusion Scorer Tests
# ===========================================================================

def test_adaptive_fusion_scorer_weights():
    winnow = WinnowingEngine(k=10, w=4)
    long_code = " ".join([f"def func_{i}(x): return x * {i}" for i in range(25)])
    long_en = " ".join([f"word{i}" for i in range(60)])
    long_ar = " ".join(["الذكاء الاصطناعي في الجامعات اليمنية وتطوير التعليم العالي"] * 12)

    # 1. Code -> alpha = 0.6
    res_code = compute_fusion_score(long_code, long_code, 0.80, "code", winnow, filename="main.py")
    assert res_code["alpha"] == 0.6

    # 2. English text -> alpha = 0.3
    res_en = compute_fusion_score(long_en, long_en, 0.80, "text", winnow, filename="essay.txt")
    assert res_en["alpha"] == 0.3

    # 3. Arabic text -> alpha = 0.25
    res_ar = compute_fusion_score(long_ar, long_ar, 0.80, "text", winnow, filename="thesis_ar.docx")
    assert res_ar["alpha"] == 0.25
    assert res_ar["language"] == "arabic"

    # 4. PDF academic paper -> alpha = 0.2
    res_pdf = compute_fusion_score(long_en, long_en, 0.80, "text", winnow, filename="paper.pdf")
    assert res_pdf["alpha"] == 0.2

    # 5. Small file (< k tokens) -> alpha = 1.0
    res_small = compute_fusion_score("short text", "short text", 0.90, "text", winnow, filename="tiny.txt")
    assert res_small["alpha"] == 1.0


# ===========================================================================
# 6. FastAPI End-to-End API & PDF Upload Tests
# ===========================================================================

def _create_minimal_pdf_bytes(text: str) -> bytes:
    """Create a valid in-memory single-page PDF with correct xref byte offsets."""
    stream_content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream_content)} >>\nstream\n".encode("latin-1") + stream_content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    return bytes(out)


def test_fastapi_upload_pdf_and_hybrid_scan():
    os.environ.setdefault("MODELS_DIR", r"D:\AI engine\models")
    from app.main import app
    from app.dependencies import _create_access_token
    from app.state import get_db

    client = TestClient(app)
    token = _create_access_token("test_admin", "admin@ministry.gov", "ministry_admin", False)
    headers = {"Authorization": f"Bearer {token}"}

    proj_a = f"pytest_proj_a_{uuid.uuid4().hex[:6]}"
    proj_b = f"pytest_proj_b_{uuid.uuid4().hex[:6]}"
    db = get_db()

    shared_code = "\n".join([
        "def compute_matrix_eigenvalues(matrix_data, iterations=100):",
        "    vector = [1.0 for _ in range(len(matrix_data))]",
        "    for step in range(iterations):",
        "        next_vec = [sum(row[j] * vector[j] for j in range(len(row))) for row in matrix_data]",
        "        norm = max(abs(x) for x in next_vec) or 1.0",
        "        vector = [x / norm for x in next_vec]",
        "    return vector",
    ] * 4)

    pdf_bytes = _create_minimal_pdf_bytes(
        "Artificial intelligence and deep learning models improve university plagiarism detection systems significantly."
    )

    try:
        # 1. Upload Project A (with a .py file and a .pdf file to test the PDF dict extraction fix)
        res_a = client.post(
            "/api/plagiarism/upload-scan",
            data={"project_name": proj_a, "scan_type": "Direct Upload Project Scan"},
            files=[
                ("files", ("eigen.py", shared_code.encode("utf-8"), "text/x-python")),
                ("files", ("report.pdf", pdf_bytes, "application/pdf")),
            ],
            headers=headers,
        )
        assert res_a.status_code == 200, res_a.text
        data_a = res_a.json()
        assert data_a["status"] == "completed"
        assert data_a["code_files_count"] == 1
        assert data_a["text_files_count"] == 1

        # 2. Upload Project B (with matching code)
        res_b = client.post(
            "/api/plagiarism/upload-scan",
            data={"project_name": proj_b, "scan_type": "Direct Upload Project Scan"},
            files=[
                ("files", ("eigen_copied.py", shared_code.encode("utf-8"), "text/x-python")),
            ],
            headers=headers,
        )
        assert res_b.status_code == 200, res_b.text

        # 3. Run Hybrid Scan on Project B
        scan_res = client.post(
            "/api/plagiarism/scan",
            json={"scan_type": "Saved Project Scan", "target": proj_b},
            headers=headers,
        )
        assert scan_res.status_code == 200, scan_res.text
        scan_data = scan_res.json()
        assert scan_data["status"] == "completed"
        matched_a = [c for c in scan_data["comparisons"] if c["project"] == proj_a]
        assert len(matched_a) >= 1
        cmp_item = matched_a[0]
        assert cmp_item["winnowing_score"] == 100.0
        assert cmp_item["semantic_score"] > 90.0
        assert cmp_item["fusion_score"] > 95.0
        assert cmp_item["status"] == "CRITICAL"
    finally:
        db.delete_project(proj_a)
        db.delete_project(proj_b)


# ===========================================================================
# 7. Round 2: Semantic discrimination, model provenance, containment, mixed alpha
# ===========================================================================

_GRADES_ORIGINAL = '''# Student grade analytics module
import math


def compute_average(scores):
    # Return the arithmetic mean of a list of scores
    if not scores:
        return 0.0
    total = 0.0
    for value in scores:
        total += value
    return total / len(scores)


def compute_std_deviation(scores):
    # Population standard deviation of the scores
    if len(scores) < 2:
        return 0.0
    mean = compute_average(scores)
    squared = 0.0
    for value in scores:
        squared += (value - mean) ** 2
    return math.sqrt(squared / len(scores))


def assign_letter_grade(score):
    # Map a numeric score to a letter grade
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    return "F"


def build_report(student_scores):
    # Build a summary report for every student
    report = {}
    for name, scores in student_scores.items():
        avg = compute_average(scores)
        report[name] = {
            "average": round(avg, 2),
            "std_dev": round(compute_std_deviation(scores), 2),
            "grade": assign_letter_grade(avg),
        }
    return report
'''

# Plagiarized: all identifiers renamed, `for` -> `while` in the report builder,
# function order reversed, comments rewritten. Not byte-identical.
_GRADES_PLAGIARIZED = '''import math


# Produces per-learner summaries
def summarize_learners(marks_by_learner):
    summary = {}
    learners = list(marks_by_learner.keys())
    idx = 0
    while idx < len(learners):
        who = learners[idx]
        marks = marks_by_learner[who]
        mean_mark = mean_of(marks)
        summary[who] = {
            "average": round(mean_mark, 2),
            "std_dev": round(spread_of(marks), 2),
            "grade": letter_for(mean_mark),
        }
        idx += 1
    return summary


# Converts a mark into its letter band
def letter_for(mark):
    if mark >= 90:
        return "A"
    elif mark >= 80:
        return "B"
    elif mark >= 70:
        return "C"
    elif mark >= 60:
        return "D"
    return "F"


# Spread (population sigma) of the marks
def spread_of(marks):
    if len(marks) < 2:
        return 0.0
    centre = mean_of(marks)
    acc = 0.0
    for m in marks:
        acc += (m - centre) ** 2
    return math.sqrt(acc / len(marks))


# Mean value of the marks list
def mean_of(marks):
    if not marks:
        return 0.0
    running = 0.0
    for m in marks:
        running += m
    return running / len(marks)
'''

_UNRELATED_CODE = '''import os
import time
from datetime import datetime


class RotatingLogWriter:
    """Append log lines to a file and rotate it when it grows too large."""

    def __init__(self, path, max_bytes=1_000_000, backups=3):
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups

    def _should_rotate(self):
        return os.path.exists(self.path) and os.path.getsize(self.path) >= self.max_bytes

    def _rotate(self):
        for i in range(self.backups - 1, 0, -1):
            src = f"{self.path}.{i}"
            dst = f"{self.path}.{i + 1}"
            if os.path.exists(src):
                os.replace(src, dst)
        if os.path.exists(self.path):
            os.replace(self.path, f"{self.path}.1")

    def write(self, level, message):
        if self._should_rotate():
            self._rotate()
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {level.upper():7s} {message}\\n")


def tail_lines(path, count=10, poll_seconds=0.0):
    """Return the last `count` lines of a log file, optionally waiting for it to appear."""
    deadline = time.time() + poll_seconds
    while not os.path.exists(path):
        if time.time() >= deadline:
            return []
        time.sleep(0.05)
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
    return [line.rstrip("\\n") for line in lines[-count:]]
'''

_EN_ORIGINAL = (
    "Universities face growing pressure to protect academic integrity as generative tools make it easy to "
    "rewrite existing work. A reliable plagiarism detection system should therefore combine two complementary "
    "signals. Lexical fingerprinting identifies passages that were copied word for word or changed only slightly, "
    "while semantic embeddings reveal submissions that express the same ideas in different words. Combining both "
    "signals with an adaptive weight allows reviewers to catch verbatim copying and heavy paraphrasing in a single "
    "report, which reduces manual effort and makes final decisions more consistent and transparent for students "
    "and examiners alike."
)
_EN_PARAPHRASE = (
    "As generative writing tools make rewording existing material effortless, universities are under increasing "
    "pressure to safeguard academic honesty. An effective plagiarism checker should consequently merge two "
    "complementary indicators. Fingerprinting of word sequences locates text that was duplicated verbatim or only "
    "lightly edited, whereas semantic vector representations expose essays that convey identical ideas using "
    "different vocabulary. Blending these indicators through an adaptive weighting scheme lets examiners detect "
    "both literal copying and extensive paraphrasing within one report, cutting manual workload and making the "
    "final judgments more consistent and transparent for students and assessors."
)
_EN_UNRELATED = (
    "Coffee plants thrive at high altitudes in tropical regions where cool nights slow the ripening of the cherries "
    "and concentrate their sugars. Farmers in Ethiopia and Colombia often grow arabica varieties under shade trees, "
    "which protect the soil from erosion and support bird populations. After harvest, the cherries are either washed "
    "to remove the fruit pulp or dried whole in the sun, and each method produces a distinct flavor profile. The "
    "green beans are then sorted, bagged, and shipped to roasters, who apply carefully controlled heat curves to "
    "develop aroma, acidity, and body before the coffee reaches consumers."
)
_AR_ORIGINAL = (
    "تواجه الجامعات ضغوطاً متزايدة لحماية النزاهة الأكاديمية بعد أن أصبحت أدوات الكتابة الآلية قادرة على إعادة "
    "صياغة الأعمال المنشورة بسهولة. ولذلك ينبغي أن يجمع نظام كشف الانتحال الموثوق بين مؤشرين متكاملين، إذ تكشف "
    "البصمات المعجمية المقاطع المنسوخة حرفياً أو المعدلة تعديلاً طفيفاً، بينما تكشف المتجهات الدلالية الأبحاث التي "
    "تعبر عن الأفكار نفسها بكلمات مختلفة. ويتيح الدمج بين المؤشرين بوزن تكيفي للمراجعين رصد النسخ الحرفي وإعادة "
    "الصياغة المكثفة في تقرير واحد، مما يقلل الجهد اليدوي ويجعل القرارات النهائية أكثر اتساقاً وشفافية."
)
_AR_PARAPHRASE = (
    "مع تمكّن برامج التوليد النصي من إعادة كتابة المواد المنشورة دون عناء، باتت مؤسسات التعليم العالي مطالبة أكثر "
    "من أي وقت مضى بصون الأمانة العلمية. ومن ثم يتعين على أداة فحص الانتحال الفعالة أن تدمج دليلين يكمل أحدهما "
    "الآخر، فبصمات تسلسل الكلمات تحدد النصوص المنقولة بحرفها أو المحررة تحريراً بسيطاً، في حين تفضح التمثيلات "
    "الدلالية المقالات التي تنقل المعاني ذاتها بمفردات أخرى. ويسمح مزج هذين الدليلين عبر آلية ترجيح مرنة للممتحنين "
    "باكتشاف النقل الحرفي والصياغة الموسعة معاً في تقرير موحد، فيخفف عبء العمل اليدوي ويمنح الأحكام النهائية قدراً "
    "أكبر من الاتساق والوضوح."
)
_AR_UNRELATED = (
    "تنمو أشجار البن في المرتفعات الاستوائية حيث تساعد الليالي الباردة على إبطاء نضج الثمار وتركيز السكريات فيها. "
    "ويزرع المزارعون في اليمن وإثيوبيا أصناف البن العربي تحت ظلال الأشجار التي تحمي التربة من الانجراف وتوفر "
    "موطناً للطيور. وبعد الحصاد تُغسل الثمار لإزالة اللب أو تُجفف كاملة تحت أشعة الشمس، ولكل طريقة نكهة مميزة. "
    "ثم تُفرز الحبوب الخضراء وتعبأ وتشحن إلى المحامص التي تطبق درجات حرارة مضبوطة بعناية لتطوير الرائحة والحموضة "
    "والقوام قبل وصول القهوة إلى المستهلكين."
)


def _best_cmp(comparisons, project, file1, file2):
    """Highest-fusion comparison row for an exact (project, file1, file2) pair, or None."""
    rows = [c for c in comparisons if c.get("project") == project and c.get("file1") == file1 and c.get("file2") == file2]
    if not rows:
        return None
    return max(rows, key=lambda c: float(c.get("fusion_score", 0) or 0))


def test_semantic_discrimination_end_to_end():
    from app.main import app
    from app.dependencies import _create_access_token
    from app.state import get_db

    client = TestClient(app)
    token = _create_access_token("test_admin", "admin@ministry.gov", "ministry_admin", False)
    headers = {"Authorization": f"Bearer {token}"}
    tag = uuid.uuid4().hex[:6]
    proj_a, proj_b, proj_c = f"pytest_disc_a_{tag}", f"pytest_disc_b_{tag}", f"pytest_disc_c_{tag}"
    db = get_db()

    def upload(name, files):
        res = client.post(
            "/api/plagiarism/upload-scan",
            data={"project_name": name, "scan_type": "Direct Upload Project Scan"},
            files=[("files", (fn, body.encode("utf-8"), mime)) for fn, body, mime in files],
            headers=headers,
        )
        assert res.status_code == 200, res.text

    try:
        upload(proj_a, [("grades.py", _GRADES_ORIGINAL, "text/x-python"),
                        ("essay_en.txt", _EN_ORIGINAL, "text/plain"),
                        ("essay_ar.txt", _AR_ORIGINAL, "text/plain")])
        upload(proj_c, [("logwriter.py", _UNRELATED_CODE, "text/x-python"),
                        ("coffee_en.txt", _EN_UNRELATED, "text/plain"),
                        ("coffee_ar.txt", _AR_UNRELATED, "text/plain")])
        upload(proj_b, [("learners.py", _GRADES_PLAGIARIZED, "text/x-python"),
                        ("essay_en_para.txt", _EN_PARAPHRASE, "text/plain"),
                        ("essay_ar_para.txt", _AR_PARAPHRASE, "text/plain")])

        # Corpus projects get semantic vectors through the public indexing endpoint
        # (Quick Scan only embeds the scanned project and its lexical candidates).
        for corpus_project in (proj_a, proj_c):
            idx = client.post(f"/api/plagiarism/projects/{corpus_project}/index-embeddings", headers=headers)
            assert idx.status_code == 200, idx.text

        scan = client.post("/api/plagiarism/scan", json={"scan_type": "Saved Project Scan", "target": proj_b},
                           headers=headers)
        assert scan.status_code == 200, scan.text
        comps = scan.json()["comparisons"]

        # --- Code: plagiarized pair must be HIGH/CRITICAL; unrelated must be absent or SAFE ---
        code_hit = _best_cmp(comps, proj_a, "learners.py", "grades.py")
        assert code_hit is not None, f"plagiarized code pair not detected; comparisons={comps}"
        assert code_hit["status"] in ("HIGH", "CRITICAL"), code_hit
        code_unrel = _best_cmp(comps, proj_c, "learners.py", "logwriter.py")
        if code_unrel is not None:
            assert code_unrel["status"] == "SAFE", code_unrel
            assert code_hit["semantic_score"] > code_unrel["semantic_score"] + 30, (code_hit, code_unrel)

        # --- English and Arabic text: paraphrase must outscore unrelated ---
        for para_file, orig_file, unrel_file in (
            ("essay_en_para.txt", "essay_en.txt", "coffee_en.txt"),
            ("essay_ar_para.txt", "essay_ar.txt", "coffee_ar.txt"),
        ):
            hit = _best_cmp(comps, proj_a, para_file, orig_file)
            assert hit is not None, f"paraphrase {para_file} not detected; comparisons={comps}"
            unrel = _best_cmp(comps, proj_c, para_file, unrel_file)
            unrel_sem = float(unrel["semantic_score"]) if unrel is not None else 0.0
            assert float(hit["semantic_score"]) > unrel_sem, (hit, unrel)
            assert float(hit["fusion_score"]) > (float(unrel["fusion_score"]) if unrel is not None else 0.0)
    finally:
        for p in (proj_a, proj_b, proj_c):
            db.delete_project(p)


def test_model_provenance_isolation():
    db = SystemDBStore()
    if db.mode != "postgresql":
        raise unittest.SkipTest("Local PostgreSQL server not active")
    tag = uuid.uuid4().hex[:6]
    p1, p2 = f"pytest_prov_a_{tag}", f"pytest_prov_b_{tag}"
    try:
        db.save_project(p1, p1, [{"relative_path": "x.py", "file_type": "code", "content": "def x(): return 1"}])
        db.save_project(p2, p2, [{"relative_path": "y.py", "file_type": "code", "content": "def y(): return 1"}])
        vs = PgVectorStore(db_store=db)
        rng = np.random.default_rng(7)
        v = rng.standard_normal(768).astype("float32")
        v /= np.linalg.norm(v)
        # Identical vectors, but produced by two different models -> must never be compared.
        vs.store_embeddings_batch(p1, [(f"{p1}::x.py", v, "code", "unixcoder-base")])
        vs.store_embeddings_batch(p2, [(f"{p2}::y.py", v, "code", "codebert-base")])
        assert not [m for m in vs.search_bulk(p1, top_k=5) if m["matched_project_id"] == p2]
        assert vs.get_pair_similarity(p1, "x.py", p2, "y.py") == 0.0
        assert vs.get_pair_similarity(p1, "x.py", p2, "y.py", raw=True) == 0.0
        # Stale-model detection: codebert rows are stale when unixcoder is expected for code.
        assert vs.needs_reindex(p2, {"code": "unixcoder-base", "text": "bge-m3"}) is True
        assert vs.needs_reindex(p1, {"code": "unixcoder-base", "text": "bge-m3"}) is False
    finally:
        db.delete_project(p1)
        db.delete_project(p2)


def test_embedded_copy_containment_signal():
    import random
    snippet = (
        "def merge_config_layers(base, override):\n"
        "    merged = {k: v for k, v in base.items() if v is not None}\n"
        "    for key, value in override.items():\n"
        "        if isinstance(value, dict) and isinstance(merged.get(key), dict):\n"
        "            merged[key] = merge_config_layers(merged[key], value)\n"
        "    return merged\n"
    )
    statements = [
        "    total = sum(x * x for x in items if x % 2 == 0)",
        "    while count < limit:\n        count += step",
        "    try:\n        value = int(raw)\n    except ValueError:\n        value = -1",
        "    with open(path, 'r') as fh:\n        lines = fh.readlines()",
        "    result = [a + b for a, b in zip(left, right)]",
        "    if flag and not other:\n        return None",
        "    mapping = dict(sorted(pairs, key=lambda p: p[1]))",
        "    for i in range(len(data) - 1, -1, -2):\n        data[i] = data[i] ** 3",
        "    assert isinstance(obj, (list, tuple)), 'bad type'",
        "    text = ' '.join(reversed(words)).upper().strip()",
    ]
    rng = random.Random(7)
    lines = []
    for f in range(24):
        lines.append(f"def generated_{f}(items, limit, step, raw, path, left, right, flag, other, pairs, data, obj, words):")
        lines.extend(rng.sample(statements, k=rng.randint(3, 6)))
        lines.append("    return locals()\n")
        if f == 12:
            lines.append(snippet)
    big = "\n".join(lines)
    assert len(snippet.strip().splitlines()) == 6
    assert len(big.splitlines()) >= 200

    res = compute_fusion_score(snippet, big, 0.5, "code", WinnowingEngine(k=15, w=5), filename="merge.py")
    assert res["embedded_copy"] is True, res
    assert res["containment_score"] >= 80.0
    assert res["winnowing_score"] < 50.0


def test_mixed_language_alpha():
    mixed = " ".join(["This system supports الذكاء الاصطناعي and semantic search للغة العربية في الجامعات"] * 6)
    assert detect_language(mixed) == "mixed"
    res = compute_fusion_score(mixed, mixed, 0.8, "text", WinnowingEngine(k=10, w=4), filename="notes.txt")
    assert res["alpha"] == 0.25
    assert res["language"] == "mixed"


class TestPlagiarismEngineAndAPI(unittest.TestCase):
    def test_01_arabic_normalization(self):
        test_arabic_normalization_unification()

    def test_02_arabic_stop_words(self):
        test_arabic_stop_words_filtered_after_normalization()

    def test_03_language_detection(self):
        test_language_detection()

    def test_04_arabic_pdf_rtl_fix(self):
        test_arabic_pdf_reversed_detection_and_fix()

    def test_05_winnowing_code_renaming(self):
        test_winnowing_code_variable_renaming_invariance()

    def test_06_winnowing_small_file_arabic(self):
        test_winnowing_small_file_arabic_diacritics_invariance()

    def test_07_local_storage_crud_and_security(self):
        test_local_storage_crud_and_security()

    def test_08_sqlite_store_and_legacy_fallback(self):
        test_sqlite_store_and_legacy_zlib_fallback()

    def test_09_postgresql_pooling_and_2step_rescoring(self):
        test_postgresql_pooling_and_2step_rescoring()

    def test_10_adaptive_fusion_scorer_weights(self):
        test_adaptive_fusion_scorer_weights()

    def test_11_fastapi_upload_pdf_and_hybrid_scan(self):
        test_fastapi_upload_pdf_and_hybrid_scan()

    def test_12_semantic_discrimination_end_to_end(self):
        test_semantic_discrimination_end_to_end()

    def test_13_model_provenance_isolation(self):
        test_model_provenance_isolation()

    def test_14_embedded_copy_containment_signal(self):
        test_embedded_copy_containment_signal()

    def test_15_mixed_language_alpha(self):
        test_mixed_language_alpha()


if __name__ == "__main__":
    unittest.main(verbosity=2)
