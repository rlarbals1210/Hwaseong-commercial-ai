import { useEffect } from "react";
import { Link } from "react-router-dom";
import { OFFICIAL_ROUTES } from "../lib/officialRoutes";
import { useAuth } from "../context/auth-context";

// 공개 진입 화면. 두 트랙(공무원 / 예비 창업자)의 공통 현관이다.
//
// 디자인은 노다지(서울 졸업작품) 랜딩의 언어를 가져왔다 — 다크 네이비 바탕, 스카이블루
// 강조, 그리드 오버레이, 스크롤 리빌. 앱 본문은 밝은 토큰 시스템이라 톤이 크게 다른데,
// 랜딩은 앱 셸 밖에서 전체화면으로 렌더되는 독립 화면이라 의도적으로 분리했다.
// 스타일은 .lp-root 아래로만 스코프해 index.css의 토큰 시스템을 오염시키지 않는다.
//
// 파이프라인에서 나온 수치는 여기에 적지 않는다. 등급·기준선은 재실행하면 바뀌는데
// 공개 화면에서는 /api/alerts/grade-notice(인증 필요)를 부를 수 없어 화면이 낡은 값을
// 계속 말하게 된다(DashboardPage에 CITY_AVG_PCT = 3.22가 박혀 있던 사고와 같은 구조).

// 심사용 계정 — 배포 직전에 실제 값으로 채운다.
// 둘 중 하나라도 비어 있으면 안내 상자를 그리지 않는다(빈 상자가 나가는 사고 방지).
const REVIEW_ACCOUNT = { username: "", password: "" };

// 파이프라인 산출값이 아니라 방법론 상수·행정구역 사실이다. 재실행해도 변하지 않는다.
const HERO_FACTS = [
  { value: "29", label: "화성시 행정동 전체" },
  { value: "4분기", label: "누적 관측 기준" },
  { value: "2분기", label: "앞서 보는 예측 시점" },
];

// 화면 나열이 아니라 담당자가 실제로 밟는 순서다. 발표 서사와 같은 문구를 쓴다 —
// 화면과 대본이 다른 표현이면 심사위원이 같은 것을 두 번 배워야 한다.
const STEPS = [
  {
    label: "발견",
    screen: "공실위험 지도",
    desc: "읍면동별로 위험 업종이 얼마나 몰려 있는지 한눈에 봅니다.",
  },
  {
    label: "분석",
    screen: "조기경보",
    desc: "모델이 2분기 뒤 위험으로 본 상권을 순위로 세웁니다.",
  },
  {
    label: "확인",
    screen: "현장 확인 우선순위",
    desc: "관측된 폐업률과 영향 점포 수로 어디부터 갈지 정합니다.",
  },
  {
    label: "조치",
    screen: "셀 상세",
    desc: "확인된 위험 신호, 상권 유형별 처방, 연결 가능한 지원사업을 모아 봅니다.",
  },
];

// 할 수 있는 것보다 하지 않는 것을 먼저 밝힌다. 행정 도구는 한계가 분명할수록 쓰인다.
const PRINCIPLES = [
  {
    tone: "blue",
    icon: "gavel",
    title: "AI가 지원 대상을 결정하지 않습니다",
    desc: "확인할 범위를 좁혀 줄 뿐이며, 최종 판단은 담당 공무원이 합니다.",
  },
  {
    tone: "teal",
    icon: "shield_person",
    title: "개별 점포를 다루지 않습니다",
    desc: "모든 출력은 읍면동 × 업종 집계 단위입니다. 특정 가게의 위험도는 산출하지도, 보여주지도 않습니다.",
  },
  {
    tone: "amber",
    icon: "help",
    title: "표본이 부족하면 판단을 보류합니다",
    desc: "점포 수가 적어 통계로 말할 수 없는 상권은 등급을 매기지 않고 사각지대로 따로 남깁니다.",
  },
  {
    tone: "green",
    icon: "lock",
    title: "행정데이터를 외부로 보내지 않습니다",
    desc: "외부 생성형 AI를 호출하지 않으며, 화면의 모든 문구는 규칙 기반으로 만듭니다.",
  },
];

const CSS = `
  .lp-root *, .lp-root *::before, .lp-root *::after { box-sizing: border-box; }
  .lp-root {
    font-family: 'Noto Sans KR', 'Inter', sans-serif;
    background: #060e1e;
    color: #ffffff;
    min-height: 100vh;
    overflow-x: hidden;
    -webkit-font-smoothing: antialiased;
  }
  .lp-num { font-family: 'Inter', 'Noto Sans KR', sans-serif; font-variant-numeric: tabular-nums; }

  /* ── 상단 고정 네비 ─────────────────────────────────────────────── */
  .lp-root .lp-nav {
    position: fixed; top: 0; left: 0; right: 0; z-index: 100; height: 72px;
    display: flex; align-items: center; justify-content: center; padding: 0 32px;
    background: rgba(6,14,30,0.85); backdrop-filter: blur(16px);
    border-bottom: 1px solid rgba(56,189,248,0.1);
  }
  .lp-nav-inner { max-width: 1280px; width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 24px; }
  .lp-nav-brand { display: flex; align-items: center; gap: 10px; text-decoration: none; flex-shrink: 0; }
  .lp-nav-mark {
    width: 32px; height: 32px; border-radius: 9px; flex-shrink: 0;
    background: linear-gradient(135deg,#0ea5e9,#0284c7); color: #fff;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 700; letter-spacing: -0.5px;
  }
  .lp-nav-name { font-size: 15px; font-weight: 700; color: #f1f5f9; white-space: nowrap; }
  .lp-nav-links { display: flex; align-items: center; gap: 26px; list-style: none; margin: 0; padding: 0; min-width: 0; }
  .lp-nav-links a { color: #cbd5e1; text-decoration: none; font-size: 14px; font-weight: 500; white-space: nowrap; transition: color .2s; }
  .lp-nav-links a:hover { color: #7dd3fc; }
  .lp-nav-right { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
  .lp-nav-ghost { color: #94a3b8; text-decoration: none; font-size: 14px; font-weight: 500; white-space: nowrap; transition: color .2s; }
  .lp-nav-ghost:hover { color: #7dd3fc; }
  .lp-nav-cta {
    background: #0ea5e9; color: #fff; text-decoration: none;
    padding: 10px 22px; border-radius: 8px; font-size: 14px; font-weight: 600;
    white-space: nowrap; transition: background .2s, transform .1s;
  }
  .lp-nav-cta:hover { background: #38bdf8; transform: translateY(-1px); }

  /* ── 히어로 ─────────────────────────────────────────────────────── */
  .lp-hero {
    position: relative; min-height: 100vh; display: flex; align-items: center;
    padding: 140px 32px 88px; overflow: hidden;
  }
  .lp-hero::before {
    content: ''; position: absolute; inset: 0; pointer-events: none;
    background-image:
      linear-gradient(rgba(56,189,248,0.04) 1px, transparent 1px),
      linear-gradient(90deg, rgba(56,189,248,0.04) 1px, transparent 1px);
    background-size: 60px 60px;
  }
  .lp-hero::after {
    content: ''; position: absolute; top: -25%; right: -12%;
    width: 820px; height: 820px; pointer-events: none;
    background: radial-gradient(circle, rgba(56,189,248,0.13) 0%, transparent 65%);
  }
  .lp-hero-inner { position: relative; z-index: 2; max-width: 1280px; width: 100%; margin: 0 auto; }
  .lp-badge {
    display: inline-flex; align-items: center; gap: 8px;
    background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.25);
    border-radius: 100px; padding: 6px 16px; font-size: 12px; font-weight: 600;
    color: #7dd3fc; letter-spacing: 0.06em; margin-bottom: 26px;
  }
  .lp-badge-dot { width: 6px; height: 6px; background: #38bdf8; border-radius: 50%; animation: lp-pulse 2s ease-in-out infinite; }
  @keyframes lp-pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(.7)} }
  .lp-hero-title {
    font-size: clamp(36px, 4.6vw, 62px); font-weight: 700; line-height: 1.18;
    letter-spacing: -0.02em; margin: 0 0 22px; word-break: keep-all; max-width: 860px;
  }
  .lp-hero-title .accent { color: #38bdf8; }
  .lp-hero-sub { font-size: 17px; color: #94a3b8; line-height: 1.8; margin: 0 0 40px; max-width: 560px; word-break: keep-all; }
  .lp-actions { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
  .lp-btn-primary {
    background: linear-gradient(135deg,#0ea5e9,#0284c7); color: #fff; text-decoration: none;
    padding: 15px 34px; border-radius: 8px; font-size: 16px; font-weight: 700;
    display: inline-flex; align-items: center; gap: 8px;
    box-shadow: 0 8px 32px rgba(14,165,233,.35); transition: transform .2s, box-shadow .2s;
  }
  .lp-btn-primary:hover { transform: translateY(-2px); box-shadow: 0 12px 40px rgba(14,165,233,.5); }
  .lp-btn-secondary {
    background: transparent; color: #cbd5e1; text-decoration: none;
    border: 1px solid rgba(255,255,255,.14);
    padding: 15px 30px; border-radius: 8px; font-size: 15px; font-weight: 500;
    display: inline-flex; align-items: center; gap: 8px; transition: border-color .2s, color .2s;
  }
  .lp-btn-secondary:hover { border-color: #38bdf8; color: #7dd3fc; }
  .lp-facts { display: flex; gap: 52px; flex-wrap: wrap; margin-top: 64px; padding-top: 34px; border-top: 1px solid rgba(255,255,255,.07); }
  .lp-fact-value { font-size: 34px; font-weight: 700; color: #38bdf8; line-height: 1; margin-bottom: 7px; }
  .lp-fact-label { font-size: 13px; color: #94a3b8; line-height: 1.4; word-break: keep-all; }

  /* ── 공통 섹션 ──────────────────────────────────────────────────── */
  .lp-section { padding: 100px 32px; position: relative; overflow: hidden; }
  .lp-section-inner { max-width: 1280px; margin: 0 auto; position: relative; z-index: 2; }
  .lp-eyebrow { font-size: 11px; font-weight: 700; letter-spacing: .15em; color: #38bdf8; margin: 0 0 14px; }
  .lp-section-title { font-size: clamp(26px, 2.8vw, 40px); font-weight: 700; line-height: 1.25; letter-spacing: -.02em; margin: 0 0 14px; word-break: keep-all; }
  .lp-section-desc { font-size: 16px; color: #94a3b8; line-height: 1.75; margin: 0; max-width: 560px; word-break: keep-all; }

  /* ── 단계 ───────────────────────────────────────────────────────── */
  .lp-flow { background: #0a1628; }
  .lp-flow::before {
    content: ''; position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
    width: 820px; height: 820px; pointer-events: none;
    background: radial-gradient(circle, rgba(56,189,248,.05) 0%, transparent 60%);
  }
  .lp-steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; margin-top: 56px; }
  .lp-step {
    background: #0d2040; border: 1px solid rgba(56,189,248,.1); border-radius: 16px;
    padding: 30px 26px; position: relative; display: flex; flex-direction: column;
  }
  .lp-step-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 16px; }
  .lp-step-num { font-size: 22px; font-weight: 700; color: rgba(56,189,248,.3); line-height: 1; }
  .lp-step-label { font-size: 21px; font-weight: 700; color: #fff; line-height: 1; }
  .lp-step-screen { font-size: 13px; font-weight: 600; color: #7dd3fc; margin-bottom: 9px; }
  .lp-step-desc { font-size: 14px; color: #94a3b8; line-height: 1.7; margin: 0; word-break: keep-all; }

  /* ── 원칙 ───────────────────────────────────────────────────────── */
  .lp-principles { background: #060e1e; }
  .lp-principle-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 2px; margin-top: 56px; }
  .lp-principle {
    background: #0d2040; border: 1px solid rgba(255,255,255,.04);
    padding: 36px 32px; position: relative; overflow: hidden; transition: transform .3s, border-color .3s;
  }
  .lp-principle:hover { transform: translateY(-4px); border-color: rgba(56,189,248,.16); z-index: 2; }
  .lp-principle::after {
    content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 1px; opacity: 0;
    background: linear-gradient(90deg, transparent, rgba(56,189,248,.35), transparent);
    transition: opacity .3s;
  }
  .lp-principle:hover::after { opacity: 1; }
  .lp-principle-num { position: absolute; right: 22px; top: 22px; font-size: 44px; font-weight: 700; color: rgba(56,189,248,.13); line-height: 1; }
  .lp-principle-icon {
    width: 50px; height: 50px; border-radius: 14px; margin-bottom: 20px;
    display: flex; align-items: center; justify-content: center;
    border: 1px solid rgba(56,189,248,.2); background: rgba(56,189,248,.1); color: #7dd3fc;
  }
  .lp-principle-icon.teal { background: rgba(45,212,191,.1); border-color: rgba(45,212,191,.2); color: #2dd4bf; }
  .lp-principle-icon.amber { background: rgba(251,191,36,.1); border-color: rgba(251,191,36,.2); color: #fbbf24; }
  .lp-principle-icon.green { background: rgba(74,222,128,.1); border-color: rgba(74,222,128,.2); color: #4ade80; }
  .lp-principle-title { font-size: 17px; font-weight: 700; color: #fff; margin: 0 0 9px; word-break: keep-all; padding-right: 44px; }
  .lp-principle-desc { font-size: 14px; color: #94a3b8; line-height: 1.7; margin: 0; word-break: keep-all; }

  /* ── 마무리 CTA ─────────────────────────────────────────────────── */
  .lp-cta { background: linear-gradient(135deg,#0d2040 0%,#0a1628 100%); border-top: 1px solid rgba(56,189,248,.08); text-align: center; padding: 110px 32px; }
  .lp-cta::before {
    content: ''; position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
    width: 1000px; height: 400px; pointer-events: none;
    background: radial-gradient(ellipse, rgba(56,189,248,.09) 0%, transparent 60%);
  }
  .lp-cta .lp-section-desc { margin: 0 auto 40px; }
  .lp-cta .lp-actions { justify-content: center; }

  .lp-account {
    max-width: 620px; margin: 44px auto 0; text-align: left;
    background: rgba(6,14,30,.6); border: 1px solid rgba(56,189,248,.16);
    border-radius: 12px; padding: 18px 22px; display: flex; gap: 14px; align-items: flex-start;
  }
  .lp-account-title { font-size: 14px; font-weight: 700; color: #fff; margin: 0 0 6px; }
  .lp-account-cred { font-size: 14px; color: #cbd5e1; margin: 0 0 6px; }
  .lp-account-cred b { color: #7dd3fc; }
  .lp-account-note { font-size: 12px; color: #64748b; line-height: 1.6; margin: 0; }

  /* ── 푸터 ───────────────────────────────────────────────────────── */
  .lp-footer {
    background: #060e1e; border-top: 1px solid rgba(255,255,255,.05);
    padding: 44px 32px; text-align: center;
    display: flex; flex-direction: column; align-items: center; gap: 10px;
  }
  .lp-footer p { font-size: 12px; color: #64748b; line-height: 1.7; margin: 0; word-break: keep-all; }

  /* ── 스크롤 리빌 ────────────────────────────────────────────────── */
  .lp-reveal { opacity: 0; transform: translateY(26px); transition: opacity .7s ease, transform .7s ease; }
  .lp-reveal.visible { opacity: 1; transform: none; }
  .lp-d1 { transition-delay: .08s; } .lp-d2 { transition-delay: .16s; }
  .lp-d3 { transition-delay: .24s; } .lp-d4 { transition-delay: .32s; }

  @media (prefers-reduced-motion: reduce) {
    .lp-reveal { opacity: 1; transform: none; transition: none; }
    .lp-badge-dot { animation: none; }
  }
  @media (max-width: 1000px) {
    .lp-nav-links { display: none; }
  }
  @media (max-width: 640px) {
    .lp-root .lp-nav { padding: 0 20px; }
    .lp-nav-name { display: none; }
    .lp-hero { padding: 112px 20px 64px; }
    .lp-section { padding: 68px 20px; }
    .lp-facts { gap: 30px; margin-top: 48px; }
    .lp-principle { padding: 28px 24px; }
  }
`;

function Icon({ name, size = 22 }) {
  return (
    <span className="material-symbols-outlined" style={{ fontSize: size }}>
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

  const enterHref = isOfficial ? "/dashboard" : "/login/official";
  const enterLabel = isOfficial ? "대시보드로 이동" : "공무원 로그인";

  useEffect(() => {
    const targets = document.querySelectorAll(".lp-reveal");
    // IntersectionObserver가 없으면 요소가 opacity 0으로 영원히 남는다 — 그때는 즉시 보인다.
    if (!("IntersectionObserver" in window)) {
      targets.forEach((el) => el.classList.add("visible"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );
    targets.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <div className="lp-root">
      <style>{CSS}</style>

      <nav className="lp-nav" aria-label="주요 메뉴">
        <div className="lp-nav-inner">
          <Link to="/" className="lp-nav-brand">
            <span className="lp-nav-mark">RN</span>
            <span className="lp-nav-name">화성시 소상공인 조기경보</span>
          </Link>

          {/* 담당자 화면 바로가기. 로그인 상태면 ?next= 가 즉시 통과해 바로가기처럼 동작한다. */}
          <ul className="lp-nav-links">
            {OFFICIAL_ROUTES.map((route) => (
              <li key={route.path}>
                <Link to={`/login/official?next=${encodeURIComponent(route.path)}`}>{route.label}</Link>
              </li>
            ))}
          </ul>

          <div className="lp-nav-right">
            <Link to="/browse" className="lp-nav-ghost">상권 둘러보기</Link>
            <Link to={enterHref} className="lp-nav-cta">{enterLabel}</Link>
          </div>
        </div>
      </nav>

      <section className="lp-hero">
        <div className="lp-hero-inner">
          <span className="lp-badge lp-reveal">
            <span className="lp-badge-dot" />
            제1회 화성 AI·DATA 기반 솔루션 경진대회
          </span>

          <h1 className="lp-hero-title lp-reveal lp-d1">
            소상공인 폐업 위험을<br />
            <span className="accent">행정이 먼저 발견합니다</span>
          </h1>

          <p className="lp-hero-sub lp-reveal lp-d2">
            읍면동 × 업종 단위로 폐업 위험을 예측하고, 담당 공무원이 어디부터 확인할지 좁혀 줍니다.
            시민이 행정을 찾아오게 하는 대신, 행정이 먼저 찾아가게 만드는 도구입니다.
          </p>

          <div className="lp-actions lp-reveal lp-d3">
            <Link to={enterHref} className="lp-btn-primary">
              <Icon name={isOfficial ? "dashboard" : "login"} size={19} />
              {enterLabel}
            </Link>
            <Link to="/browse" className="lp-btn-secondary">
              <Icon name="map_search" size={19} />
              로그인 없이 상권 둘러보기
            </Link>
          </div>

          <div className="lp-facts lp-reveal lp-d4">
            {HERO_FACTS.map((fact) => (
              <div key={fact.label}>
                <div className="lp-fact-value lp-num">{fact.value}</div>
                <div className="lp-fact-label">{fact.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-section lp-flow" aria-labelledby="flow-heading">
        <div className="lp-section-inner">
          <p className="lp-eyebrow lp-reveal">HOW IT WORKS</p>
          <h2 id="flow-heading" className="lp-section-title lp-reveal lp-d1">어떻게 작동하나요</h2>
          <p className="lp-section-desc lp-reveal lp-d2">
            담당자가 분기마다 밟는 네 단계입니다. 각 단계가 하나의 화면에 대응합니다.
          </p>

          <div className="lp-steps">
            {STEPS.map((step, i) => (
              <div key={step.label} className={`lp-step lp-reveal lp-d${i + 1}`}>
                <div className="lp-step-head">
                  <span className="lp-step-num lp-num">0{i + 1}</span>
                  <span className="lp-step-label">{step.label}</span>
                </div>
                <div className="lp-step-screen">{step.screen}</div>
                <p className="lp-step-desc">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 할 수 있는 것만 늘어놓는 대신 한계를 먼저 밝힌다. Q&A에서 반드시 나오는
          질문("AI가 지원 대상을 정하나", "개인정보는")을 화면이 미리 답해둔다. */}
      <section className="lp-section lp-principles" aria-labelledby="principles-heading">
        <div className="lp-section-inner">
          <p className="lp-eyebrow lp-reveal">PRINCIPLES</p>
          <h2 id="principles-heading" className="lp-section-title lp-reveal lp-d1">이 서비스가 하지 않는 것</h2>
          <p className="lp-section-desc lp-reveal lp-d2">
            행정에서 실제로 쓰이려면, 무엇을 할 수 있는지보다 무엇을 하지 않는지가 분명해야 합니다.
          </p>

          <div className="lp-principle-grid">
            {PRINCIPLES.map((item, i) => (
              <div key={item.title} className={`lp-principle lp-reveal lp-d${i + 1}`}>
                <span className="lp-principle-num lp-num">0{i + 1}</span>
                <div className={`lp-principle-icon ${item.tone}`}>
                  <Icon name={item.icon} size={24} />
                </div>
                <h3 className="lp-principle-title">{item.title}</h3>
                <p className="lp-principle-desc">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-section lp-cta">
        <div className="lp-section-inner">
          <h2 className="lp-section-title lp-reveal">
            위험해지면 <span style={{ color: "#38bdf8" }}>행정이 먼저 찾아옵니다</span>
          </h2>
          <p className="lp-section-desc lp-reveal lp-d1">
            소상공인은 아무것도 하지 않아도 됩니다. 그것이 이 설계의 목표입니다.
          </p>

          <div className="lp-actions lp-reveal lp-d2">
            <Link to={enterHref} className="lp-btn-primary">
              <Icon name={isOfficial ? "dashboard" : "login"} size={19} />
              {enterLabel}
            </Link>
            <Link to="/browse" className="lp-btn-secondary">
              <Icon name="map_search" size={19} />
              상권 둘러보기
            </Link>
          </div>

          {showAccount && (
            <div className="lp-account lp-reveal lp-d3">
              <span style={{ color: "#7dd3fc", flexShrink: 0 }}><Icon name="key" size={20} /></span>
              <div style={{ minWidth: 0 }}>
                <p className="lp-account-title">심사용 계정</p>
                <p className="lp-account-cred lp-num">
                  아이디 <b>{REVIEW_ACCOUNT.username}</b> · 비밀번호 <b>{REVIEW_ACCOUNT.password}</b>
                </p>
                <p className="lp-account-note">
                  심사 기간 열람용 계정입니다. 모든 화면은 읍면동 × 업종 집계 단위이며 개별 점포 정보는 포함하지 않습니다.
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      <footer className="lp-footer">
        <p>제1회 화성 AI·DATA 기반 솔루션 경진대회 출품작 · 데이터 출처: 소상공인시장진흥공단 상가(상권)정보</p>
        <p>모든 출력은 읍면동 × 업종 집계 단위입니다. AI는 확인 범위를 좁혀 줄 뿐, 최종 판단은 담당자가 합니다.</p>
      </footer>
    </div>
  );
}
