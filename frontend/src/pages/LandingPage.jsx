import { Link } from "react-router-dom";
import { OFFICIAL_ROUTES } from "../lib/officialRoutes";
import { useAuth } from "../context/auth-context";

// 공개 진입 화면. 두 트랙(공무원 / 예비 창업자)의 공통 현관이다.
//
// 파이프라인에서 나온 수치는 여기에 적지 않는다. 등급·기준선은 재실행하면 바뀌는데
// 공개 화면에서는 /api/alerts/grade-notice(인증 필요)를 부를 수 없어 화면이 낡은 값을
// 계속 말하게 된다(DashboardPage에 CITY_AVG_PCT = 3.22가 박혀 있던 사고와 같은 구조).
// 그래서 여기 숫자는 파이프라인과 무관한 외부 사실만 쓴다.

// 심사용 계정 — 배포 직전에 실제 값으로 채운다.
// 둘 중 하나라도 비어 있으면 안내 상자를 그리지 않는다(빈 상자가 나가는 사고 방지).
const REVIEW_ACCOUNT = { username: "", password: "" };

const STEPS = [
  { label: "발견", desc: "공실위험 지도" },
  { label: "분석", desc: "조기경보 순위" },
  { label: "확인", desc: "현장 확인 우선순위" },
  { label: "조치", desc: "셀 상세 · 후속 조치 검토안" },
];

function Icon({ name, size = 20, color = "var(--primary)" }) {
  return (
    <span className="material-symbols-outlined" style={{ fontSize: size, color }}>
      {name}
    </span>
  );
}

export default function LandingPage() {
  const showAccount = Boolean(REVIEW_ACCOUNT.username && REVIEW_ACCOUNT.password);
  // 로그인한 담당자도 로고를 눌러 여기로 돌아온다. 그 사람에게 "공무원 로그인" 버튼을
  // 내밀면 이미 한 일을 또 하라는 말이 된다.
  const { isAuthenticated, role } = useAuth();
  const isOfficial = isAuthenticated && role === "official";

  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-gray)", padding: "56px 20px 64px" }}>
      <div style={{ maxWidth: 940, margin: "0 auto" }}>

        <header style={{ textAlign: "center", marginBottom: 40 }}>
          <div
            style={{
              width: 52, height: 52, borderRadius: "var(--radius-lg)",
              background: "var(--primary)", color: "var(--on-primary)",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              fontWeight: 700, fontSize: 19, letterSpacing: "-0.5px", marginBottom: 18,
            }}
          >
            RN
          </div>
          <h1 className="t-h1" style={{ margin: 0, lineHeight: 1.3 }}>
            화성시 소상공인 폐업위험 조기경보
          </h1>
          <p className="t-body" style={{ color: "var(--ink-muted)", margin: "14px auto 0", maxWidth: 560, lineHeight: 1.7 }}>
            읍면동 × 업종 단위로 위험을 예측하고,
            담당자가 어디부터 확인할지 좁혀 줍니다.
          </p>

          {/* 파이프라인 재실행과 무관한 외부 통계만 쓴다. 등급·셀 수는 여기 적지 않는다. */}
          <p
            className="t-caption"
            style={{
              color: "var(--ink-secondary)", background: "var(--surface-container-low)",
              borderRadius: "var(--radius-full)", display: "inline-block",
              padding: "8px 16px", margin: "20px 0 0", lineHeight: 1.6,
            }}
          >
            인구 100만 고성장 도시, 그러나 소상공인 폐업률은 경기도 3위
          </p>
        </header>

        <div
          style={{
            display: "flex", justifyContent: "center", alignItems: "center",
            gap: 8, flexWrap: "wrap", marginBottom: 40,
          }}
        >
          {STEPS.map((step, i) => (
            <span key={step.label} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <span style={{ textAlign: "center" }}>
                <span className="t-caption" style={{ display: "block", fontWeight: 700, color: "var(--primary)" }}>
                  {step.label}
                </span>
                <span className="t-caption" style={{ color: "var(--ink-faint)" }}>{step.desc}</span>
              </span>
              {i < STEPS.length - 1 && <Icon name="arrow_forward" size={16} color="var(--ink-faint)" />}
            </span>
          ))}
        </div>

        <section aria-labelledby="official-heading" style={{ marginBottom: 32 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
            <h2 id="official-heading" className="t-title" style={{ margin: 0 }}>담당 공무원용 화면</h2>
            <span className="t-caption" style={{ color: "var(--ink-faint)" }}>
            </span>
          </div>

          {/* 기능 카드는 로그인으로 보내되 목적지를 들고 간다(?next=). 로그인만 시키고
              대시보드로 떨구면 담당자가 방금 고른 화면을 다시 찾아가야 한다. */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
            {OFFICIAL_ROUTES.map((route) => (
              <Link
                key={route.path}
                to={`/login/official?next=${encodeURIComponent(route.path)}`}
                className="card"
                style={{
                  padding: 16, textDecoration: "none", display: "flex", gap: 12,
                  alignItems: "flex-start", color: "var(--on-surface)",
                }}
              >
                <span
                  style={{
                    width: 38, height: 38, borderRadius: "var(--radius-md)", flexShrink: 0,
                    background: "var(--primary-fixed)", display: "inline-flex",
                    alignItems: "center", justifyContent: "center",
                  }}
                >
                  <Icon name={route.icon} />
                </span>
                <span style={{ minWidth: 0 }}>
                  <span className="t-body-sm" style={{ display: "block", fontWeight: 600 }}>
                    {route.label}
                  </span>
                  <span className="t-caption" style={{ display: "block", color: "var(--ink-muted)", marginTop: 3, lineHeight: 1.6 }}>
                    {route.summary}
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </section>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 28 }}>
          <Link
            to={isOfficial ? "/dashboard" : "/login/official"}
            className="btn-primary"
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              textDecoration: "none", padding: "13px 16px",
            }}
          >
            <Icon name={isOfficial ? "dashboard" : "badge"} size={19} color="var(--on-primary)" />
            {isOfficial ? "조기경보 대시보드로 이동" : "공무원 로그인"}
          </Link>

          <Link
            to="/browse"
            className="btn-utility"
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              textDecoration: "none", padding: "13px 16px", fontWeight: 600,
              color: "var(--primary)", background: "var(--primary-fixed)",
              borderColor: "var(--primary-fixed-dim)",
            }}
          >
            <Icon name="map_search" size={19} />
            로그인 없이 상권 둘러보기
          </Link>
        </div>

        {showAccount && (
          <div
            className="card"
            style={{ padding: 16, display: "flex", gap: 12, alignItems: "flex-start", marginBottom: 24 }}
          >
            <Icon name="key" size={19} color="var(--ink-muted)" />
            <div style={{ minWidth: 0 }}>
              <div className="t-body-sm" style={{ fontWeight: 600 }}>심사용 계정</div>
              <div
                className="t-caption"
                style={{ color: "var(--ink-secondary)", marginTop: 4, fontVariantNumeric: "tabular-nums" }}
              >
                아이디 <b style={{ color: "var(--on-surface)" }}>{REVIEW_ACCOUNT.username}</b>
                {" · "}
                비밀번호 <b style={{ color: "var(--on-surface)" }}>{REVIEW_ACCOUNT.password}</b>
              </div>
              <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 4, lineHeight: 1.6 }}>
                심사 기간 열람용 계정입니다. 모든 화면은 읍면동 × 업종 집계 단위이며 개별 점포 정보는 포함하지 않습니다.
              </div>
            </div>
          </div>
        )}

        <p className="t-caption" style={{ textAlign: "center", color: "var(--ink-faint)", lineHeight: 1.7, margin: 0 }}>
          제1회 화성 AI·DATA 기반 솔루션 경진대회 출품작
          <br />
          모든 출력은 읍면동 × 업종 집계 단위입니다. AI는 확인 범위를 좁혀 줄 뿐, 최종 판단은 담당자가 합니다.
        </p>
      </div>
    </div>
  );
}
