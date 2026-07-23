import { Routes, Route, Link, useLocation, useNavigate } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import MapPage from "./pages/MapPage";
import PolicyPage from "./pages/PolicyPage";
import ConsultPage from "./pages/ConsultPage";
import RoleSelectPage from "./pages/RoleSelectPage";
import OfficialLoginPage from "./pages/OfficialLoginPage";
import CitizenLoginPage from "./pages/CitizenLoginPage";
import RequireRole from "./components/RequireRole";
import { useAuth } from "./context/AuthContext";

const NAV = [
  { path: "/dashboard", label: "조기경보 대시보드", icon: "dashboard", role: "official", Component: DashboardPage },
  { path: "/map", label: "공실위험 지도", icon: "map", role: "official", Component: MapPage },
  { path: "/policy", label: "정책자금 우선순위", icon: "grid_view", role: "official", Component: PolicyPage },
  { path: "/consult", label: "창업 상담", icon: "chat_bubble", role: "citizen", Component: ConsultPage },
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
  const visibleNav = NAV.filter((n) => n.role === role);
  const isOfficialShell = role === "official";

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const routes = (
    <Routes>
      <Route path="/" element={<RoleSelectPage />} />
      <Route path="/login/official" element={<OfficialLoginPage />} />
      <Route path="/login/citizen" element={<CitizenLoginPage />} />
      {NAV.map(({ path, role, Component }) => (
        <Route
          key={path}
          path={path}
          element={
            <RequireRole role={role}>
              <Component />
            </RequireRole>
          }
        />
      ))}
    </Routes>
  );

  if (isOfficialShell) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>
        <Sidebar nav={visibleNav} pathname={pathname} username={username} onLogout={handleLogout} />
        <main style={{ marginLeft: 240, maxWidth: 1440, padding: "32px 40px", boxSizing: "border-box" }}>{routes}</main>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>
      <nav
        className="print-hide"
        style={{
          background: "var(--primary)",
          color: "#fff",
          padding: "0 24px",
          display: "flex",
          alignItems: "center",
          gap: 32,
          height: 56,
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 15, whiteSpace: "nowrap" }}>화성시 소상공인 AI</span>
        {visibleNav.map(({ path, label }) => (
          <Link
            key={path}
            to={path}
            style={{
              color: pathname === path ? "var(--secondary-container)" : "rgba(255,255,255,0.75)",
              textDecoration: "none",
              fontSize: 13,
              fontWeight: pathname === path ? 700 : 400,
              borderBottom: pathname === path ? "2px solid var(--secondary-container)" : "2px solid transparent",
              paddingBottom: 2,
            }}
          >
            {label}
          </Link>
        ))}
        {isAuthenticated && (
          <button
            onClick={handleLogout}
            style={{
              marginLeft: "auto",
              background: "none",
              border: "none",
              color: "rgba(255,255,255,0.75)",
              fontSize: 13,
              cursor: "pointer",
              padding: 0,
            }}
          >
            로그아웃
          </button>
        )}
      </nav>

      <main style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 16px" }}>{routes}</main>
    </div>
  );
}
