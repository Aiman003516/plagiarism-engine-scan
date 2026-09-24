import ast
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Callable
from difflib import SequenceMatcher

import pygments
from pygments.lexers import get_lexer_for_filename, guess_lexer, TextLexer
from pygments.token import Token

class CodePlagiarismDetector:
    """
    Multi-language Code Plagiarism Detector supporting:
    1. Lexical Pygments Token Fingerprinting (Variable/Comment/Literal stripping).
    2. Python AST Structural Representation Mode.
    3. Pairwise sequence similarity matching with high-performance length capping.
    """

    def __init__(self, similarity_threshold: float = 0.65):
        self.similarity_threshold = similarity_threshold

    @staticmethod
    def get_token_fingerprint(code_text: str, filename: Optional[str] = None) -> List[str]:
        """
        Tokenizes source code into abstract structural tokens.
        Strips variable names, literal constants, comments, and whitespace.
        """
        if not code_text or not code_text.strip():
            return []

        try:
            if filename:
                lexer = get_lexer_for_filename(filename, stripall=True)
            else:
                lexer = guess_lexer(code_text)
        except Exception:
            lexer = TextLexer(stripall=True)

        tokens = pygments.lex(code_text, lexer)
        fingerprint = []

        for toktype, value in tokens:
            if toktype in Token.Text or toktype in Token.Comment:
                continue

            if toktype in Token.Keyword:
                fingerprint.append(f"K:{value}")
            elif toktype in Token.Operator:
                fingerprint.append(f"O:{value}")
            elif toktype in Token.Name:
                fingerprint.append("ID")
            elif toktype in Token.Literal.String:
                fingerprint.append("STR")
            elif toktype in Token.Literal.Number:
                fingerprint.append("NUM")
            elif toktype in Token.Punctuation:
                fingerprint.append(f"P:{value}")
            else:
                fingerprint.append("TOK")

        return fingerprint

    @staticmethod
    def get_python_ast_fingerprint(code_text: str) -> List[str]:
        """
        Parses Python source code into Abstract Syntax Tree (AST) node sequence.
        Normalizes variable names, docstrings, and function names into generic AST structures.
        """
        if not code_text or not code_text.strip():
            return []

        try:
            tree = ast.parse(code_text)
            ast_tokens = [type(node).__name__ for node in ast.walk(tree)]
            return ast_tokens
        except SyntaxError:
            return CodePlagiarismDetector.get_token_fingerprint(code_text, filename="temp.py")

    @staticmethod
    def compute_neural_code_similarity(code1: str, code2: str) -> Optional[float]:
        """
        Computes semantic vector cosine similarity using CodeBERT neural embeddings.
        Returns float between 0.0 and 1.0, or None if neural models are unavailable.
        """
        try:
            from plagiarism_engine.vector_store import model_pool
            model = model_pool.get_model("code") or model_pool.get_model("minilm")
            if not model or not code1.strip() or not code2.strip():
                return None
            import numpy as np
            emb1 = model.encode(code1[:4000], convert_to_numpy=True)
            emb2 = model.encode(code2[:4000], convert_to_numpy=True)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            cosine = float(np.dot(emb1, emb2) / (norm1 * norm2))
            return max(0.0, min(1.0, round(cosine, 4)))
        except Exception:
            return None

    def compare_code(
        self, 
        code1: str, 
        code2: str, 
        filename1: Optional[str] = None, 
        filename2: Optional[str] = None,
        use_ast: bool = False,
        use_neural: bool = True
    ) -> Dict[str, Any]:
        """
        Compares two code snippets and returns a hybrid composite similarity score:
        Composite Score = 0.5 * (AST Structural Ratio) + 0.5 * (CodeBERT Neural Cosine Sim)
        """
        if use_ast or (filename1 and filename1.endswith('.py') and filename2 and filename2.endswith('.py')):
            fp1 = self.get_python_ast_fingerprint(code1)
            fp2 = self.get_python_ast_fingerprint(code2)
            mode = "Python AST Structure"
        else:
            fp1 = self.get_token_fingerprint(code1, filename1)
            fp2 = self.get_token_fingerprint(code2, filename2)
            mode = "Token Structural Fingerprint"

        if not fp1 or not fp2:
            return {
                "similarity": 0.0,
                "similarity_percentage": "0.0%",
                "ast_similarity": 0.0,
                "neural_similarity": 0.0,
                "is_plagiarized": False,
                "mode": mode,
                "tokens_count_1": len(fp1),
                "tokens_count_2": len(fp2)
            }

        # Fast ratio sanity check before full block alignment
        len1, len2 = len(fp1), len(fp2)
        if len1 > 4 * len2 or len2 > 4 * len1:
            return {
                "similarity": 0.0,
                "similarity_percentage": "0.0%",
                "ast_similarity": 0.0,
                "neural_similarity": 0.0,
                "is_plagiarized": False,
                "mode": mode,
                "tokens_count_1": len1,
                "tokens_count_2": len2
            }

        # Cap token sequences to 1500 max tokens to guarantee O(N^2) safety on giant monorepo files
        fp1_sample = fp1[:1500]
        fp2_sample = fp2[:1500]

        matcher = SequenceMatcher(None, fp1_sample, fp2_sample)
        ast_similarity = round(float(matcher.ratio()), 4)

        # Compute CodeBERT neural semantic similarity
        neural_sim = None
        if use_neural:
            neural_sim = self.compute_neural_code_similarity(code1, code2)

        if neural_sim is not None:
            similarity = round(0.5 * ast_similarity + 0.5 * neural_sim, 4)
            full_mode = f"{mode} + CodeBERT Neural Hybrid"
        else:
            similarity = ast_similarity
            full_mode = mode

        is_plagiarized = similarity >= self.similarity_threshold

        return {
            "similarity": similarity,
            "similarity_percentage": f"{round(similarity * 100, 2)}%",
            "ast_similarity": ast_similarity,
            "neural_similarity": neural_sim if neural_sim is not None else 0.0,
            "is_plagiarized": is_plagiarized,
            "threshold": self.similarity_threshold,
            "mode": full_mode,
            "tokens_count_1": len1,
            "tokens_count_2": len2
        }

    @staticmethod
    def _resolve_file_type(file_rec: Dict[str, Any]) -> str:
        """
        Safely resolve file_type from the record, falling back to extension-based
        categorization when file_type is None or missing. Prevents silent data loss
        where files with missing types are dropped from both code and text scanners.
        """
        from plagiarism_engine.extractor import CODE_EXTENSIONS, TEXT_EXTENSIONS
        ft = file_rec.get('file_type')
        if ft:
            return ft
        ext = Path(file_rec.get('filename', '')).suffix.lower()
        if ext in CODE_EXTENSIONS:
            return 'code'
        elif ext in TEXT_EXTENSIONS:
            return 'text'
        return 'text'

    def scan_code_files(
        self, 
        files1: List[Dict[str, Any]], 
        files2: List[Dict[str, Any]], 
        use_ast: bool = False,
        cross_language: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Pairwise multi-file project code plagiarism scanner.
        Compares matching extension code files in Project 1 against Project 2.
        Precomputes token fingerprints to eliminate $O(N \\times M)$ lexical parsing bottlenecks.
        
        Args:
            cross_language: When True, skip extension matching and compare all code files
                            against each other using structural fingerprinting. This catches
                            students who translate algorithms between languages (e.g. Python → Java).
        """
        matches = []
        
        # 1. Filter code files only (with safe file_type re-derivation)
        c1 = [f for f in files1 if self._resolve_file_type(f) == 'code' and f.get('content', '').strip()]
        c2 = [f for f in files2 if self._resolve_file_type(f) == 'code' and f.get('content', '').strip()]
        
        if not c1 or not c2:
            return []
            
        # 2. Pre-compute fingerprints for all files in Project 1
        fp1_cache = {}
        for f in c1:
            fn = f.get('filename', '')
            is_py = fn.endswith('.py')
            if use_ast or is_py:
                fp = self.get_python_ast_fingerprint(f['content'])
                mode = "Python AST Structure"
            else:
                fp = self.get_token_fingerprint(f['content'], fn)
                mode = "Token Structural Fingerprint"
            # Cap at 1500 directly in cache to save memory
            fp1_cache[f.get('relative_path', fn)] = {"fp": fp[:1500] if fp else [], "mode": mode}

        # 3. Pre-compute fingerprints for all files in Project 2
        fp2_cache = {}
        for f in c2:
            fn = f.get('filename', '')
            is_py = fn.endswith('.py')
            if use_ast or is_py:
                fp = self.get_python_ast_fingerprint(f['content'])
                mode = "Python AST Structure"
            else:
                fp = self.get_token_fingerprint(f['content'], fn)
                mode = "Token Structural Fingerprint"
            fp2_cache[f.get('relative_path', fn)] = {"fp": fp[:1500] if fp else [], "mode": mode}

        # 4. Perform lightweight pairwise SequenceMatcher loop with quick_ratio() pre-filter
        for f1 in c1:
            if progress_callback:
                progress_callback(f"   -> Comparing {f1.get('filename', '')} against {len(c2)} files...")
                
            ext1 = f1.get('extension', '').lower()
            fp1_data = fp1_cache[f1.get('relative_path', f1.get('filename', ''))]
            fp1_toks = fp1_data['fp']
            
            for f2 in c2:
                ext2 = f2.get('extension', '').lower()
                
                # Only compare matching extensions (skip if cross-language mode is enabled)
                if not cross_language and ext1 and ext2 and ext1 != ext2:
                    continue
                    
                fp2_data = fp2_cache[f2.get('relative_path', f2.get('filename', ''))]
                fp2_toks = fp2_data['fp']
                
                if not fp1_toks or not fp2_toks:
                    continue
                    
                len1, len2 = len(fp1_toks), len(fp2_toks)
                if len1 > 4 * len2 or len2 > 4 * len1:
                    continue

                matcher = SequenceMatcher(None, fp1_toks, fp2_toks)
                
                # Priority 4: quick_ratio() pre-filter — eliminates ~70% of obviously
                # dissimilar pairs before the expensive full LCS computation
                quick = matcher.quick_ratio()
                if quick < self.similarity_threshold - 0.15:
                    continue
                    
                similarity = round(float(matcher.ratio()), 4)
                
                if similarity >= self.similarity_threshold:
                    matches.append({
                        "file1": f1.get('relative_path', f1.get('filename', '')),
                        "file2": f2.get('relative_path', f2.get('filename', '')),
                        "similarity": similarity,
                        "similarity_percentage": f"{round(similarity * 100, 2)}%",
                        "mode": fp1_data['mode']
                    })

        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches

    def scan_code_files_at_scale(
        self,
        files1: List[Dict[str, Any]],
        files2: List[Dict[str, Any]],
        use_ast: bool = False,
        cross_language: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Scalable code plagiarism scanner using MinHash + LSH for candidate discovery.
        Reduces O(N²) pairwise comparison to O(N) indexing + O(K) verification,
        where K << N². Designed for corpora of 100K+ files.

        Architecture:
            Tier 1 (MinHash + LSH): Index all files, discover candidate pairs in O(N).
            Tier 2 (SequenceMatcher): Run precise comparison only on candidate pairs.
        """
        from plagiarism_engine.minhash_index import MinHashLSHIndex

        # 1. Filter code files with safe file_type re-derivation
        c1 = [f for f in files1 if self._resolve_file_type(f) == 'code' and f.get('content', '').strip()]
        c2 = [f for f in files2 if self._resolve_file_type(f) == 'code' and f.get('content', '').strip()]

        if not c1 or not c2:
            return []

        # 2. Build MinHash LSH Index from Project 2 (the reference corpus)
        lsh_index = MinHashLSHIndex(threshold=max(0.3, self.similarity_threshold - 0.2), num_perm=128)

        if progress_callback:
            progress_callback(f"   -> Indexing {len(c2)} reference files into MinHash LSH...")

        # Pre-compute fingerprints for Project 2 and index them
        fp2_cache = {}
        for f in c2:
            fn = f.get('filename', '')
            key = f.get('relative_path', fn)
            is_py = fn.endswith('.py')
            if use_ast or is_py:
                fp = self.get_python_ast_fingerprint(f['content'])
                mode = "Python AST Structure"
            else:
                fp = self.get_token_fingerprint(f['content'], fn)
                mode = "Token Structural Fingerprint"
            capped = fp[:1500] if fp else []
            fp2_cache[key] = {"fp": capped, "mode": mode, "rec": f}

            # Index into LSH using token fingerprint shingles
            if capped:
                lsh_index.index_code_tokens(key, capped)

        # 3. Pre-compute fingerprints for Project 1
        fp1_cache = {}
        for f in c1:
            fn = f.get('filename', '')
            key = f.get('relative_path', fn)
            is_py = fn.endswith('.py')
            if use_ast or is_py:
                fp = self.get_python_ast_fingerprint(f['content'])
                mode = "Python AST Structure"
            else:
                fp = self.get_token_fingerprint(f['content'], fn)
                mode = "Token Structural Fingerprint"
            fp1_cache[key] = {"fp": fp[:1500] if fp else [], "mode": mode, "rec": f}

        # 4. For each file in Project 1, query LSH for candidate matches
        matches = []
        total_candidates = 0

        for key1, data1 in fp1_cache.items():
            fp1_toks = data1['fp']
            if not fp1_toks:
                continue

            ext1 = data1['rec'].get('extension', '').lower()

            if progress_callback:
                progress_callback(f"   -> LSH querying candidates for {data1['rec'].get('filename', '')}...")

            # Tier 1: LSH candidate discovery
            candidate_keys = lsh_index.query_candidates_from_tokens(fp1_toks)
            total_candidates += len(candidate_keys)

            # Tier 2: Precise verification only on candidates
            for key2 in candidate_keys:
                if key2 not in fp2_cache:
                    continue

                data2 = fp2_cache[key2]
                fp2_toks = data2['fp']

                if not fp2_toks:
                    continue

                # Extension filter (skip if cross-language enabled)
                if not cross_language:
                    ext2 = data2['rec'].get('extension', '').lower()
                    if ext1 and ext2 and ext1 != ext2:
                        continue

                # Length ratio sanity check
                len1, len2 = len(fp1_toks), len(fp2_toks)
                if len1 > 4 * len2 or len2 > 4 * len1:
                    continue

                matcher = SequenceMatcher(None, fp1_toks, fp2_toks)

                # quick_ratio() pre-filter
                if matcher.quick_ratio() < self.similarity_threshold - 0.15:
                    continue

                similarity = round(float(matcher.ratio()), 4)

                if similarity >= self.similarity_threshold:
                    matches.append({
                        "file1": key1,
                        "file2": key2,
                        "similarity": similarity,
                        "similarity_percentage": f"{round(similarity * 100, 2)}%",
                        "mode": data1['mode']
                    })

        if progress_callback:
            progress_callback(f"   -> MinHash LSH reduced search space to {total_candidates} candidate pairs (from {len(c1) * len(c2)} brute-force pairs)")

        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches
