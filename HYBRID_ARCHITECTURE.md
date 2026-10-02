# Hybrid Vector Architecture: FAISS + pgvector + Adaptive Fusion

> **Project**: Ministry Plagiarism Detection Engine  
> **Author**: Aiman  
> **Date**: October 2, 2026  
> **Status**: Architecture Specification (Pre-Implementation)

---

## 1. Executive Summary

This document specifies a **Hybrid Vector Architecture** that combines the absolute
in-memory speed of **FAISS** (Facebook AI Similarity Search) with the serverless cloud
persistence of **pgvector** (PostgreSQL vector extension), unified by a novel
**Adaptive Fusion Scoring Algorithm** that intelligently blends lexical (Winnowing)
and semantic (embedding-based) similarity scores.

The goal is to build a plagiarism detection engine that:
- Runs at **sub-millisecond search latency** on local/VPS deployments (FAISS)
- Operates on **fully serverless cloud platforms** like Supabase/Neon (pgvector)
- Detects **both exact copy-paste AND intelligent paraphrasing** (Adaptive Fusion)
- Scales to **millions of documents** without degradation

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        PROJECT UPLOAD                            │
│                                                                  │
│   Raw Files → FileExtractor → Clean Text                         │
│                    │                                             │
│         ┌──────────┴──────────┐                                  │
│         ▼                     ▼                                  │
│   Winnowing Engine      CodeBERT / BGE-M3                        │
│   (Fingerprints)        (Vector Embeddings)                      │
│         │                     │                                  │
│         ▼                     ├──────────────────┐               │
│   fingerprint_index      ┌───▼───┐          ┌───▼───┐           │
│   table (PostgreSQL)     │pgvector│          │ FAISS │           │
│                          │ column │          │ index │           │
│                          │(Source │          │(Speed │           │
│                          │of Truth)│         │ Cache)│           │
│                          └───┬───┘          └───┬───┘           │
│                              │                  │                │
│                              └────────┬─────────┘                │
│                                       ▼                          │
│                              Search Orchestrator                 │
│                              (Tries FAISS first,                 │
│                               falls back to pgvector)            │
│                                       │                          │
│                                       ▼                          │
│                           ┌───────────────────────┐              │
│                           │  Adaptive Fusion       │              │
│                           │  Scoring Engine         │              │
│                           │                         │              │
│                           │  S = α·Winnowing        │              │
│                           │    + (1-α)·Semantic     │              │
│                           └───────────────────────┘              │
│                                       │                          │
│                                       ▼                          │
│                              Final Similarity Score              │
│                              + Verdict (SAFE / FLAG / HIGH)      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. The Two Vector Engines

### 3.1 pgvector (Source of Truth)

pgvector is a PostgreSQL extension that adds a `VECTOR(n)` column type to standard
SQL tables. Vectors are stored as first-class database values with full ACID
guarantees, indexing (IVFFlat, HNSW), and SQL-native filtering.

**How we will use it:**

```sql
-- Add a vector column to the existing project_files table
ALTER TABLE project_files
    ADD COLUMN embedding VECTOR(768);  -- CodeBERT outputs 768-dim vectors

-- Create an HNSW index for fast approximate nearest-neighbor search
CREATE INDEX idx_project_files_embedding
    ON project_files
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Search: find the top 10 most similar files across ALL projects
SELECT pf.project_id, pf.relative_path,
       1 - (pf.embedding <=> query_embedding) AS cosine_similarity
FROM project_files pf
WHERE pf.project_id != 'current_project_id'
  AND pf.embedding IS NOT NULL
ORDER BY pf.embedding <=> query_embedding
LIMIT 10;

-- Filtered search: only compare within a specific college
SELECT pf.project_id, pf.relative_path,
       1 - (pf.embedding <=> query_embedding) AS cosine_similarity
FROM project_files pf
JOIN projects p ON p.id = pf.project_id
WHERE p.university = 'Ibb University'
  AND pf.project_id != 'current_project_id'
ORDER BY pf.embedding <=> query_embedding
LIMIT 10;
```

### 3.2 FAISS (Speed Cache)

FAISS is a C++ library (with Python bindings) that holds vectors entirely in RAM.
It is the fastest known implementation for brute-force and approximate nearest
neighbor search.

**How we will use it:**

```python
# On server startup: hydrate FAISS from pgvector
def hydrate_faiss_from_db():
    """Load all vectors from PostgreSQL into an in-memory FAISS index."""
    rows = db.execute("SELECT id, embedding FROM project_files WHERE embedding IS NOT NULL")
    vectors = np.array([row['embedding'] for row in rows], dtype='float32')
    ids = np.array([hash(row['id']) for row in rows], dtype='int64')

    faiss.normalize_L2(vectors)  # Normalize for cosine similarity
    index = faiss.IndexIDMap(faiss.IndexFlatIP(768))
    index.add_with_ids(vectors, ids)
    return index

# On search: try FAISS first, fall back to pgvector
def search_similar(query_vector, top_k=10):
    if faiss_index is not None and faiss_index.ntotal > 0:
        # FAISS: ~0.5ms for 100K vectors
        scores, ids = faiss_index.search(query_vector, top_k)
        return resolve_ids_to_files(ids, scores)
    else:
        # pgvector fallback: ~15ms for 100K vectors
        return db.execute(pgvector_search_query, [query_vector, top_k])
```

### 3.3 Write-Through Synchronization

Every time a new vector is generated (during Deep Scan indexing):

1. **Write to pgvector FIRST** (source of truth, durable)
2. **Write to FAISS SECOND** (speed cache, volatile)
3. If FAISS write fails (out of memory, etc.), the system continues — pgvector
   still has the vector for fallback search.

Every time a project is deleted:
1. Delete vectors from pgvector (`DELETE FROM project_files WHERE project_id = ?`)
2. Remove IDs from FAISS (`index.remove_ids(id_array)`)

---

## 4. Adaptive Fusion Scoring Algorithm

### 4.1 The Formula

The final similarity score between two documents A and B is:

```
S_final(A, B) = α · S_winnowing(A, B) + (1 - α) · S_semantic(A, B)
```

Where:
- S_winnowing = Jaccard similarity of Winnowing fingerprint sets
- S_semantic  = Cosine similarity of embedding vectors (from FAISS or pgvector)
- α (alpha)   = Adaptive weight, determined by file characteristics

### 4.2 Adaptive Weight (α) Rules

| File Characteristic               | α Value | Reasoning                                          |
|------------------------------------|---------|-----------------------------------------------------|
| Code file (`.py`, `.java`, `.cpp`) | 0.6     | Code has rigid structure; exact matching is strong   |
| Text file (`.txt`, `.md`, `.docx`) | 0.3     | Students paraphrase text; semantics matter more      |
| Small file (< k tokens)           | 1.0     | Only exact match; semantics unreliable on tiny data  |
| Mixed project (code + docs)        | 0.5     | Balanced weight for mixed content                    |
| PDF academic paper                 | 0.2     | Heavy paraphrasing expected; semantics dominate      |

### 4.3 Verdict Thresholds

| Final Score Range | Verdict    | Color  | Action                        |
|-------------------|------------|--------|-------------------------------|
| 0% – 20%         | SAFE       | Green  | No action needed              |
| 21% – 50%        | LOW        | Yellow | Manual review recommended     |
| 51% – 75%        | HIGH       | Orange | Likely plagiarism, investigate |
| 76% – 100%       | CRITICAL   | Red    | Almost certain plagiarism     |

### 4.4 Implementation

```python
def compute_fusion_score(
    file_a_content: str,
    file_b_content: str,
    file_a_embedding: np.ndarray,
    file_b_embedding: np.ndarray,
    file_type: str,
    token_count: int,
    winnowing_engine: WinnowingEngine,
) -> dict:
    """
    Hybrid Plagiarism Score: combines Winnowing (lexical) with
    embedding cosine similarity (semantic) using an adaptive weight.
    """
    # 1. Compute Winnowing similarity
    if file_type == "code":
        fp_a = set(h for h, _ in winnowing_engine.compute_code_fingerprints(file_a_content, "a"))
        fp_b = set(h for h, _ in winnowing_engine.compute_code_fingerprints(file_b_content, "b"))
    else:
        fp_a = set(h for h, _ in winnowing_engine.compute_text_fingerprints(file_a_content))
        fp_b = set(h for h, _ in winnowing_engine.compute_text_fingerprints(file_b_content))

    s_winnowing = winnowing_engine.jaccard_similarity(fp_a, fp_b)

    # 2. Compute Semantic similarity (cosine)
    from numpy.linalg import norm
    if norm(file_a_embedding) > 0 and norm(file_b_embedding) > 0:
        s_semantic = float(np.dot(file_a_embedding, file_b_embedding) /
                          (norm(file_a_embedding) * norm(file_b_embedding)))
        s_semantic = max(0.0, s_semantic)  # Clamp negatives
    else:
        s_semantic = 0.0

    # 3. Determine adaptive alpha
    if token_count < winnowing_engine.k:
        alpha = 1.0       # Small file: exact match only
    elif file_type == "code":
        alpha = 0.6       # Code: structure matters
    elif file_type == "text":
        alpha = 0.3       # Text: semantics matter
    else:
        alpha = 0.5       # Mixed/unknown: balanced

    # 4. Fuse scores
    s_final = alpha * s_winnowing + (1 - alpha) * s_semantic

    # 5. Determine verdict
    if s_final >= 0.76:
        verdict = "CRITICAL"
    elif s_final >= 0.51:
        verdict = "HIGH"
    elif s_final >= 0.21:
        verdict = "LOW"
    else:
        verdict = "SAFE"

    return {
        "winnowing_score": round(s_winnowing * 100, 2),
        "semantic_score": round(s_semantic * 100, 2),
        "fusion_score": round(s_final * 100, 2),
        "alpha": alpha,
        "verdict": verdict,
        "method": "hybrid_fusion_v1",
    }
```

---

## 5. Deployment Modes

The hybrid architecture supports three deployment configurations:

### Mode 1: Local Development (Current)
```
Database:  SQLite (local file)
Vectors:   FAISS only (in-memory, loaded from .faiss files on disk)
Storage:   Local filesystem (data/ folder)
Speed:     Maximum (everything in RAM)
Limitation: No cloud, no persistence across crashes
```

### Mode 2: VPS / Dedicated Server (Recommended for University)
```
Database:  PostgreSQL (local or managed, e.g., DigitalOcean)
Vectors:   pgvector (source of truth) + FAISS (speed cache)
Storage:   Local filesystem or mounted volume
Speed:     Near-maximum (FAISS in RAM, pgvector as backup)
Limitation: Single server, no horizontal scaling
```

### Mode 3: Fully Serverless (Future / Cloud)
```
Database:  Supabase PostgreSQL / Neon
Vectors:   pgvector ONLY (FAISS cannot persist on serverless)
Storage:   Supabase Storage / AWS S3
Speed:     Good (pgvector HNSW index, ~15-80ms per search)
Limitation: No FAISS acceleration (serverless has no persistent RAM)
```

---

## 6. Pros and Cons

### 6.1 Pros of the Hybrid Architecture

| # | Advantage | Detail |
|---|-----------|--------|
| 1 | **Maximum Speed** | FAISS in-memory search at ~0.5ms for 100K vectors. No other solution on Earth is faster for brute-force vector search. |
| 2 | **Cloud-Native Persistence** | pgvector stores vectors inside PostgreSQL. Supabase, Neon, AWS RDS all support it natively. Zero data loss on restart. |
| 3 | **SQL Filtering** | pgvector allows `WHERE college = 'X'` in vector queries. FAISS alone cannot do this — it returns raw IDs that must be cross-referenced. |
| 4 | **Graceful Degradation** | If FAISS crashes or runs out of RAM, the system seamlessly falls back to pgvector. The user never knows. |
| 5 | **Deployment Flexibility** | The same codebase works on a laptop (FAISS only), a VPS (both), or Supabase (pgvector only). No code changes needed. |
| 6 | **Research Novelty** | The Adaptive Fusion Algorithm (α-weighted Winnowing + Semantic) is a genuine contribution. Most plagiarism tools use only one method. |
| 7 | **Scalability** | pgvector's HNSW index scales to millions of vectors. FAISS's IVF index scales to billions. |
| 8 | **Cost Efficiency** | On a VPS, FAISS uses only RAM (free after server cost). pgvector uses the database you already pay for. No additional vector DB subscription (Pinecone = $70/mo+). |

### 6.2 Cons of the Hybrid Architecture

| # | Disadvantage | Detail | Mitigation |
|---|-------------|--------|------------|
| 1 | **Double Write Overhead** | Every vector must be written to both pgvector AND FAISS during indexing. This doubles the write time. | Write to pgvector first (async), then FAISS. The user only waits for pgvector. FAISS sync can be deferred. |
| 2 | **RAM Consumption** | FAISS holds ALL vectors in memory. 100K files × 768 dimensions × 4 bytes = ~300 MB RAM. 1M files = ~3 GB. | Set a configurable `FAISS_MAX_VECTORS` limit. Beyond this threshold, disable FAISS and rely on pgvector only. |
| 3 | **Consistency Risk** | If the server crashes between writing to pgvector and FAISS, FAISS will be stale. | On startup, FAISS is always re-hydrated from pgvector (source of truth). Staleness lasts at most until the next restart. |
| 4 | **Cold Start Latency** | On serverless (Supabase), FAISS is unavailable. The first search must use pgvector, which is ~30x slower than FAISS. | For serverless, pgvector's HNSW index keeps latency under 80ms — still far under the 1-second user threshold. |
| 5 | **Increased Code Complexity** | Maintaining two vector backends means more code paths, more tests, and more potential bugs. | Abstract both behind a single `VectorSearchService` interface with `.store()`, `.search()`, and `.delete()` methods. The rest of the app doesn't know or care which backend is active. |
| 6 | **FAISS is Not ACID** | FAISS has no transactions, no rollback, no crash recovery. If the process is killed mid-write, the index can corrupt. | FAISS is expendable (it's a cache). If corrupted, delete the `.faiss` file and let the startup hydration rebuild it from pgvector. |
| 7 | **Model Dependency** | CodeBERT and BGE-M3 models are 400MB+ each. They must be downloaded and cached on the server. On serverless, this is impractical. | For serverless, use an external embedding API (OpenAI, Cohere) instead of local models, or pre-compute embeddings during upload on a VPS and store them in pgvector. |
| 8 | **pgvector Index Build Time** | Building an HNSW index on 1M+ vectors can take 10-30 minutes. During this time, searches are slower. | Build the index during off-peak hours. Use `CREATE INDEX CONCURRENTLY` to avoid locking the table. |

### 6.3 Pros and Cons of the Adaptive Fusion Algorithm Specifically

| Aspect | Pro | Con |
|--------|-----|-----|
| **Accuracy** | Catches both lazy copy-paste (Winnowing) AND smart paraphrasing (semantic) in one pass | The α weights are heuristic-based, not trained on labeled data. They may need tuning per institution. |
| **Transparency** | Returns three scores (Winnowing %, Semantic %, Fusion %) so the professor sees exactly WHY a file was flagged | Three scores can confuse non-technical users. The UI must clearly explain what each score means. |
| **Small Files** | α=1.0 for small files eliminates the false-positive problem entirely | Very small files (< 50 tokens) will only match exact copies. A student who copies 10 lines and renames 1 variable will evade detection. |
| **Language Agnostic** | Winnowing works on any language. CodeBERT works on 6 programming languages. BGE-M3 works on 100+ human languages. | CodeBERT is trained primarily on Python, Java, JavaScript, PHP, Ruby, Go. It may underperform on Dart, Rust, or Assembly. |

---

## 7. Migration Path

### Phase 1: Current State (SQLite + FAISS)
- Already working. All bugs fixed.
- No pgvector, no fusion scoring.

### Phase 2: Add pgvector (PostgreSQL Migration)
- Replace SQLite with PostgreSQL.
- Add `VECTOR(768)` column to `project_files`.
- Store embeddings in pgvector during Deep Scan indexing.
- FAISS continues to work as the speed cache.
- Add `hydrate_faiss_from_db()` on startup.

### Phase 3: Implement Adaptive Fusion
- Add `compute_fusion_score()` to the engine.
- Update the scan endpoints to return `winnowing_score`, `semantic_score`, and `fusion_score`.
- Update the frontend to display all three scores with visual breakdowns.

### Phase 4: Serverless Readiness
- Abstract file storage behind a `StorageService` (local FS vs S3).
- Abstract vector search behind a `VectorSearchService` (FAISS vs pgvector).
- Deploy to Supabase (pgvector only, no FAISS) or VPS (both).

---

## 8. Time Complexity Summary

| Operation | Winnowing | FAISS (Flat) | FAISS (IVF) | pgvector (HNSW) |
|-----------|-----------|-------------|-------------|-----------------|
| Index 1 file | O(N) | O(d) | O(d) | O(d·log N) |
| Search 10K files | O(S₁+S₂) | O(N·d) ≈ 0.5ms | O(√N·d) ≈ 0.1ms | O(log N·d) ≈ 15ms |
| Search 1M files | O(S₁+S₂) | O(N·d) ≈ 50ms | O(√N·d) ≈ 5ms | O(log N·d) ≈ 80ms |
| Filtered search | N/A | ❌ Not supported | ❌ Not supported | ✅ O(log N·d) |
| Delete 1 project | O(1) | O(N) rebuild | O(N) rebuild | O(1) per row |

Where:
- N = total number of vectors in the index
- d = vector dimension (768 for CodeBERT)
- S₁, S₂ = fingerprint set sizes for the two files being compared

---

## 9. Conclusion

The Hybrid Architecture is not just an engineering optimization — it is a genuine
research contribution. By combining the raw speed of FAISS with the cloud persistence
of pgvector, and unifying lexical and semantic detection through an adaptive fusion
algorithm, this system achieves a detection capability that exceeds any single-method
approach.

The key insight is that **no single algorithm catches all forms of plagiarism**.
Winnowing catches exact copy-paste but fails on paraphrasing. Embeddings catch
paraphrasing but produce false positives on small files. The Adaptive Fusion
Algorithm uses the strengths of each method precisely where they are strongest,
weighted by the characteristics of the file being analyzed.

This is the architecture that will power the Ministry Plagiarism Detection Engine.
