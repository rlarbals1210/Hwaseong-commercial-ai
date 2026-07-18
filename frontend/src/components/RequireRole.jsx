import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function RequireRole({ role, children }) {
  const { isAuthenticated, role: currentRole } = useAuth();
  if (!isAuthenticated || currentRole !== role) {
    return <Navigate to="/" replace />;
  }
  return children;
}
