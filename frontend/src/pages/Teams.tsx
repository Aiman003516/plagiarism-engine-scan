import { useState, useEffect } from "react";
import { Users, RefreshCw, Search, Trash2, Plus, X, Loader2, UserPlus, GraduationCap, CheckCircle2, KeyRound, Unlock, Lock } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { teamsApi, TeamData } from "../lib/api";
import { useTeamsCache } from "../lib/useTeamsCache";

interface SearchStudentResult {
  id: string;
  name: string;
  enrollment_number: string;
  department?: string | null;
  college?: string | null;
  university?: string | null;
  team_id?: string | null;
  team_name?: string | null;
}

export default function Teams() {
  const { t } = useTranslation();
  const { teams, loading, error, refresh: load } = useTeamsCache();
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [activeTeam, setActiveTeam] = useState<TeamData | null>(null);
  const [enrollment, setEnrollment] = useState("");
  const [saving, setSaving] = useState(false);

  // Live student search state
  const [studentQuery, setStudentQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchStudentResult[]>([]);
  const [searchingStudents, setSearchingStudents] = useState(false);

  const openTeam = async (team: TeamData) => {
    try {
      const detail = await teamsApi.getById(team.id);
      setActiveTeam(detail);
      setStudentQuery("");
      setSearchResults([]);
      setEnrollment("");
    } catch (e: any) {
      toast.error(e?.message || "Failed to load team");
    }
  };

  const createTeam = async () => {
    if (!newName.trim()) {
      toast.error(t("team_name"));
      return;
    }
    setSaving(true);
    try {
      await teamsApi.create({ name: newName.trim() });
      toast.success(t("create_team"));
      setNewName("");
      setShowCreate(false);
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to create team");
    } finally {
      setSaving(false);
    }
  };

  // Debounced live student search
  useEffect(() => {
    if (!activeTeam || !studentQuery.trim() || studentQuery.trim().length < 2) {
      setSearchResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setSearchingStudents(true);
      try {
        const res = await teamsApi.searchStudents(studentQuery.trim());
        setSearchResults(res.students || []);
      } catch (e) {
        console.error("Student search error", e);
      } finally {
        setSearchingStudents(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [studentQuery, activeTeam]);

  const addMemberByEnrollment = async (enrollNumber: string) => {
    if (!activeTeam || !enrollNumber.trim()) return;
    setSaving(true);
    try {
      await teamsApi.addMember(activeTeam.id, enrollNumber.trim());
      toast.success(t("add_member"));
      setEnrollment("");
      setStudentQuery("");
      setSearchResults([]);
      openTeam(activeTeam);
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to add member");
    } finally {
      setSaving(false);
    }
  };

  const removeMember = async (studentId: string) => {
    if (!activeTeam) return;
    try {
      await teamsApi.removeMember(activeTeam.id, studentId);
      toast.success(t("delete_success"));
      openTeam(activeTeam);
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to remove member");
    }
  };

  const deleteTeam = async (team: TeamData) => {
    if (!window.confirm(t("confirm_delete"))) return;
    try {
      await teamsApi.delete(team.id);
      toast.success(t("delete_success"));
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to delete team");
    }
  };

  const toggleSubmission = async (team: TeamData) => {
    try {
      const updated = await teamsApi.toggleSubmission(team.id, !team.submission_allowed);
      toast.success(
        updated.submission_allowed
          ? `One-time proposal submission granted to ${team.name}`
          : `Submission token revoked for ${team.name}`
      );
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to update submission permission");
    }
  };

  const userStr = localStorage.getItem("user_data") || localStorage.getItem("user");
  let userRole = "";
  try {
    userRole = JSON.parse(userStr || "{}").role || "";
  } catch {}
  const canManageSubmissions = ["faculty", "college_admin", "university_admin", "ministry_admin"].includes(userRole);

  const filtered = teams.filter(
    (team) =>
      !search.trim() ||
      (team.name || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <header className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-text-main">
            {t("teams_title")}
          </h1>
          <p className="text-text-muted mt-1">{t("teams_subtitle")}</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input-field w-full pl-9"
              placeholder={t("search_members")}
            />
          </div>
          {canManageSubmissions && (
            <button onClick={() => setShowCreate(true)} className="btn-primary flex-shrink-0">
              <Plus className="w-4 h-4" /> {t("add_team")}
            </button>
          )}
        </div>
      </header>

      {loading ? (
        <div className="flex items-center justify-center min-h-[40vh] text-text-muted">
          <RefreshCw className="w-6 h-6 animate-spin text-accent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-panel p-10 text-center text-text-muted rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
          <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-500/10 text-teal-500">
            <Users className="w-6 h-6" />
          </span>
          {t("no_teams_found")}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((team) => (
            <div
              key={team.id}
              className="glass-card rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-teal-500/10 text-teal-500 flex items-center justify-center">
                    <Users className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-text-main">{team.name}</h3>
                    <p className="text-xs text-text-muted">
                      {t("members")}: {team.member_count ?? team.members?.length ?? 0}
                    </p>
                  </div>
                </div>
                {canManageSubmissions && (
                  <button
                    onClick={() => deleteTeam(team)}
                    className="btn-danger-icon"
                    title={t("delete")}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>

              {/* One-Time Submission Permission Status */}
              <div className="mt-3 pt-3 border-t border-glass-border flex items-center justify-between text-xs">
                <span className="text-text-muted text-[11px]">Proposal Submission:</span>
                {team.submission_allowed ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                    <Unlock className="w-3 h-3" /> Token Active
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-surface text-text-muted border border-glass-border">
                    <Lock className="w-3 h-3 text-amber-500" /> Locked
                  </span>
                )}
              </div>

              {canManageSubmissions && (
                <button
                  onClick={() => toggleSubmission(team)}
                  className={`mt-2.5 w-full py-1.5 px-3 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-all shadow-sm ${
                    team.submission_allowed
                      ? "bg-red-500/10 hover:bg-red-500/20 text-red-600 dark:text-red-400 border border-red-500/25"
                      : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25"
                  }`}
                >
                  <KeyRound className="w-3.5 h-3.5" />
                  {team.submission_allowed ? "Revoke Proposal Token" : "Grant 1-Time Proposal Submission"}
                </button>
              )}

              <button
                onClick={() => openTeam(team)}
                className="btn-secondary mt-2.5 w-full py-2 text-sm"
              >
                {t("members")}
              </button>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-md p-6 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800">
            <h2 className="text-lg font-semibold text-text-main mb-4">{t("add_team")}</h2>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("team_name")}
            </label>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="input-field w-full"
              placeholder={t("team_name")}
            />
            <div className="flex justify-end gap-3 mt-5">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded-lg text-sm text-text-muted hover:bg-surface"
              >
                {t("cancel")}
              </button>
              <button onClick={createTeam} disabled={saving} className="btn-primary">
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {t("create_team")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Team Detail & Member Ingestion Modal */}
      {activeTeam && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-2xl max-h-[85vh] flex flex-col rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <div className="flex items-center gap-2">
                <Users className="w-5 h-5 text-teal-500" />
                <h2 className="text-lg font-bold text-text-main">{activeTeam.name}</h2>
              </div>
              <button
                onClick={() => setActiveTeam(null)}
                className="p-1.5 rounded-lg text-text-muted hover:bg-surface"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 space-y-5 overflow-y-auto flex-1">
              {/* Interactive Student Search & Quick Add */}
              {canManageSubmissions && (
                <div className="p-4 rounded-xl bg-surface/50 border border-border/60">
                <label className="block text-xs font-semibold text-text-muted uppercase mb-2">
                  Search & Add Student to Team
                </label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                  <input
                    value={studentQuery}
                    onChange={(e) => setStudentQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && studentQuery.trim()) {
                        addMemberByEnrollment(studentQuery.trim());
                      }
                    }}
                    className="input-field w-full pl-9 pr-24 text-sm"
                    placeholder="Search by student name or enrollment number..."
                  />
                  {searchingStudents && (
                    <RefreshCw className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted animate-spin" />
                  )}
                </div>

                {/* Live Autocomplete Results */}
                {searchResults.length > 0 && (
                  <div className="mt-2 max-h-48 overflow-y-auto rounded-xl border border-border bg-card shadow-lg divide-y divide-border/50">
                    {searchResults.map((stu) => {
                      const isAlreadyInThisTeam = activeTeam.members?.some(
                        (m) => m.enrollment_number === stu.enrollment_number
                      );
                      const isAssignedOtherTeam = !!stu.team_id && stu.team_id !== activeTeam.id;

                      return (
                        <div
                          key={stu.id}
                          className="p-2.5 flex items-center justify-between hover:bg-surface/60 transition-colors"
                        >
                          <div className="min-w-0 pr-2">
                            <div className="font-medium text-sm text-text-main truncate flex items-center gap-1.5">
                              <GraduationCap className="w-3.5 h-3.5 text-primary shrink-0" />
                              {stu.name}
                            </div>
                            <div className="text-xs text-text-muted font-mono flex items-center gap-2 mt-0.5">
                              <span className="text-primary">{stu.enrollment_number}</span>
                              {stu.department && <span>• {stu.department}</span>}
                              {stu.college && <span>• {stu.college}</span>}
                            </div>
                          </div>

                          <div className="flex items-center gap-2 flex-shrink-0">
                            {isAlreadyInThisTeam ? (
                              <span className="text-[11px] font-semibold text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded">
                                Current Member
                              </span>
                            ) : isAssignedOtherTeam ? (
                              <span className="text-[11px] text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded">
                                In {stu.team_name || "Another Team"}
                              </span>
                            ) : (
                              <button
                                onClick={() => addMemberByEnrollment(stu.enrollment_number)}
                                disabled={saving}
                                className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-primary text-primary-text hover:opacity-90 transition-all flex items-center gap-1"
                              >
                                <UserPlus className="w-3 h-3" /> Add
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
                {studentQuery.trim().length >= 2 && !searchingStudents && searchResults.length === 0 && (
                  <p className="text-xs text-text-muted mt-2 px-1">
                    No students found matching "{studentQuery}". You can also enter an enrollment ID directly.
                  </p>
                )}
              </div>
              )}

              {/* Current Team Members List */}
              <div>
                <h3 className="text-sm font-semibold text-text-main mb-2.5 flex items-center justify-between">
                  <span>Current Team Members</span>
                  <span className="text-xs font-medium text-text-muted">
                    {activeTeam.members?.length ?? 0} Members
                  </span>
                </h3>

                {!activeTeam.members || activeTeam.members.length === 0 ? (
                  <div className="p-8 text-center text-text-muted bg-surface/30 rounded-xl border border-border/40">
                    <Users className="w-8 h-8 mx-auto mb-2 opacity-40 text-teal-500" />
                    <p className="text-sm font-medium">No members added yet</p>
                    <p className="text-xs mt-1">Use the search box above to add students by name or enrollment ID.</p>
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {activeTeam.members.map((m) => (
                      <li
                        key={m.id}
                        className="flex items-center gap-3 px-3.5 py-2.5 rounded-xl bg-surface/50 border border-border/60 hover:bg-surface/80 transition-colors"
                      >
                        <div className="w-8 h-8 rounded-lg bg-teal-500/10 text-teal-500 flex items-center justify-center font-bold text-xs shrink-0">
                          {m.name.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-text-main text-sm truncate">{m.name}</div>
                          <div className="text-xs text-text-muted font-mono">{m.enrollment_number}</div>
                        </div>
                        {canManageSubmissions && (
                          <button
                            onClick={() => removeMember(m.id)}
                            className="btn-danger-icon"
                            title={t("remove")}
                          >
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
