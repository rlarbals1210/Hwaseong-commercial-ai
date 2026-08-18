import { Routes, Route, Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import MapPage from "./pages/MapPage";
import PolicyPage from "./pages/PolicyPage";
import OfficialLoginPage from "./pages/OfficialLoginPage";
import RequireRole from "./components/RequireRole";
import { useAuth } from "./context/auth-context";

// 공무원 정책 의사결정 지원 전용.
// 시민(소상공인) 직접조회 화면은 2026-08-18 설계 결정으로 제외했다 — 상세 사유는 CLAUDE.md '설계 결정' 절 참조.
const NAV = [
  { path: "/dashboard", label: "조기경보 대시보드", icon: "dashboard", Component: DashboardPage },
  { path: "/map", label: "공실위험 지도", icon: "map", Component: MapPage },
  { path: "/policy", label: "현장점검 우선순위", icon: "grid_view", Component: PolicyPage },
];

function Sidebar({ nav, pathname, username, onLogout }) {
  const initials = username ? username.slice(0, 2).toUpperCase() : "?";

  return (
    <aside
      style={{
        position: "fixed",
        left: 0,
        top: 0,
        width: 240,
        height: "100vh",
        background: "var(--primary)",
        color: "#fff",
        display: "flex",
        flexDirection: "column",
        padding: "24px 16px",
        boxSizing: "border-box",
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 24, paddingLeft: 8 }}>Reverse Nodaji</div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: 12,
          borderRadius: 8,
          background: "rgba(255,255,255,0.08)",
          marginBottom: 24,
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: "var(--secondary-container)",
            color: "var(--on-secondary-container)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 13,
            fontWeight: 700,
            flexShrink: 0,
          }}
        >
          {initials}
        </div>
        <div style={{ overflow: "hidden" }}>
          <div style={{ fontSize: 13, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {username || "공무원"}
          </div>
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.6)" }}>공무원 계정</div>
        </div>
      </div>

      <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {nav.map(({ path, label, icon }) => {
          const active = pathname === path;
          return (
            <Link
              key={path}
              to={path}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "10px 12px",
                borderRadius: 8,
                textDecoration: "none",
                color: active ? "var(--on-secondary-container)" : "rgba(255,255,255,0.75)",
                background: active ? "var(--secondary-container)" : "transparent",
                fontSize: 14,
                fontWeight: active ? 700 : 400,
                borderLeft: active ? "3px solid #fff" : "3px solid transparent",
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
                {icon}
              </span>
              {label}
            </Link>
          );
        })}
      </nav>

      <button
        onClick={onLogout}
        style={{
          marginTop: "auto",
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 12px",
          borderRadius: 8,
          background: "none",
          border: "none",
          color: "rgba(255,255,255,0.75)",
          fontSize: 14,
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
          logout
        </span>
        로그아웃
      </button>
    </aside>
  );
}

export default function App() {
  const { pathname } = useLocation();
  const { isAuthenticated, role, username, logout } = useAuth();
  const navigate = useNavigate();
  const isOfficial = isAuthenticated && role === "official";

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const loginElement = isOfficial ? <Navigate to="/dashboard" replace /> : <OfficialLoginPage />;

  const routes = (
    <Routes>
      <Route path="/" element={loginElement} />
      <Route path="/login/official" element={loginElement} />
      {NAV.map(({ path, Component }) => (
        <Route
          key={path}
          path={path}
          element={
            <RequireRole role="official">
              <Component />
            </RequireRole>
          }
        />
      ))}
    </Routes>
  );

  if (isOfficial) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>
        <Sidebar nav={NAV} pathname={pathname} username={username} onLogout={handleLogout} />
        <main style={{ marginLeft: 240, maxWidth: 1440, padding: "32px 40px", boxSizing: "border-box" }}>{routes}</main>
      </div>
    );
  }

  // 미인증 상태: 로그인 화면이 자체 전체화면 레이아웃을 가지므로 셸을 씌우지 않는다.
  return <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>{routes}</div>;
}
