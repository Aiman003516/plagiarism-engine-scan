"""Central file-scope policy: the single source of truth for which files are scanned.

Every entry point (folder walk, ZIP/Git import, direct uploads, analysis of already-stored
projects, embedding indexing) asks `is_scannable()` before a file is stored, fingerprinted,
embedded or scored.

Excluded by design:
- config / manifest / lock files: unrelated projects share near-identical configs
  (measured: package.json <-> package.json raw cosine 0.96 between unrelated projects), so
  they carry no authorship signal and only create false positives;
- framework template / generated files (e.g. vite-env.d.ts, manage.py, wsgi.py, gradlew);
- logs and tabular data (.log/.csv/.tsv): not authored work, and very large;
- binaries, unsupported extensions, oversized files, dependency/build directories.
"""

from pathlib import PurePath
from typing import Optional, Tuple

# --------------------------------------------------------------------------- scannable types
CODE_EXTENSIONS = {
    '.py', '.cpp', '.c', '.h', '.hpp', '.cc', '.cxx',
    '.java', '.js', '.ts', '.jsx', '.tsx', '.cs', '.mjs', '.cjs',
    '.go', '.rs', '.php', '.html', '.htm', '.css', '.scss', '.sass', '.less',
    '.rb', '.swift', '.kt', '.kts', '.sql', '.sh',
    '.bash', '.zsh', '.pl', '.r', '.m', '.scala',
    '.dart', '.vue', '.svelte', '.lua',
}

TEXT_EXTENSIONS = {
    '.txt', '.pdf', '.docx', '.doc', '.md', '.markdown',
    '.rst', '.tex', '.rtf',
}

BINARY_DOCUMENT_EXTENSIONS = {'.pdf', '.docx', '.doc'}

# --------------------------------------------------------------------------- excluded types
CONFIG_EXTENSIONS = {
    '.json', '.jsonc', '.json5', '.yaml', '.yml', '.toml', '.xml', '.ini', '.cfg', '.conf',
    '.properties', '.lock', '.env', '.gradle', '.plist', '.editorconfig', '.pbxproj',
    '.csproj', '.vcxproj', '.sln', '.iml', '.xcconfig', '.npmrc', '.nvmrc', '.babelrc',
}

DATA_LOG_EXTENSIONS = {'.log', '.csv', '.tsv', '.jsonl', '.ndjson'}

BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.bmp', '.svg', '.webp',
    '.exe', '.dll', '.so', '.dylib', '.db', '.sqlite', '.sqlite3',
    '.pyc', '.pyo', '.pyd', '.class', '.jar', '.war', '.zip', '.tar', '.gz', '.7z',
    '.rar', '.pdf.tmp', '.bin', '.dat', '.o', '.a', '.obj', '.eot',
    '.ttf', '.woff', '.woff2', '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv',
    '.pt', '.pth', '.h5', '.onnx', '.pkl', '.pickle', '.joblib', '.tflite', '.parquet',
    '.safetensors', '.ckpt', '.gguf', '.msgpack', '.npy', '.npz', '.spm',
}

# Data files identified by name (tokenizer vocabularies etc. inside model folders).
DATA_FILENAMES = {'vocab.txt', 'merges.txt', 'vocab.json', 'sentencepiece.bpe.model', 'tokenizer.model'}

# Config / manifest / tooling files identified by exact (lower-case) file name.
CONFIG_FILENAMES = {
    # package managers & locks
    'package.json', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb',
    'pipfile', 'pipfile.lock', 'poetry.lock', 'pyproject.toml', 'setup.cfg', 'setup.py',
    'requirements.txt', 'requirements-dev.txt', 'gemfile', 'gemfile.lock', 'composer.json',
    'composer.lock', 'cargo.toml', 'cargo.lock', 'go.mod', 'go.sum', 'pubspec.yaml',
    'pubspec.lock', 'podfile', 'podfile.lock', 'build.gradle', 'settings.gradle', 'pom.xml',
    'manifest.json', 'manifest.in', 'androidmanifest.xml', 'info.plist',
    # tooling / CI / containers
    'dockerfile', 'docker-compose.yml', 'docker-compose.yaml', 'makefile', 'cmakelists.txt',
    'procfile', 'vercel.json', 'netlify.toml', 'firebase.json', 'tsconfig.json',
    'jsconfig.json', 'config.json', 'components.json', 'analysis_options.yaml',
    '.gitignore', '.gitattributes', '.dockerignore', '.eslintrc', '.eslintignore',
    '.prettierrc', '.prettierignore', '.editorconfig', '.npmrc', '.nvmrc', '.babelrc',
    '.env', '.env.example', '.env.local', '.flake8', '.pylintrc', 'tox.ini', 'pytest.ini',
    # repository meta documents (not authored submission content)
    'readme.md', 'readme.txt', 'readme.rst', 'readme.markdown', 'readme',
    'license', 'license.txt', 'license.md', 'copying', 'changelog.md', 'contributing.md',
    'code_of_conduct.md', 'security.md',
    '.ds_store', 'thumbs.db',
}

# Framework templates and generated files: identical across unrelated projects by construction.
TEMPLATE_FILENAMES = {
    'vite-env.d.ts', 'react-app-env.d.ts', 'next-env.d.ts', 'env.d.ts',
    'reportwebvitals.js', 'reportwebvitals.ts', 'setuptests.js', 'setuptests.ts',
    'serviceworker.js', 'registerserviceworker.js',
    'manage.py', 'wsgi.py', 'asgi.py',
    'gradlew', 'gradlew.bat', 'mvnw', 'mvnw.cmd',
    'generated_plugin_registrant.dart', 'generated_plugin_registrant.h',
    'generated_plugin_registrant.cc', 'generated_plugin_registrant.m',
    'generatedpluginregistrant.swift', 'generatedpluginregistrant.java',
}

# Suffixes of generated / minified / tool-config files (matched on the lower-case file name).
EXCLUDED_SUFFIXES = (
    '.d.ts', '.g.dart', '.freezed.dart', '.mocks.dart', '.min.js', '.min.css', '.map',
    '.config.js', '.config.ts', '.config.mjs', '.config.cjs',      # vite/webpack/tailwind/... configs
    '.conf.js', '.designer.cs', '.generated.cs', '_pb2.py', '_pb2_grpc.py',
)

IGNORED_DIR_NAMES = {
    # Python
    'venv', 'env', '.venv', '__pycache__', 'htmlcov', 'wheels', 'site-packages', '.pytest_cache',
    '.mypy_cache', '.tox', '.eggs',
    # Node.js / Web
    'node_modules', 'bower_components', 'jspm_packages', '.next', '.nuxt', '.cache', '.parcel-cache',
    # Java/Android/Kotlin/Scala
    'captures', 'gen', '.gradle',
    # C/C++/.NET
    'debug', 'release', 'x64', 'x86', 'cmake-build-debug', 'cmake-build-release', 'cmakefiles',
    '.nuget',
    # Go / Rust / Ruby / PHP
    'vendor', 'pkg', 'tmp', '.cargo',
    # Mobile (Flutter / iOS)
    'pods', 'ephemeral', 'deriveddata', '.dart_tool', '.symlinks',
    # Unity / GameDev
    'library', 'temp', 'builds', 'logs', 'memorycaptures',
    # General build / outputs / cache
    'build', 'dist', 'target', 'bin', 'obj', 'out', 'coverage',
    # Project specific (legacy vector stores). NOTE: 'models' is deliberately NOT ignored: it is one of
    # the most common source folders (Django, Flutter lib/models, MVC). ML weight files inside model
    # folders are excluded by extension (BINARY_EXTENSIONS) and vocab files by name (DATA_FILENAMES).
    'chroma_db', 'chroma_demo_db', 'chroma_test_folder_db', 'chroma_app_db',
    # Git and IDE meta
    '.git', '.github', '.vscode', '.idea', '.vs', '.run',
}

MAX_SOURCE_BYTES = 2 * 1024 * 1024        # source / plain-text file (bigger = generated or data)
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024     # PDF / DOCX (raw size; images inflate it)

# Reasons returned by is_scannable()
REASON_CONFIG = "config"
REASON_TEMPLATE = "template"
REASON_DATA_LOG = "data_or_log"
REASON_BINARY = "binary"
REASON_UNSUPPORTED = "unsupported"
REASON_TOO_LARGE = "too_large"
REASON_IGNORED_DIR = "ignored_dir"


def _parts(relative_path: str):
    return [p for p in PurePath(str(relative_path).replace("\\", "/")).parts if p not in ("", "/", ".")]


def is_scannable(relative_path: str, size_bytes: Optional[int] = None) -> Tuple[bool, str]:
    """Return (True, "") if the file must be scanned, else (False, reason).

    `relative_path` may contain directories (either slash style). `size_bytes` is optional: the raw
    size for PDF/DOCX, the content size for everything else.
    """
    parts = _parts(relative_path)
    if not parts:
        return False, REASON_UNSUPPORTED
    name = parts[-1].lower()

    for d in parts[:-1]:
        dl = d.lower()
        if dl in IGNORED_DIR_NAMES or (dl.startswith('.') and dl not in ('..',)):
            return False, REASON_IGNORED_DIR

    ext = PurePath(name).suffix.lower()

    if name in CONFIG_FILENAMES or name.startswith('.env'):
        return False, REASON_CONFIG
    if name in TEMPLATE_FILENAMES:
        return False, REASON_TEMPLATE
    if name in DATA_FILENAMES:
        return False, REASON_DATA_LOG
    if name.endswith(EXCLUDED_SUFFIXES):
        return False, REASON_CONFIG if '.config.' in name or '.conf.' in name else REASON_TEMPLATE
    if ext in CONFIG_EXTENSIONS:
        return False, REASON_CONFIG
    if ext in DATA_LOG_EXTENSIONS:
        return False, REASON_DATA_LOG
    if ext in BINARY_EXTENSIONS:
        return False, REASON_BINARY
    if ext not in CODE_EXTENSIONS and ext not in TEXT_EXTENSIONS:
        return False, REASON_UNSUPPORTED

    if size_bytes is not None:
        limit = MAX_DOCUMENT_BYTES if ext in BINARY_DOCUMENT_EXTENSIONS else MAX_SOURCE_BYTES
        if size_bytes > limit:
            return False, REASON_TOO_LARGE
    return True, ""


def file_type_for(relative_path: str) -> str:
    """'code' or 'text' for a scannable file (callers should check is_scannable() first)."""
    ext = PurePath(str(relative_path).replace("\\", "/")).suffix.lower()
    if ext in ('.doc', '.docx'):
        return 'text'
    return 'code' if ext in CODE_EXTENSIONS else 'text'


def filter_scannable(files, path_key: str = "relative_path"):
    """Split file records into (kept, excluded). `excluded` items are {"path", "reason"} dicts.

    Content length is used as the size for non-document files; documents were already
    size-checked on their raw bytes by the caller (or are accepted here).
    """
    kept, excluded = [], []
    for f in files:
        path = f.get(path_key) or f.get("filename") or ""
        ext = PurePath(str(path).replace("\\", "/")).suffix.lower()
        size = None
        if ext not in BINARY_DOCUMENT_EXTENSIONS:
            content = f.get("content") or ""
            size = len(content.encode("utf-8", errors="ignore")) if isinstance(content, str) else len(content)
        ok, reason = is_scannable(path, size)
        if ok:
            kept.append(f)
        else:
            excluded.append({"path": path, "reason": reason})
    return kept, excluded
