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


# ===========================================================================
# 8. Round 3 / Phase 1: central file-scope policy
# ===========================================================================

def test_file_policy_classification():
    from plagiarism_engine.file_policy import is_scannable

    rejected = {
        "package.json": "config", "frontend/package-lock.json": "config", "pyproject.toml": "config",
        "app/config.yaml": "config", "docker-compose.yml": "config", ".env.example": "config",
        "android/app/src/main/AndroidManifest.xml": "config", "web/manifest.json": "config",
        "vite.config.ts": "config", "tailwind.config.js": "config", "requirements.txt": "config",
        "README.md": "config", "src/vite-env.d.ts": "template", "backend/manage.py": "template",
        "lib/models/user.g.dart": "template", "static/app.min.js": "template", "dist/app.js": "ignored_dir",
        "apps/android_build_log.txt.log": "data_or_log", "data/train.csv": "data_or_log",
        "results.tsv": "data_or_log", "assets/logo.png": "binary", "Makefile": "config",
        "node_modules/react/index.js": "ignored_dir", ".git/config": "ignored_dir",
        "LICENSE": "config", "notes.unknownext": "unsupported",
    }
    for path, reason in rejected.items():
        ok, got = is_scannable(path)
        assert not ok and got == reason, (path, ok, got, reason)

    accepted = ["main.py", "src/App.tsx", "src/index.css", "templates/index.html", "lib/main.dart",
                "packages/core/core_data/lib/src/repo.dart", "thesis.pdf", "essay.docx", "chapter1.md",
                "notes.txt", "db/schema.sql", "Program.cs",
                # 'models/' is a normal source folder (Django / Flutter / MVC) and must be scanned
                "app/models/user.py", "lib/models/invoice.dart"]
    for path in accepted:
        ok, got = is_scannable(path)
        assert ok, (path, got)
    assert is_scannable("models/bge-m3/vocab.txt") == (False, "data_or_log")
    assert is_scannable("models/bge-m3/model.safetensors") == (False, "binary")

    # Size cap: a 3 MB "source" file is generated/data, a 3 MB PDF is a normal thesis.
    assert is_scannable("big.py", 3 * 1024 * 1024) == (False, "too_large")
    assert is_scannable("thesis.pdf", 3 * 1024 * 1024) == (True, "")


def test_walk_stops_completely_at_total_size_limit():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        body = "\n".join(f"def f{i}(x):\n    return x * {i}" for i in range(40))  # ~1 KB, > min_lines
        for d in ("a", "b", "c", "d"):
            (root / d).mkdir()
            for i in range(3):
                (root / d / f"m{i}.py").write_bytes(body.encode("utf-8"))
        (root / "a" / "package.json").write_bytes(b'{"name": "x"}')
        size = len(body.encode("utf-8"))
        excluded = []
        files = FileExtractor.scan_project_directory(root, max_total_bytes=size * 4 + 10, excluded_out=excluded)
        # The cap admits exactly 4 files; the walk must stop entirely (previously it only left the
        # current directory's loop and kept reading the remaining directories).
        assert len(files) == 4, [f["relative_path"] for f in files]
        assert all(f["relative_path"].endswith(".py") for f in files)
        assert not any("package.json" in f["relative_path"] for f in files)


def test_upload_excludes_config_and_logs_end_to_end():
    from app.main import app
    from app.dependencies import _create_access_token
    from app.state import get_db

    client = TestClient(app)
    token = _create_access_token("test_admin", "admin@ministry.gov", "ministry_admin", False)
    headers = {"Authorization": f"Bearer {token}"}
    proj = f"pytest_policy_{uuid.uuid4().hex[:6]}"
    db = get_db()
    code = "\n".join(f"def handler_{i}(req):\n    return {{'ok': {i}}}" for i in range(30))
    try:
        res = client.post(
            "/api/plagiarism/upload-scan",
            data={"project_name": proj, "scan_type": "Direct Upload Project Scan"},
            files=[
                ("files", ("main.py", code.encode("utf-8"), "text/x-python")),
                ("files", ("package.json", b'{"name": "demo", "version": "1.0.0"}', "application/json")),
                ("files", ("build.log", b"BUILD SUCCESSFUL in 3s\n" * 50, "text/plain")),
                ("files", ("data.csv", b"a,b,c\n1,2,3\n" * 50, "text/csv")),
                ("files", ("vite.config.ts", b"export default defineConfig({ plugins: [] })", "text/plain")),
            ],
            headers=headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total_files"] == 1, body
        assert body["excluded_files_count"] == 4, body
        reasons = {e["path"]: e["reason"] for e in body["excluded_files"]}
        assert reasons == {"package.json": "config", "build.log": "data_or_log",
                           "data.csv": "data_or_log", "vite.config.ts": "config"}, reasons
        stored = sorted(f["relative_path"] for f in db.get_project_files(proj))
        assert stored == ["main.py"], stored
        assert set(db.get_project_fingerprints(proj).keys()) <= {"main.py"}

        # An upload with ONLY excluded files is a clear 400, not a 500 / empty project.
        bad = client.post(
            "/api/plagiarism/upload-scan",
            data={"project_name": proj + "_cfg", "scan_type": "Direct Upload Project Scan"},
            files=[("files", ("package.json", b'{"name": "demo"}', "application/json"))],
            headers=headers,
        )
        assert bad.status_code == 400, bad.text
        assert "No scannable files" in bad.json()["detail"]
    finally:
        db.delete_project(proj)
        db.delete_project(proj + "_cfg")


# ===========================================================================
# 9. Round 3 / Phase 2: scoring redesign & evidence gates
# ===========================================================================

def test_code_gate():
    winnow = WinnowingEngine(k=15, w=5)
    code_a = "\n".join([f"def calculate_total_{i}(x, y):\n    return (x + y) * {i}" for i in range(25)])
    code_b = "\n".join([f"class DataRecord_{i}:\n    NAME = 'record_{i}'\n    ACTIVE = True" for i in range(25)])

    # 1. Zero shared fingerprints with high semantic score (0.95)
    # Code is never flagged on meaning alone: capped at LOW (<= 50.0), never HIGH or CRITICAL
    res_zero = compute_fusion_score(code_a, code_b, 0.95, "code", winnow, filename="algo.py")
    assert res_zero["shared_fingerprints"] == 0, res_zero
    assert res_zero["lexical_evidence"] is False
    assert res_zero["fusion_score"] <= 50.0, res_zero
    assert res_zero["verdict"] in ("SAFE", "LOW"), res_zero
    assert res_zero["verdict"] not in ("HIGH", "CRITICAL"), res_zero

    # 2. Restructured code with >= 3 shared fingerprints and high semantic score (0.75)
    # Reaches HIGH via restructured code boost
    code_c = "\n".join([f"def calculate_total_{i}(x, y):\n    return (x + y) * {i}" for i in range(6)] +
                       [f"def mutated_zeta_{i}(val):\n    res = val * {i}\n    return res" for i in range(20)])
    res_shared = compute_fusion_score(code_a, code_c, 0.75, "code", winnow, filename="algo.py")
    assert res_shared["shared_fingerprints"] >= 3, res_shared
    assert res_shared["lexical_evidence"] is True
    assert res_shared["fusion_score"] > 50.0, res_shared
    assert res_shared["verdict"] in ("HIGH", "CRITICAL"), res_shared
    assert res_shared["rule"] == "code_restructured_boost"


def test_text_cap():
    winnow = WinnowingEngine(k=10, w=4)
    text_a = " ".join([f"quantum_computing_concept_{i}" for i in range(60)])
    text_b = " ".join([f"ancient_philosophy_history_{j}" for j in range(60)])

    # Academic PDF with zero lexical overlap and 1.0 semantic score (uncapped 0.80 -> would be CRITICAL)
    res_pdf = compute_fusion_score(text_a, text_b, 1.0, "text", winnow, filename="thesis.pdf")
    assert res_pdf["shared_fingerprints"] == 0, res_pdf
    assert res_pdf["fusion_score"] <= 75.0, res_pdf
    assert res_pdf["verdict"] != "CRITICAL", res_pdf
    assert res_pdf["verdict"] == "HIGH", res_pdf
    assert "zero_fp_capped_high" in res_pdf["rule"]

    # English text with zero lexical overlap and high semantic score (0.98 -> 0.70 * 0.98 = 68.6%)
    res_txt = compute_fusion_score(text_a, text_b, 0.98, "text", winnow, filename="essay.txt")
    assert res_txt["shared_fingerprints"] == 0, res_txt
    assert res_txt["fusion_score"] <= 75.0, res_txt
    assert res_txt["verdict"] != "CRITICAL", res_txt


def test_embedded_copy_production_params():
    import random

    # Production parameters k=50, w=10
    snippet = '''def embedded_algorithm_suite(data_stream, threshold_limit, factor):
    cleaned = [v for v in data_stream if v is not None and v > 0]
    total_acc = 0
    transformed_records = []
    for item_idx, value in enumerate(cleaned):
        if value >= threshold_limit:
            total_acc += value * factor
            transformed_records.append((item_idx, total_acc, "HIGH"))
        else:
            total_acc -= value // 2
            transformed_records.append((item_idx, total_acc, "LOW"))
    matrix = [[(i + 1) * (j + 1) for j in range(min(5, len(cleaned)))] for i in range(min(5, len(cleaned)))]
    return total_acc, transformed_records, matrix
'''
    statements = [
        "    total = sum(x * x for x in items if x % 2 == 0)",
        "    while count < limit:\n        count += step",
        "    try:\n        value = int(raw)\n    except ValueError:\n        value = -1",
        "    with open(path, 'r', encoding='utf-8') as fh:\n        lines = fh.readlines()",
        "    result = [a + b for a, b in zip(left, right)]",
        "    if flag and not other:\n        return None",
        "    mapping = dict(sorted(pairs, key=lambda p: p[1]))",
        "    for i in range(len(data) - 1, -1, -2):\n        data[i] = data[i] ** 3",
        "    assert isinstance(obj, (list, tuple)), 'bad type'",
        "    text = ' '.join(reversed(words)).upper().strip()",
    ]
    rng = random.Random(42)
    lines = []
    for f in range(60):
        lines.append(f"def generated_{f}(items, limit, step, raw, path, left, right, flag, other, pairs, data, obj, words):")
        lines.extend(rng.sample(statements, k=rng.randint(4, 7)))
        lines.append("    return locals()\n")
        if f == 30:
            lines.append(snippet)
    big = "\n".join(lines)

    winnow_prod = WinnowingEngine(k=50, w=10)
    res = compute_fusion_score(snippet, big, 0.50, "code", winnow_prod, filename="module.py")
    assert res["embedded_copy"] is True, res
    assert res["containment_score"] >= 80.0, res
    assert res["winnowing_score"] < 50.0, res
    assert res["lexical_evidence"] is True
    assert res["fusion_score"] >= 65.0, res
    assert res["verdict"] in ("HIGH", "CRITICAL"), res


def test_common_fp_suppression():
    from app.main import app
    from app.dependencies import _create_access_token
    from app.state import get_db

    client = TestClient(app)
    token = _create_access_token("test_admin", "admin@ministry.gov", "ministry_admin", False)
    headers = {"Authorization": f"Bearer {token}"}
    tag = uuid.uuid4().hex[:6]
    db = get_db()

    # Template boilerplate code that will be present in 6 projects
    template_code = "\n\n".join([
        f"def boilerplate_handler_{i}(request, response, context):\n"
        f"    payload = {{'handler_id': {i}, 'status': 'initialized', 'active': True}}\n"
        f"    headers = {{'X-Handler-Version': '1.0.{i}', 'Content-Type': 'application/json'}}\n"
        f"    return payload, headers"
        for i in range(15)
    ])

    projects = [f"pytest_tmpl_{tag}_{i}" for i in range(6)]

    try:
        # Upload 6 projects sharing the exact same boilerplate file
        for idx, p_name in enumerate(projects):
            files = [("boilerplate.py", template_code, "text/x-python")]
            if idx == 5:
                files.append(("unique_impl.py", "def unique_custom_function():\n    return 'secret'\n", "text/x-python"))
            res = client.post(
                "/api/plagiarism/upload-scan",
                data={"project_name": p_name, "scan_type": "Direct Upload Project Scan"},
                files=[("files", (fn, body.encode("utf-8"), mime)) for fn, body, mime in files],
                headers=headers,
            )
            assert res.status_code == 200, res.text

        # Verify get_common_fingerprints detects the template fingerprints
        common_fps = db.get_common_fingerprints(max_projects=5)
        assert len(common_fps) > 0, "Template fingerprints should be identified as common across >= 6 projects"

        # Scan project 5 against the repository
        scan = client.post(
            "/api/plagiarism/scan",
            json={"scan_type": "Saved Project Scan", "target": projects[5]},
            headers=headers,
        )
        assert scan.status_code == 200, scan.text
        comps = scan.json()["comparisons"]

        # The boilerplate template must NOT be flagged as plagiarized against the other 5 projects
        template_hits = [c for c in comps if c.get("file1") == "boilerplate.py" or c.get("file2") == "boilerplate.py"]
        assert len(template_hits) == 0, f"Common template boilerplate was flagged: {template_hits}"

    finally:
        for p_name in projects:
            try:
                db.delete_project(p_name)
            except Exception:
                pass


def test_small_file_exact_code_detected():
    from app.main import app
    from app.dependencies import _create_access_token
    from app.state import get_db

    client = TestClient(app)
    token = _create_access_token("test_admin", "admin@ministry.gov", "ministry_admin", False)
    headers = {"Authorization": f"Bearer {token}"}
    tag = uuid.uuid4().hex[:6]
    db = get_db()

    proj_a = f"pytest_small_a_{tag}"
    proj_b = f"pytest_small_b_{tag}"

    # Small code file (< 50 tokens, produces exactly 1 fingerprint under production k=50)
    small_code = "def authenticate_user(token):\n    return token.startswith('bearer_')\n"

    try:
        res_a = client.post(
            "/api/plagiarism/upload-scan",
            data={"project_name": proj_a, "scan_type": "Direct Upload Project Scan"},
            files=[("files", ("auth_helper.py", small_code.encode("utf-8"), "text/x-python"))],
            headers=headers,
        )
        assert res_a.status_code == 200, res_a.text

        res_b = client.post(
            "/api/plagiarism/upload-scan",
            data={"project_name": proj_b, "scan_type": "Direct Upload Project Scan"},
            files=[("files", ("auth_helper.py", small_code.encode("utf-8"), "text/x-python"))],
            headers=headers,
        )
        assert res_b.status_code == 200, res_b.text

        scan = client.post(
            "/api/plagiarism/scan",
            json={"scan_type": "Saved Project Scan", "target": proj_b},
            headers=headers,
        )
        assert scan.status_code == 200, scan.text
        comps = scan.json()["comparisons"]

        hit = _best_cmp(comps, proj_a, "auth_helper.py", "auth_helper.py")
        assert hit is not None, f"Small exact code file was not detected; comparisons={comps}"
        assert hit["status"] == "CRITICAL", hit
        assert hit["fusion_score"] == 100.0, hit

    finally:
        db.delete_project(proj_a)
        db.delete_project(proj_b)


def test_fusion_scorer_default_filename_guess_lexer():
    winnow = WinnowingEngine(k=15, w=5)
    code = (
        "def merge_config_layers(base, override):\n"
        "    merged = {k: v for k, v in base.items() if v is not None}\n"
        "    for key, value in override.items():\n"
        "        if isinstance(value, dict) and isinstance(merged.get(key), dict):\n"
        "            merged[key] = merge_config_layers(merged[key], value)\n"
        "    return merged\n"
    )
    # Default filename="" triggers Pygments guess_lexer cleanly without crash
    res = compute_fusion_score(code, code, 0.70, "code", winnow, filename="", filename_b="")
    assert res["shared_fingerprints"] >= 5, res
    assert res["fusion_score"] == 88.0, res
    assert res["verdict"] == "CRITICAL", res


def test_containment_elevation_condition():
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

    winnow = WinnowingEngine(k=15, w=5)
    res = compute_fusion_score(snippet, big, 0.40, "code", winnow, filename="snippet.py", filename_b="big.py")
    assert res["embedded_copy"] is True, res
    assert res["containment_score"] >= 80.0, res
    assert res["fusion_score"] >= 60.0, res


def test_symmetric_small_file_detection():
    from app.main import app
    from app.dependencies import _create_access_token
    from app.state import get_db

    client = TestClient(app)
    token = _create_access_token("test_admin", "admin@ministry.gov", "ministry_admin", False)
    headers = {"Authorization": f"Bearer {token}"}
    tag = uuid.uuid4().hex[:6]
    db = get_db()

    proj_small = f"pytest_sym_s_{tag}"
    proj_large = f"pytest_sym_l_{tag}"

    small_code = "def check_signature(sig, key):\n    return sig == key + '_valid'\n"
    noise_code = "def large_system_routine():\n    # large noise implementation\n    " + "\n    ".join([f"x_{i} = {i} * 10" for i in range(60)]) + "\n    return x_0\n"

    try:
        res_s = client.post(
            "/api/plagiarism/upload-scan",
            data={"project_name": proj_small, "scan_type": "Direct Upload Project Scan"},
            files=[("files", ("sig_check.py", small_code.encode("utf-8"), "text/x-python"))],
            headers=headers,
        )
        assert res_s.status_code == 200, res_s.text

        res_l = client.post(
            "/api/plagiarism/upload-scan",
            data={"project_name": proj_large, "scan_type": "Direct Upload Project Scan"},
            files=[
                ("files", ("sig_check.py", small_code.encode("utf-8"), "text/x-python")),
                ("files", ("routine.py", noise_code.encode("utf-8"), "text/x-python")),
            ],
            headers=headers,
        )
        assert res_l.status_code == 200, res_l.text

        scan = client.post(
            "/api/plagiarism/scan",
            json={"scan_type": "Saved Project Scan", "target": proj_large},
            headers=headers,
        )
        assert scan.status_code == 200, scan.text
        comps = scan.json()["comparisons"]

        hit = _best_cmp(comps, proj_small, "sig_check.py", "sig_check.py")
        assert hit is not None, f"Symmetric small file detection failed; comps={comps}"
        assert hit["status"] == "CRITICAL", hit
        assert hit["fusion_score"] == 100.0, hit

    finally:
        db.delete_project(proj_small)
        db.delete_project(proj_large)


def test_compare_endpoints_reject_excluded_files():
    from app.main import app
    from app.dependencies import _create_access_token

    client = TestClient(app)
    token = _create_access_token("test_admin", "admin@ministry.gov", "ministry_admin", False)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/plagiarism/compare-files",
        json={
            "project_a": "any_proj",
            "file_a": "package-lock.json",
            "project_b": "other_proj",
            "file_b": "main.py",
        },
        headers=headers,
    )
    assert res.status_code == 400, res.text
    assert "not scannable" in res.json().get("detail", "")


def test_incremental_reindex():
    from app.state import get_db, get_vstore
    from app.services.embeddings import _index_project_embeddings

    tag = uuid.uuid4().hex[:6]
    proj_name = f"pytest_incr_{tag}"
    db = get_db()
    vstore = get_vstore()

    try:
        # 1. Create project with 2 files
        files_init = [
            {"relative_path": "a.py", "file_type": "code", "content": "def func_a():\n    return 42\n"},
            {"relative_path": "b.py", "file_type": "code", "content": "def func_b():\n    return 99\n"},
        ]
        db.save_project(proj_name, proj_name, files_init)

        # Initially project needs indexing
        assert vstore.needs_reindex(proj_name) is True
        plan = vstore.get_reindex_plan(proj_name)
        assert len(plan["missing"]) == 2
        assert len(plan["valid"]) == 0

        # Index the project
        res1 = _index_project_embeddings(vstore, db, proj_name)
        assert res1["code"] == 2
        assert vstore.needs_reindex(proj_name) is False

        # 2. Add a 3rd file without touching a.py and b.py
        file_c = {"relative_path": "c.py", "file_type": "code", "content": "def func_c():\n    return 123\n"}
        db.save_project(proj_name, proj_name, files_init + [file_c])

        # Now project needs reindex only for the new file
        assert vstore.needs_reindex(proj_name) is True
        plan2 = vstore.get_reindex_plan(proj_name)
        assert plan2["missing"] == ["c.py"]
        assert set(plan2["valid"]) == {"a.py", "b.py"}

        # Run incremental indexing: only the missing file c.py should be encoded
        res2 = _index_project_embeddings(vstore, db, proj_name)
        assert res2["code"] == 1, f"Expected exactly 1 incremental file indexed, got: {res2}"
        assert vstore.needs_reindex(proj_name) is False

        # All 3 files are now valid
        plan3 = vstore.get_reindex_plan(proj_name)
        assert set(plan3["valid"]) == {"a.py", "b.py", "c.py"}
        assert len(plan3["missing"]) == 0

    finally:
        db.delete_project(proj_name)


def test_jwt_guard_and_env_configuration():
    import os
    from app.dependencies import validate_jwt_secret
    from plagiarism_engine.db.helpers import get_database_url, DEFAULT_PG_URL

    # 1. Empty / whitespace secret in production raises RuntimeError
    for empty_val in ["", "   ", None]:
        failed = False
        try:
            validate_jwt_secret(empty_val, app_env="production")
        except RuntimeError as e:
            failed = True
            assert "JWT_SECRET must be set when APP_ENV=production" in str(e)
        assert failed, f"Expected empty value '{empty_val}' to raise RuntimeError"

    # 2. Known placeholders in production raise RuntimeError
    for placeholder in ["your-secret-here", "change-me", "secret", "secret-key", "default-secret"]:
        failed = False
        try:
            validate_jwt_secret(placeholder, app_env="production")
        except RuntimeError as e:
            failed = True
            assert "cannot be a known insecure placeholder" in str(e)
        assert failed, f"Expected placeholder '{placeholder}' to raise RuntimeError"

    # 3. Short secrets (< 32 chars) in production raise RuntimeError
    failed = False
    try:
        validate_jwt_secret("short-secret-key-12345", app_env="production")
    except RuntimeError as e:
        failed = True
        assert "at least 32 characters long" in str(e)
    assert failed, "Expected short secret to raise RuntimeError"

    # 4. Valid secret (>= 32 chars) in production succeeds
    valid_secret = "a_very_secure_random_production_jwt_secret_key_12345"
    assert validate_jwt_secret(valid_secret, app_env="production") == valid_secret

    # 5. In development, None or empty generates a random secret
    dev_secret = validate_jwt_secret(None, app_env="development")
    assert isinstance(dev_secret, str) and len(dev_secret) == 64

    # 6. Database URL guard in production
    old_env = os.environ.copy()
    try:
        os.environ["APP_ENV"] = "production"
        os.environ.pop("DATABASE_URL", None)
        failed = False
        try:
            get_database_url()
        except RuntimeError as e:
            failed = True
            assert "DATABASE_URL must be explicitly configured when APP_ENV=production" in str(e)
        assert failed, "Expected unset DATABASE_URL in production to raise RuntimeError"

        # In dev, unset DATABASE_URL returns DEFAULT_PG_URL
        os.environ["APP_ENV"] = "development"
        assert get_database_url() == DEFAULT_PG_URL

        # With explicit DATABASE_URL, it is returned in either mode
        custom_url = "postgresql://produser:secret@proddb:5432/prod_plagiarism"
        os.environ["DATABASE_URL"] = custom_url
        os.environ["APP_ENV"] = "production"
        assert get_database_url() == custom_url
    finally:
        os.environ.clear()
        os.environ.update(old_env)


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

    def test_16_file_policy_classification(self):
        test_file_policy_classification()

    def test_17_walk_stops_completely_at_total_size_limit(self):
        test_walk_stops_completely_at_total_size_limit()

    def test_18_upload_excludes_config_and_logs_end_to_end(self):
        test_upload_excludes_config_and_logs_end_to_end()

    def test_19_code_gate(self):
        test_code_gate()

    def test_20_text_cap(self):
        test_text_cap()

    def test_21_embedded_copy_production_params(self):
        test_embedded_copy_production_params()

    def test_22_common_fp_suppression(self):
        test_common_fp_suppression()

    def test_23_small_file_exact_code_detected(self):
        test_small_file_exact_code_detected()

    def test_24_fusion_scorer_default_filename_guess_lexer(self):
        test_fusion_scorer_default_filename_guess_lexer()

    def test_25_containment_elevation_condition(self):
        test_containment_elevation_condition()

    def test_26_symmetric_small_file_detection(self):
        test_symmetric_small_file_detection()

    def test_27_compare_endpoints_reject_excluded_files(self):
        test_compare_endpoints_reject_excluded_files()

    def test_28_incremental_reindex(self):
        test_incremental_reindex()

    def test_29_jwt_guard(self):
        test_jwt_guard_and_env_configuration()


if __name__ == "__main__":
    unittest.main(verbosity=2)
