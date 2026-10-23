export const CODE_EXTS = new Set([
  "py", "js", "jsx", "ts", "tsx", "mjs", "cjs", "java", "c", "cpp", "cc", "cxx", "h", "hpp", "cs",
  "go", "rs", "php", "rb", "swift", "kt", "kts", "scala", "html", "htm", "css", "scss", "sass", "less",
  "sql", "sh", "bash", "zsh", "pl", "lua", "dart", "r", "m", "vue", "svelte"
]);

export const TEXT_EXTS = new Set(["pdf", "docx", "doc", "txt", "md", "markdown", "rst", "tex", "rtf"]);

// ---------------------------------------------------------------------------
// File-scope policy (mirror of plagiarism_engine/file_policy.py — the backend is
// authoritative and re-checks every file). Config, framework template, log and data
// files carry no authorship signal and only create false positives, so they are
// never uploaded, stored or scored.
// ---------------------------------------------------------------------------
export const CONFIG_EXTS = new Set([
  "json", "jsonc", "json5", "yaml", "yml", "toml", "xml", "ini", "cfg", "conf", "properties",
  "lock", "env", "gradle", "plist", "editorconfig", "pbxproj", "csproj", "vcxproj", "sln", "iml",
  "xcconfig", "npmrc", "nvmrc", "babelrc"
]);
export const DATA_LOG_EXTS = new Set(["log", "csv", "tsv", "jsonl", "ndjson"]);
export const CONFIG_FILENAMES = new Set([
  "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "pyproject.toml", "setup.py",
  "setup.cfg", "requirements.txt", "requirements-dev.txt", "pipfile", "pubspec.yaml", "pom.xml",
  "build.gradle", "settings.gradle", "manifest.json", "dockerfile", "docker-compose.yml",
  "makefile", "cmakelists.txt", "tsconfig.json", "jsconfig.json", "config.json", ".gitignore",
  "readme.md", "readme.txt", "readme", "license", "license.txt", "license.md", "changelog.md"
]);
export const TEMPLATE_FILENAMES = new Set([
  "vite-env.d.ts", "react-app-env.d.ts", "next-env.d.ts", "reportwebvitals.js", "reportwebvitals.ts",
  "setuptests.js", "setuptests.ts", "serviceworker.js", "manage.py", "wsgi.py", "asgi.py",
  "gradlew", "gradlew.bat", "mvnw", "mvnw.cmd", "generated_plugin_registrant.dart"
]);
const EXCLUDED_SUFFIXES = [
  ".d.ts", ".g.dart", ".freezed.dart", ".min.js", ".min.css", ".map",
  ".config.js", ".config.ts", ".config.mjs", ".config.cjs", ".conf.js"
];

/** Returns an exclusion reason ("config" | "template" | "data_or_log") or null if the file is scannable. */
export const policyExclusionReason = (fileName: string): string | null => {
  const name = fileName.toLowerCase();
  const ext = name.includes(".") ? name.split(".").pop() || "" : "";
  if (CONFIG_FILENAMES.has(name) || name.startsWith(".env")) return "config";
  if (TEMPLATE_FILENAMES.has(name)) return "template";
  if (EXCLUDED_SUFFIXES.some(s => name.endsWith(s))) return name.includes(".config.") || name.includes(".conf.") ? "config" : "template";
  if (CONFIG_EXTS.has(ext)) return "config";
  if (DATA_LOG_EXTS.has(ext)) return "data_or_log";
  return null;
};
export const ARCHIVE_EXTS = new Set(["zip", "rar", "tar", "gz", "7z", "bz2"]);

export const IGNORE_PATTERNS = [
  "node_modules", ".venv", "venv", "env", ".env", ".git", ".idea", ".vscode",
  "__pycache__", "dist", "build", ".next", ".nuxt", ".cache", "bin", "obj", ".nuget",
  ".gradle", ".cargo", "site-packages", ".pytest_cache", ".mypy_cache", "vendor",
  "target", "out", "coverage", "debug", "release", "x64", "x86", "pods", ".dart_tool",
  "builds", "logs", "tmp", "temp"
];

export const BINARY_EXTS = new Set([
  "exe", "dll", "so", "dylib", "class", "pyc", "pyo", "pyd", "o", "a", "iso", "dmg",
  "wasm", "bin", "pt", "pth", "h5", "hdf5", "onnx", "pkl", "pickle", "joblib",
  "safetensors", "parquet", "tflite", "db", "sqlite", "npy", "whl",
  "mp4", "avi", "mov", "mkv", "mp3", "wav", "png", "jpg", "jpeg", "gif", "ico"
]);

export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
};

export const traverseDirectoryEntry = async (
  entry: any,
  path = ""
): Promise<{ file: File; path: string }[]> => {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file(
        (file: File) => {
          resolve([{ file, path: path ? `${path}/${file.name}` : file.name }]);
        },
        () => resolve([])
      );
    } else if (entry.isDirectory) {
      const dirReader = entry.createReader();
      const entries: any[] = [];
      const readEntries = () => {
        dirReader.readEntries(
          async (result: any[]) => {
            if (result.length === 0) {
              const nestedFiles: { file: File; path: string }[] = [];
              for (const childEntry of entries) {
                const childPath = path ? `${path}/${entry.name}` : entry.name;
                const childFiles = await traverseDirectoryEntry(childEntry, childPath);
                nestedFiles.push(...childFiles);
              }
              resolve(nestedFiles);
            } else {
              entries.push(...result);
              readEntries();
            }
          },
          () => resolve([])
        );
      };
      readEntries();
    } else {
      resolve([]);
    }
  });
};
