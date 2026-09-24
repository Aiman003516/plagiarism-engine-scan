import { useEffect, useState } from "react";
import { Users, RefreshCw, Search, Trash2, Plus, X, Loader2 } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { teamsApi, TeamData } from "../lib/api";

export default function Teams() {
  const { t } = useTranslation();
  const [teams, setTeams] = useState<TeamData[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [activeTeam, setActiveTeam] = useState<TeamData | null>(null);
  const [enrollment, setEnrollment] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await teamsApi.getAll();
      setTeams(res.teams || []);
    } catch (e: any) {
      toast.error(e?.message || "Failed to load teams");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openTeam = async (team: TeamData) => {
    try {
      const detail = await teamsApi.getById(team.id);
      setActiveTeam(detail);
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

  const addMember = async () => {
    if (!activeTeam || !enrollment.trim()) return;
    setSaving(true);
    try {
      await teamsApi.addMember(activeTeam.id, enrollment.trim());
      toast.success(t("add_member"));
      setEnrollment("");
      openTeam(activeTeam);
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
          <button onClick={() => setShowCreate(true)} className="btn-primary flex-shrink-0">
            <Plus className="w-4 h-4" /> {t("add_team")}
          </button>
        </div>
      </header>

      {loading ? (
        <div className="flex items-center justify-center min-h-[40vh] text-text-muted">
          <RefreshCw className="w-6 h-6 animate-spin text-accent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-panel p-10 text-center text-text-muted">
          <Users className="w-8 h-8 mx-auto mb-3 opacity-50" />
          {t("no_teams_found")}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((team) => (
            <div key={team.id} className="glass-card">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-primary text-primary-text flex items-center justify-center">
                    <Users className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-text-main">{team.name}</h3>
                    <p className="text-xs text-text-muted">
                      {t("members")}: {team.members?.length ?? 0}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => deleteTeam(team)}
                  className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/10 transition-colors"
                  title={t("delete")}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
              <button
                onClick={() => openTeam(team)}
                className="mt-4 w-full py-2 rounded-lg border border-border text-sm text-text-main hover:bg-surface/50 transition-colors"
              >
                {t("members")}
              </button>
            </div>
          ))}
        </div>
      )}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="glass-panel w-full max-w-md p-6">
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

      {activeTeam && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="glass-panel w-full max-w-xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h2 className="text-lg font-semibold text-text-main">{activeTeam.name}</h2>
              <button
                onClick={() => setActiveTeam(null)}
                className="p-1.5 rounded-lg text-text-muted hover:bg-text-muted/10"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 space-y-4 overflow-y-auto flex-1">
              <div className="flex gap-2">
                <input
                  value={enrollment}
                  onChange={(e) => setEnrollment(e.target.value)}
                  className="input-field flex-1"
                  placeholder={t("enrollment_number")}
                />
                <button onClick={addMember} disabled={saving} className="btn-primary flex-shrink-0">
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} {t("add_member")}
                </button>
              </div>

              <div>
                <h3 className="text-sm font-medium text-text-main mb-2">{t("members")}</h3>
                {!activeTeam.members || activeTeam.members.length === 0 ? (
                  <p className="text-text-muted text-sm text-center py-6">{t("no_members")}</p>
                ) : (
                  <ul className="space-y-2">
                    {activeTeam.members.map((m) => (
                      <li
                        key={m.id}
                        className="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface/50 border border-border/50"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-text-main text-sm truncate">{m.name}</div>
                          <div className="text-xs text-text-muted">{m.enrollment_number}</div>
                        </div>
                        <button
                          onClick={() => removeMember(m.id)}
                          className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/10"
                          title={t("remove")}
                        >
                          <X className="w-4 h-4" />
                        </button>
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

