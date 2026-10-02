# Phase 3 Goal: Arabic Language Support

## Objective
Add full Arabic plagiarism detection to the system — Arabic text preprocessing, Winnowing integration, PDF extraction fixes, RTL diff viewer, and Arabic UI translations.

## Context
Read `MASTER_ROADMAP.md` in this repo for the full project context. This is Phase 3 of 6.
Phase 2 (refactoring) must be completed before starting this phase.

## Tasks

### Task 1: Create `plagiarism_engine/arabic_preprocessor.py`

Build an Arabic text preprocessor with:
- `normalize_arabic(text)` — remove diacritics (tashkeel: فَتْحَة → فتحة), remove tatweel/kashida (عـــربي → عربي), normalize hamza variants (إ أ آ → ا)
- `tokenize_arabic(text)` — extract Arabic + Latin words, remove Arabic stop words (provide at least 50 common ones: في، من، على، إلى، عن، مع، هذا، هذه، etc.)
- `detect_language(text)` — return "arabic" (>70% Arabic chars), "english" (<30%), or "mixed"
- All functions must handle None/empty input gracefully
- Unicode ranges: Arabic block is `\u0600-\u06FF`, diacritics are `\u064B-\u0652`

### Task 2: Update Winnowing for Arabic

In `plagiarism_engine/winnowing.py`, modify `compute_text_fingerprints()`:
- Import `detect_language` and `tokenize_arabic` from `arabic_preprocessor`
- Auto-detect language of input text
- If Arabic → use `tokenize_arabic()` for tokenization
- If Mixed → merge Arabic tokens + English tokens
- If English → use existing `preprocess_text()` (no change)
- The small-file bypass (`if len(tokens) < self.k`) must still work for Arabic

### Task 3: Fix Arabic PDF Extraction

In `plagiarism_engine/extractor.py`:
- Add `_is_arabic_reversed(text)` static method — detect if Arabic words appear in reversed order (common in some PDF generators)
- Add `_fix_arabic_direction(text)` static method — reverse word order in Arabic lines
- Call these in the PDF extraction pipeline after `page.extract_text()`

### Task 4: RTL Diff Viewer

In the DiffViewer component (frontend):
- Add an `isRTL(text)` helper that checks if text has more Arabic chars than Latin chars
- Dynamically set `dir="rtl"` on text containers when Arabic is detected
- Add `'Noto Sans Arabic', 'Amiri'` to the font-family fallback for Arabic text
- Ensure the side-by-side comparison layout doesn't break with RTL text

### Task 5: Arabic i18n Translations

In `frontend/src/lib/i18n.tsx`:
- Add a complete `ar` translation resource bundle alongside the existing `en` bundle
- Key translations needed:
  - Dashboard: لوحة التحكم
  - Projects: المشاريع  
  - Plagiarism Scanner: محرك كشف الانتحال
  - Upload: رفع
  - Deep Scan: الفحص العميق
  - Similarity: التشابه
  - Safe: آمن
  - Flagged: مشبوه
  - Settings: الإعدادات
  - Users: المستخدمين
  - Teams: الفرق
  - Logout: تسجيل الخروج
- Add a language switcher button in the sidebar or settings page

### Task 6: Verify

1. Run `cd frontend && npx tsc --noEmit` — zero errors
2. Start backend + frontend
3. Test: upload an Arabic PDF → verify text extraction is correct
4. Test: upload two Arabic documents with copied paragraphs → run scan → verify Winnowing detects similarity
5. Test: open the Diff Viewer for Arabic results → verify RTL rendering
6. Test: switch UI to Arabic → verify all labels are translated
7. Git push

## Success Criteria
- [ ] `detect_language()` correctly identifies Arabic, English, and Mixed text
- [ ] Winnowing produces fingerprints for Arabic documents (no dead zone)
- [ ] Arabic PDF text extracts in correct reading order
- [ ] Diff Viewer renders Arabic text right-to-left
- [ ] UI can switch to Arabic language
- [ ] All existing English functionality unchanged
- [ ] Git pushed to GitHub
