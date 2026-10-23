import { Navigate, Outlet } from "react-router-dom";

interface RoleGuardProps {
  allowedRoles: string[];
}

export default function RoleGuard({ allowedRoles }: RoleGuardProps) {
  const token = localStorage.getItem("auth_token");
  const userStr = localStorage.getItem("user_data") || localStorage.getItem("user");

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (!userStr) {
    // Authenticated token without profile data: allow outlet or fetch profile
    return <Outlet />;
  }

  try {
    const user = JSON.parse(userStr);
    const role = user?.role || "student";
    if (allowedRoles && allowedRoles.length > 0 && !allowedRoles.includes(role)) {
      // Role not allowed: redirect safely based on role
      return <Navigate to={role === "student" ? "/projects" : "/dashboard"} replace />;
    }
  } catch {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
