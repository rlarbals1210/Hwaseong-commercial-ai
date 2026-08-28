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

// 사이드바는 짙은 남색 대신 캔버스와 같은 톤 + hairline 경계로 처리한다.
// "크롬은 물러나고 콘텐츠가 말한다"는 원칙 — 내비게이션이 시각적 무게를 가져가지 않는다.
function Sidebar({ nav, pathname, username, onLogout, onOpenQuickStart }) {
  const initials = username ? username.slice(0, 2).toUpperCase() : "?";

  const rowBase = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "9px 12px",
    borderRadius: "var(--radius-md)",
    textDecoration: "none",
    fontSize: 15,
    transition: "background 0.12s ease, color 0.12s ease",
  };

  return (
    <aside
      style={{
        position: "fixed",
        left: 0,
        top: 0,
        width: 248,
        height: "100vh",
        background: "var(--surface-container-low)",
        borderRight: "1px solid var(--hairline)",
        display: "flex",
        flexDirection: "column",
        padding: 16,
        boxSizing: "border-box",
      }}
    >
      {/* 브랜드 — 로고를 누르면 홈(서비스 소개)으로 */}
      <Link
        to="/"
        style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 8px 0", textDecoration: "none" }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "var(--radius-md)",
            background: "var(--primary)",
            color: "var(--on-primary)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            fontWeight: 700,
            fontSize: 15,
            letterSpacing: "-0.5px",
          }}
        >
          RN
        </div>
        <div style={{ lineHeight: 1.25 }}>
          <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>화성시 소상공인 조기경보</div>
        </div>
      </Link>

      <div style={{ height: 1, background: "var(--hairline)", margin: "16px 0" }} />

      {/* 내비게이션 — 활성 행은 톤 차이 + primary 텍스트로만 표시(테두리·막대 없음) */}
      <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {nav.map(({ path, label, icon }) => {
          const active = pathname === path;
          return (
            <Link
              key={path}
              to={path}
              data-quickstart-path={path}
              style={{
                ...rowBase,
                color: active ? "var(--primary)" : "var(--ink-muted)",
                // 회색 사이드바 위에서 활성 행만 흰 카드처럼 떠오르게 — 겹친 종이 느낌
                background: active ? "var(--surface-container-lowest)" : "transparent",
                border: active ? "1px solid var(--hairline)" : "1px solid transparent",
                fontWeight: active ? 600 : 400,
              }}
            >
              <span
                className={`material-symbols-outlined${active ? " fill" : ""}`}
                style={{ fontSize: 20 }}
              >
                {icon}
              </span>
              {label}
            </Link>
          );
        })}
      </nav>

      {/* 계정 + 로그아웃 */}
      <div style={{ marginTop: "auto" }}>
        <div style={{ height: 1, background: "var(--hairline)", marginBottom: 12 }} />
        <button
          type="button"
          onClick={onOpenQuickStart}
          style={{
            ...rowBase,
            width: "100%",
            marginBottom: 8,
            background: "none",
            border: "1px solid transparent",
            color: "var(--ink-muted)",
            cursor: "pointer",
            textAlign: "left",
            fontFamily: "inherit",
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
            help
          </span>
          업무별 사용법
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 8px 12px" }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: "var(--radius-full)",
              background: "var(--secondary-container)",
              color: "var(--on-secondary-container)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 12,
              fontWeight: 700,
              flexShrink: 0,
            }}
          >
            {initials}
          </div>
          <div style={{ overflow: "hidden" }}>
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: "var(--on-surface)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {username || "공무원"}
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>공무원 계정</div>
          </div>
        </div>
        <button
          onClick={onLogout}
          style={{
            ...rowBase,
            width: "100%",
            background: "none",
            border: "none",
            color: "var(--ink-muted)",
            cursor: "pointer",
            textAlign: "left",
            fontFamily: "inherit",
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
            logout
          </span>
          로그아웃
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
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--ink-muted)" }}>
      <span
        className="material-symbols-outlined"
        style={{ fontSize: 18, color: "var(--accent-teal)" }}
      >
        database
      </span>
      <span>
        <b style={{ color: "var(--on-surface)", fontWeight: 600 }}>
          {year}년 {q}분기
        </b>{" "}
        기준
      </span>
    </div>
  );
}

// 본문 영역 상단 가로바. 사이드바의 세로 hairline과 만나 L자 프레임을 이루면서
// 캔버스와 같은 톤이던 두 영역의 경계를 만든다. 순백 배경 + 하단 hairline.
function TopBar({ title }) {
  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 30,
        height: 60,
        flexShrink: 0,
        background: "var(--surface-container-lowest)",
        borderBottom: "1px solid var(--hairline)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 40px",
        boxSizing: "border-box",
      }}
    >
      <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.2px", color: "var(--on-surface)" }}>
        {title}
      </div>
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
  const [dismissedLoginSequence, setDismissedLoginSequence] = useState(0);
  const shouldAutoOpenQuickStart = isOfficial && loginSequence > dismissedLoginSequence;
  const quickStartOpen = isOfficial && (manualQuickStartOpen || shouldAutoOpenQuickStart);

  const closeQuickStart = () => {
    setDismissedLoginSequence(loginSequence);
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
    return (
      <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>
        <Sidebar
          nav={NAV}
          pathname={pathname}
          username={username}
          onLogout={handleLogout}
          onOpenQuickStart={() => setManualQuickStartOpen(true)}
        />
        <div style={{ marginLeft: 248, display: "flex", flexDirection: "column", minHeight: "100vh" }}>
          <TopBar title={current?.label ?? "조기경보 대시보드"} />
          <main style={{ maxWidth: 1440, padding: "28px 40px 48px", boxSizing: "border-box" }}>{routes}</main>
        </div>
        <OfficialQuickStart
          open={quickStartOpen}
          onClose={closeQuickStart}
        />
      </div>
    );
  }

  // 미인증 상태: 로그인 화면이 자체 전체화면 레이아웃을 가지므로 셸을 씌우지 않는다.
  return <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>{routes}</div>;
}
