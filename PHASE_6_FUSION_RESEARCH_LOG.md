# Phase 6: Hybrid Fusion Algorithm Research Log

## Overview
This log details the mathematical and architectural updates to the Hybrid Fusion Algorithm (Phase 6), taking into account the removal of local FAISS and the shift to PostgreSQL's `pgvector` for semantic embeddings.

## Core Formula
The core fusion score between a query file ($A$) and a target file ($B$) is given by:

$$ S_{fusion}(A, B) = \alpha \cdot S_{winnowing}(A, B) + (1 - \alpha) \cdot S_{semantic}(A, B) $$

### 1. Winnowing Score ($S_{winnowing}$)
Calculated using Jaccard Similarity of k-gram rolling hashes (fingerprints):
$$ S_{winnowing} = \frac{|FP(A) \cap FP(B)|}{|FP(A) \cup FP(B)|} $$

### 2. Semantic Score ($S_{semantic}$)
Calculated using Exact Cosine Similarity. **Critical Change:** Since FAISS was removed, this computation has been pushed directly into the PostgreSQL database layer using `pgvector`:
$$ S_{semantic} = \cos(A, B) = \frac{\vec{A} \cdot \vec{B}}{\|\vec{A}\| \|\vec{B}\|} $$
This is executed efficiently in SQL as:
`1 - (embedding <=> query_embedding)`

## The Adaptive Weight ($\alpha$)
The weight $\alpha$ determines how much emphasis is placed on exact lexical matches vs. paraphrased semantic meaning. The system adapts this weight dynamically:

- **$\alpha = 1.0$**: Applied when a file is too small to embed meaningfully, or when semantic scores are absent. Strictly structural.
- **$\alpha = 0.6$**: Applied to **Code** files. Structural syntax and exact token patterns are more indicative of plagiarism in code than in text.
- **$\alpha = 0.3$**: Applied to standard **Text** files. Writers often paraphrase or use synonyms, so semantic meaning takes priority.
- **$\alpha = 0.25$**: Applied to **Arabic Text**. Due to the high morphological richness and vast synonymy of Arabic, exact lexical matching is less reliable; meaning is prioritized heavily.

## Verdict Thresholds
The final fused score is evaluated against standardized thresholds:
- $S_{fusion} \ge 0.76 \implies$ **CRITICAL**
- $S_{fusion} \ge 0.51 \implies$ **HIGH**
- $S_{fusion} \ge 0.21 \implies$ **LOW**
- $S_{fusion} < 0.21 \implies$ **SAFE**

## Architectural Gains from Cutting FAISS
1. **Memory Efficiency**: Previously, `numpy` vectors were loaded into local RAM to compute `np.dot`. Now, Postgres computes the similarity on disk-backed indexes, reducing the Python memory footprint of the API server from $\mathcal{O}(N)$ (where $N$ is total system vectors) to $\mathcal{O}(1)$.
2. **Speed (Pre-calculation)**: During Phase 3's candidate generation, the system runs a single `search_bulk` query to PostgreSQL which yields the top semantic matches before the Python fusion loop even begins. 
3. **Decoupled Workload**: The Python `fusion_scorer.py` now purely acts as the mathematical combiner rather than bearing the load of semantic nearest-neighbor search.

## Round 2 Addendum — Calibration, Model Choice, and Known Limitations

### Semantic score calibration
Raw cosine similarity is not comparable across models: on the in-code labeled set in
`scripts/calibrate_semantic_models.py`, **unrelated** pairs averaged 0.98 cosine with `codebert-base`,
0.30 with `unixcoder-base`, and 0.72 with `bge-m3`. The pipeline therefore fuses a *calibrated* score
`clip((cos - floor) / (1 - floor), 0, 1)` with a per-model floor (mean unrelated cosine) from
`calibration_results.md`. The code model was switched from `codebert-base` (AUC 0.970, margin −0.001)
to `unixcoder-base` (AUC 1.000, margin +0.228). Every stored vector is tagged with `embedding_model`,
and vectors from different models are never compared.

### Known limitation — embedded copies vs. Jaccard
`S_winnowing` follows the spec and uses **Jaccard** similarity, but candidate discovery uses the
**overlap coefficient** (shared / min). When a short fragment is pasted into a much larger file, overlap
is high while Jaccard stays low, so the fused score can understate the copy. The fusion formula is
unchanged; instead every comparison now also reports `containment_score` (= |A∩B| / min(|A|,|B|)) and
an `embedded_copy` flag (containment ≥ 0.80, smaller set ≥ 5 fingerprints, Jaccard < 0.50) so reviewers
can see these cases. Whether `embedded_copy` should raise the verdict is an open research decision.

### Known limitation — calibration data
The calibration set is synthetic (in-code, ≥ 60-word texts, 10+10 code pairs, 8+8 EN and AR pairs).
Floors should be re-measured on real university submissions (e.g. Ibb University Arabic PDFs) before
the thresholds are treated as final.

---

## Round 3 / Production Specification — Evidence-Gated Fusion Scoring

To resolve the embedded copy dead zone and eliminate semantic false positives on unrelated code, the engine implements an **Evidence-Gated Fusion Algorithm**:

### 1. Elevated Embedded Copy Containment
When a smaller code or text file is embedded into a larger file:
- If $\text{containment} \ge 0.80$ and $|FP_{smaller}| \ge 5$ fingerprints:
  $$s_{lexical} = \max(s_{winnowing}, \text{containment})$$
- This prevents large surrounding files from diluting the Jaccard denominator, reliably elevating verbatim copy-pastes to **HIGH** or **CRITICAL**.

### 2. Code Semantic Gating
- **Code is never admitted on semantic similarity alone.**
- A semantic boost applies if and only if the pair shares $\ge 3$ Winnowing fingerprints, calibrated semantic score $\ge 0.70$, and $s_{winnowing} < 0.50$:
  $$S_{fusion} = 0.30 \cdot s_{winnowing} + 0.70 \cdot s_{semantic}$$
- If fewer than 3 fingerprints are shared, code similarity is capped at **LOW** ($\le 0.50$).

### 3. Zero-Evidence Ceilings
- **Code with 0 shared fingerprints:** Capped at **LOW** ($\le 0.50$), preventing unrelated frameworks from triggering alarms.
- **Text with 0 shared fingerprints:** Admitted on semantic score if raw cosine $\ge 0.885$ (BGE-M3), but strictly capped at **HIGH** ($\le 0.75$, never **CRITICAL**).

### 4. MOSS-Style Common Boilerplate Suppression
Fingerprints occurring in $> \max(5, 5\% \text{ of total projects})$ distinct projects are automatically excluded from candidate counts, eliminating false-positive alarms from common library imports, boilerplate templates, and framework scaffolding.

### 5. Empirical Verification on Production Monorepos
Evaluated on `realeval_mizan_monorepo` (522 files, 121,029 fingerprints):
- **0 false positives** at HIGH or CRITICAL between unrelated software repositories.
- Batched SQL candidate indexing accelerated Quick Scan lexical matching from 6 min 13 s to 1.41 s.

