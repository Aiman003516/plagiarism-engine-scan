import os
import re
import warnings
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import pypdf
import docx

from plagiarism_engine.file_policy import (
    CODE_EXTENSIONS,
    TEXT_EXTENSIONS,
    BINARY_EXTENSIONS,
    IGNORED_DIR_NAMES,
    CONFIG_FILENAMES,
    TEMPLATE_FILENAMES,
    MAX_SOURCE_BYTES,
    MAX_DOCUMENT_BYTES,
    BINARY_DOCUMENT_EXTENSIONS,
    is_scannable,
    file_type_for,
)

# Backward-compatible aliases (importers: scripts/real_corpus_eval.py and others). The lists
# themselves live in plagiarism_engine/file_policy.py; directory names are compared lower-case.
DEFAULT_IGNORE_DIRS = IGNORED_DIR_NAMES
DEFAULT_IGNORE_FILES = CONFIG_FILENAMES | TEMPLATE_FILENAMES

def sanitize_text(text: str) -> str:
    """Removes NUL (0x00) characters and invalid unicode bytes for PostgreSQL compatibility."""
    if not text:
        return ""
    return text.replace('\x00', '')

class FileExtractor:
    """Extracts text/code from files and project directories with encoding fallbacks and directory/config filtering."""

    @staticmethod
    def _is_arabic_reversed(text: str) -> bool:
        """Detect if Arabic words appear in reversed order (e.g. ending in 'لا' instead of starting with 'ال')."""
        words = re.findall(r'[\u0600-\u06FF]+', text)
        if not words: return False
        al_prefix = sum(1 for w in words if w.startswith('ال'))
        la_suffix = sum(1 for w in words if w.endswith('لا'))
        # If 'لا' suffix is significantly more common than 'ال' prefix, it's likely reversed
        return la_suffix > al_prefix and la_suffix >= 1

    @staticmethod
    def _fix_arabic_direction(text: str) -> str:
        """Reverse character order in Arabic lines to fix visual RTL extraction while preserving LTR Latin/numeric tokens."""
        lines = text.split('\n')
        fixed_lines = []
        for line in lines:
            if re.search(r'[\u0600-\u06FF]', line):
                # Reverse the whole visual line so RTL words and characters are restored to logical order,
                # then flip back any embedded LTR Latin/number tokens so e.g. 'nohtyP' stays 'Python'.
                rev_line = line[::-1]
                rev_line = re.sub(r'[a-zA-Z0-9_.\-]+', lambda m: m.group(0)[::-1], rev_line)
                fixed_lines.append(rev_line)
            else:
                fixed_lines.append(line)
        return '\n'.join(fixed_lines)

    @staticmethod
    def extract_text_from_pdf(pdf_path: Union[str, Path]) -> str:
        """Extract text from a PDF file using pypdf."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        text_chunks = []
        try:
            with open(pdf_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page_num, page in enumerate(reader.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            if FileExtractor._is_arabic_reversed(page_text):
                                page_text = FileExtractor._fix_arabic_direction(page_text)
                            text_chunks.append(page_text)
                    except Exception:
                        continue
        except Exception:
            return ""
        return sanitize_text("\n".join(text_chunks))

    @staticmethod
    def extract_text_from_docx(docx_path: Union[str, Path]) -> str:
        """Extract text from a Word document (.docx) using python-docx."""
        docx_path = Path(docx_path)
        if not docx_path.exists():
            raise FileNotFoundError(f"Word document not found: {docx_path}")

        doc = docx.Document(docx_path)
        text_chunks = []
        
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_chunks.append(paragraph.text)
                
        for table in doc.tables:
            for row in table.rows:
                row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_text:
                    text_chunks.append(" | ".join(row_text))
                    
        return sanitize_text("\n".join(text_chunks))

    @staticmethod
    def read_text_file(file_path: Union[str, Path]) -> str:
        """Read text/code file using multiple encoding fallbacks (UTF-8, UTF-8-sig, CP1256, Latin-1)."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        encodings = ['utf-8', 'utf-8-sig', 'cp1256', 'latin-1', 'iso-8859-1']
        raw_text = ""
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    raw_text = f.read()
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if not raw_text:
            try:
                with open(file_path, 'rb') as f:
                    raw_text = f.read().decode('utf-8', errors='ignore')
            except Exception:
                raw_text = ""

        return sanitize_text(raw_text)

    @classmethod
    def categorize_file(cls, filename_or_path: Union[str, Path]) -> str:
        """Categorize file as 'code' or 'text' based on file extension.

        Word documents are always 'text'. Note: legacy binary '.doc' cannot be parsed by
        python-docx (OpenXML only); extract_file() degrades gracefully to "" for it.
        Whether a file is scanned at all is decided by file_policy.is_scannable().
        """
        return file_type_for(str(filename_or_path))

    @classmethod
    def extract_file(cls, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Extract content and metadata from a single file."""
        path = Path(file_path)
        ext = path.suffix.lower()
        file_type = cls.categorize_file(path)

        if ext == '.pdf':
            content = cls.extract_text_from_pdf(path)
        elif ext == '.doc':
            # Legacy binary .doc (OLE2) is NOT supported by python-docx, which only reads
            # OpenXML .docx. Skip it with a warning instead of crashing the whole scan.
            warnings.warn(
                f"Skipping legacy .doc file '{path.name}': python-docx only supports .docx (OpenXML). "
                f"Convert it to .docx to include it in the scan.",
                stacklevel=2,
            )
            content = ""
        elif ext == '.docx':
            try:
                content = cls.extract_text_from_docx(path)
            except Exception as e:
                warnings.warn(
                    f"Could not extract text from Word document '{path.name}': {e}",
                    stacklevel=2,
                )
                content = ""
        else:
            content = cls.read_text_file(path)

        return {
            "path": str(path),
            "filename": path.name,
            "extension": ext,
            "file_type": file_type,
            "content": sanitize_text(content)
        }

    @classmethod
    def scan_project_directory(
        cls, 
        dir_path: Union[str, Path], 
        ignore_dirs: Optional[set] = None,
        ignore_files: Optional[set] = None,
        min_lines: int = 3,
        max_total_bytes: int = 500 * 1024 * 1024,
        excluded_out: Optional[list] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recursively scan a project directory, filtering out dependency, build, binary, config,
        template, log/data, documentation, and trivial init files (see plagiarism_engine.file_policy).

        `max_total_bytes` caps the total raw size read; once reached, the WHOLE walk stops.
        If `excluded_out` is a list, {"path", "reason"} entries are appended for files the policy rejected.
        """
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Directory not found: {dir_path}")

        ignored_d = {d.lower() for d in (DEFAULT_IGNORE_DIRS if ignore_dirs is None else ignore_dirs)}
        ignored_f = {f.lower() for f in (DEFAULT_IGNORE_FILES if ignore_files is None else ignore_files)}
        extracted_files = []

        total_size = 0
        size_exceeded = False

        for root, dirs, files in os.walk(dir_path):
            if size_exceeded:
                break
            dirs[:] = [d for d in dirs if d.lower() not in ignored_d and not d.startswith('.')]

            for file in files:
                file_name_lower = file.lower()
                if file_name_lower in ignored_f:
                    continue

                file_path = Path(root) / file
                rel_path = str(file_path.relative_to(dir_path))
                try:
                    file_size = file_path.stat().st_size
                except OSError:
                    continue

                ok, reason = is_scannable(rel_path, file_size)
                if not ok:
                    if excluded_out is not None and reason not in ("binary", "unsupported", "ignored_dir"):
                        excluded_out.append({"path": rel_path, "reason": reason})
                    continue

                if total_size + file_size > max_total_bytes:
                    size_exceeded = True
                    break

                try:
                    record = cls.extract_file(file_path)
                except Exception:
                    continue
                lines = [l.strip() for l in record['content'].splitlines() if l.strip() and not l.strip().startswith('#')]

                # Filter out trivial files with fewer than min_lines
                if len(lines) < min_lines:
                    continue

                # Filter out trivial __init__.py files with < 5 non-trivial lines
                if file_name_lower == '__init__.py' and len(lines) < 5:
                    continue

                record["relative_path"] = rel_path
                extracted_files.append(record)
                total_size += file_size

        return extracted_files
