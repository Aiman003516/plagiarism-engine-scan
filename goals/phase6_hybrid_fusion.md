# Phase 6 Goal: Hybrid Fusion Algorithm

## Objective
Implement the Adaptive Fusion Scoring Algorithm that combines Winnowing (lexical) similarity with embedding (semantic) similarity using file-type-aware α weights. Update scan endpoints and frontend to display all three scores.

## Context
Read `MASTER_ROADMAP.md` in this repo for the full project context. This is Phase 6 of 6 (the final phase).
Phases 2-5 must be completed before starting this phase.

## Tasks

### Task 1: Create the Fusion Scoring Engine

Create `plagiarism_engine/fusion_scorer.py`:

```python
import numpy as np
from numpy.linalg import norm
from plagiarism_engine.winnowing import WinnowingEngine
from plagiarism_engine.arabic_preprocessor import detect_language

def compute_fusion_score(
    file_a_content: str,
    file_b_content: str,
    file_a_embedding: np.ndarray | None,
    file_b_embedding: np.ndarray | None,
    file_type: str,           # "code" or "text"
    token_count: int,
    winnowing_engine: WinnowingEngine,
) -> dict:
    """
    Hybrid Plagiarism Score: α·Winnowing + (1-α)·Semantic
    with adaptive α based on file type, size, and language.
    """
    # 1. Winnowing (Jaccard)
    if file_type == "code":
        fp_a = set(h for h, _ in winnowing_engine.compute_code_fingerprints(file_a_content, "a"))
        fp_b = set(h for h, _ in winnowing_engine.compute_code_fingerprints(file_b_content, "b"))
    else:
        fp_a = set(h for h, _ in winnowing_engine.compute_text_fingerprints(file_a_content))
        fp_b = set(h for h, _ in winnowing_engine.compute_text_fingerprints(file_b_content))
    s_winnowing = winnowing_engine.jaccard_similarity(fp_a, fp_b)

    # 2. Semantic (Cosine) — only if both embeddings exist
    s_semantic = 0.0
    has_semantic = False
    if file_a_embedding is not None and file_b_embedding is not None:
        na, nb = norm(file_a_embedding), norm(file_b_embedding)
        if na > 0 and nb > 0:
            s_semantic = max(0.0, float(np.dot(file_a_embedding, file_b_embedding) / (na * nb)))
            has_semantic = True

    # 3. Adaptive alpha
    lang = detect_language(file_a_content)
    if not has_semantic:
        alpha = 1.0           # No embeddings available, Winnowing only
    elif token_count < winnowing_engine.k:
        alpha = 1.0           # Small file: exact match only
    elif file_type == "code":
        alpha = 0.6           # Code: structure matters
    elif lang == "arabic":
        alpha = 0.25          # Arabic: rich synonyms, semantics critical
    elif file_type == "text":
        alpha = 0.3           # English text: paraphrasing common
    else:
        alpha = 0.5           # Mixed/unknown

    # 4. Fuse
    s_final = alpha * s_winnowing + (1 - alpha) * s_semantic

    # 5. Verdict
    if s_final >= 0.76:   verdict = "CRITICAL"
    elif s_final >= 0.51: verdict = "HIGH"
    elif s_final >= 0.21: verdict = "LOW"
    else:                 verdict = "SAFE"

    return {
        "winnowing_score": round(s_winnowing * 100, 2),
        "semantic_score": round(s_semantic * 100, 2),
        "fusion_score": round(s_final * 100, 2),
        "alpha": alpha,
        "verdict": verdict,
        "language": lang,
        "method": "hybrid_fusion_v1",
    }
```

### Task 2: Integrate Fusion into Scan Endpoints

In the scanner router (created in Phase 2):
- When the scan compares two files, call `compute_fusion_score()` instead of only returning the Winnowing Jaccard score
- Pass embeddings from the HybridVectorService (created in Phase 4)
- The scan results should now include all three scores: `winnowing_score`, `semantic_score`, `fusion_score`
- The `verdict` field should use the fusion score, not just Winnowing

Update the SSE stream events to include the new score fields.

### Task 3: Update the Scan Report Schema

In the database schema, update `scan_reports` to store:
- `winnowing_score` REAL
- `semantic_score` REAL
- `fusion_score` REAL
- `alpha` REAL
- `verdict` TEXT

### Task 4: Update Frontend — Score Display

In the scan results UI:
- Show a **three-bar breakdown** for each matched file pair:
  - 🔵 Winnowing Score (lexical match %)
  - 🟣 Semantic Score (meaning match %)
  - 🟠 Fusion Score (final combined %)
- Show the verdict badge with color: SAFE (green), LOW (yellow), HIGH (orange), CRITICAL (red)
- Add a tooltip or info icon explaining what each score means:
  - Winnowing: "Detects exact copy-paste of code or text"
  - Semantic: "Detects paraphrasing, variable renaming, and translation"
  - Fusion: "Combined score weighted by file type and language"

### Task 5: Update Dashboard Stats

On the Dashboard:
- Show the average fusion score across all scanned projects
- Show a pie chart or bar of verdicts (how many SAFE, LOW, HIGH, CRITICAL)

### Task 6: Verify

1. Upload two files with exact copied content → expect HIGH Winnowing, HIGH Semantic, CRITICAL Fusion
2. Upload two files where one is a paraphrased version → expect LOW Winnowing, HIGH Semantic, HIGH Fusion
3. Upload two completely different files → expect SAFE across all scores
4. Upload Arabic documents with copied content → verify α=0.25 is applied
5. Upload a small file (<50 tokens) → verify α=1.0 (Winnowing only)
6. Check the frontend displays all three score bars correctly
7. Check the dashboard shows verdict distribution
8. Run `cd frontend && npx tsc --noEmit`
9. Git push with tag: `git tag v2.0-hybrid-fusion && git push --tags`

## Success Criteria
- [ ] `compute_fusion_score()` returns all three scores + verdict
- [ ] Scan endpoints return fusion results instead of Winnowing-only
- [ ] Frontend displays three-bar score breakdown with tooltips
- [ ] Dashboard shows verdict distribution
- [ ] Arabic documents get α=0.25 automatically
- [ ] Small files get α=1.0 automatically
- [ ] Scan reports store all score fields in the database
- [ ] Git tagged as `v2.0-hybrid-fusion` and pushed
