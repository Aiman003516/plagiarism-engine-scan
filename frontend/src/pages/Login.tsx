import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { Shield, Mail, Lock, Loader2 } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../lib/api";

export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // One field for both identities: an email (staff/admin) or an enrollment ID
  // (student). The backend resolves it against the users then students table.
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

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
        navigate("/dashboard");
      }
    } catch (err: any) {
      toast.error(err?.message || t("invalid_credentials"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-background p-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md glass-panel p-8"
      >
        <div className="flex flex-col items-center mb-6">
          <div className="w-12 h-12 rounded-2xl bg-primary text-primary-text flex items-center justify-center mb-3">
            <Shield className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold text-text-main">{t("login_title")}</h1>
          <p className="text-sm text-text-muted mt-1">{t("login_subtitle")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("login_identifier")}
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                className="input-field w-full pl-9"
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
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-field w-full pl-9"
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
