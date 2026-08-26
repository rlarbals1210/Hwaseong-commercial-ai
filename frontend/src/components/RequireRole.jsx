import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/auth-context";
import { safeNext } from "../lib/officialRoutes";

export default function RequireRole({ role, children }) {
  const { isAuthenticated, role: currentRole } = useAuth();
  const { pathname } = useLocation();
  if (!isAuthenticated || currentRole !== role) {
    // 가려던 경로를 들고 간다 — 로그인 뒤 다시 찾아 들어가게 하지 않는다.
    // 화이트리스트 밖(예: /cells/:id)이면 next를 붙이지 않고 기본 흐름을 탄다.
    const next = safeNext(pathname, null);
    const to = next ? `/login/official?next=${encodeURIComponent(next)}` : "/login/official";
    return <Navigate to={to} replace />;
  }
  return children;
}
