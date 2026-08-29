import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/auth-context";

// 공개 진입 화면. 두 트랙(공무원 / 예비 창업자)의 공통 현관이다.
//
// 디자인은 기존 서울 졸업작품 랜딩의 언어를 가져왔다 — 다크 네이비 바탕, 스카이블루
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
  { value: "29", label: "화성시 읍면동 전체" },
  { value: "4분기", label: "누적 관측 기준" },
  { value: "2분기", label: "앞서 보는 예측 시점" },
];

const AUDIENCES = [
  {
    key: "official",
    eyebrow: "담당 공무원",
    icon: "admin_panel_settings",
    title: "확인해야 할 상권부터 좁힙니다",
    desc: "모든 상권을 일일이 찾는 대신 AI 경보와 관측 근거로 어디부터 확인할지 정합니다.",
    points: [
      "2분기 뒤 위험 상권을 상대 순위로 확인",
      "지도와 사각지대로 지역별 상황 파악",
      "관측 폐업률과 영향 점포 수로 현장 확인 순서 결정",
    ],
  },
  {
    key: "citizen",
    eyebrow: "창업 준비 시민",
    icon: "storefront",
    title: "나에게 맞는 후보 상권을 비교합니다",
    desc: "업종과 가장 걱정되는 조건을 고르면 수요·공급과 폐업 부담을 함께 살펴볼 지역을 제시합니다.",
    points: [
      "준비 중인 업종과 상권 고민 선택",
      "조건에 맞는 후보 상권 3곳 확인",
      "후보 간 지표와 현장 확인사항 비교",
    ],
  },
];

// 화면 나열이 아니라 사용자가 실제로 밟는 순서다. 발표 서사와 같은 문구를 쓴다 —
// 화면과 대본이 다른 표현이면 심사위원이 같은 것을 두 번 배워야 한다.
const OFFICIAL_STEPS = [
  {
    label: "경보 확인",
    screen: "조기경보",
    desc: "모델이 2분기 뒤 위험으로 본 상권을 순위로 세웁니다.",
  },
  {
    label: "지역 파악",
    screen: "상권 위험 지도",
    desc: "읍면동별로 위험 업종이 얼마나 몰려 있는지 한눈에 봅니다.",
  },
  {
    label: "순서 결정",
    screen: "현장 확인 우선순위",
    desc: "관측된 폐업률과 영향 점포 수로 어디부터 갈지 정합니다.",
  },
  {
    label: "근거 확인",
    screen: "상세·비교",
    desc: "확인된 신호와 비교 상권, 후속 조치 검토안을 함께 확인합니다.",
  },
];

const CITIZEN_STEPS = [
  {
    label: "업종 선택",
    screen: "상권 둘러보기",
    desc: "준비 중인 업종을 골라 화성시 전체 후보를 불러옵니다.",
  },
  {
    label: "고민 선택",
    screen: "맞춤 조건",
    desc: "수요, 폐업 부담, 경쟁 중 가장 걱정되는 조건을 고릅니다.",
  },
  {
    label: "후보 확인",
    screen: "추천 3곳",
    desc: "조건 적합도와 추천 이유, 확인할 점을 함께 살펴봅니다.",
  },
  {
    label: "비교",
    screen: "상권 상세",
    desc: "후보 두 곳의 관측 지표를 비교하고 현장 확인사항을 정리합니다.",
  },
];

// 서비스 개요 뒤에서 해석 원칙을 밝힌다. 행정 도구는 한계가 분명할수록 쓰인다.
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
    overflow-x: clip;
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
  .lp-nav-ghost {
    color: #cbd5e1; text-decoration: none; font-size: 14px; font-weight: 500; white-space: nowrap;
    background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);
    padding: 9px 18px; border-radius: 8px; transition: background .2s, border-color .2s, color .2s;
  }
  .lp-nav-ghost:hover { background: rgba(255,255,255,.1); border-color: rgba(255,255,255,.22); color: #7dd3fc; }
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
    color: #fff;
  }
  .lp-hero-title .accent { color: #38bdf8; }
  .lp-hero-sub { font-size: 17px; color: #94a3b8; line-height: 1.8; margin: 0 0 34px; max-width: 700px; word-break: keep-all; }
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
  .lp-facts { display: flex; gap: 52px; flex-wrap: wrap; margin-top: 8px; padding-top: 34px; border-top: 1px solid rgba(255,255,255,.07); }
  .lp-fact-value { font-size: 34px; font-weight: 700; color: #38bdf8; line-height: 1; margin-bottom: 7px; }
  .lp-fact-label { font-size: 13px; color: #94a3b8; line-height: 1.4; word-break: keep-all; }

  /* ── 공통 섹션 ──────────────────────────────────────────────────── */
  .lp-section { padding: 100px 32px; position: relative; overflow: hidden; }
  .lp-section-inner { max-width: 1280px; margin: 0 auto; position: relative; z-index: 2; }
  .lp-eyebrow { font-size: 11px; font-weight: 700; letter-spacing: .15em; color: #38bdf8; margin: 0 0 14px; }
  .lp-section-title { font-size: clamp(26px, 2.8vw, 40px); font-weight: 700; line-height: 1.25; letter-spacing: -.02em; margin: 0 0 14px; word-break: keep-all; color: #fff; }
  .lp-section-desc { font-size: 16px; color: #94a3b8; line-height: 1.75; margin: 0; max-width: 560px; word-break: keep-all; }

  /* ── 이용 대상 ──────────────────────────────────────────────────── */
  .lp-audiences {
    min-height: 210vh; padding-top: 0; padding-bottom: 0;
    background: #060e1e; overflow: visible;
  }
  .lp-audience-story {
    min-height: calc(100vh - 72px); position: sticky; top: 72px;
    display: flex; align-items: center; padding: 56px 0;
  }
  .lp-audience-story-grid {
    width: 100%; display: grid; grid-template-columns: minmax(280px,.82fr) minmax(480px,1.18fr);
    gap: clamp(36px,5vw,76px); align-items: center;
  }
  .lp-audience-copy .lp-section-desc { max-width: 460px; }
  .lp-audience-progress { display: grid; gap: 8px; margin-top: 32px; max-width: 390px; }
  .lp-audience-progress-btn {
    appearance: none; width: 100%; display: grid; grid-template-columns: 36px 1fr auto;
    align-items: center; gap: 12px; padding: 13px 14px; border: 0; border-radius: 12px;
    background: transparent; color: #64748b; text-align: left; cursor: pointer;
    font: inherit; transition: color .35s, background .35s, transform .35s;
  }
  .lp-audience-progress-btn:hover { color: #cbd5e1; background: rgba(255,255,255,.035); }
  .lp-audience-progress-btn.active { color: #f8fafc; background: rgba(56,189,248,.08); transform: translateX(6px); }
  .lp-audience-progress-num { font-size: 12px; font-weight: 700; color: #475569; letter-spacing: .08em; }
  .lp-audience-progress-btn.active .lp-audience-progress-num { color: #38bdf8; }
  .lp-audience-progress-label { font-size: 14px; font-weight: 700; }
  .lp-audience-progress-line {
    width: 34px; height: 2px; border-radius: 2px; background: rgba(148,163,184,.18);
    overflow: hidden;
  }
  .lp-audience-progress-line::after {
    content: ''; display: block; width: 100%; height: 100%; background: #38bdf8;
    transform: scaleX(0); transform-origin: left; transition: transform .55s ease;
  }
  .lp-audience-progress-btn.active .lp-audience-progress-line::after { transform: scaleX(1); }
  .lp-audience-stage { min-height: 500px; position: relative; perspective: 1000px; }
  .lp-audience-card {
    position: absolute; inset: 0; min-height: 500px; display: flex; flex-direction: column; overflow: hidden;
    padding: 38px; border-radius: 20px; background: linear-gradient(145deg,#0d2040,#0a172b);
    border: 1px solid rgba(56,189,248,.14);
    opacity: 0; transform: translate3d(0,-42px,0) scale(.965) rotateX(2deg);
    pointer-events: none; transition: opacity .55s ease, transform .75s cubic-bezier(.22,1,.36,1), border-color .4s;
  }
  .lp-audience-card.citizen { transform: translate3d(0,42px,0) scale(.965) rotateX(-2deg); }
  .lp-audience-card.active {
    opacity: 1; transform: translate3d(0,0,0) scale(1) rotateX(0); pointer-events: auto;
  }
  .lp-audience-card::after {
    content: ''; position: absolute; width: 320px; height: 320px; right: -130px; top: -150px;
    border-radius: 50%; background: rgba(56,189,248,.08); pointer-events: none;
  }
  .lp-audience-card.citizen { border-color: rgba(45,212,191,.18); }
  .lp-audience-card.citizen::after { background: rgba(45,212,191,.08); }
  .lp-audience-top { display: flex; align-items: center; gap: 14px; margin-bottom: 24px; position: relative; z-index: 1; }
  .lp-audience-icon {
    width: 52px; height: 52px; border-radius: 15px; display: inline-flex; align-items: center; justify-content: center;
    color: #7dd3fc; background: rgba(56,189,248,.1); border: 1px solid rgba(56,189,248,.2);
  }
  .lp-audience-card.citizen .lp-audience-icon { color: #5eead4; background: rgba(45,212,191,.1); border-color: rgba(45,212,191,.2); }
  .lp-audience-eyebrow { font-size: 12px; color: #7dd3fc; font-weight: 700; letter-spacing: .08em; margin: 0 0 4px; }
  .lp-audience-card.citizen .lp-audience-eyebrow { color: #5eead4; }
  .lp-audience-type { font-size: 14px; color: #94a3b8; margin: 0; }
  .lp-audience-title { font-size: 25px; color: #fff; line-height: 1.35; letter-spacing: -.02em; margin: 0 0 12px; word-break: keep-all; }
  .lp-audience-desc { font-size: 15px; color: #94a3b8; line-height: 1.75; margin: 0 0 24px; word-break: keep-all; }
  .lp-audience-points { list-style: none; padding: 0; margin: 0 0 30px; display: grid; gap: 13px; }
  .lp-audience-points li { display: flex; gap: 10px; align-items: flex-start; color: #cbd5e1; font-size: 14px; line-height: 1.6; word-break: keep-all; }
  .lp-audience-points .material-symbols-outlined { color: #38bdf8; margin-top: 2px; }
  .lp-audience-card.citizen .lp-audience-points .material-symbols-outlined { color: #2dd4bf; }
  .lp-audience-link {
    margin-top: auto; align-self: flex-start; display: inline-flex; align-items: center; gap: 7px;
    color: #7dd3fc; text-decoration: none; font-size: 14px; font-weight: 700;
  }
  .lp-audience-card.citizen .lp-audience-link { color: #5eead4; }
  .lp-audience-link:hover { text-decoration: underline; text-underline-offset: 4px; }

  /* ── 단계 ───────────────────────────────────────────────────────── */
  .lp-flow { background: #0a1628; }
  .lp-flow::before {
    content: ''; position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
    width: 820px; height: 820px; pointer-events: none;
    background: radial-gradient(circle, rgba(56,189,248,.05) 0%, transparent 60%);
  }
  .lp-flow-lanes { display: grid; gap: 18px; margin-top: 52px; }
  .lp-flow-lane {
    --flow-color: #38bdf8; --flow-rgb: 56,189,248;
    position: relative; overflow: hidden; padding: 32px; border-radius: 22px;
    background: linear-gradient(135deg,rgba(10,31,58,.92),rgba(6,20,40,.88));
    border: 1px solid rgba(var(--flow-rgb),.2);
  }
  .lp-flow-lane::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg,var(--flow-color),rgba(var(--flow-rgb),.12));
  }
  .lp-flow-lane.citizen {
    --flow-color: #2dd4bf; --flow-rgb: 45,212,191;
    background: linear-gradient(135deg,rgba(7,38,48,.9),rgba(6,25,38,.88));
  }
  .lp-flow-lane-head { display: flex; gap: 13px; align-items: center; }
  .lp-flow-lane-icon {
    width: 42px; height: 42px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0; color: var(--flow-color); background: rgba(var(--flow-rgb),.1); border: 1px solid rgba(var(--flow-rgb),.22);
  }
  .lp-flow-lane-title { font-size: 18px; color: #fff; font-weight: 700; margin: 0 0 3px; }
  .lp-flow-lane-desc { font-size: 13px; color: #94a3b8; margin: 0; }
  .lp-flow-direction {
    margin-left: auto; display: inline-flex; align-items: center; gap: 7px;
    color: var(--flow-color); font-size: 11px; font-weight: 700; letter-spacing: .08em;
  }
  .lp-steps {
    display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 26px;
    position: relative; margin-top: 30px;
  }
  .lp-steps::before {
    content: ''; position: absolute; top: 25px; left: 6%; right: 6%; height: 2px;
    background: linear-gradient(90deg,rgba(var(--flow-rgb),.28),var(--flow-color));
    transform: scaleX(0); transform-origin: left;
    transition: transform 1.15s cubic-bezier(.22,1,.36,1);
  }
  .lp-flow-lane.visible .lp-steps::before { transform: scaleX(1); }
  .lp-step {
    position: relative; z-index: 1; display: flex; flex-direction: column;
    opacity: 0; transform: translateX(24px);
    transition: opacity .5s ease, transform .65s cubic-bezier(.22,1,.36,1);
  }
  .lp-flow-lane.visible .lp-step { opacity: 1; transform: none; }
  .lp-flow-lane.visible .lp-step:nth-child(2) { transition-delay: .1s; }
  .lp-flow-lane.visible .lp-step:nth-child(3) { transition-delay: .2s; }
  .lp-flow-lane.visible .lp-step:nth-child(4) { transition-delay: .3s; }
  .lp-step-marker {
    width: 52px; height: 52px; margin: 0 auto 18px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    background: #0a1628; border: 2px solid rgba(var(--flow-rgb),.5);
    color: var(--flow-color); font-size: 13px; font-weight: 800;
    box-shadow: 0 0 0 6px rgba(var(--flow-rgb),.07);
  }
  .lp-step:first-child .lp-step-marker { box-shadow: 0 0 0 7px rgba(var(--flow-rgb),.12),0 0 24px rgba(var(--flow-rgb),.16); }
  .lp-step:last-child .lp-step-marker { background: var(--flow-color); border-color: var(--flow-color); color: #061221; }
  .lp-step-body {
    flex: 1; min-height: 164px; padding: 21px 19px; border-radius: 15px;
    background: rgba(13,32,64,.78); border: 1px solid rgba(var(--flow-rgb),.14);
    box-shadow: 0 12px 30px rgba(0,0,0,.12);
  }
  .lp-flow-lane.citizen .lp-step-body { background: rgba(8,42,51,.72); }
  .lp-step-label { display: block; font-size: 19px; font-weight: 700; color: #fff; line-height: 1.25; margin-bottom: 12px; }
  .lp-step-screen { font-size: 13px; font-weight: 700; color: var(--flow-color); margin-bottom: 8px; }
  .lp-step-desc { font-size: 14px; color: #94a3b8; line-height: 1.7; margin: 0; word-break: keep-all; }
  .lp-step-arrow {
    position: absolute; z-index: 2; top: 17px; right: -22px;
    display: inline-flex; color: var(--flow-color); filter: drop-shadow(0 0 6px rgba(var(--flow-rgb),.35));
    opacity: 0; transform: translateX(-8px); transition: opacity .35s ease, transform .5s cubic-bezier(.22,1,.36,1);
  }
  .lp-flow-lane.visible .lp-step-arrow { opacity: 1; transform: none; }
  .lp-flow-lane.visible .lp-step:nth-child(1) .lp-step-arrow { transition-delay: .16s; }
  .lp-flow-lane.visible .lp-step:nth-child(2) .lp-step-arrow { transition-delay: .3s; }
  .lp-flow-lane.visible .lp-step:nth-child(3) .lp-step-arrow { transition-delay: .44s; }

  @keyframes lp-flow-focus {
    0%,100% { box-shadow: 0 0 0 7px rgba(var(--flow-rgb),.11),0 0 18px rgba(var(--flow-rgb),.12); }
    50% { box-shadow: 0 0 0 10px rgba(var(--flow-rgb),.17),0 0 34px rgba(var(--flow-rgb),.28); }
  }

  /* ── 원칙 ───────────────────────────────────────────────────────── */
  .lp-principles { background: #060e1e; }
  .lp-principles .lp-section-desc { max-width: 780px; }
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
  .lp-cta-note { font-size: 13px; color: #64748b; line-height: 1.7; margin: 22px auto 0; max-width: 720px; word-break: keep-all; }

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
    .lp-audience-card, .lp-audience-progress-btn, .lp-audience-progress-line::after,
    .lp-step, .lp-step-body, .lp-step-marker, .lp-step-arrow, .lp-steps::before { transition: none; animation: none; }
  }
  @media (max-width: 1000px) {
    .lp-nav-links { display: none; }
    .lp-audience-story-grid { grid-template-columns: minmax(230px,.75fr) minmax(420px,1.25fr); gap: 30px; }
    .lp-flow-lane { padding: 30px 28px; }
    .lp-steps { grid-template-columns: 1fr; gap: 0; }
    .lp-steps::before {
      top: 26px; bottom: 26px; left: 25px; right: auto; width: 2px; height: auto;
      background: linear-gradient(180deg,rgba(var(--flow-rgb),.28),var(--flow-color));
      transform: scaleY(0); transform-origin: top;
    }
    .lp-flow-lane.visible .lp-steps::before { transform: scaleY(1); }
    .lp-step { display: grid; grid-template-columns: 52px minmax(0,1fr); gap: 18px; padding-bottom: 24px; }
    .lp-flow-lane.visible .lp-step {
      opacity: .4; transform: translateY(22px); transition-delay: 0s;
    }
    .lp-flow-lane.visible .lp-step.lp-flow-complete {
      opacity: .72; transform: none;
    }
    .lp-flow-lane.visible .lp-step.lp-flow-current {
      opacity: 1; transform: none;
    }
    .lp-step:last-child { padding-bottom: 0; }
    .lp-step-marker { margin: 0; }
    .lp-step-body { min-height: 0; padding: 20px 22px; transition: border-color .35s,box-shadow .35s,transform .45s; }
    .lp-step.lp-flow-current .lp-step-body {
      transform: translateX(5px); border-color: rgba(var(--flow-rgb),.46);
      box-shadow: 0 16px 38px rgba(0,0,0,.2),0 0 0 1px rgba(var(--flow-rgb),.08);
    }
    .lp-step.lp-flow-current .lp-step-marker { animation: lp-flow-focus 1.7s ease-in-out infinite; }
    .lp-step.lp-flow-complete .lp-step-marker {
      background: rgba(var(--flow-rgb),.14); border-color: rgba(var(--flow-rgb),.72);
    }
    .lp-step-arrow {
      top: auto; right: auto; left: 17px; bottom: 1px;
      opacity: .18; transform: rotate(90deg) translateX(-5px); transition-delay: 0s;
    }
    .lp-flow-lane.visible .lp-step-arrow { opacity: .18; transform: rotate(90deg); transition-delay: 0s; }
    .lp-flow-lane.visible .lp-step.lp-flow-current .lp-step-arrow,
    .lp-flow-lane.visible .lp-step.lp-flow-complete .lp-step-arrow {
      opacity: 1; filter: drop-shadow(0 0 8px rgba(var(--flow-rgb),.55));
    }
  }
  @media (max-width: 780px) {
    .lp-audiences { min-height: 220vh; }
    .lp-audience-story { padding: 34px 0 30px; }
    .lp-audience-story-grid { grid-template-columns: 1fr; gap: 24px; }
    .lp-audience-copy .lp-section-desc { max-width: none; }
    .lp-audience-progress { grid-template-columns: repeat(2,minmax(0,1fr)); max-width: none; margin-top: 20px; }
    .lp-audience-progress-btn { grid-template-columns: 30px 1fr; }
    .lp-audience-progress-line { display: none; }
    .lp-audience-stage, .lp-audience-card { min-height: 390px; }
  }
  @media (max-width: 640px) {
    .lp-root .lp-nav { padding: 0 20px; }
    .lp-nav-name { display: none; }
    .lp-hero { padding: 112px 20px 64px; }
    .lp-section { padding: 68px 20px; }
    .lp-facts { gap: 30px; margin-top: 8px; }
    .lp-audience-card { padding: 28px 24px; }
    .lp-flow-lane { padding: 22px 18px; }
    .lp-flow-direction { display: none; }
    .lp-step { grid-template-columns: 46px minmax(0,1fr); gap: 14px; }
    .lp-step-marker { width: 46px; height: 46px; }
    .lp-steps::before { left: 22px; }
    .lp-step-arrow { left: 14px; }
    .lp-step-body { padding: 18px; }
    .lp-principle { padding: 28px 24px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .lp-step, .lp-step-body, .lp-step-marker, .lp-step-arrow, .lp-steps::before { transition: none; animation: none !important; }
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
  const [activeAudience, setActiveAudience] = useState("official");
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

  useEffect(() => {
    const section = document.getElementById("audiences");
    if (!section) return undefined;

    let frameId = 0;
    const updateAudience = () => {
      const rect = section.getBoundingClientRect();
      const travel = Math.max(1, section.offsetHeight - window.innerHeight);
      const progress = Math.min(1, Math.max(0, -rect.top / travel));
      const nextAudience = progress >= 0.5 ? "citizen" : "official";
      setActiveAudience((current) => current === nextAudience ? current : nextAudience);
    };
    const requestUpdate = () => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(updateAudience);
    };

    updateAudience();
    window.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate);
    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("scroll", requestUpdate);
      window.removeEventListener("resize", requestUpdate);
    };
  }, []);

  useEffect(() => {
    const lanes = Array.from(document.querySelectorAll(".lp-flow-lane"));
    if (!lanes.length) return undefined;

    let frameId = 0;
    const updateFlow = () => {
      const isVertical = window.matchMedia("(max-width: 1000px)").matches;
      const triggerY = window.innerHeight * 0.56;

      lanes.forEach((lane) => {
        const steps = Array.from(lane.querySelectorAll(".lp-step"));
        if (!isVertical) {
          steps.forEach((step) => step.classList.remove("lp-flow-current", "lp-flow-complete"));
          return;
        }

        let currentIndex = 0;
        steps.forEach((step, index) => {
          const marker = step.querySelector(".lp-step-marker");
          if (marker && marker.getBoundingClientRect().top <= triggerY) currentIndex = index;
        });
        steps.forEach((step, index) => {
          step.classList.toggle("lp-flow-current", index === currentIndex);
          step.classList.toggle("lp-flow-complete", index < currentIndex);
        });
      });
    };
    const requestUpdate = () => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(updateFlow);
    };

    updateFlow();
    window.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate);
    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("scroll", requestUpdate);
      window.removeEventListener("resize", requestUpdate);
    };
  }, []);

  const scrollToAudience = (audienceKey) => {
    const section = document.getElementById("audiences");
    if (!section) return;

    const sectionTop = window.scrollY + section.getBoundingClientRect().top;
    const travel = Math.max(1, section.offsetHeight - window.innerHeight);
    const targetProgress = audienceKey === "citizen" ? 0.72 : 0.18;
    window.scrollTo({ top: sectionTop + travel * targetProgress, behavior: "smooth" });
  };

  return (
    <div className="lp-root">
      <style>{CSS}</style>

      <nav className="lp-nav" aria-label="주요 메뉴">
        <div className="lp-nav-inner">
          <Link to="/" className="lp-nav-brand">
            <span className="lp-nav-mark">HS</span>
            <span className="lp-nav-name">화성시 상권 지원</span>
          </Link>

          <ul className="lp-nav-links">
            <li><a href="#overview">서비스 개요</a></li>
            <li><a href="#audiences">이용 대상</a></li>
            <li><a href="#flows">이용 흐름</a></li>
            <li><a href="#principles">이용 원칙</a></li>
          </ul>

          <div className="lp-nav-right">
            <Link to="/browse" className="lp-nav-ghost">상권 둘러보기</Link>
            <Link to={enterHref} className="lp-nav-cta">{enterLabel}</Link>
          </div>
        </div>
      </nav>

      <section id="overview" className="lp-hero">
        <div className="lp-hero-inner">
          <span className="lp-badge lp-reveal">
            <span className="lp-badge-dot" />
            화성시 상권 의사결정 지원 서비스
          </span>

          <h1 className="lp-hero-title lp-reveal lp-d1">
            위험 상권은 먼저 발견하고<br />
            <span className="accent">창업 후보는 근거로 비교합니다</span>
          </h1>

          <p className="lp-hero-sub lp-reveal lp-d2">
            담당 공무원에게 폐업 위험 조기경보와 현장 확인 근거를,
            창업 준비 시민에게 수요·공급 기반의 맞춤 상권 탐색을 제공합니다.
          </p>

          <div className="lp-facts lp-reveal lp-d3">
            {HERO_FACTS.map((fact) => (
              <div key={fact.label}>
                <div className="lp-fact-value lp-num">{fact.value}</div>
                <div className="lp-fact-label">{fact.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="audiences" className="lp-section lp-audiences" aria-labelledby="audiences-heading">
        <div className="lp-section-inner lp-audience-story">
          <div className="lp-audience-story-grid">
            <div className="lp-audience-copy">
              <p className="lp-eyebrow lp-reveal">WHO IT HELPS</p>
              <h2 id="audiences-heading" className="lp-section-title lp-reveal lp-d1">두 사용자, 두 가지 이용 방식</h2>
              <p className="lp-section-desc lp-reveal lp-d2">
                담당 공무원은 위험 신호와 현장 확인 근거를 확인하고, 창업 준비 시민은 수요·공급을 바탕으로 후보 상권을 비교합니다.
              </p>

              <div className="lp-audience-progress lp-reveal lp-d3" aria-label="이용자 흐름 선택">
                {AUDIENCES.map((audience, i) => (
                  <button
                    key={audience.key}
                    type="button"
                    className={`lp-audience-progress-btn ${activeAudience === audience.key ? "active" : ""}`}
                    aria-pressed={activeAudience === audience.key}
                    onClick={() => scrollToAudience(audience.key)}
                  >
                    <span className="lp-audience-progress-num lp-num">0{i + 1}</span>
                    <span className="lp-audience-progress-label">{audience.eyebrow}</span>
                    <span className="lp-audience-progress-line" aria-hidden="true" />
                  </button>
                ))}
              </div>
            </div>

            <div className="lp-audience-stage">
              {AUDIENCES.map((audience) => {
                const href = audience.key === "official" ? enterHref : "/browse";
                const linkLabel = audience.key === "official" ? "공무원 화면으로 이동" : "맞춤 상권 찾기";
                const isActive = activeAudience === audience.key;
                return (
                  <article
                    key={audience.key}
                    className={`lp-audience-card ${audience.key} ${isActive ? "active" : ""}`}
                    aria-hidden={!isActive}
                  >
                    <div className="lp-audience-top">
                      <span className="lp-audience-icon"><Icon name={audience.icon} size={27} /></span>
                      <div>
                        <p className="lp-audience-eyebrow">{audience.eyebrow}</p>
                        <p className="lp-audience-type">{audience.key === "official" ? "폐업 조기경보" : "창업 상권 탐색"}</p>
                      </div>
                    </div>
                    <h3 className="lp-audience-title">{audience.title}</h3>
                    <p className="lp-audience-desc">{audience.desc}</p>
                    <ul className="lp-audience-points">
                      {audience.points.map((point) => (
                        <li key={point}><Icon name="check_circle" size={18} /> <span>{point}</span></li>
                      ))}
                    </ul>
                    <Link to={href} className="lp-audience-link" tabIndex={isActive ? 0 : -1}>
                      {linkLabel} <Icon name="arrow_forward" size={18} />
                    </Link>
                  </article>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section id="flows" className="lp-section lp-flow" aria-labelledby="flow-heading">
        <div className="lp-section-inner">
          <p className="lp-eyebrow lp-reveal">HOW TO USE</p>
          <h2 id="flow-heading" className="lp-section-title lp-reveal lp-d1">목적에 따라 이렇게 사용합니다</h2>
          <p className="lp-section-desc lp-reveal lp-d2">
            공무원은 위험 신호에서 현장 확인 순서까지, 시민은 업종 선택에서 후보 상권 비교까지 이어집니다.
          </p>

          <div className="lp-flow-lanes">
            {[
              { key: "official", title: "담당 공무원 흐름", desc: "위험 발견에서 현장 확인 근거까지", icon: "admin_panel_settings", steps: OFFICIAL_STEPS },
              { key: "citizen", title: "창업 준비 시민 흐름", desc: "업종 선택에서 후보 상권 비교까지", icon: "storefront", steps: CITIZEN_STEPS },
            ].map((flow) => (
              <div key={flow.key} className={`lp-flow-lane ${flow.key} lp-reveal`}>
                <div className="lp-flow-lane-head">
                  <span className="lp-flow-lane-icon"><Icon name={flow.icon} size={22} /></span>
                  <div>
                    <p className="lp-flow-lane-title">{flow.title}</p>
                    <p className="lp-flow-lane-desc">{flow.desc}</p>
                  </div>
                  <span className="lp-flow-direction" aria-hidden="true">
                    시작 <Icon name="arrow_forward" size={16} /> 결과
                  </span>
                </div>
                <div className="lp-steps">
                  {flow.steps.map((step, i) => (
                    <div key={step.label} className="lp-step">
                      <div className="lp-step-marker lp-num">0{i + 1}</div>
                      <div className="lp-step-body">
                        <span className="lp-step-label">{step.label}</span>
                        <div className="lp-step-screen">{step.screen}</div>
                        <p className="lp-step-desc">{step.desc}</p>
                      </div>
                      {i < flow.steps.length - 1 && (
                        <span className="lp-step-arrow" aria-hidden="true"><Icon name="arrow_forward" size={18} /></span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Q&A에서 반드시 나오는 질문("AI가 지원 대상을 정하나", "개인정보는")을
          사용 원칙으로 미리 답해둔다. */}
      <section id="principles" className="lp-section lp-principles" aria-labelledby="principles-heading">
        <div className="lp-section-inner">
          <p className="lp-eyebrow lp-reveal">PRINCIPLES</p>
          <h2 id="principles-heading" className="lp-section-title lp-reveal lp-d1">결과를 해석할 때 지키는 원칙</h2>
          <p className="lp-section-desc lp-reveal lp-d2">
            AI는 판단을 대신하지 않습니다. 관측 근거와 한계를 함께 보여주고 최종 결정은 사용자에게 남깁니다.
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
            공무원은 위험 상권을,<br />
            <span style={{ color: "#38bdf8" }}>시민은 창업 후보를 확인하세요</span>
          </h2>
          <p className="lp-section-desc lp-reveal lp-d1">
            폐업 위험 조기경보와 수요·공급 기반 맞춤 상권 탐색을 각 화면에서 바로 확인할 수 있습니다.
          </p>

          <div className="lp-actions lp-reveal lp-d2">
            <Link to={enterHref} className="lp-btn-primary">
              <Icon name={isOfficial ? "dashboard" : "admin_panel_settings"} size={19} />
              {isOfficial ? "공무원 업무 시작" : "공무원 로그인"}
            </Link>
            <Link to="/browse" className="lp-btn-secondary">
              <Icon name="storefront" size={19} />
              나에게 맞는 상권 찾기
            </Link>
          </div>

          <p className="lp-cta-note lp-reveal lp-d3">
            모든 결과는 읍면동 × 업종 단위의 상대 비교입니다. 특정 점포의 폐업이나 창업 성공을 단정하지 않습니다.
          </p>

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
        <p>공무원에게는 폐업 조기경보를, 창업 준비 시민에게는 수요·공급 기반 상권 탐색을 제공합니다.</p>
      </footer>
    </div>
  );
}
