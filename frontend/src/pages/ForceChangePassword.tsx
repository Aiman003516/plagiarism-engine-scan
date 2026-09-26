/**
 * ForceChangePassword — mandatory password rotation screen.
 *
 * Reached from /login or /register when the backend reports
 * `requires_password_change: true` (provisioned student accounts, or accounts
 * an admin flagged for a reset). Calls POST /api/auth/change-password and, on
 * success, stores the freshly issued token (flag cleared) and enters the app.
 */

import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { ShieldCheck, Lock, Loader2 } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../lib/api";

export default function ForceChangePassword() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  // /login and /register forward the password the user just authenticated
  // with, so the endpoint's required `old_password` is already known. When the
  // page is opened directly (no router state) we ask for it explicitly.
  const forwardedOldPassword =
    (location.state as { oldPassword?: string } | null)?.oldPassword ?? "";

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const oldPassword = forwardedOldPassword || currentPassword;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!oldPassword) {
      toast.error(t("invalid_credentials"));
      return;
    }
    if (newPassword.length < 8) {
      toast.error(t("password_too_short"));
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error(t("password_mismatch"));
      return;
    }
    if (newPassword === oldPassword) {
      toast.error(t("password_same_as_old"));
      return;
    }

    setLoading(true);
    try {
      const res = await authApi.changePassword(oldPassword, newPassword);

      // The response carries a new JWT with requires_password_change cleared.
      if (res.token) localStorage.setItem("auth_token", res.token);

      // Keep the cached profile in sync so nothing re-triggers the redirect.
      const cached = localStorage.getItem("user_data");
      if (cached) {
        try {
          const user = JSON.parse(cached);
          user.requires_password_change = false;
          localStorage.setItem("user_data", JSON.stringify(user));
        } catch {
          // Corrupt cache entry — drop it rather than persist a stale flag.
          localStorage.removeItem("user_data");
        }
      }

      toast.success(t("password_changed"));
      navigate("/dashboard", { replace: true });
    } catch (err: any) {
      toast.error(err?.message || t("invalid_credentials"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md glass-panel p-8"
      >
        <div className="flex flex-col items-center mb-6">
          <div className="w-12 h-12 rounded-2xl bg-primary text-primary-text flex items-center justify-center mb-3">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold text-text-main">
            {t("force_password_title")}
          </h1>
          <p className="text-sm text-text-muted mt-1 text-center">
            {t("force_password_subtitle")}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Only shown when we did not receive the old password via router state. */}
          {!forwardedOldPassword && (
            <div>
              <label className="block text-sm font-medium text-text-main mb-1.5">
                {t("current_password")}
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="input-field w-full pl-9"
                  placeholder={t("current_password")}
                  autoComplete="current-password"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("new_password")}
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="input-field w-full pl-9"
                placeholder={t("new_password")}
                autoComplete="new-password"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("confirm_password")}
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="input-field w-full pl-9"
                placeholder={t("confirm_password")}
                autoComplete="new-password"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-2.5"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              t("update_password")
            )}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
