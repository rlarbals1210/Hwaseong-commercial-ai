import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";
import { GradeBadge } from "../components/Badge";
import { NAVER_CLIENT_ID, loadNaverMap, fitBoundsTight, featureName, featurePaths } from "../lib/naverMap";
import useCategories from "../hooks/useCategories";
import useGradeNotice from "../hooks/useGradeNotice";
import useDongs from "../hooks/useDongs";
import usePublicQuery from "../hooks/usePublicQuery";
import SearchableSelect from "../components/SearchableSelect";
import "./officialMapSearch.css";

// 다른 화면과 같은 정의. 이 파일에만 사본이 없어 백엔드 raw 값(2자리)이 그대로 찍혔다 —
// 같은 상권이 대시보드에서 7.1%, 여기서 7.14%로 보였다.
const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

// 지도 배색 — 단일 색조 밝기 단계 (2026-08-29 전면 교체)
//
// 이전에는 등급별 상태색(안정 초록 / 주의 주황 / 위험 빨강)을 폴리곤에 그대로 칠했다.
// 세 가지가 동시에 걸렸다.
//
//   1. 적록색맹에서 초록과 빨강이 구분되지 않는다. 남성 12명 중 1명이고, 공공 서비스다.
//   2. 채도 높은 원색 초록이 화면에서 제일 튀었다. 위험을 찾는 지도인데 눈이 제일 먼저
//      가는 곳이 "안전한 동네"였다.
//   3. 형태 선택이 틀렸다. 위험 업종 비율은 크기(magnitude)라서 한 색의 밝기 단계로
//      그려야 한다. 서로 다른 색조는 "종류가 다르다"는 뜻이고, 여기 값들은 종류가 아니라
//      정도의 차이다.
//
// 따뜻한 계열 한 색조의 5단계로 바꿨다. 초록은 아예 쓰지 않는다.
//
// 밝기 검증(OKLab L): 0.931 / 0.841 / 0.732 / 0.608 / 0.434 — 단조 감소하고 단계 간격이
// 모두 0.09 이상이다. 밝기만으로 순서가 읽히므로 색각과 무관하게 동작한다.
//
// 구간은 실측 분포로 잘랐다(29개 읍면동, 최신 분기): 0%가 9곳, 최대 44.4%.
//
// label은 범례에 그대로 찍힌다. 한글 라벨을 길게 쓰면 다섯 칸에서 서로 붙어버려
// ("10% 미만10~20%") 읽을 수 없다. 단위는 제목에 한 번만 쓰고 여기는 숫자만 둔다.
const RISK_RAMP = [
  { min: 0,  max: 0,        color: "#fbe3d4", label: "0" },
  { min: 0,  max: 10,       color: "#f7bd93", label: "~10" },
  { min: 10, max: 20,       color: "#ef8b4d", label: "10–20" },
  { min: 20, max: 30,       color: "#d4551a", label: "20–30" },
  { min: 30, max: Infinity, color: "#96170f", label: "30+" },
];
const HOLD_COLOR = "#b9bcc4";   // 판단 보류 — 색조가 없는 중립 회색. 램프의 어느 단계도 아니다.

/** 위험 업종 비율(%) -> 폴리곤 색. 범례도 같은 함수를 쓴다.
 *  예전에는 백엔드가 색을 내려주고 프론트에 범례가 따로 있어서 둘이 어긋난 적이 있다
 *  (2026-08-25 감사). 이제 색의 출처는 이 파일 하나다. */
function riskColor(ratio) {
  if (ratio == null) return HOLD_COLOR;
  if (ratio <= 0) return RISK_RAMP[0].color;
  const step = RISK_RAMP.find((s) => ratio > s.min && ratio <= s.max);
  return step ? step.color : RISK_RAMP[RISK_RAMP.length - 1].color;
}

// 색은 값, 진하기는 근거의 두께다. 범례 옆 한 줄로 그 규칙을 밝힌다.
const OPACITY_NOTE = "흐리게 칠해진 읍면동은 표본이 충분한 업종이 10개 미만이라 근거가 얕습니다.";

// 이 화면에만 있던 loadErrorMessage를 lib/api.js의 describeApiError로 옮겼다.
// 다른 6개 화면이 같은 처리를 못 갖고 있어서, 토큰이 만료되면 그 화면들은
// "불러오지 못했습니다"만 반복하고 재로그인하라는 안내가 없었다.

/** 업종 평균 대비 위치를 한 줄로 보여주는 막대.
 *
 *  "10.49%"만 있으면 그게 높은지 낮은지 알 수 없다. 업종마다 정상 수준이 다르기 때문이다
 *  (일반교육 11.57% vs 부동산서비스 2.95%). 기준선을 눈금으로 찍고 셀을 그 옆에 놓는다.
 *  축 최대는 업종 평균의 2.5배로 고정한다 — 행마다 축이 달라지면 막대 길이를 세로로
 *  비교할 수 없고, 그게 이 표에서 눈이 제일 먼저 하는 일이다.
 */
function ExcessBar({ rate, average }) {
  if (rate == null || average == null || average <= 0) return null;
  const max = average * 2.5;
  const pos = Math.min(rate / max, 1) * 100;
  const basePos = Math.min(average / max, 1) * 100;
  const over = rate > average;
  return (
    <div style={{ position: "relative", height: 6, background: "var(--surface-sunken, #eee)", borderRadius: 3, marginTop: 5 }}>
      <div
        style={{
          position: "absolute", left: 0, top: 0, bottom: 0, width: `${pos}%`,
          background: over ? "var(--error)" : "var(--ink-faint)", borderRadius: 3, opacity: over ? 0.85 : 0.45,
        }}
      />
      {/* 업종 평균 눈금. 막대 위에 그려야 가려지지 않는다. */}
      <div
        style={{
          position: "absolute", left: `${basePos}%`, top: -2, bottom: -2, width: 2,
          background: "var(--on-surface)", opacity: 0.55, transform: "translateX(-1px)",
        }}
      />
    </div>
  );
}

function RankingTable({ rows, loading, error, category, categories, categoryError, onCategoryChange, sort, onSortChange, onClose }) {
  const { sampleMin } = useGradeNotice();
  // 한 업종으로 좁히면 표시 순위와 업종 내 순위가 같은 키로 정렬돼 숫자가 똑같아진다.
  // 같은 값 두 열을 나란히 두는 대신 열을 접고, 모집단 크기는 아래 설명으로 옮긴다.
  const filtered = Boolean(category);
  const industryTotal = filtered ? rows.find((r) => r.industry_total)?.industry_total : null;
  const byExcess = sort === "excess";

  return (
    <div className="card">
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap" }}>
        <h3 className="t-h3" style={{ margin: 0 }}>
          상권 순위표 — {byExcess ? "업종 평균 대비 초과폭" : "최근 1년 누적 폐업률"}
        </h3>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          {/* 정렬 축 전환. 같은 데이터를 다른 질문으로 읽는 것이라 필터가 아니라 탭에 가깝다. */}
          <div className="seg">
            {[
              { key: "rate", label: "폐업률 높은 순" },
              { key: "excess", label: "업종 평균 대비" },
            ].map((option) => (
              <button
                key={option.key}
                type="button"
                onClick={() => onSortChange(option.key)}
                aria-pressed={sort === option.key}
                className="seg-item"
              >
                {option.label}
              </button>
            ))}
          </div>
          <SearchableSelect label="업종" icon="storefront"
            options={categories.map((c) => ({ value: c, label: c }))}
            value={category} emptyLabel="전체 업종" onChange={onCategoryChange} />
          {/* 서랍으로 열리는 표라 닫는 길이 표 안에도 있어야 한다. 지도 위 버튼까지
              마우스를 올려보내지 않게 한다. */}
          {onClose && (
            <button type="button" onClick={onClose} aria-label="순위표 닫기" className="btn-ghost">
              <span className="material-symbols-outlined" style={{ fontSize: 20 }}>close</span>
            </button>
          )}
        </div>
      </div>
      <p style={{ margin: "6px 0 16px", fontSize: 12, color: "var(--outline)" }}>
        순수 관측치 정렬, 보정·예측 없음(표본 {sampleMin}개 이상 업종만 집계).
        {byExcess ? (
          <>
            {" "}<b style={{ color: "var(--ink-secondary)" }}>
              업종마다 정상 폐업률이 달라(일반교육 11.6% · 부동산서비스 3.0%) 절대값만으로는 비교가 안 됩니다.
            </b>{" "}
            그 업종의 화성시 전체 평균을 기준선으로 두고, 얼마나 벗어났는지로 줄을 세웠습니다.
          </>
        ) : (
          <>
            {" "}단일 분기는 폐업 1~2건 차이로 값이 크게 튀어 4분기 누적으로 봅니다.
          </>
        )}
        {/* 위 지도는 동x분기 집계라 업종 축이 없다. 필터가 지도까지 걸린 것으로 읽히면 안 된다. */}
        {" "}<b style={{ color: "var(--ink-secondary)" }}>업종 선택은 이 표에만 적용되며, 위 지도는 전체 업종 기준입니다.</b>
        {categoryError && (
          <span style={{ color: "var(--error)" }}> 업종 목록을 불러오지 못했습니다.</span>
        )}
        {filtered && industryTotal && (
          <> {category} · 분석 가능 {industryTotal}곳 중 상위 {rows.length}</>
        )}
      </p>
      {loading ? (
        <div className="t-body-sm" style={{ padding: 24, textAlign: "center", color: "var(--ink-faint)" }}>불러오는 중...</div>
      ) : error ? (
        <div className="t-body-sm" style={{ padding: 24, textAlign: "center", color: "var(--error)" }}>{error}</div>
      ) : rows.length === 0 ? (
        /* 0으로 채우면 "판단 불가"가 "가장 안전"으로 읽힌다. 없는 이유를 적는다. */
        <div className="t-body-sm" style={{ padding: 24, textAlign: "center", color: "var(--ink-faint)", lineHeight: 1.7 }}>
          {filtered
            ? `${category}은(는) 최근 1년 누적값이 아직 산출되지 않았습니다. 4분기가 쌓여야 값이 나옵니다.`
            : "데이터 없음"}
        </div>
      ) : (
        /* 사각지대·비교 화면과 같은 패턴. 이 표만 스크롤 래퍼가 없어 1280px에서 헤더가 줄바꿈됐다. */
        <div style={{ overflowX: "auto" }}>
        <table style={{ minWidth: 560 }}>
          <thead>
            <tr>
              <th style={{ fontWeight: 600 }}>순위</th>
              <th style={{ fontWeight: 600 }}>읍면동</th>
              <th style={{ fontWeight: 600 }}>업종</th>
              <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>최근 1년 누적 폐업률</th>
              {byExcess && <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>업종 평균 대비</th>}
              <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>폐업</th>
              <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>점포수</th>
              {!filtered && <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>업종 내</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.area_id}-${r.industry_id}`}>
                <td style={{ padding: "8px 4px", color: "var(--outline)" }}>{r.rank}</td>
                {/* 읍면동 칸을 셀 상세로 잇는다. 폐업률 최악 목록을 보여주고 클릭할 수 없으면
                    담당자의 다음 행동이 끊긴다(사각지대 표와 같은 처리). */}
                <td style={{ padding: "8px 4px", fontWeight: 600 }}>
                  <Link
                    to={`/cells/${r.area_id}/${r.industry_id}`}
                    style={{ color: "var(--on-surface)", textDecoration: "none" }}
                  >
                    {r.dong}
                  </Link>
                </td>
                <td style={{ color: "var(--ink-muted)" }}>{r.category}</td>
                <td className="t-metric" style={{ textAlign: "right", color: "var(--error)" }}>
                  {fmt(r.closure_rate_pct)}%
                  {/* 기준선 대비 위치. 절대값 옆에 붙여야 "이게 높은 건가"에 같은 자리에서 답한다. */}
                  {byExcess && <ExcessBar rate={r.closure_rate_pct} average={r.industry_avg_pct} />}
                </td>
                {byExcess && (
                  <td className="t-metric" style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {r.excess_pp == null ? (
                      <span style={{ color: "var(--ink-faint)", fontWeight: 400 }}>—</span>
                    ) : (
                      <>
                        <span style={{ color: r.excess_pp > 0 ? "var(--error)" : "var(--ink-muted)", fontWeight: 700 }}>
                          {r.excess_pp > 0 ? "+" : ""}{fmt(r.excess_pp, 2)}pp
                        </span>
                        <div className="t-caption" style={{ color: "var(--ink-faint)", fontWeight: 400, marginTop: 2 }}>
                          평균 {fmt(r.industry_avg_pct, 2)}%
                          {r.excess_ratio != null && ` · ${fmt(r.excess_ratio, 2)}배`}
                        </div>
                      </>
                    )}
                  </td>
                )}
                <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-muted)" }}>{r.cumulative_closure_count ?? "—"}곳</td>
                <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-muted)" }}>{r.store_count}</td>
                {!filtered && (
                  <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-faint)" }}>
                    {r.industry_rank ? `${r.industry_rank}/${r.industry_total}` : "—"}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}

/** 읍면동 상세 패널.
 *
 *  예전 패널은 "위험 업종 비율 0.0%"와 표본 충족률만 말하고 끝났다. 담당자의 다음 질문은
 *  반드시 "그래서 어느 업종인가"인데 화면에서 동선이 끊겼다.
 *
 *  세 가지를 한 화면에서 답한다 —
 *    ① 어느 업종이 나쁜가   업종 목록(표본충분, 폐업률 순)
 *    ② 동 전체로는 어떤가   업종 구분 없이 묶은 폐업률 + 나머지 지역과의 비교
 *    ③ 무엇이 안 보이는가   사각지대 규모
 *  배후인구는 등급·유형 판정에 관여하지 않는다. 원인의 방향을 좁히는 참고 자료다.
 */
/* 한 줄에 세 가지가 들어간다 — 무엇을 재는가(label) / 값(children) / 단서(hint).
 *
 * 제목과 값을 크기·굵기로만 갈랐더니 "큰 글자 옆의 작은 글자"일 뿐 종류가 달라 보이지
 * 않았다. 둘 다 결국 같은 축(강함↔약함) 위에 있어서다. 그래서 값은 아예 다른 물건으로
 * 만든다 — 카드보다 한 톤 눌린 판 위에 hairline을 두르고 그 안에 올린다.
 * 디자인 시스템의 "입체감은 그림자가 아니라 hairline + 톤 차이" 원칙을 그대로 쓴 것이다.
 *
 *   제목  카드 바탕 위의 굵은 글자   — 묻는 것
 *   값    눌린 판 안의 고정폭 숫자   — 답. 테두리가 있어 형태로 먼저 구분된다
 *   단서  연한 회색 잔글씨          — 배경
 *
 * after: 판 밖에 따로 붙는 것(등급 배지 등). 배지를 판 안에 넣으면 칩 안의 칩이 된다.
 */
function Row({ label, children, hint, after }) {
  return (
    <div style={{ padding: "12px 0", borderTop: "1px solid var(--hairline)" }}>
      {/* 패널이 360px이라 긴 제목과 긴 값이 만나면 한 줄에 안 들어간다(예: "주의가 필요한
          업종" + "위험 3개 · 주의 2개"). 값은 nowrap으로 묶고 컨테이너만 접히게 해서,
          모자랄 때 값이 통째로 아랫줄로 내려가도록 한다 — 값 중간이 끊기는 것보다 낫다. */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span className="value-label">{label}</span>
        <span className="value-plate" style={{ marginLeft: "auto" }}>{children}</span>
        {after}
      </div>
      {hint && <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 6, lineHeight: 1.5 }}>{hint}</div>}
    </div>
  );
}

function AreaPanel({ selected, detail, loading, category, onClose }) {
  const { sampleMin } = useGradeNotice();
  const [expandedArea, setExpandedArea] = useState(null);
  if (!selected) return null;
  const judged = selected.risk_ratio != null;
  const industries = detail?.industries ?? [];
  const showAllIndustries = expandedArea === selected.name;
  const visibleIndustries = showAllIndustries ? industries : industries.slice(0, 3);
  const dashboardParams = new URLSearchParams({ dong: selected.name });
  if (category) dashboardParams.set("category", category);
  const trend = Number(selected.trend);
  const trendLabel = Number.isFinite(trend)
    ? `분기당 ${trend > 0 ? "+" : ""}${trend.toFixed(3)}%p`
    : "—";
  const VS = {
    높음: { label: "시 평균보다 높음", cls: "badge badge-warn" },
    낮음: { label: "시 평균보다 낮음", cls: "badge badge-ok" },
    차이없음: { label: "유의차 없음", cls: "badge badge-neutral" },
  }[detail?.vs_city ?? "차이없음"];

  return (
    <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h3 className="t-h3" style={{ margin: 0 }}>{selected.name}</h3>
          <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 2 }}>
            {detail ? `${detail.quarter_label} 기준 · 점포 ${detail.total_stores.toLocaleString()}곳` : " "}
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="닫기" className="btn-ghost">
          <span className="material-symbols-outlined" style={{ fontSize: 20 }}>close</span>
        </button>
      </div>

      {/* 등급 요약 */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, margin: "16px 0 4px", flexWrap: "wrap" }}>
        {judged ? (
          <>
            <span className="t-metric t-metric-lg" style={{ color: selected.color, lineHeight: 1 }}>
              {fmt(selected.risk_ratio)}%
            </span>
            <span
              style={{
                fontSize: 12, fontWeight: 700, color: selected.color,
                background: `color-mix(in srgb, ${selected.color} 12%, white)`,
                padding: "4px 12px", borderRadius: "var(--radius-full)",
              }}
            >
              {selected.risk_level}
            </span>
            {/* 근거의 두께는 칩 하나로만 말한다. 자세한 내용은 title과 아래
                "표본 기준 충족 업종" 줄, 지도 범례에 이미 있다. */}
            {selected.evidence_thin && (
              <span className="badge badge-neutral" title={selected.hold_notice ?? undefined}>
                근거 얕음
              </span>
            )}
          </>
        ) : (
          <GradeBadge grade="판단보류" />
        )}
      </div>
      <div className="t-caption" style={{ color: "var(--ink-muted)", marginBottom: 12 }}>
        {judged ? "위험 업종 비율 (최근 1년 누적)" : "읍면동 등급을 판정할 표본이 부족합니다"}
      </div>

      {loading && <div className="t-caption" style={{ color: "var(--ink-muted)", padding: "10px 0" }}>상세 불러오는 중…</div>}

      {detail && (
        <>
          {/* 업종별로는 표본이 모자란 동도 동 전체를 묶으면 분모가 수천이 되어 판정할 수 있다.
              이 줄이 "커버율 0% = 아무것도 모른다"를 막는다. */}
          <Row
            label="동 전체 폐업률"
            after={<span className={VS.cls}>{VS.label}</span>}
            hint={
              detail.city_pooled_closure_rate_pct != null
                ? `업종 구분 없이 묶은 값 · 화성시 ${fmt(detail.city_pooled_closure_rate_pct, 2)}%`
                : "업종 구분 없이 묶은 값"
            }
          >
            {fmt(detail.pooled_closure_rate_pct, 2)}%
          </Row>

          <Row label="주의가 필요한 업종" hint={`점포 ${sampleMin}곳 이상인 ${detail.sample_sufficient_cells}개 업종 중`}>
            <span style={{ color: "var(--error)" }}>위험 {detail.risk_cells}개</span>
            <span style={{ color: "var(--ink-faint)", margin: "0 5px" }}>·</span>
            <span style={{ color: "var(--accent-orange)" }}>주의 {detail.caution_cells}개</span>
          </Row>

          <Row
            label="폐업률 추이"
            hint="최근 4개 분기의 누적 폐업률 흐름입니다. 양수면 상승, 음수면 하락을 뜻합니다."
          >
            {trendLabel}
          </Row>

          <Row
            label="표본 기준 충족 업종"
            hint={
              selected.evidence_thin
                ? `표본 충족률 ${detail.coverage_pct}% · 업종 10개 미만이라 읍면동 등급의 근거가 얕습니다`
                : `표본 충족률 ${detail.coverage_pct}% · 점포 ${sampleMin}곳 이상 기준`
            }
          >
            {detail.sample_sufficient_cells}개 / 전체 {detail.total_cells}개
          </Row>

          <Row
            label="사각지대"
            hint={`점포 ${sampleMin}곳 미만이라 통계 판단을 보류한 업종 · 점포 ${detail.blindspot_stores.toLocaleString()}곳, 전체의 ${
              detail.total_stores ? Math.round(detail.blindspot_stores / detail.total_stores * 100) : 0
            }%`}
          >
            {detail.blindspot_cells}개 업종
          </Row>

          {detail.population != null && (
            <Row
              label="배후인구"
              hint={
                detail.population_change_pct != null
                  ? `${detail.population_from_label} → ${detail.population_to_label} ${detail.population_change_pct > 0 ? "+" : ""}${detail.population_change_pct}%`
                  : null
              }
            >
              {detail.population.toLocaleString()}명
            </Row>
          )}

          {/* "그래서 어느 업종인가" — 이 목록이 이 패널의 존재 이유다 */}
          {industries.length > 0 && (
            <div className="official-map-industry-list" style={{ marginTop: 16 }}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
                {/* Row의 label과 같은 성격(무엇을 재는가)이라 같은 무게로 맞춘다. */}
                <div className="t-body-sm" style={{ color: "var(--on-surface)", fontWeight: 600 }}>
                  업종별 폐업률
                </div>
                <span className="t-caption" style={{ color: "var(--ink-faint)", flexShrink: 0 }}>
                  표본 기준 충족 {industries.length}개
                </span>
              </div>
              <div style={{ margin: "0 -6px" }}>
                {visibleIndustries.map((item) => (
                  <Link
                    key={item.industry_id}
                    to={`/cells/${item.area_id}/${item.industry_id}`}
                    style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "7px 6px", borderRadius: "var(--radius-sm)",
                      textDecoration: "none", color: "inherit",
                    }}
                  >
                    <span className="t-caption" style={{ color: "var(--on-surface)", flex: "1 1 auto", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {item.category}
                    </span>
                    <span className="t-caption" style={{ color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
                      {fmt(item.cumulative_closure_rate_pct, 1)}%
                    </span>
                    <GradeBadge grade={item.risk_grade} />
                  </Link>
                ))}
              </div>
              {industries.length > 3 && (
                <button
                  type="button"
                  className="official-map-industry-toggle"
                  aria-expanded={showAllIndustries}
                  onClick={() => setExpandedArea(showAllIndustries ? null : selected.name)}
                >
                  {showAllIndustries ? "간단히 보기" : `전체 ${industries.length}개 보기`}
                  <span className="material-symbols-outlined" aria-hidden="true">
                    {showAllIndustries ? "expand_less" : "expand_more"}
                  </span>
                </button>
              )}
            </div>
          )}
        </>
      )}
      <div className="official-map-dashboard-action">
        <div className="t-caption" style={{ color: "var(--ink-muted)" }}>
          {selected.name} · {category || "전체 업종"}
        </div>
        <Link to={`/dashboard?${dashboardParams}`} className="btn-utility">
          조기경보 대시보드 보기
          <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
        </Link>
      </div>
    </div>
  );
}

export default function MapPage() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const detailPanelRef = useRef(null);
  const polygonsRef = useRef([]);
  const geometryRef = useRef(null);
  const areaPolygonsRef = useRef([]);
  const [mapVersion, setMapVersion] = useState(0);
  const [focusVersion, setFocusVersion] = useState(0);
  const { dongs, error: dongError } = useDongs();
  const [riskData, setRiskData] = useState([]);
  const [selectedName, setSelectedName] = useState(null);
  const selected = selectedName ? { name: selectedName, ...riskData.find((row) => row.dong === selectedName) } : null;
  const detailQuery = usePublicQuery(selected?.area_id ? `/api/alerts/area/${selected.area_id}/detail` : null);
  const [tooltip, setTooltip] = useState(null);
  const [ranking, setRanking] = useState([]);
  const [rankingLoading, setRankingLoading] = useState(true);
  const [category, setCategory] = useState("");
  // 순위표 정렬 축. "폐업률 높은 순"이 기본 — 처음 여는 사람에게는 절대값이 자연스럽다.
  const [rankSort, setRankSort] = useState("rate");
  // 순위표는 지도를 떠나지 않고 서랍으로 연다. 기본값은 닫힘 — 지도가 먼저 보여야 한다.
  const [rankingOpen, setRankingOpen] = useState(false);
  // 순위표와 같은 집합(최신 분기·표본충분)을 좁히는 purpose를 쓴다.
  const { categories, error: categoryError } = useCategories("policy");
  const [mapError, setMapError] = useState("");
  const [rankingError, setRankingError] = useState("");

  useEffect(() => {
    // apiFetchJson을 쓴다. 예전처럼 raw fetch로 상태를 직접 처리하면 401이 와도
    // 앱이 로그아웃 상태로 넘어가지 않아, 화면만 오류 문구를 띄운 채 머문다.
    apiFetchJson(`/api/alerts/vacancy-risk/map`)
      .then((d) => {
        // 오류 본문은 배열이 아니라 {detail: ...}라 그대로 넣으면 map()에서 터진다
        setRiskData(Array.isArray(d) ? d : []);
        setMapError("");
      })
      .catch((err) => {
        setRiskData([]);
        setMapError(describeApiError(err));
      });
  }, []);

  // 순위표만 업종 필터에 반응한다. 지도 fetch와 한 effect에 두면 업종을 바꿀 때마다
  // riskData가 새 배열이 되어 폴리곤 29개가 통째로 다시 그려진다.
  useEffect(() => {
    const params = new URLSearchParams({ limit: 10, sort: rankSort });
    if (category) params.set("category", category);
    apiFetchJson(`/api/alerts/closure-rate-ranking?${params}`)
      .then((d) => {
        setRanking(Array.isArray(d) ? d : []);
        setRankingError("");
      })
      .catch((err) => {
        setRanking([]);
        setRankingError(describeApiError(err));
      })
      .finally(() => setRankingLoading(false));
  }, [category, rankSort]);

  const selectArea = useCallback((name) => {
    setRankingOpen(false);
    setTooltip(null);
    setSelectedName(name || null);
    setFocusVersion((version) => version + 1);
  }, []);

  const drawPolygons = useCallback((map, geojson, riskMap) => {
    polygonsRef.current.forEach((p) => p.setMap(null));
    polygonsRef.current = [];
    areaPolygonsRef.current = [];

    geojson.features.forEach((feat) => {
      const name = feat.properties.dong_name || feat.properties.EMD_KOR_NM || "";
      const risk = riskMap[name];
      const ratio = risk?.risk_ratio ?? null;
      // 색은 여기서 정한다. 백엔드의 risk.color(등급 상태색)는 더 이상 폴리곤에 쓰지 않는다.
      const color = riskColor(ratio);
      const held = ratio == null;   // 판단 보류 — 표본 충분 업종이 기준 미만
      const coverage = risk?.coverage_pct ?? null;
      // 색은 값, 진하기는 근거의 두께. 표본충분 업종이 적은 동은 값을 내되 흐리게 칠해
      // "이 색을 얼마나 믿을지"를 같이 보여준다. 숨기는 것보다 알려주는 쪽을 택했다.
      const thin = Boolean(risk?.evidence_thin);
      const baseOpacity = held ? 0.5 : thin ? 0.45 : 0.8;
      const hoverOpacity = held ? 0.7 : thin ? 0.65 : 0.95;
      // 판단 보류는 색조가 없는 회색이라 램프의 제일 옅은 단계(0%)와 헷갈릴 수 있다.
      // 테두리를 점선으로 끊어 색 말고도 구분되게 한다.

      const coords = feat.geometry.type === "Polygon"
        ? [feat.geometry.coordinates]
        : feat.geometry.coordinates;

      coords.forEach((rings) => {
        const path = rings[0].map(([lng, lat]) => new window.naver.maps.LatLng(lat, lng));
        const polygon = new window.naver.maps.Polygon({
          map, paths: [path], fillColor: color, fillOpacity: baseOpacity,
          strokeColor: held ? "#6b7280" : "#ffffff",
          strokeWeight: held ? 1.2 : 1.5,
          strokeStyle: held ? "shortdash" : "solid",
          clickable: true,
        });

        window.naver.maps.Event.addListener(polygon, "mouseover", (e) => {
          polygon.setOptions({ fillOpacity: hoverOpacity });
          setTooltip({ name, ratio, coverage, color, thin, x: e.pointerEvent.clientX, y: e.pointerEvent.clientY });
        });
        window.naver.maps.Event.addListener(polygon, "mousemove", (e) => {
          setTooltip((t) => t ? { ...t, x: e.pointerEvent.clientX, y: e.pointerEvent.clientY } : null);
        });
        window.naver.maps.Event.addListener(polygon, "mouseout", () => {
          polygon.setOptions({ fillOpacity: baseOpacity });
          setTooltip(null);
        });
        window.naver.maps.Event.addListener(polygon, "click", () => {
          selectArea(name);
        });

        polygonsRef.current.push(polygon);
        areaPolygonsRef.current.push({ name, polygon, held });
      });
    });
  }, [selectArea]);

  useEffect(() => {
    if (!NAVER_CLIENT_ID) return;
    const riskMap = Object.fromEntries(riskData.map((r) => [r.dong, r]));

    loadNaverMap().then(() => {
      if (!mapRef.current) return;
      if (!mapInstanceRef.current) {
        mapInstanceRef.current = new window.naver.maps.Map(mapRef.current, {
          center: new window.naver.maps.LatLng(37.1997, 126.8312),
          zoom: 11,
        });
      }
      fetch("/hwaseong_emd.geojson")
        .then((r) => r.json())
        .then((geojson) => {
          geometryRef.current = geojson;
          drawPolygons(mapInstanceRef.current, geojson, riskMap);
          setMapVersion((version) => version + 1);
        })
        .catch(() => {
          // console.warn만 하면 타일은 뜨는데 폴리곤이 하나도 없는 상태가 되고,
          // 담당자는 "데이터가 없구나"로 읽는다. 원인을 화면에 남긴다.
          setMapError(
            "지도 경계 파일(hwaseong_emd.geojson)을 불러오지 못했습니다. " +
            "frontend/public에 파일이 있는지 확인해주세요."
          );
        });
    }).catch((err) => setMapError(err.message));
  }, [riskData, drawPolygons]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    const geojson = geometryRef.current;
    if (!map || !geojson || !window.naver?.maps) return;
    areaPolygonsRef.current.forEach(({ name, polygon, held }) => polygon.setOptions({
      strokeColor: name === selectedName ? "#174f79" : held ? "#6b7280" : "#ffffff",
      strokeWeight: name === selectedName ? 3.5 : held ? 1.2 : 1.5,
      strokeStyle: name === selectedName ? "solid" : held ? "shortdash" : "solid",
    }));
    const features = selectedName ? geojson.features.filter((feature) => featureName(feature) === selectedName) : geojson.features;
    if (!features.length) return;
    const bounds = new window.naver.maps.LatLngBounds();
    features.forEach((feature) => featurePaths(feature).forEach((path) => path.forEach((point) => bounds.extend(point))));
    const focus = () => {
      map.autoResize();
      if (!selectedName) {
        fitBoundsTight(map, bounds);
        return;
      }
      const canvas = mapRef.current.getBoundingClientRect();
      const panel = detailPanelRef.current?.getBoundingClientRect();
      const narrow = window.matchMedia("(max-width: 1100px)").matches;
      const margin = narrow
        ? { top: 145, right: 24, bottom: panel ? canvas.bottom - panel.top + 20 : 24, left: 24 }
        : { top: 105, right: panel ? canvas.right - panel.left + 24 : 24, bottom: 110, left: 28 };
      map.fitBounds(bounds, margin);
      // fitBounds의 비대칭 여백만으로는 패널을 피하지 못하므로 남은 공간의 중앙에 맞춘다.
      const projection = map.getProjection();
      const point = projection.fromCoordToOffset(bounds.getCenter());
      const targetX = (margin.left + canvas.width - margin.right) / 2;
      const targetY = (margin.top + canvas.height - margin.bottom) / 2;
      map.setCenter(projection.fromOffsetToCoord(new window.naver.maps.Point(
        canvas.width / 2 + point.x - targetX, canvas.height / 2 + point.y - targetY,
      )));
    };
    let frame = requestAnimationFrame(focus);
    const resize = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(focus); };
    window.addEventListener("resize", resize);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("resize", resize); };
  }, [selectedName, focusVersion, mapVersion]);

  return (
    <div className="official-page official-map-page">
      <div className="official-map-workspace">
        {/* 순위표를 별도 화면(탭)에서 지도 위 서랍으로 옮겼다(2026-08-29).
            탭은 지도를 떠나야 표를 볼 수 있어서, 담당자가 "이 동이 왜 진한지"를 확인하려면
            화면을 왕복해야 했다. 지도를 켜 둔 채로 표를 여닫는다.

            서랍과 상세 패널은 동시에 열지 않는다. 둘 다 지도 위에 뜨는데 겹치면
            어느 쪽이 위인지에 따라 한쪽이 잘린다. 여는 쪽이 다른 쪽을 닫는다. */}
        <div className="official-map-stage">
          {mapError && (
            <div role="alert" className="official-map-error">
              <span className="material-symbols-outlined" style={{ fontSize: 20, color: "var(--error)" }}>error</span>
              <span className="t-body-sm" style={{ color: "var(--on-surface)" }}>{mapError}</span>
            </div>
          )}
          <div
            ref={mapRef}
            className="official-map-canvas"
          >
            {!NAVER_CLIENT_ID && (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--outline)", flexDirection: "column", gap: 8 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 32 }}>map</span>
                <span style={{ fontSize: 14 }}>frontend/.env에 VITE_NAVER_MAP_CLIENT_ID를 설정하세요</span>
              </div>
            )}
          </div>

          <div className="official-map-search">
            <SearchableSelect label="지역" icon="location_on" unit="곳"
              options={dongs.map((name) => ({ value: name, label: name }))}
              value={selected?.name ?? ""} emptyLabel="화성시 전체"
              onChange={selectArea} />
            {dongError && <p role="alert">{dongError}</p>}
          </div>

          <div className="official-map-legend">
            <span className="t-eyebrow official-map-legend-title">
              위험 업종 비율 (%)
            </span>
            <div className="official-map-legend-items">
              {/* 칸 사이를 2px 띄운다. 붙여 놓으면 경계가 색 차이로만 읽혀서 인접한 두
                  단계가 한 덩어리로 보인다. */}
              <div style={{ display: "flex", gap: 2, alignItems: "flex-end" }}>
                {RISK_RAMP.map((step) => (
                  <div key={step.label} style={{ width: 46, textAlign: "center" }}>
                    <div style={{ height: 10, background: step.color, borderRadius: 2 }} />
                    <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 4, fontSize: 10.5, whiteSpace: "nowrap" }}>
                      {step.label}
                    </div>
                  </div>
                ))}
              </div>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, marginLeft: 4 }}>
                <span style={{ width: 14, height: 10, background: HOLD_COLOR, border: "1px dashed #6b7280", display: "inline-block", flexShrink: 0 }} />
                <span className="t-caption" style={{ color: "var(--ink-secondary)" }}>판단 보류</span>
              </span>
            </div>
            <span className="t-caption official-map-legend-note">
              {OPACITY_NOTE}
            </span>
          </div>

          <button
            type="button"
            className="official-map-ranking-toggle"
            aria-expanded={rankingOpen}
            onClick={() => {
              setTooltip(null);
              setRankingOpen((open) => {
                if (!open) setSelectedName(null);
                return !open;
              });
            }}
          >
            <span className="material-symbols-outlined">{rankingOpen ? "close" : "table_rows"}</span>
            상권 순위표{ranking.length ? ` (${ranking.length})` : ""}
          </button>

          {selected && (
            <div ref={detailPanelRef} className="official-map-detail-panel">
              {detailQuery.error && <p role="alert" className="official-map-detail-error">{detailQuery.error}</p>}
              <AreaPanel
                selected={selected}
                detail={detailQuery.data}
                loading={detailQuery.loading}
                category={category}
                onClose={() => setSelectedName(null)}
              />
            </div>
          )}

          {rankingOpen && (
          <div className="official-map-ranking-drawer">
          <RankingTable
            rows={ranking}
            loading={rankingLoading}
            error={rankingError}
            category={category}
            categories={categories}
            categoryError={categoryError}
            onCategoryChange={(next) => {
              setRankingLoading(true);
              setRankingError("");
              setCategory(next);
            }}
            sort={rankSort}
            onSortChange={(next) => {
              if (next === rankSort) return;
              setRankingLoading(true);
              setRankingError("");
              setRankSort(next);
            }}
            onClose={() => setRankingOpen(false)}
          />
          </div>
          )}
        </div>
      </div>

      {tooltip && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x + 12,
            top: tooltip.y - 32,
            pointerEvents: "none",
            background: "var(--on-surface)",
            color: "#fff",
            fontSize: 12,
            padding: "7px 11px",
            borderRadius: "var(--radius-md)",
            boxShadow: "var(--elev-2)",
            zIndex: 9999,
          }}
        >
          <b>{tooltip.name}</b>
          {tooltip.ratio != null && <span style={{ marginLeft: 8, color: tooltip.color }}>위험 업종 비율 {tooltip.ratio}%</span>}
          {tooltip.ratio == null && <span style={{ marginLeft: 8, color: "var(--ink-faint)" }}>판단보류</span>}
          {tooltip.thin && <span style={{ marginLeft: 6, color: "var(--ink-faint)" }}>· 근거 얕음</span>}
          {tooltip.coverage != null && <span style={{ marginLeft: 8 }}>표본 충족 {tooltip.coverage}%</span>}
        </div>
      )}
    </div>
  );
}
