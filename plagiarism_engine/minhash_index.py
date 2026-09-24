"""
MinHash + LSH Scalability Layer for Plagiarism Detection at Scale (100K+ documents).

Instead of O(N²) brute-force pairwise comparison, this module:
1. Computes a compact MinHash signature (128 hashes) per document in O(N) time.
2. Indexes signatures in an LSH (Locality-Sensitive Hashing) structure.
3. Queries return only candidate pairs likely to be similar — typically reducing
   5 billion comparisons down to ~50K candidates.

Uses the `datasketch` library (production-grade, used by Google/industry).
"""

import re
from typing import List, Dict, Any, Optional, Set, Tuple
from datasketch import MinHash, MinHashLSH


def _text_shingles(text: str, k: int = 3) -> Set[str]:
    """
    Generates word-level k-shingles from text.
    A 3-shingle of "the cat sat on the mat" = {"the cat sat", "cat sat on", "sat on the", "on the mat"}.
    k=3 provides good recall for plagiarism detection while keeping signatures compact.
    """
    words = re.findall(r'\w+', text.lower())
    if len(words) < k:
        return set(words) if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def _token_shingles(tokens: List[str], k: int = 3) -> Set[str]:
    """
    Generates k-shingles from a pre-tokenized code fingerprint sequence.
    Example: ["K:def", "ID", "P:(", "P:)"] with k=3 → {"K:def ID P:(", "ID P:( P:)"}
    """
    if len(tokens) < k:
        return set(tokens) if tokens else set()
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


class MinHashLSHIndex:
    """
    Production MinHash + LSH Index for sub-linear similarity candidate discovery.

    Supports two domains:
    - 'text': Uses word-level shingles for natural language documents.
    - 'code': Uses token-level shingles from code fingerprint sequences.

    Usage:
        index = MinHashLSHIndex(threshold=0.5, num_perm=128)
        index.index_document("doc1", "some long text content", domain="text")
        index.index_document("doc2", "similar long text content", domain="text")
        candidates = index.query_candidates("similar long text", domain="text")
        # candidates = {"doc1", "doc2"}  — only likely-similar docs returned
    """

    def __init__(self, threshold: float = 0.5, num_perm: int = 128):
        """
        Args:
            threshold: Jaccard similarity threshold for LSH bucketing (0.0 to 1.0).
                       Lower = more candidates (higher recall, lower precision).
                       0.5 is a good balance for plagiarism detection.
            num_perm: Number of hash permutations for MinHash signatures.
                      128 gives good accuracy. 256 for higher precision at 2x memory cost.
        """
        self.threshold = threshold
        self.num_perm = num_perm

        # Separate LSH indexes for code vs text (different shingling strategies)
        self._text_lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self._code_lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)

        # Cache of computed MinHash signatures for re-query / verification
        self._text_signatures: Dict[str, MinHash] = {}
        self._code_signatures: Dict[str, MinHash] = {}

    def _get_lsh(self, domain: str):
        return self._code_lsh if domain == "code" else self._text_lsh

    def _get_cache(self, domain: str):
        return self._code_signatures if domain == "code" else self._text_signatures

    def _compute_minhash(self, shingles: Set[str]) -> MinHash:
        """Compute a MinHash signature from a set of shingles."""
        m = MinHash(num_perm=self.num_perm)
        for s in shingles:
            m.update(s.encode('utf-8'))
        return m

    def index_document(self, doc_id: str, content: str, domain: str = "text") -> None:
        """
        Index a single document into the appropriate LSH index.

        Args:
            doc_id: Unique identifier for the document.
            content: Raw text content (for text domain) or raw code (for code domain).
            domain: "text" or "code".
        """
        if not content or not content.strip():
            return

        if domain == "code":
            # For code, we use word-level shingles on the raw code as a fast approximation.
            # The precise token fingerprint comparison happens in the verification stage.
            shingles = _text_shingles(content, k=3)
        else:
            shingles = _text_shingles(content, k=3)

        if not shingles:
            return

        mh = self._compute_minhash(shingles)
        lsh = self._get_lsh(domain)
        cache = self._get_cache(domain)

        # Avoid duplicate key errors on re-indexing
        if doc_id in cache:
            try:
                lsh.remove(doc_id)
            except ValueError:
                pass

        try:
            lsh.insert(doc_id, mh)
            cache[doc_id] = mh
        except ValueError:
            # Duplicate key — already indexed
            pass

    def index_code_tokens(self, doc_id: str, tokens: List[str]) -> None:
        """
        Index a code document using its pre-computed token fingerprint sequence.
        More accurate than raw code shingles for structural similarity.
        """
        if not tokens:
            return

        shingles = _token_shingles(tokens, k=4)
        if not shingles:
            return

        mh = self._compute_minhash(shingles)
        lsh = self._code_lsh
        cache = self._code_signatures

        if doc_id in cache:
            try:
                lsh.remove(doc_id)
            except ValueError:
                pass

        try:
            lsh.insert(doc_id, mh)
            cache[doc_id] = mh
        except ValueError:
            pass

    def query_candidates(self, content: str, domain: str = "text") -> List[str]:
        """
        Query the LSH index for candidate documents similar to the given content.
        Returns a list of doc_ids that are likely similar (above the threshold).
        """
        if not content or not content.strip():
            return []

        if domain == "code":
            shingles = _text_shingles(content, k=3)
        else:
            shingles = _text_shingles(content, k=3)

        if not shingles:
            return []

        mh = self._compute_minhash(shingles)
        lsh = self._get_lsh(domain)

        try:
            return lsh.query(mh)
        except Exception:
            return []

    def query_candidates_from_tokens(self, tokens: List[str]) -> List[str]:
        """Query code LSH index using pre-computed token fingerprints."""
        if not tokens:
            return []

        shingles = _token_shingles(tokens, k=4)
        if not shingles:
            return []

        mh = self._compute_minhash(shingles)
        try:
            return self._code_lsh.query(mh)
        except Exception:
            return []

    def batch_index(self, documents: List[Dict[str, Any]], domain: str = "text",
                    id_key: str = "id", content_key: str = "content") -> int:
        """
        Bulk index a list of documents.

        Args:
            documents: List of dicts with at least id_key and content_key.
            domain: "text" or "code".
            id_key: Key for document ID in each dict.
            content_key: Key for document content in each dict.

        Returns:
            Number of documents successfully indexed.
        """
        indexed = 0
        for doc in documents:
            doc_id = doc.get(id_key, "")
            content = doc.get(content_key, "")
            if doc_id and content:
                self.index_document(doc_id, content, domain=domain)
                indexed += 1
        return indexed

    def get_all_candidate_pairs(self, domain: str = "text") -> List[Tuple[str, str]]:
        """
        Extract all candidate pairs from the LSH index.
        This is more efficient than querying each document individually
        when you need the full set of candidate pairs.
        """
        cache = self._get_cache(domain)
        lsh = self._get_lsh(domain)
        seen_pairs = set()
        pairs = []

        for doc_id, mh in cache.items():
            try:
                candidates = lsh.query(mh)
                for cand_id in candidates:
                    if cand_id != doc_id:
                        pair = tuple(sorted([doc_id, cand_id]))
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            pairs.append(pair)
            except Exception:
                continue

        return pairs

    @property
    def text_count(self) -> int:
        return len(self._text_signatures)

    @property
    def code_count(self) -> int:
        return len(self._code_signatures)
