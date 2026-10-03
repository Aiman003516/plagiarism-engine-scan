import hashlib
from typing import List, Tuple, Set

class WinnowingEngine:
    """
    Winnowing algorithm for document fingerprinting (Schleimer et al., 2003).
    Guarantees detection of shared substrings of length >= threshold (t = k + w - 1).
    """

    def __init__(self, k: int = 50, w: int = 10):
        self.k = k  # k-gram size (50: larger k-grams suppress false positives on small files)
        self.w = w  # window size

    def _hash(self, kgram: str) -> int:
        """Create a 60-bit hash for a k-gram."""
        # Use 15 hex characters (60 bits) to fit safely inside PostgreSQL's signed BIGINT (max ~9.2e18).
        # 16 hex chars (64 bits) creates unsigned integers that exceed PostgreSQL's BIGINT max.
        return int(hashlib.md5(kgram.encode('utf-8')).hexdigest()[:15], 16)

    def compute_fingerprints(self, token_sequence: List[str]) -> List[Tuple[int, int]]:
        """
        Returns a list of (hash_value, position) fingerprints.
        """
        if len(token_sequence) < self.k:
            return []

        # 1. Generate k-grams and their hashes
        hashes = []
        for i in range(len(token_sequence) - self.k + 1):
            kgram = "\x00".join(token_sequence[i : i + self.k])
            hashes.append((self._hash(kgram), i))

        if not hashes:
            return []

        # 2. Slide window of size w and pick minimum hash per window (Winnowing)
        fingerprints = []
        # Keep track of the previously selected fingerprint to avoid duplicates from overlapping windows
        last_selected_pos = -1

        for i in range(len(hashes) - self.w + 1):
            window = hashes[i : i + self.w]
            # Find minimum hash in the window. If tied, pick the rightmost one.
            min_hash, min_pos = min(window, key=lambda x: (x[0], -x[1]))

            if min_pos != last_selected_pos:
                fingerprints.append((min_hash, min_pos))
                last_selected_pos = min_pos

        return fingerprints

    def _small_file_exact_fingerprints(self, text: str) -> List[Tuple[int, int]]:
        """
        Small File Exact Match Bypass.

        Documents that carry too little content for k-gram/winnowing statistics
        to be meaningful — sparse, low-entropy fingerprints caused false-positive
        matches on boilerplate and tiny snippets. Such files are instead hashed as
        ONE exact-match fingerprint over the entire normalized text, so two small
        files only match when their normalized content is identical.

        This method ALWAYS produces fingerprints when called. The decision of WHEN
        to use it belongs to the callers (compute_code_fingerprints /
        compute_text_fingerprints), which trigger it based on the document's TOKEN
        count rather than its line count — Winnowing operates on tokens, so the
        bypass must be measured in tokens too.

        Returns:
            [(hash, 0)] -> exact-match fingerprint over the whole document
            []          -> document with no alphanumeric content at all
        """
        # File is too small for statistical hashing. Hash the entire normalized
        # text as one single exact-match fingerprint.
        normalized = ''.join(filter(str.isalnum, (text or '').lower()))
        if not normalized:
            return []
        exact_hash = int(hashlib.md5(normalized.encode('utf-8')).hexdigest(), 16) % (2**32)
        return [(exact_hash, 0)]

    def compute_code_fingerprints(self, code_text: str, filename: str) -> List[Tuple[int, int]]:
        """
        Tokenize code using Pygments fingerprinting, then winnow.
        Files with fewer than k tokens take the exact-match bypass, because
        Winnowing operates on tokens (not lines) and a k-gram cannot be formed
        from fewer than k tokens.
        """
        from plagiarism_engine.code_detector import CodePlagiarismDetector
        tokens = CodePlagiarismDetector.get_token_fingerprint(code_text, filename)

        if len(tokens) < self.k:
            # Too few tokens for statistical k-gram hashing.
            # Fall back to whole-file exact-match to avoid false positives
            # AND to avoid producing zero fingerprints (dead zone).
            fallback = self._small_file_exact_fingerprints(code_text)
            return fallback if fallback else []

        return self.compute_fingerprints(tokens)

    def compute_text_fingerprints(self, text: str) -> List[Tuple[int, int]]:
        """
        Normalize and word-tokenize text, then winnow. 
        For text, we typically use slightly larger k and w, but we'll stick to the defaults 
        or allow overrides via instance initialization.
        Documents with fewer than k words take the exact-match bypass, because
        Winnowing operates on tokens (not lines) and a k-gram cannot be formed
        from fewer than k tokens.
        """
        from plagiarism_engine.text_detector import preprocess_text
        from plagiarism_engine.arabic_preprocessor import detect_language, tokenize_arabic
        
        lang = detect_language(text)
        if lang == "arabic":
            tokens = tokenize_arabic(text)
        elif lang == "mixed":
            tokens = tokenize_arabic(text) + preprocess_text(text).split()
        else:
            tokens = preprocess_text(text).split()

        if len(tokens) < self.k:
            # Too few tokens for statistical k-gram hashing.
            # Fall back to whole-file exact-match to avoid false positives
            # AND to avoid producing zero fingerprints (dead zone).
            fallback = self._small_file_exact_fingerprints(text)
            return fallback if fallback else []

        return self.compute_fingerprints(tokens)

    @staticmethod
    def jaccard_similarity(fp1: Set[int], fp2: Set[int]) -> float:
        """Jaccard coefficient between two fingerprint sets."""
        if not fp1 or not fp2:
            return 0.0
        intersection = len(fp1 & fp2)
        union = len(fp1 | fp2)
        return float(intersection) / union
