from typing import Optional

import numpy as np
from plagiarism_engine.winnowing import WinnowingEngine
from plagiarism_engine.arabic_preprocessor import detect_language

# Verdict thresholds shared by the fusion pipeline, the scan summary and deep-scan.
VERDICT_THRESHOLDS = ((0.76, "CRITICAL"), (0.51, "HIGH"), (0.21, "LOW"))


def verdict_for(score_0_1: float) -> str:
    """Map a 0..1 score to SAFE / LOW / HIGH / CRITICAL (single source of truth)."""
    for threshold, label in VERDICT_THRESHOLDS:
        if score_0_1 >= threshold:
            return label
    return "SAFE"


def calibrate_semantic(raw: float, model_name: Optional[str]) -> float:
    """Map a raw cosine to a calibrated 0..1 score using the per-model unrelated-pair floor.

    calibrated = clip((raw - floor) / (1 - floor), 0, 1). Unknown / None model -> floor 0.0,
    i.e. the score is returned unchanged (clipped to [0, 1]).
    """
    from plagiarism_engine.config import SEMANTIC_CALIBRATION_FLOOR

    floor = float(SEMANTIC_CALIBRATION_FLOOR.get(model_name, 0.0)) if model_name else 0.0
    raw = float(raw)
    if floor >= 1.0:
        return 0.0
    return float(np.clip((raw - floor) / (1.0 - floor), 0.0, 1.0))


def compute_fusion_score(
    file_a_content: str,
    file_b_content: str,
    semantic_score: float,
    file_type: str,           # "code", "text", or "pdf"
    winnowing_engine: WinnowingEngine,
    filename: str = "",
    filename_b: str = "",
) -> dict:
    """
    Hybrid Plagiarism Score: α·Winnowing + (1-α)·Semantic
    with adaptive α based on file type, size, language, and lexical evidence.

    `semantic_score` is expected to be the *calibrated* semantic similarity (0..1).
    """
    from plagiarism_engine.config import CODE_SEMANTIC_GATE

    is_pdf = file_type == "pdf" or (filename and filename.lower().endswith(".pdf"))
    fn_a = filename or None
    fn_b = filename_b or filename or None

    # 1. Winnowing (Jaccard, per spec) + containment signal
    if file_type == "code":
        fp_a = set(h for h, _ in winnowing_engine.compute_code_fingerprints(file_a_content, fn_a))
        fp_b = set(h for h, _ in winnowing_engine.compute_code_fingerprints(file_b_content, fn_b))
    else:
        fp_a = set(h for h, _ in winnowing_engine.compute_text_fingerprints(file_a_content))
        fp_b = set(h for h, _ in winnowing_engine.compute_text_fingerprints(file_b_content))
    s_winnowing = winnowing_engine.jaccard_similarity(fp_a, fp_b)

    shared = len(fp_a & fp_b)
    smaller = min(len(fp_a), len(fp_b))
    containment = (shared / smaller) if smaller > 0 else 0.0
    embedded_copy = bool(containment >= 0.80 and smaller >= 5 and s_winnowing < 0.50)
    s_lexical = max(s_winnowing, containment) if (smaller >= 5 and containment >= 0.80) else s_winnowing

    evidence = shared >= CODE_SEMANTIC_GATE.get("min_shared_fps", 3)

    # Calculate tokens using Pygments tokenization for code, whitespace for text
    if file_type == "code":
        from plagiarism_engine.code_detector import CodePlagiarismDetector
        tok_a = len(CodePlagiarismDetector.get_token_fingerprint(file_a_content, fn_a))
        tok_b = len(CodePlagiarismDetector.get_token_fingerprint(file_b_content, fn_b))
        token_count = max(tok_a, tok_b)
    else:
        token_count = max(len(file_a_content.split()), len(file_b_content.split()))

    # 2. Adaptive alpha
    lang = detect_language(file_a_content)
    if lang == "unknown" and file_b_content:
        lang = detect_language(file_b_content)

    rule = "standard"
    if semantic_score <= 0.0:
        alpha = 1.0           # No semantics available or zero
        rule = "no_semantics"
    elif token_count < winnowing_engine.k:
        alpha = 1.0           # Small file: exact match only
        rule = "small_file_exact"
    elif file_type == "code":
        if evidence and semantic_score >= CODE_SEMANTIC_GATE.get("min_calibrated", 0.70) and s_winnowing < 0.50:
            alpha = CODE_SEMANTIC_GATE.get("alpha", 0.30)  # Restructured code with lexical evidence
            rule = "code_restructured_boost"
        else:
            alpha = 0.60      # Normal code: structure matters
            rule = "code_standard"
    elif lang in ("arabic", "mixed"):
        alpha = 0.25          # Arabic / mixed Arabic-English: rich synonyms, semantics critical
        rule = "text_arabic"
    elif is_pdf:
        alpha = 0.20          # Academic paper (PDF): heavy paraphrasing
        rule = "text_pdf"
    elif file_type == "text":
        alpha = 0.30          # English text: paraphrasing common
        rule = "text_standard"
    else:
        alpha = 0.50          # Mixed/unknown
        rule = "mixed_default"

    # 3. Fuse
    s_final = alpha * s_lexical + (1.0 - alpha) * semantic_score

    # Caps for matches lacking lexical evidence:
    # - Code is never flagged on meaning alone: without >= 1 shared fingerprint, cap at LOW (0.50)
    # - Text paraphrase without lexical overlap can reach HIGH, but never CRITICAL (cap at 0.75)
    LOW_CEILING = 0.50
    HIGH_CEILING = 0.75

    if file_type == "code":
        if shared == 0:
            if s_final > LOW_CEILING:
                s_final = LOW_CEILING
                rule += ":zero_fp_capped_low"
    else:
        if shared == 0:
            if s_final > HIGH_CEILING:
                s_final = HIGH_CEILING
                rule += ":zero_fp_capped_high"

    # 4. Verdict
    verdict = verdict_for(s_final)

    return {
        "winnowing_score": round(s_winnowing * 100, 2),
        "semantic_score": round(semantic_score * 100, 2),
        "fusion_score": round(s_final * 100, 2),
        "containment_score": round(containment * 100, 2),
        "embedded_copy": embedded_copy,
        "alpha": alpha,
        "shared_fingerprints": shared,
        "lexical_evidence": bool(evidence),
        "rule": rule,
        "verdict": verdict,
        "language": lang,
        "method": "hybrid_fusion_v2",  # v2 uses Postgres 2-Step Rescoring directly
    }
