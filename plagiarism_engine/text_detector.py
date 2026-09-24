import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def normalize_arabic_text(text: str) -> str:
    """
    Normalizes Arabic text by:
    - Stripping Tashkeel / Diacritics (ً ٌ ٍ َ ُ ِ ْ ّ).
    - Stripping Tatweel / Kashida (ـ).
    - Normalizing Alef variants (أ, إ, آ -> ا).
    - Normalizing Teh Marbuta (ة -> ه).
    - Normalizing Alef Maqsura (ى -> ي).
    """
    if not text:
        return ""

    text = re.sub(r'[\u064B-\u0652\u0640]', '', text)
    text = re.sub(r'[\u0622\u0623\u0625]', '\u0627', text)
    text = re.sub(r'\u0629', '\u0647', text)
    text = re.sub(r'\u0649', '\u064A', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def preprocess_text(text: str) -> str:
    """Preprocesses both Arabic and English text for similarity calculations."""
    if not text:
        return ""
    text = normalize_arabic_text(text)
    text = text.lower()
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_document_title(text: str, filename: str = "") -> str:
    """
    Extracts the document title from markdown '# Title', PDF first heading line, or filename.
    """
    if not text:
        return filename
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:5]:
        if line.startswith('#'):
            return re.sub(r'^#+\s*', '', line).strip()
        elif len(line) > 5 and len(line) < 150:
            return line
    return filename

def extract_keywords_tfidf(text: str, top_k: int = 10) -> List[str]:
    """
    Automatically extracts top K key terms/phrases from text using TF-IDF n-grams.
    """
    clean_text = preprocess_text(text)
    if not clean_text or len(clean_text) < 20:
        return []

    try:
        vectorizer = TfidfVectorizer(ngram_range=(1, 3), max_features=top_k, stop_words='english')
        vectorizer.fit([clean_text])
        features = vectorizer.get_feature_names_out()
        return list(features)
    except Exception:
        # Fallback word extraction if TF-IDF fit fails on small text
        words = re.findall(r'\w{4,}', clean_text)
        return list(set(words[:top_k]))

class TextPlagiarismDetector:
    """
    Arabic & English NLP Text Plagiarism Detector using Title, Keyword, and Full-Text TF-IDF Cosine Similarity.
    Computes a Weighted Composite Score: 30% Title + 30% Keywords + 40% Text Body.
    """

    def __init__(self, similarity_threshold: float = 0.50):
        self.similarity_threshold = similarity_threshold

    def compare_pair(self, text1: str, text2: str, title1: str = "", title2: str = "", kw1: Optional[List[str]] = None, kw2: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Calculates Weighted Composite Similarity between two texts.
        Composite Score = 30% Title + 30% Keywords + 40% Text Body.
        """
        clean1 = preprocess_text(text1)
        clean2 = preprocess_text(text2)

        if not clean1 or not clean2:
            return {"similarity": 0.0, "similarity_percentage": "0%", "is_plagiarized": False}

        # 1. Title Similarity
        t1 = preprocess_text(title1) if title1 else preprocess_text(extract_document_title(text1))
        t2 = preprocess_text(title2) if title2 else preprocess_text(extract_document_title(text2))
        
        if t1 and t2:
            t_vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
            t_mat = t_vec.fit_transform([t1, t2])
            title_score = float(cosine_similarity(t_mat[0:1], t_mat[1:2])[0][0])
        else:
            title_score = 0.0

        # 2. Keyword Similarity
        k1_list = kw1 if kw1 else extract_keywords_tfidf(text1, top_k=10)
        k2_list = kw2 if kw2 else extract_keywords_tfidf(text2, top_k=10)
        
        k1_str = " ".join(k1_list)
        k2_str = " ".join(k2_list)
        
        if k1_str and k2_str:
            k_vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
            k_mat = k_vec.fit_transform([k1_str, k2_str])
            kw_score = float(cosine_similarity(k_mat[0:1], k_mat[1:2])[0][0])
        else:
            kw_score = 0.0

        # 3. Body Text Similarity
        vectorizer = TfidfVectorizer(ngram_range=(2, 4), analyzer='char_wb')
        tfidf_matrix = vectorizer.fit_transform([clean1, clean2])
        body_score = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])

        # Weighted Composite Score calculation
        composite_score = round((0.30 * title_score) + (0.30 * kw_score) + (0.40 * body_score), 4)

        return {
            "similarity": composite_score,
            "similarity_percentage": f"{round(composite_score * 100, 2)}%",
            "is_plagiarized": composite_score >= self.similarity_threshold,
            "threshold": self.similarity_threshold,
            "title_score": round(title_score, 4),
            "keyword_score": round(kw_score, 4),
            "body_score": round(body_score, 4),
            "keywords_doc1": k1_list,
            "keywords_doc2": k2_list
        }

    def batch_compare(
        self, 
        documents: List[Dict[str, Any]], 
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Pairwise TF-IDF cosine similarity across a corpus of documents with Title & Keyword weighting.
        """
        eff_threshold = threshold if threshold is not None else self.similarity_threshold
        if len(documents) < 2:
            return []

        results = []
        num_docs = len(documents)
        
        for i in range(num_docs):
            doc1 = documents[i]
            for j in range(i + 1, num_docs):
                doc2 = documents[j]
                
                res = self.compare_pair(
                    text1=doc1.get('content', ''),
                    text2=doc2.get('content', ''),
                    title1=doc1.get('title', doc1.get('filename', '')),
                    title2=doc2.get('title', doc2.get('filename', '')),
                    kw1=doc1.get('keywords'),
                    kw2=doc2.get('keywords')
                )

                score = res['similarity']
                results.append({
                    "doc1_id": doc1.get('id', f"doc_{i}"),
                    "doc1_name": doc1.get('filename', f"doc_{i}"),
                    "doc2_id": doc2.get('id', f"doc_{j}"),
                    "doc2_name": doc2.get('filename', f"doc_{j}"),
                    "similarity": score,
                    "similarity_percentage": res['similarity_percentage'],
                    "title_score": res['title_score'],
                    "keyword_score": res['keyword_score'],
                    "body_score": res['body_score'],
                    "is_plagiarized": score >= eff_threshold,
                    "threshold": eff_threshold
                })

        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results

    @staticmethod
    def _resolve_file_type(file_rec: Dict[str, Any]) -> str:
        """
        Safely resolve file_type from the record, falling back to extension-based
        categorization when file_type is None or missing.
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

    def scan_text_files(
        self,
        files1: List[Dict[str, Any]],
        files2: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Optimized batch text scanning between two sets of files.
        Vectorizes all documents at once to guarantee fast execution.
        """
        # Filter to only text files and valid content (with safe file_type re-derivation)
        t1 = [f for f in files1 if self._resolve_file_type(f) == 'text' and f.get('content', '').strip()]
        t2 = [f for f in files2 if self._resolve_file_type(f) == 'text' and f.get('content', '').strip()]
        
        if not t1 or not t2:
            return []
            
        all_docs = t1 + t2
        num_t1 = len(t1)
        
        # 1. Preprocess everything
        clean_bodies = [preprocess_text(f.get('content', '')) for f in all_docs]
        titles = [preprocess_text(f.get('title', f.get('filename', ''))) or extract_document_title(f.get('content', '')) for f in all_docs]
        keywords_list = [extract_keywords_tfidf(f.get('content', '')) for f in all_docs]
        k_strings = [" ".join(kw) for kw in keywords_list]
        
        # 2. Vectorize Titles (Once)
        t_vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
        try:
            t_mat = t_vec.fit_transform(titles)
            t_sim_matrix = cosine_similarity(t_mat[:num_t1], t_mat[num_t1:])
        except ValueError:
            t_sim_matrix = np.zeros((num_t1, len(t2)))
            
        # 3. Vectorize Keywords (Once)
        k_vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
        try:
            k_mat = k_vec.fit_transform(k_strings)
            k_sim_matrix = cosine_similarity(k_mat[:num_t1], k_mat[num_t1:])
        except ValueError:
            k_sim_matrix = np.zeros((num_t1, len(t2)))
            
        # 4. Vectorize Body (Once)
        b_vec = TfidfVectorizer(ngram_range=(2, 4), analyzer='char_wb')
        try:
            b_mat = b_vec.fit_transform(clean_bodies)
            b_sim_matrix = cosine_similarity(b_mat[:num_t1], b_mat[num_t1:])
        except ValueError:
            b_sim_matrix = np.zeros((num_t1, len(t2)))
            
        # 5. Compute Composite Scores
        comp_matrix = (0.30 * t_sim_matrix) + (0.30 * k_sim_matrix) + (0.40 * b_sim_matrix)
        
        # 6. Extract matches
        matches = []
        for i in range(num_t1):
            for j in range(len(t2)):
                score = round(float(comp_matrix[i, j]), 4)
                if score >= self.similarity_threshold:
                    matches.append({
                        "file1": t1[i].get('relative_path', t1[i].get('filename', '')),
                        "file2": t2[j].get('relative_path', t2[j].get('filename', '')),
                        "similarity": score,
                        "similarity_percentage": f"{round(score * 100, 2)}%",
                        "is_plagiarized": True,
                        "title_score": round(float(t_sim_matrix[i, j]), 4),
                        "keyword_score": round(float(k_sim_matrix[i, j]), 4),
                        "body_score": round(float(b_sim_matrix[i, j]), 4),
                        "keywords_doc1": keywords_list[i],
                        "keywords_doc2": keywords_list[num_t1 + j]
                    })
                    
        # Sort by similarity descending
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches

    def scan_text_files_at_scale(
        self,
        files1: List[Dict[str, Any]],
        files2: List[Dict[str, Any]],
        progress_callback=None
    ) -> List[Dict[str, Any]]:
        """
        Scalable text plagiarism scanner using MinHash + LSH for candidate discovery.
        Reduces O(N²) pairwise TF-IDF cosine to O(N) MinHash indexing + O(K) verification.
        Designed for corpora of 100K+ documents without RAM overflow.

        Architecture:
            Tier 1 (MinHash + LSH): Index all docs, discover candidate pairs in O(N).
            Tier 2 (TF-IDF Cosine): Run precise weighted composite only on candidate pairs.
        """
        from plagiarism_engine.minhash_index import MinHashLSHIndex

        # 1. Filter text files with safe file_type re-derivation
        t1 = [f for f in files1 if self._resolve_file_type(f) == 'text' and f.get('content', '').strip()]
        t2 = [f for f in files2 if self._resolve_file_type(f) == 'text' and f.get('content', '').strip()]

        if not t1 or not t2:
            return []

        # 2. Build MinHash LSH Index from file set 2 (the reference corpus)
        lsh_index = MinHashLSHIndex(
            threshold=max(0.25, self.similarity_threshold - 0.25),
            num_perm=128
        )

        if progress_callback:
            progress_callback(f"   -> Indexing {len(t2)} reference text documents into MinHash LSH...")

        # Index all reference documents
        t2_by_key = {}
        for f in t2:
            key = f.get('relative_path', f.get('filename', ''))
            content = f.get('content', '')
            t2_by_key[key] = f
            lsh_index.index_document(key, content, domain="text")

        # 3. For each document in set 1, query LSH for candidates, then verify
        matches = []
        total_candidates = 0

        for f1 in t1:
            key1 = f1.get('relative_path', f1.get('filename', ''))
            content1 = f1.get('content', '')

            if progress_callback:
                progress_callback(f"   -> LSH querying candidates for {f1.get('filename', '')}...")

            # Tier 1: LSH candidate discovery
            candidate_keys = lsh_index.query_candidates(content1, domain="text")
            total_candidates += len(candidate_keys)

            # Tier 2: Precise verification only on candidates
            for key2 in candidate_keys:
                if key2 not in t2_by_key:
                    continue

                f2 = t2_by_key[key2]
                result = self.compare_pair(
                    text1=content1,
                    text2=f2.get('content', ''),
                    title1=f1.get('title', f1.get('filename', '')),
                    title2=f2.get('title', f2.get('filename', '')),
                    kw1=f1.get('keywords'),
                    kw2=f2.get('keywords')
                )

                score = result['similarity']
                if score >= self.similarity_threshold:
                    matches.append({
                        "file1": key1,
                        "file2": key2,
                        "similarity": score,
                        "similarity_percentage": result['similarity_percentage'],
                        "is_plagiarized": True,
                        "title_score": result['title_score'],
                        "keyword_score": result['keyword_score'],
                        "body_score": result['body_score'],
                        "keywords_doc1": result['keywords_doc1'],
                        "keywords_doc2": result['keywords_doc2']
                    })

        if progress_callback:
            progress_callback(
                f"   -> MinHash LSH reduced search space to {total_candidates} candidate pairs "
                f"(from {len(t1) * len(t2)} brute-force pairs)"
            )

        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches

