import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { Shield, Mail, Lock, User, Loader2 } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../lib/api";

const ROLES = [
  { value: "ministry_admin", label: "Ministry Admin" },
  { value: "college_admin", label: "College Admin" },
  { value: "student", label: "Student" },
];

export default function Register() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    role: "college_admin",
    college_id: "",
  });
  const [loading, setLoading] = useState(false);

  const update = (key: string, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim() || !form.password) {
      toast.error(t("invalid_credentials"));
      return;
    }
    setLoading(true);
    try {
      const res = await authApi.register({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
        college_id: form.college_id || undefined,
      });
      localStorage.setItem("auth_token", res.token);
      localStorage.setItem("user_data", JSON.stringify(res.user));
      toast.success(t("register_success"));
      navigate("/dashboard");
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
            <Shield className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold text-text-main">{t("register_title")}</h1>
          <p className="text-sm text-text-muted mt-1">{t("register_subtitle")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("full_name")}
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="text"
                value={form.name}
                onChange={(e) => update("name", e.target.value)}
                className="input-field w-full pl-9"
                placeholder={t("full_name")}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("login_email")}
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="email"
                value={form.email}
                onChange={(e) => update("email", e.target.value)}
                className="input-field w-full pl-9"
                placeholder={t("login_email")}
                autoComplete="email"
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
                value={form.password}
                onChange={(e) => update("password", e.target.value)}
                className="input-field w-full pl-9"
                placeholder={t("password")}
                autoComplete="new-password"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("role")}
            </label>
            <select
              value={form.role}
              onChange={(e) => update("role", e.target.value)}
              className="input-field w-full"
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-main mb-1.5">
              {t("college")}
            </label>
            <input
              type="text"
              value={form.college_id}
              onChange={(e) => update("college_id", e.target.value)}
              className="input-field w-full"
              placeholder={t("college")}
            />
          </div>

          <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : t("sign_up")}
          </button>
        </form>

        <p className="text-sm text-text-muted text-center mt-6">
          {t("have_account")}{" "}
          <Link to="/login" className="text-primary font-medium hover:underline">
            {t("sign_in")}
          </Link>
        </p>
      </motion.div>
    </div>
  );
}
