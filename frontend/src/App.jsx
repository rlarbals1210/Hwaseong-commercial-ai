import { useEffect, useState } from "react";
import { Routes, Route, Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import MapPage from "./pages/MapPage";
import PolicyPage from "./pages/PolicyPage";
import OfficialLoginPage from "./pages/OfficialLoginPage";
import CellDetailPage from "./pages/CellDetailPage";
import BlindspotPage from "./pages/BlindspotPage";
import ComparePage from "./pages/ComparePage";
import BrowsePage from "./pages/BrowsePage";
import TrendPage from "./pages/TrendPage";
import ReportPage from "./pages/ReportPage";
import LandingPage from "./pages/LandingPage";
import RequireRole from "./components/RequireRole";
import OfficialQuickStart from "./components/OfficialQuickStart";
import { useAuth } from "./context/auth-context";
import { apiFetchJson } from "./lib/api";
import { OFFICIAL_ROUTES, safeNext } from "./lib/officialRoutes";

// 공무원 정책 의사결정 지원 전용.
// 시민(소상공인) 직접조회 화면은 2026-08-18 설계 결정으로 제외했다 — 상세 사유는 CLAUDE.md '설계 결정' 절 참조.
// 경로·라벨·아이콘은 lib/officialRoutes.js가 단일 출처다(랜딩 카드가 같은 배열을 쓴다).
// 여기서는 화면 컴포넌트만 짝지어 붙인다.
//   /blindspots — 표본부족으로 다른 화면에서 빠지는 상권(전체 점포의 38%)의 별도 트랙
//   /compare    — 두 상권을 나란히 놓고, 차이가 표본 크기로 설명되면 "차이 없음"으로 표시
const COMPONENTS = {
  "/dashboard": DashboardPage,
  "/map": MapPage,
  "/policy": PolicyPage,
  "/blindspots": BlindspotPage,
  "/compare": ComparePage,
};

const NAV = OFFICIAL_ROUTES.map((route) => ({ ...route, Component: COMPONENTS[route.path] }));

// 공무원 셸은 공개 랜딩·상권 둘러보기와 같은 다크 네이비 계열을 쓴다.
// 데이터 화면의 정보 밀도는 유지하고, 현재 위치와 업무 동선만 색과 깊이로 분명하게 구분한다.
function Sidebar({ nav, pathname, username, onLogout, onOpenQuickStart }) {
  const initials = username ? username.slice(0, 2).toUpperCase() : "?";

  return (
    <aside className="official-sidebar">
      {/* 브랜드 — 로고를 누르면 홈(서비스 소개)으로 */}
      <Link to="/" className="official-brand">
        <div className="official-brand-mark">HS</div>
        <div className="official-brand-copy">
          <strong>화성시 상권 지원</strong>
          <span>소상공인 조기경보</span>
        </div>
      </Link>

      <div className="official-sidebar-divider" />

      <nav className="official-nav" aria-label="공무원 업무 메뉴">
        {nav.map(({ path, label, icon }) => {
          const active = pathname === path;
          return (
            <Link
              key={path}
              to={path}
              data-quickstart-path={path}
              className={`official-nav-link${active ? " active" : ""}`}
              aria-current={active ? "page" : undefined}
              title={label}
            >
              <span className={`material-symbols-outlined${active ? " fill" : ""}`}>
                {icon}
              </span>
              <span className="official-nav-label">{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* 계정 + 로그아웃 */}
      <div className="official-sidebar-footer">
        <div className="official-sidebar-divider" />
        <button
          type="button"
          onClick={onOpenQuickStart}
          className="official-nav-link official-help-button"
          aria-label="현재 화면 사용법"
          title="현재 화면 사용법"
        >
          <span className="material-symbols-outlined">help</span>
          <span className="official-nav-label">현재 화면 사용법</span>
        </button>
        <div className="official-account">
          <div className="official-account-avatar">{initials}</div>
          <div className="official-account-copy">
            <strong>{username || "공무원"}</strong>
            <span>공무원 계정</span>
          </div>
        </div>
        <button
          onClick={onLogout}
          className="official-nav-link official-logout-button"
          aria-label="로그아웃"
          title="로그아웃"
        >
          <span className="material-symbols-outlined">logout</span>
          <span className="official-nav-label">로그아웃</span>
        </button>
      </div>
    </aside>
  );
}

// 데이터 기준 분기 — 하드코딩하지 않고 실제 적재된 최신 분기를 조회한다.
// "이 화면이 언제 기준인가"는 분기 배치로 도는 도구에서 반드시 보여야 할 정보다.
function DataFreshness() {
  const [quarter, setQuarter] = useState(null);

  useEffect(() => {
    apiFetchJson("/api/analysis/quarters")
      .then((d) => {
        const list = d?.quarters ?? [];
        if (list.length) setQuarter(Math.max(...list));
      })
      .catch(() => {});
  }, []);

  if (!quarter) return null;
  const year = Math.floor(quarter / 10);
  const q = quarter % 10;
  return (
    <div className="official-freshness">
      <span className="material-symbols-outlined">database</span>
      <span>
        <b>{year}년 {q}분기</b> 기준
      </span>
    </div>
  );
}

function TopBar({ title }) {
  return (
    <header className="official-topbar">
      <div className="official-topbar-title">{title}</div>
      <DataFreshness />
    </header>
  );
}

// 로그인 없이 열리는 경로. 공무원 셸(사이드바)을 씌우지 않고 전체화면으로 렌더한다.
const PUBLIC_PATHS = ["/", "/browse", "/trends", "/report"];

export default function App() {
  const { pathname, search } = useLocation();
  const { isAuthenticated, role, username, loginSequence, logout } = useAuth();
  const navigate = useNavigate();
  const isOfficial = isAuthenticated && role === "official";
  const isPublicPage = PUBLIC_PATHS.includes(pathname);
  const [manualQuickStartOpen, setManualQuickStartOpen] = useState(false);
  const [dismissedQuickStartKeys, setDismissedQuickStartKeys] = useState(() => new Set());
  const isGuidePath = NAV.some((item) => item.path === pathname);
  const quickStartKey = `${loginSequence}:${pathname}`;
  const shouldAutoOpenQuickStart = isOfficial
    && loginSequence > 0
    && isGuidePath
    && !dismissedQuickStartKeys.has(quickStartKey);
  const quickStartOpen = isOfficial && isGuidePath && (manualQuickStartOpen || shouldAutoOpenQuickStart);

  const closeQuickStart = () => {
    if (loginSequence > 0 && isGuidePath) {
      setDismissedQuickStartKeys((current) => {
        if (current.has(quickStartKey)) return current;
        const next = new Set(current);
        next.add(quickStartKey);
        return next;
      });
    }
    setManualQuickStartOpen(false);
  };

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const loginElement = isOfficial
    ? <Navigate to={safeNext(new URLSearchParams(search).get("next"))} replace />
    : <OfficialLoginPage />;

  const routes = (
    <Routes>
      {/* 진입 화면은 두 트랙의 공통 현관. 로그인 상태에서도 그대로 보여준다 —
          로고로 홈에 돌아올 수 있어야 하는데, 여기서 대시보드로 튕기면 돌아올 곳이 없어진다. */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login/official" element={loginElement} />
      {/* 상권 둘러보기 — 예비 창업자용 공개 화면. RequireRole로 감싸지 않는다.
          2026-08-18에 제외한 것은 기존 소상공인의 자가진단이고 이건 별개 트랙이다
          (사유는 backend/routers/public.py 상단 주석). */}
      <Route path="/browse" element={<BrowsePage />} />
      <Route path="/trends" element={<TrendPage />} />
      <Route path="/report" element={<ReportPage />} />
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
      {/* 셀 상세는 사이드바에 노출하지 않는다 — 목록에서 클릭해 들어오는 종착지다 */}
      <Route
        path="/cells/:areaId/:industryId"
        element={
          <RequireRole role="official">
            <CellDetailPage />
          </RequireRole>
        }
      />
    </Routes>
  );

  if (isOfficial && !isPublicPage) {
    const current = NAV.find((n) => n.path === pathname);
    const topBarTitle = current?.label ?? (pathname.startsWith("/cells/") ? "상권 상세" : "조기경보 대시보드");
    return (
      <div className="official-shell">
        <Sidebar
          nav={NAV}
          pathname={pathname}
          username={username}
          onLogout={handleLogout}
          onOpenQuickStart={() => {
            if (isGuidePath) setManualQuickStartOpen(true);
          }}
        />
        <div className="official-content">
          <TopBar title={topBarTitle} />
          <main key={pathname} className="official-main">{routes}</main>
        </div>
        <OfficialQuickStart
          open={quickStartOpen}
          onClose={closeQuickStart}
          path={pathname}
        />
      </div>
    );
  }

  // 미인증 상태: 로그인 화면이 자체 전체화면 레이아웃을 가지므로 셸을 씌우지 않는다.
  return <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>{routes}</div>;
}
