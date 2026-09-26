import hashlib
from typing import List, Tuple, Set

class WinnowingEngine:
    """
    Winnowing algorithm for document fingerprinting (Schleimer et al., 2003).
    Guarantees detection of shared substrings of length >= threshold (t = k + w - 1).
    """

    def __init__(self, k: int = 15, w: int = 10):
        self.k = k  # k-gram size
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

    def compute_code_fingerprints(self, code_text: str, filename: str) -> List[Tuple[int, int]]:
        """
        Tokenize code using Pygments fingerprinting, then winnow.
        """
        from plagiarism_engine.code_detector import CodePlagiarismDetector
        tokens = CodePlagiarismDetector.get_token_fingerprint(code_text, filename)
        return self.compute_fingerprints(tokens)

    def compute_text_fingerprints(self, text: str) -> List[Tuple[int, int]]:
        """
        Normalize and word-tokenize text, then winnow. 
        For text, we typically use slightly larger k and w, but we'll stick to the defaults 
        or allow overrides via instance initialization.
        """
        from plagiarism_engine.text_detector import preprocess_text
        words = preprocess_text(text).split()
        return self.compute_fingerprints(words)

    @staticmethod
    def jaccard_similarity(fp1: Set[int], fp2: Set[int]) -> float:
        """Jaccard coefficient between two fingerprint sets."""
        if not fp1 or not fp2:
            return 0.0
        intersection = len(fp1 & fp2)
        union = len(fp1 | fp2)
        return float(intersection) / union
