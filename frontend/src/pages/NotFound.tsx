import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center">
      <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-4 p-2.5 shadow-sm overflow-hidden">
        <img src="/favicon.svg" alt="NAZAHA Logo" className="w-full h-full object-contain" />
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
