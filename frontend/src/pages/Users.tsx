import { useState, useRef } from "react";
import { UserCog, RefreshCw, Search, Trash2, Plus, Loader2, Upload, Download, FileSpreadsheet, CheckCircle2, AlertCircle, X } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { usersApi, UserProfileData } from "../lib/api";
import { useUsersCache } from "../lib/useUsersCache";
import { TableSkeleton } from "../components/Skeletons";

const ROLES = [
  { value: "student", label: "Student" },
  { value: "faculty", label: "Faculty / Department Head" },
  { value: "college_admin", label: "College Admin" },
  { value: "university_admin", label: "University Admin" },
  { value: "ministry_admin", label: "Ministry Admin" },
];

interface ParsedStudent {
  name: string;
  enrollment_number: string;
  college?: string;
  department?: string;
  university?: string;
  password?: string;
}

export default function Users() {
  const { t } = useTranslation();
  const [roleFilter, setRoleFilter] = useState("");
  const { users, loading, error, refresh: load } = useUsersCache(roleFilter || undefined);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [bulkImporting, setBulkImporting] = useState(false);
  const [bulkParsedStudents, setBulkParsedStudents] = useState<ParsedStudent[]>([]);
  const [bulkFileName, setBulkFileName] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "123456",
    role: "student",
    college_id: "",
    enrollment_number: "",
    department: "",
    university: "",
    college: "",
  });

  const handleRoleChange = (newRole: string) => {
    setForm((prev) => ({
      ...prev,
      role: newRole,
      password: newRole === "student" ? (prev.password || "123456") : "",
    }));
  };

  const createUser = async () => {
    if (!form.name.trim()) {
      toast.error("Please enter a full name");
      return;
    }

    if (form.role === "student") {
      if (!form.enrollment_number.trim()) {
        toast.error("Please enter an Enrollment / Student ID");
        return;
      }
    } else {
      if (!form.email.trim() || !form.password) {
        toast.error("Please enter an email and password");
        return;
      }
    }

    setSaving(true);
    try {
      await usersApi.create({
        name: form.name.trim(),
        email: form.role === "student" && !form.email.trim()
          ? `${form.enrollment_number.trim()}@student.edu`
          : form.email.trim(),
        password: form.password || "123456",
        role: form.role,
        college_id: form.college_id || form.college || undefined,
        enrollment_number: form.enrollment_number.trim() || undefined,
        department: form.department.trim() || undefined,
        university: form.university.trim() || undefined,
        college: form.college.trim() || undefined,
      });

      toast.success(t("register_success"));
      setForm({
        name: "",
        email: "",
        password: "123456",
        role: "student",
        college_id: "",
        enrollment_number: "",
        department: "",
        university: "",
        college: "",
      });
      setShowCreate(false);
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to create user");
    } finally {
      setSaving(false);
    }
  };

  const deleteUser = async (user: UserProfileData) => {
    if (!window.confirm(t("confirm_delete"))) return;
    try {
      await usersApi.delete(user.id);
      toast.success(t("delete_success"));
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to delete user");
    }
  };

  // CSV parsing logic for Bulk Import
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setBulkFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (!text) return;

      const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
      if (lines.length <= 1) {
        toast.error("CSV file contains no data rows");
        return;
      }

      // Check header row
      const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
      const nameIdx = headers.findIndex((h) => h.includes("name"));
      const enrollIdx = headers.findIndex((h) => h.includes("enroll") || h.includes("id") || h.includes("student_id"));
      const collegeIdx = headers.findIndex((h) => h.includes("college"));
      const deptIdx = headers.findIndex((h) => h.includes("dept") || h.includes("department"));
      const uniIdx = headers.findIndex((h) => h.includes("uni") || h.includes("university"));

      if (enrollIdx === -1 && nameIdx === -1) {
        toast.error("CSV must contain at least 'name' and 'enrollment_number' columns");
        return;
      }

      const parsed: ParsedStudent[] = [];
      for (let i = 1; i < lines.length; i++) {
        const cols = lines[i].split(",").map((c) => c.trim().replace(/^"|"$/g, ""));
        if (cols.length === 0 || !cols.some((c) => c.length > 0)) continue;

        const name = nameIdx >= 0 && cols[nameIdx] ? cols[nameIdx] : "";
        const enrollment_number = enrollIdx >= 0 && cols[enrollIdx] ? cols[enrollIdx] : cols[0];
        const college = collegeIdx >= 0 ? cols[collegeIdx] : undefined;
        const department = deptIdx >= 0 ? cols[deptIdx] : undefined;
        const university = uniIdx >= 0 ? cols[uniIdx] : undefined;

        if (enrollment_number) {
          parsed.push({
            name: name || `Student ${enrollment_number}`,
            enrollment_number,
            college,
            department,
            university,
            password: "123456",
          });
        }
      }

      setBulkParsedStudents(parsed);
      toast.success(`Parsed ${parsed.length} students from ${file.name}`);
    };
    reader.readAsText(file);
  };

  const handleDownloadTemplate = () => {
    const csvContent = "name,enrollment_number,college,department,university\nAhmed Ali,20240101,Faculty of Computer Science,Software Engineering,Sana'a University\nSara Hassan,20240102,Faculty of Engineering,Information Technology,Aden University\nMustafa Tareq,20240103,Faculty of Science,Computer Science,Taiz University";
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", "students_import_template.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExecuteBulkImport = async () => {
    if (bulkParsedStudents.length === 0) {
      toast.error("No students parsed to import");
      return;
    }

    setBulkImporting(true);
    try {
      const res = await usersApi.bulkImportStudents(bulkParsedStudents);
      toast.success(`Imported ${res.imported_count} students successfully!`);
      if (res.failed_count > 0) {
        toast.error(`${res.failed_count} students skipped (already exist or invalid)`);
      }
      setBulkParsedStudents([]);
      setBulkFileName("");
      setShowBulkModal(false);
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to bulk import students");
    } finally {
      setBulkImporting(false);
    }
  };

  const filtered = users.filter(
    (u) =>
      !search.trim() ||
      (u.name || "").toLowerCase().includes(search.toLowerCase()) ||
      (u.email || "").toLowerCase().includes(search.toLowerCase())
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div>
      {/* Tier 1: Page Header with Title on Start & Actions on End */}
      <header className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-text-main">
            {t("users_title")}
          </h1>
          <p className="text-text-muted mt-1">{t("users_subtitle")}</p>
        </div>
        <div className="flex items-center gap-2.5 shrink-0">
          <button
            onClick={() => setShowBulkModal(true)}
            className="btn-secondary text-xs px-3.5 py-2 font-semibold flex items-center gap-1.5"
            title="Bulk import students from CSV or Excel file"
          >
            <FileSpreadsheet className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>Bulk Import</span>
          </button>
          <button onClick={() => setShowCreate(true)} className="btn-primary text-xs px-4 py-2 font-semibold flex items-center gap-1.5">
            <Plus className="w-4 h-4" />
            <span>{t("add_user")}</span>
          </button>
        </div>
      </header>

      {/* Tier 2: Dedicated Filter & Search Toolbar */}
      <div className="mb-4 flex flex-col sm:flex-row items-center justify-between gap-3 bg-surface/50 p-2.5 rounded-xl border border-border">
        <div className="relative w-full sm:w-72">
          <Search className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-field w-full ps-9 text-xs py-2"
            placeholder={t("search_users")}
          />
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto justify-between sm:justify-end">
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="input-field text-xs py-2 w-full sm:w-52"
          >
            <option value="">{t("all_roles") || "All Roles"}</option>
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {t(`role_${r.value}`) || r.label}
              </option>
            ))}
          </select>
          <span className="text-xs text-text-muted whitespace-nowrap px-2.5 py-1 rounded-md bg-surface-hover/80 border border-border/60">
            {filtered.length} {filtered.length === 1 ? (t("user") || "user") : (t("total_users") || "users")}
          </span>
        </div>
      </div>

      {loading ? (
        <TableSkeleton columns={5} rows={8} />
      ) : filtered.length === 0 ? (
        <div className="glass-panel p-10 text-center text-text-muted rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
          <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-purple-500/10 text-purple-500">
            <UserCog className="w-6 h-6" />
          </span>
          {t("no_users_found")}
        </div>
      ) : (
        <div className="glass-panel overflow-hidden rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-surface/95 backdrop-blur">
                <tr className="text-start text-text-muted border-b border-border">
                  <th className="py-3 px-4 font-medium">{t("name")}</th>
                  <th className="py-3 px-4 font-medium">{t("email")} / ID</th>
                  <th className="py-3 px-4 font-medium">{t("role")}</th>
                  <th className="py-3 px-4 font-medium">{t("college")}</th>
                  <th className="py-3 px-4 font-medium text-end">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((u) => (
                  <tr key={u.id} className="hover:bg-surface/50 transition-colors border-b border-border/40 last:border-0">
                    <td className="py-3 px-4 font-medium text-text-main">{u.name}</td>
                    <td className="py-3 px-4 text-text-muted font-mono text-xs">{u.email}</td>
                    <td className="py-3 px-4">
                      <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ${
                        u.role === "student"
                          ? "bg-blue-500/10 text-blue-500 ring-blue-500/20"
                          : u.role === "faculty"
                          ? "bg-emerald-500/10 text-emerald-500 ring-emerald-500/20"
                          : "bg-purple-500/10 text-purple-500 ring-purple-500/20"
                      }`}>
                        {u.role}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-text-muted">{u.college_id || "—"}</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center justify-end">
                        <button
                          onClick={() => deleteUser(u)}
                          className="btn-danger-icon"
                          title={t("delete")}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length > PAGE_SIZE && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-border">
              <span className="text-xs text-text-muted">
                {t("showing_page")} {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} {t("of_pages")} {filtered.length}
              </span>
              <div className="flex items-center gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-2.5 py-1 rounded-lg text-xs text-text-muted border border-border hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {t("prev_page")}
                </button>
                <span className="text-xs text-text-muted">{page} / {totalPages}</span>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="px-2.5 py-1 rounded-lg text-xs text-text-muted border border-border hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {t("next_page")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Role-Aware Add User Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-lg p-6 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-text-main flex items-center gap-2">
                <UserCog className="w-5 h-5 text-primary" /> {t("add_user")}
              </h2>
              <button
                onClick={() => setShowCreate(false)}
                className="p-1 rounded-lg text-text-muted hover:bg-surface"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                  User Role
                </label>
                <select
                  value={form.role}
                  onChange={(e) => handleRoleChange(e.target.value)}
                  className="input-field w-full font-medium"
                >
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {t(`role_${r.value}`) || r.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                  Full Name <span className="text-red-500">*</span>
                </label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="input-field w-full"
                  placeholder="e.g. Ali Mohammed"
                />
              </div>

              {form.role === "student" ? (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                        Enrollment / Student ID <span className="text-red-500">*</span>
                      </label>
                      <input
                        value={form.enrollment_number}
                        onChange={(e) => setForm({ ...form, enrollment_number: e.target.value })}
                        className="input-field w-full font-mono text-sm"
                        placeholder="e.g. 20240105"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                        Department
                      </label>
                      <input
                        value={form.department}
                        onChange={(e) => setForm({ ...form, department: e.target.value })}
                        className="input-field w-full text-sm"
                        placeholder="e.g. Computer Science"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                        College
                      </label>
                      <input
                        value={form.college}
                        onChange={(e) => setForm({ ...form, college: e.target.value, college_id: e.target.value })}
                        className="input-field w-full text-sm"
                        placeholder="e.g. College of Engineering"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                        University
                      </label>
                      <input
                        value={form.university}
                        onChange={(e) => setForm({ ...form, university: e.target.value })}
                        className="input-field w-full text-sm"
                        placeholder="e.g. Sana'a University"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                      Temporary Password (Default 123456)
                    </label>
                    <input
                      type="text"
                      value={form.password}
                      onChange={(e) => setForm({ ...form, password: e.target.value })}
                      className="input-field w-full font-mono text-sm bg-surface/50"
                      placeholder="123456"
                    />
                    <p className="text-[11px] text-text-muted mt-1">
                      Student will log in with Enrollment ID and will be prompted to set a permanent password upon first login.
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                      Email Address <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="email"
                      value={form.email}
                      onChange={(e) => setForm({ ...form, email: e.target.value })}
                      className="input-field w-full text-sm"
                      placeholder="staff@university.edu"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                      Password <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="password"
                      value={form.password}
                      onChange={(e) => setForm({ ...form, password: e.target.value })}
                      className="input-field w-full text-sm"
                      placeholder="Enter secure password"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                      College / Faculty
                    </label>
                    <input
                      value={form.college_id}
                      onChange={(e) => setForm({ ...form, college_id: e.target.value })}
                      className="input-field w-full text-sm"
                      placeholder="e.g. College of Science"
                    />
                  </div>
                </>
              )}
            </div>

            <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-border">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded-lg text-sm text-text-muted hover:bg-surface"
              >
                {t("cancel")}
              </button>
              <button onClick={createUser} disabled={saving} className="btn-primary">
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {t("save")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk CSV Import Modal */}
      {showBulkModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-2xl p-6 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between pb-4 border-b border-border">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-emerald-500" />
                <h2 className="text-lg font-bold text-text-main">Bulk Import Students (CSV / Excel)</h2>
              </div>
              <button
                onClick={() => {
                  setShowBulkModal(false);
                  setBulkParsedStudents([]);
                  setBulkFileName("");
                }}
                className="p-1 rounded-lg text-text-muted hover:bg-surface"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="py-4 space-y-4 overflow-y-auto flex-1">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl bg-surface/50 border border-border/60">
                <div>
                  <h4 className="text-sm font-semibold text-text-main">Standard CSV Import Template</h4>
                  <p className="text-xs text-text-muted mt-0.5">
                    Columns: name, enrollment_number, college, department, university
                  </p>
                </div>
                <button
                  onClick={handleDownloadTemplate}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-all flex items-center gap-1.5 flex-shrink-0"
                >
                  <Download className="w-3.5 h-3.5" /> Download Template (.csv)
                </button>
              </div>

              <div>
                <input
                  type="file"
                  accept=".csv,text/csv,application/vnd.ms-excel"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full border-2 border-dashed border-border/80 hover:border-emerald-500/60 rounded-xl p-8 text-center transition-all bg-surface/20 hover:bg-surface/40 flex flex-col items-center justify-center gap-2"
                >
                  <Upload className="w-8 h-8 text-emerald-500" />
                  <span className="text-sm font-semibold text-text-main">
                    {bulkFileName ? `Selected: ${bulkFileName}` : "Click to select CSV File"}
                  </span>
                  <span className="text-xs text-text-muted">
                    Supports comma-separated .csv exported from Excel or Google Sheets
                  </span>
                </button>
              </div>

              {bulkParsedStudents.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-text-muted uppercase">
                      Parsed Preview ({bulkParsedStudents.length} Students)
                    </span>
                    <span className="text-xs text-emerald-500 font-medium">✓ Ready to Ingest</span>
                  </div>
                  <div className="max-h-48 overflow-y-auto rounded-xl border border-border/60">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-surface sticky top-0 border-b border-border">
                        <tr>
                          <th className="p-2 font-medium">Name</th>
                          <th className="p-2 font-medium">Enrollment ID</th>
                          <th className="p-2 font-medium">Department</th>
                          <th className="p-2 font-medium">College</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/40">
                        {bulkParsedStudents.map((s, idx) => (
                          <tr key={idx} className="hover:bg-surface/30">
                            <td className="p-2 font-medium">{s.name}</td>
                            <td className="p-2 font-mono text-primary">{s.enrollment_number}</td>
                            <td className="p-2 text-text-muted">{s.department || "—"}</td>
                            <td className="p-2 text-text-muted">{s.college || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-border mt-auto">
              <button
                onClick={() => {
                  setShowBulkModal(false);
                  setBulkParsedStudents([]);
                  setBulkFileName("");
                }}
                className="px-4 py-2 rounded-lg text-sm text-text-muted hover:bg-surface"
              >
                {t("cancel")}
              </button>
              <button
                onClick={handleExecuteBulkImport}
                disabled={bulkImporting || bulkParsedStudents.length === 0}
                className="btn-primary"
              >
                {bulkImporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                Import {bulkParsedStudents.length > 0 ? `(${bulkParsedStudents.length})` : ""} Students
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
