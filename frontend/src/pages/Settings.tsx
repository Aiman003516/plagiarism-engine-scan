import { useEffect, useState } from "react";
import { Save, Loader2, Globe, Gauge } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { settingsApi, SettingsMap } from "../lib/api";

export default function Settings() {
  const { t, i18n } = useTranslation();
  const [settings, setSettings] = useState<SettingsMap>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setSettings(await settingsApi.getAll());
      } catch (e: any) {
        toast.error(e?.message || "Failed to load settings");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const updated = await settingsApi.update(settings);
      setSettings(updated);
      toast.success(t("settings_saved"));
    } catch (e: any) {
      toast.error(e?.message || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const setValue = (key: string, value: any) =>
    setSettings((s) => ({ ...s, [key]: value }));

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh] text-text-muted">
        <Loader2 className="w-6 h-6 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <header className="mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-text-main">
          {t("settings_title")}
        </h1>
        <p className="text-text-muted mt-1">{t("settings_subtitle")}</p>
      </header>

      <section className="glass-panel p-6 space-y-6">
        <h2 className="text-lg font-semibold text-text-main flex items-center gap-2">
          <Gauge className="w-4 h-4 text-accent-text bg-accent rounded p-0.5" />
          {t("system_config")}
        </h2>

        <div>
          <label className="block text-sm font-medium text-text-main mb-2">
            {t("similarity_threshold")}
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={0}
              max={100}
              value={Number(settings.similarity_threshold ?? 0)}
              onChange={(e) => setValue("similarity_threshold", Number(e.target.value))}
              className="flex-1 accent-[var(--color-primary)]"
            />
            <span className="text-sm font-semibold text-text-main w-12 text-right">
              {Number(settings.similarity_threshold ?? 0)}%
            </span>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-text-main mb-2">
            {t("max_upload_size_mb")}
          </label>
          <input
            type="number"
            value={Number(settings.max_upload_size_mb ?? 0)}
            onChange={(e) => setValue("max_upload_size_mb", Number(e.target.value))}
            className="input-field w-full"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-text-main mb-2 flex items-center gap-2">
            <Globe className="w-4 h-4 text-text-muted" />
            {t("default_language")}
          </label>
          <select
            value={String(settings.default_language ?? "en")}
            onChange={(e) => setValue("default_language", e.target.value)}
            className="input-field w-full"
          >
            <option value="en">{t("english")}</option>
            <option value="ar">{t("arabic")}</option>
          </select>
        </div>
      </section>

      <section className="glass-panel p-6 mt-4 space-y-4">
        <h2 className="text-lg font-semibold text-text-main">{t("appearance")}</h2>
        <div>
          <label className="block text-sm font-medium text-text-main mb-2">
            {t("language")}
          </label>
          <select
            value={i18n.language}
            onChange={(e) => i18n.changeLanguage(e.target.value)}
            className="input-field w-full"
          >
            <option value="en">{t("english")}</option>
            <option value="ar">{t("arabic")}</option>
          </select>
        </div>
      </section>

      <div className="mt-6 flex justify-end">
        <button onClick={save} disabled={saving} className="btn-primary">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {t("save_settings")}
        </button>
      </div>
    </div>
  );
}
