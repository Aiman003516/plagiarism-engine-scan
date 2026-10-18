export const CODE_EXTS = new Set([
  "py", "js", "jsx", "ts", "tsx", "java", "c", "cpp", "h", "hpp", "cs",
  "go", "rs", "php", "rb", "swift", "kt", "scala", "html", "css", "sql", "sh",
  "json", "yaml", "yml", "xml", "dart", "r", "m", "vue", "svelte"
]);

export const TEXT_EXTS = new Set(["pdf", "docx", "doc", "txt", "md", "tex", "rtf", "odt"]);
export const ARCHIVE_EXTS = new Set(["zip", "rar", "tar", "gz", "7z", "bz2"]);

export const IGNORE_PATTERNS = [
  "node_modules", ".venv", "venv", "env", ".env", ".git", ".idea", ".vscode",
  "__pycache__", "dist", "build", ".next", ".nuxt", ".cache", "bin", "obj", ".nuget",
  ".gradle", ".cargo", "site-packages", ".pytest_cache", ".mypy_cache", "vendor"
];

export const BINARY_EXTS = new Set([
  "exe", "dll", "so", "dylib", "class", "pyc", "pyo", "pyd", "o", "a", "iso", "dmg",
  "wasm", "bin", "pt", "pth", "h5", "hdf5", "onnx", "pkl", "pickle", "joblib",
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
