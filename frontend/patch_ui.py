import re

with open('src/pages/Plagiarism.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

# Add pageMode state
code = code.replace(
    'const [activeTab, setActiveTab] = useState<"direct" | "git">("direct");',
    'const [pageMode, setPageMode] = useState<"intake" | "scan">("intake");\n  const [activeTab, setActiveTab] = useState<"direct" | "git">("direct");\n  const [savedProjects, setSavedProjects] = useState<any[]>([]);\n  const [selectedProject, setSelectedProject] = useState<string>("");'
)

# Fetch projects when pageMode changes to scan
code = code.replace(
    'export function Plagiarism() {',
    'export function Plagiarism() {'
)

fetch_eff = '''
  useEffect(() => {
    if (pageMode === 'scan') {
      plagiarismApi.getProjects().then(setSavedProjects).catch(console.error);
    }
  }, [pageMode]);
'''
code = code.replace('const [activeTab, setActiveTab]', fetch_eff + 'const [activeTab, setActiveTab]')

# Create a scan UI function
scan_ui = '''
  const renderScanPage = () => (
    <div className="space-y-6 animate-fade-in">
      <div className="bg-card border border-border/50 rounded-xl p-8 flex flex-col items-center">
        <Database className="w-16 h-16 text-primary mb-4" />
        <h2 className="text-2xl font-bold mb-2">Run Plagiarism Analysis</h2>
        <p className="text-muted-foreground text-center max-w-lg mb-8">
          Select a project that has already been indexed into the database to instantly run a system-wide plagiarism scan.
        </p>
        <div className="flex gap-4 w-full max-w-md">
          <select 
            className="flex-1 bg-background border border-input rounded-lg px-4"
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
          >
            <option value="">Select a saved project...</option>
            {savedProjects.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <button 
            disabled={!selectedProject || isScanning}
            onClick={async () => {
              setIsScanning(true);
              setScanLogs(['Starting instant analysis...']);
              try {
                const res = await plagiarismApi.scanProject(selectedProject);
                setScanResult(res);
                toast.success('Scan complete in milliseconds!');
              } catch(e: any) {
                toast.error(e.message);
              }
              setIsScanning(false);
            }}
            className="bg-primary text-primary-foreground px-6 py-3 rounded-lg font-medium hover:bg-primary/90 flex items-center gap-2 disabled:opacity-50"
          >
            {isScanning ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Search className="w-5 h-5" />}
            Run Scan
          </button>
        </div>
      </div>
      {scanResult && renderResultReport()}
    </div>
  );
'''

# Find the start of the render function
code = code.replace(
    'return (',
    scan_ui + '\n  return ('
)

# Add the segmented control at the top of the UI
header_html = '''
      {/* Dynamic Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-8 gap-4">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2.5 bg-primary/10 text-primary rounded-xl ring-1 ring-primary/20 shadow-sm">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <h1 className="text-3xl font-bold text-foreground tracking-tight">Ministry Graduation Engine</h1>
          </div>
          <p className="text-muted-foreground text-sm max-w-xl leading-relaxed">
            Upload and index graduation projects into the centralized database, or scan an existing project for code similarity.
          </p>
        </div>
        
        {/* Page Mode Switcher */}
        <div className="flex p-1 bg-secondary/30 rounded-lg ring-1 ring-border/50">
          <button
            onClick={() => { setPageMode("intake"); setScanResult(null); }}
            className={lex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 }
          >
            <UploadCloud className="w-4 h-4" />
            Intake Project
          </button>
          <button
            onClick={() => { setPageMode("scan"); setScanResult(null); }}
            className={lex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 }
          >
            <Search className="w-4 h-4" />
            Scan Database
          </button>
        </div>
      </div>
'''

# Replace the original header
code = re.sub(
    r'\{\/\* Dynamic Header \*\/\}.*?<\/p>\s*<\/div>\s*<\/div>',
    header_html,
    code,
    flags=re.DOTALL
)

# Conditionally render intake vs scan
code = code.replace(
    '{/* Core Grid Layout - Full Width */}',
    '{pageMode === "scan" ? renderScanPage() : (\n      <>\n      {/* Core Grid Layout - Full Width */}'
)

code = code.replace(
    '      {/* Detailed Result Report View (Slides in when scanResult exists) */}',
    '      </>\n      )}\n      {/* Detailed Result Report View (Slides in when scanResult exists) */}'
)

# And fix the intake button texts
code = code.replace('Run Direct Plagiarism Scan', 'Upload & Index Project')
code = code.replace('Run Git Plagiarism Scan', 'Clone & Index Project')

with open('src/pages/Plagiarism.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
print("UI patched")
