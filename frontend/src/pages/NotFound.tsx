import { ShieldCheck, ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center">
      <div className="w-16 h-16 rounded-2xl bg-accent text-accent-text flex items-center justify-center mb-4">
        <ShieldCheck className="w-8 h-8" />
      </div>
      <h1 className="text-4xl font-bold text-text-main mb-2">404</h1>
      <p className="text-lg text-text-muted mb-1">{t("not_found_title")}</p>
      <p className="text-sm text-text-muted mb-6">{t("not_found_desc")}</p>
      <Link to="/dashboard" className="btn-primary">
        <ArrowLeft className="w-4 h-4" />
        {t("back_home")}
      </Link>
    </div>
  );
}
