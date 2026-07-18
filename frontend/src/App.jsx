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
  { path: "/dashboard", label: "조기경보 대시보드", role: "official", Component: DashboardPage },
  { path: "/map", label: "공실위험 지도", role: "official", Component: MapPage },
  { path: "/policy", label: "정책자금 우선순위", role: "official", Component: PolicyPage },
  { path: "/consult", label: "창업 상담", role: "citizen", Component: ConsultPage },
];

export default function App() {
  const { pathname } = useLocation();
  const { isAuthenticated, role, logout } = useAuth();
  const navigate = useNavigate();
  const visibleNav = NAV.filter((n) => n.role === role);

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  return (
    <div style={{ minHeight: "100vh", background: "#F8FAFC", fontFamily: "'Pretendard', 'Apple SD Gothic Neo', sans-serif" }}>
      <nav style={{
        background: "#1E3A5F", color: "#fff", padding: "0 24px",
        display: "flex", alignItems: "center", gap: 32, height: 56,
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <span style={{ fontWeight: 700, fontSize: 15, whiteSpace: "nowrap" }}>
          화성시 소상공인 AI
        </span>
        {visibleNav.map(({ path, label }) => (
          <Link key={path} to={path} style={{
            color: pathname === path ? "#60A5FA" : "#CBD5E1",
            textDecoration: "none", fontSize: 13, fontWeight: pathname === path ? 700 : 400,
            borderBottom: pathname === path ? "2px solid #60A5FA" : "2px solid transparent",
            paddingBottom: 2,
          }}>
            {label}
          </Link>
        ))}
        {isAuthenticated && (
          <button
            onClick={handleLogout}
            style={{
              marginLeft: "auto", background: "none", border: "none", color: "#CBD5E1",
              fontSize: 13, cursor: "pointer", padding: 0,
            }}
          >
            로그아웃
          </button>
        )}
      </nav>

      <main style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 16px" }}>
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
      </main>
    </div>
  );
}
