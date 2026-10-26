import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Lock, Loader2, Globe, Sun, Moon } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../lib/api";
import { useDarkMode } from "../lib/useTheme";

export default function Login() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [isDark, toggleDarkMode] = useDarkMode();
  // One field for both identities: an email (staff/admin) or an enrollment ID
  // (student). The backend resolves it against the users then students table.
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const toggleLanguage = () => {
    const next = i18n.language === "ar" ? "en" : "ar";
    i18n.changeLanguage(next);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier.trim() || !password) {
      toast.error(t("invalid_credentials"));
      return;
    }
    setLoading(true);
    try {
      const res = await authApi.login(identifier.trim(), password);
      localStorage.setItem("auth_token", res.token);
      localStorage.setItem("user_data", JSON.stringify(res.user));
      toast.success(t("login_success"));
      // Provisioned accounts must rotate their password before using the app.
      if (res.user.requires_password_change) {
        navigate("/force-change-password", {
          state: { oldPassword: password },
        });
      } else {
        if (res.user.role === "student") {
          navigate("/projects");
        } else {
          navigate("/dashboard");
        }
      }
    } catch (err: any) {
      toast.error(err?.message || t("invalid_credentials"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center bg-background p-4">
      {/* Top Floating Controls: Dark Mode & Icon-Only Language Switcher */}
      <div className="absolute top-4 end-4 z-10 flex items-center gap-2">
        <button
          type="button"
          onClick={toggleDarkMode}
          className="p-2.5 rounded-xl border border-border bg-surface/80 backdrop-blur text-text-muted hover:text-text-main hover:bg-surface-hover transition-all duration-200 shadow-sm flex items-center justify-center"
          title={isDark ? (i18n.language === "ar" ? "التبديل إلى الوضع النهاري" : "Switch to Light Mode") : (i18n.language === "ar" ? "التبديل إلى الوضع الليلي" : "Switch to Dark Mode")}
          aria-label="Toggle dark mode"
        >
          {isDark ? (
            <Sun className="w-4 h-4 text-amber-400" />
          ) : (
            <Moon className="w-4 h-4 text-indigo-400" />
          )}
        </button>

        <button
          type="button"
          onClick={toggleLanguage}
          className="p-2.5 rounded-xl border border-border bg-surface/80 backdrop-blur text-primary hover:bg-surface-hover hover:border-primary/40 transition-all duration-200 shadow-sm flex items-center justify-center"
          title={i18n.language === "ar" ? "English" : "العربية"}
          aria-label="Toggle language"
        >
          <Globe className="w-4 h-4 text-primary" />
        </button>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md glass-panel p-8"
      >
        <div className="flex flex-col items-center mb-6">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-3 shadow-md p-2.5 overflow-hidden">
            <img src="/favicon.svg" alt="NAZAHA Logo" className="w-full h-full object-contain" />
          </div>
          <h1 className="text-2xl font-bold text-text-main text-center">{t("login_title")}</h1>
          <p className="text-sm text-text-muted mt-1 text-center">{t("login_subtitle")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("login_identifier")}
            </label>
            <div className="relative">
              <Mail className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                className="input-field w-full ps-9"
                placeholder={t("login_identifier")}
                autoComplete="username"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("password")}
            </label>
            <div className="relative">
              <Lock className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-field w-full ps-9"
                placeholder={t("password")}
                autoComplete="current-password"
              />
            </div>
          </div>

          <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              t("sign_in")
            )}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
