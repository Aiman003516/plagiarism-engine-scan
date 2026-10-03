"""
Arabic text preprocessing for plagiarism detection.
- Diacritics removal (تشكيل): فَتْحَة → فتحة
- Tatweel removal (kashida): عـــربي → عربي
- Hamza normalization: إ أ آ → ا
- Arabic stop words removal
- Language auto-detection (Arabic / English / Mixed)
"""
import re

DIACRITICS = re.compile(r'[\u0617-\u061A\u064B-\u0652\u0656-\u065F\u0670]')
TATWEEL = re.compile(r'\u0640')
HAMZA_MAP = str.maketrans({
    '\u0622': '\u0627', '\u0623': '\u0627',
    '\u0625': '\u0627', '\u0671': '\u0627',
})

ARABIC_STOP_WORDS = {
    'في', 'من', 'على', 'إلى', 'عن', 'مع', 'هذا', 'هذه', 'ذلك', 'تلك',
    'التي', 'الذي', 'هو', 'هي', 'هم', 'هن', 'أن', 'إن', 'كان', 'كانت',
    'يكون', 'تكون', 'لا', 'لم', 'لن', 'قد', 'ما', 'بعد', 'قبل', 'بين',
    'حتى', 'كل', 'بعض', 'غير', 'أو', 'ثم', 'إذا', 'لكن', 'أما', 'أي',
    'عند', 'منذ', 'حول', 'خلال', 'ضد', 'نحو', 'فوق', 'تحت', 'أمام', 'وراء',
}

def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    text = DIACRITICS.sub('', text)
    text = TATWEEL.sub('', text)
    text = text.translate(HAMZA_MAP)
    return text

def tokenize_arabic(text: str) -> list[str]:
    if not text:
        return []
    normalized = normalize_arabic(text)
    words = re.findall(r'[\u0600-\u06FF]+|[a-zA-Z]+', normalized)
    return [w for w in words if w not in ARABIC_STOP_WORDS and len(w) > 1]

def detect_language(text: str) -> str:
    if not text:
        return "unknown"
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    latin_chars = len(re.findall(r'[a-zA-Z]', text))
    total = arabic_chars + latin_chars
    if total == 0: return "unknown"
    ratio = arabic_chars / total
    if ratio > 0.7: return "arabic"
    elif ratio < 0.3: return "english"
    else: return "mixed"
