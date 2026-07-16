import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "../store/auth";

export default function ProtectedRoute() {
  const location = useLocation();
  const apiKey = useAuthStore((s) => s.apiKey);
  const projectId = useAuthStore((s) => s.projectId);

  if (!apiKey || !projectId) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <Outlet />;
}
