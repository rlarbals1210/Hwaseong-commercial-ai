import { Routes, Route, Link, useLocation } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import MapPage from "./pages/MapPage";
import PolicyPage from "./pages/PolicyPage";
import ConsultPage from "./pages/ConsultPage";

const NAV = [
  { path: "/", label: "조기경보 대시보드" },
  { path: "/map", label: "공실위험 지도" },
  { path: "/policy", label: "정책자금 우선순위" },
  { path: "/consult", label: "창업 상담" },
];

export default function App() {
  const { pathname } = useLocation();

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
        {NAV.map(({ path, label }) => (
          <Link key={path} to={path} style={{
            color: pathname === path ? "#60A5FA" : "#CBD5E1",
            textDecoration: "none", fontSize: 13, fontWeight: pathname === path ? 700 : 400,
            borderBottom: pathname === path ? "2px solid #60A5FA" : "2px solid transparent",
            paddingBottom: 2,
          }}>
            {label}
          </Link>
        ))}
      </nav>

      <main style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 16px" }}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/policy" element={<PolicyPage />} />
          <Route path="/consult" element={<ConsultPage />} />
        </Routes>
      </main>
    </div>
  );
}
