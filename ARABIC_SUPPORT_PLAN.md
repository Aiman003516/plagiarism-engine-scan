# Arabic Plagiarism Detection — Architecture & Implementation Plan

> **Project**: Ministry Plagiarism Detection Engine  
> **Scope**: Full Arabic document and mixed Arabic-English plagiarism support  
> **Priority**: HIGH — This is a Yemeni university system. Arabic is the primary language.  
> **Date**: October 2, 2026

> [!IMPORTANT]
> **Execution Order**: This plan must be implemented **AFTER** the codebase refactoring
> (splitting `backend.py`, `db.py`, `Plagiarism.tsx`) but **BEFORE** the PostgreSQL/pgvector
> migration. Reason: Arabic support creates new files and modifies small, clean files
> (`winnowing.py`, `extractor.py`). Doing it before refactoring risks merge conflicts
> when files are moved. Doing it before Postgres is safe because Arabic preprocessing
> is pure Python logic with zero database dependency.
>
> **Full execution order:**
> 1. ✅ Bug fixes (DONE)
> 2. Codebase refactoring (split exploded files into modules)
> 3. **→ Arabic support (this plan) ←**
> 4. PostgreSQL + pgvector migration
> 5. Cloud storage migration (Supabase/S3)
> 6. Hybrid Fusion Algorithm implementation

---

## 1. Why Arabic Matters

This system is built for the Yemeni Ministry of Higher Education. The majority of
graduation projects at Ibb University and other Yemeni universities contain:
- Arabic abstracts (ملخص البحث)
- Arabic problem statements (مشكلة البحث)
- Arabic literature reviews (الدراسات السابقة)
- Mixed Arabic-English technical documents
- English source code with Arabic comments

A plagiarism engine that only detects English copying is fundamentally incomplete
for its intended audience.

---

## 2. Current State: What Works and What Doesn't

| Component | English | Arabic | Issue |
|-----------|---------|--------|-------|
| PDF Text Extraction | ✅ | ⚠️ Partial | Some Arabic PDFs reverse character order |
| DOCX Text Extraction | ✅ | ✅ Works | python-docx handles Unicode natively |
| Winnowing (Fingerprinting) | ✅ | ⚠️ Broken | Tokenizer strips diacritics, no Arabic normalization |
| CodeBERT (Code Embeddings) | ✅ | N/A | Code is always English-ish |
| BGE-M3 (Text Embeddings) | ✅ | ✅ Ready | Model supports Arabic natively, just never called with Arabic text |
| Diff Viewer (Frontend) | ✅ | ❌ Broken | LTR layout, no RTL support |
| Stop Word Removal | ✅ | ❌ Missing | Only English stop words exist |
| UI Labels & Buttons | ✅ | ⚠️ i18n exists | i18next is installed but Arabic translations are incomplete |

---

## 3. What We Need to Build

### 3.1 Arabic Text Preprocessor

Create `plagiarism_engine/arabic_preprocessor.py`:

```python
"""
Arabic-specific text preprocessing for plagiarism detection.

Handles:
- Diacritics removal (تشكيل): فَتْحَة → فتحة
- Tatweel removal (kashida): عـــربي → عربي
- Hamza normalization: إ أ آ → ا
- Taa Marbuta normalization: ة → ه (optional, configurable)
- Arabic stop words removal
- Mixed Arabic-English text segmentation
"""
import re

# Arabic diacritics (tashkeel) Unicode range
DIACRITICS = re.compile(r'[\u0617-\u061A\u064B-\u0652\u0656-\u065F\u0670]')

# Tatweel (kashida) character
TATWEEL = re.compile(r'\u0640')

# Hamza variants → bare Alef
HAMZA_MAP = str.maketrans({
    '\u0622': '\u0627',  # آ → ا
    '\u0623': '\u0627',  # أ → ا
    '\u0625': '\u0627',  # إ → ا
    '\u0671': '\u0627',  # ٱ → ا
})

# Common Arabic stop words (top 50)
ARABIC_STOP_WORDS = {
    'في', 'من', 'على', 'إلى', 'عن', 'مع', 'هذا', 'هذه', 'ذلك', 'تلك',
    'التي', 'الذي', 'هو', 'هي', 'هم', 'هن', 'أن', 'إن', 'كان', 'كانت',
    'يكون', 'تكون', 'لا', 'لم', 'لن', 'قد', 'ما', 'بعد', 'قبل', 'بين',
    'حتى', 'كل', 'بعض', 'غير', 'أو', 'ثم', 'إذا', 'لكن', 'أما', 'أي',
    'عند', 'منذ', 'حول', 'خلال', 'ضد', 'نحو', 'فوق', 'تحت', 'أمام', 'وراء',
}

def normalize_arabic(text: str) -> str:
    """Full Arabic normalization pipeline."""
    text = DIACRITICS.sub('', text)           # Remove tashkeel
    text = TATWEEL.sub('', text)              # Remove kashida
    text = text.translate(HAMZA_MAP)           # Normalize hamza
    return text

def tokenize_arabic(text: str) -> list[str]:
    """Tokenize Arabic text, removing stop words."""
    normalized = normalize_arabic(text)
    words = re.findall(r'[\u0600-\u06FF]+|[a-zA-Z]+', normalized)
    return [w for w in words if w not in ARABIC_STOP_WORDS and len(w) > 1]

def detect_language(text: str) -> str:
    """Detect if text is primarily Arabic, English, or Mixed."""
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    latin_chars = len(re.findall(r'[a-zA-Z]', text))
    total = arabic_chars + latin_chars
    if total == 0:
        return "unknown"
    arabic_ratio = arabic_chars / total
    if arabic_ratio > 0.7:
        return "arabic"
    elif arabic_ratio < 0.3:
        return "english"
    else:
        return "mixed"
```

### 3.2 Update Winnowing for Arabic

In `winnowing.py`, update `compute_text_fingerprints()`:

```python
def compute_text_fingerprints(self, text: str) -> List[Tuple[int, int]]:
    from plagiarism_engine.arabic_preprocessor import detect_language, tokenize_arabic
    from plagiarism_engine.text_detector import preprocess_text

    lang = detect_language(text)

    if lang == "arabic":
        tokens = tokenize_arabic(text)
    elif lang == "mixed":
        # Process both scripts separately, merge fingerprints
        arabic_tokens = tokenize_arabic(text)
        english_tokens = preprocess_text(text).split()
        tokens = arabic_tokens + english_tokens
    else:
        tokens = preprocess_text(text).split()

    if len(tokens) < self.k:
        fallback = self._small_file_exact_fingerprints(text)
        return fallback if fallback else []

    return self.compute_fingerprints(tokens)
```

### 3.3 Fix Arabic PDF Extraction

In `extractor.py`, add post-processing for Arabic PDFs:

```python
def extract_text_from_pdf(self, file_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        # Fix reversed Arabic text (common in some PDF generators)
        if self._is_arabic_reversed(text):
            text = self._fix_arabic_direction(text)
        pages.append(text)
    return "\n".join(pages)

@staticmethod
def _is_arabic_reversed(text: str) -> bool:
    """Detect if Arabic text was extracted in reversed order."""
    import re
    arabic_words = re.findall(r'[\u0600-\u06FF]+', text)
    if len(arabic_words) < 3:
        return False
    # Check if common Arabic sentence-starters appear at the END
    starters = {'في', 'من', 'على', 'إن', 'أن', 'هذا', 'هذه'}
    last_words = set(arabic_words[-5:])
    return bool(last_words & starters)

@staticmethod
def _fix_arabic_direction(text: str) -> str:
    """Reverse word order in lines that appear to be RTL-flipped."""
    lines = text.split('\n')
    fixed = []
    for line in lines:
        if any('\u0600' <= c <= '\u06FF' for c in line):
            words = line.split()
            fixed.append(' '.join(reversed(words)))
        else:
            fixed.append(line)
    return '\n'.join(fixed)
```

### 3.4 RTL Support in the Diff Viewer

In `frontend/src/components/DiffViewer.tsx`, add direction detection:

```tsx
// Detect if content is primarily Arabic
const isRTL = (text: string) => {
  const arabicChars = (text.match(/[\u0600-\u06FF]/g) || []).length;
  const latinChars = (text.match(/[a-zA-Z]/g) || []).length;
  return arabicChars > latinChars;
};

// In the render, apply dir="rtl" dynamically
<pre
  dir={isRTL(row.text) ? "rtl" : "ltr"}
  className="font-mono text-sm whitespace-pre-wrap"
  style={{ fontFamily: isRTL(row.text)
    ? "'Noto Sans Arabic', 'Amiri', monospace"
    : "monospace"
  }}
>
  {row.text}
</pre>
```

### 3.5 Arabic i18n for the UI

The system already has `i18next` installed. We need to add Arabic translations:

```typescript
// frontend/src/lib/i18n.tsx — add Arabic resource bundle
const resources = {
  en: { translation: { ... } },  // existing
  ar: {
    translation: {
      dashboard: "لوحة التحكم",
      projects: "المشاريع",
      plagiarism_scanner: "محرك كشف الانتحال",
      upload_project: "رفع مشروع",
      run_deep_scan: "تشغيل الفحص العميق",
      similarity: "التشابه",
      safe: "آمن",
      flagged: "مشبوه",
      high_plagiarism: "انتحال عالي",
      // ... etc
    }
  }
};
```

---

## 4. The Semantic Embedding Advantage for Arabic

BGE-M3 (the model we already have) was trained on Arabic text. This means:

| Scenario | Winnowing | BGE-M3 (Semantic) |
|----------|-----------|-------------------|
| Student copies Arabic paragraph word-for-word | ✅ Catches it | ✅ Catches it |
| Student replaces Arabic words with synonyms | ❌ Misses it | ✅ Catches it |
| Student translates English paper to Arabic | ❌ Misses it | ✅ Catches it |
| Student translates Arabic paper to English | ❌ Misses it | ✅ Catches it |
| Student copies code with Arabic comments | ✅ Catches code | ✅ Catches both |

This is why the Hybrid Fusion Algorithm is critical for Arabic. Winnowing alone
would miss most Arabic plagiarism because Arabic has extremely rich synonyms.

---

## 5. Implementation Order

| Phase | Task | Effort |
|-------|------|--------|
| A | Create `arabic_preprocessor.py` (normalization + tokenizer) | ~2 hours |
| B | Update `winnowing.py` to detect language and route to Arabic tokenizer | ~1 hour |
| C | Fix Arabic PDF extraction in `extractor.py` | ~1 hour |
| D | Add RTL support to `DiffViewer.tsx` | ~1 hour |
| E | Add Arabic i18n translations | ~2 hours |
| F | Test with real Arabic graduation projects from Ibb University | ~2 hours |

**Total estimated effort: ~9 hours**

---

## 6. Testing Strategy

1. Collect 5-10 real Arabic graduation project PDFs from Ibb University
2. Upload them through the system
3. Verify text extraction preserves Arabic correctly
4. Copy a paragraph from one project into another, upload both
5. Run Quick Scan → verify Winnowing catches the copy
6. Paraphrase the paragraph (use synonyms), upload
7. Run Deep Scan → verify BGE-M3 catches the paraphrasing
8. Open the Diff Viewer → verify RTL rendering is correct
9. Test a mixed Arabic-English document
10. Test cross-language detection (Arabic abstract vs English translation)
