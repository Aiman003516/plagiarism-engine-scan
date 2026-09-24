import { useEffect, useState } from "react";
import { UserCog, RefreshCw, Search, Trash2, Plus, Loader2 } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { usersApi, UserProfileData } from "../lib/api";

const ROLES = [
  { value: "ministry_admin", label: "Ministry Admin" },
  { value: "college_admin", label: "College Admin" },
  { value: "student", label: "Student" },
];

export default function Users() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<UserProfileData[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    role: "college_admin",
    college_id: "",
  });

  const load = async () => {
    setLoading(true);
    try {
      const res = await usersApi.getAll(roleFilter ? { role: roleFilter } : undefined);
      setUsers(res.users || []);
    } catch (e: any) {
      toast.error(e?.message || "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roleFilter]);

  const createUser = async () => {
    if (!form.name.trim() || !form.email.trim() || !form.password) {
      toast.error(t("invalid_credentials"));
      return;
    }
    setSaving(true);
    try {
      await usersApi.create({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
        college_id: form.college_id || undefined,
      });
      toast.success(t("register_success"));
      setForm({ name: "", email: "", password: "", role: "college_admin", college_id: "" });
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
      <header className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-text-main">
            {t("users_title")}
          </h1>
          <p className="text-text-muted mt-1">{t("users_subtitle")}</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input-field w-full pl-9"
              placeholder={t("search_users")}
            />
          </div>
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="input-field"
          >
            <option value="">{t("role")}</option>
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          <button onClick={() => setShowCreate(true)} className="btn-primary flex-shrink-0">
            <Plus className="w-4 h-4" /> {t("add_user")}
          </button>
        </div>
      </header>

      {loading ? (
        <div className="flex items-center justify-center min-h-[40vh] text-text-muted">
          <RefreshCw className="w-6 h-6 animate-spin text-accent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-panel p-10 text-center text-text-muted">
          <UserCog className="w-8 h-8 mx-auto mb-3 opacity-50" />
          {t("no_users_found")}
        </div>
      ) : (
        <div className="glass-panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-surface/95 backdrop-blur">
                <tr className="text-left text-text-muted border-b border-border">
                  <th className="py-3 px-4 font-medium">{t("name")}</th>
                  <th className="py-3 px-4 font-medium">{t("email")}</th>
                  <th className="py-3 px-4 font-medium">{t("role")}</th>
                  <th className="py-3 px-4 font-medium">{t("college")}</th>
                  <th className="py-3 px-4 font-medium text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((u) => (
                  <tr key={u.id} className="hover:bg-surface/50 transition-colors border-b border-border/40 last:border-0">
                    <td className="py-3 px-4 font-medium text-text-main">{u.name}</td>
                    <td className="py-3 px-4 text-text-muted">{u.email}</td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-accent text-accent-text">
                        {u.role}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-text-muted">{u.college_id || "—"}</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center justify-end">
                        <button
                          onClick={() => deleteUser(u)}
                          className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/10 transition-colors"
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
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="glass-panel w-full max-w-md p-6">
            <h2 className="text-lg font-semibold text-text-main mb-4">{t("add_user")}</h2>
            <div className="space-y-3">
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="input-field w-full"
                placeholder={t("full_name")}
              />
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="input-field w-full"
                placeholder={t("email")}
              />
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="input-field w-full"
                placeholder={t("password")}
              />
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="input-field w-full"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
              <input
                value={form.college_id}
                onChange={(e) => setForm({ ...form, college_id: e.target.value })}
                className="input-field w-full"
                placeholder={t("college")}
              />
            </div>
            <div className="flex justify-end gap-3 mt-5">
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
    </div>
  );
}

