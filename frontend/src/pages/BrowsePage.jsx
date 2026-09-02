import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import BrowseIntroModal from "../components/BrowseIntroModal";
import FitScorePanel from "../components/FitScorePanel";
import AreaComparison from "../components/exploration/AreaComparison";
import AreaFilter from "../components/exploration/AreaFilter";
import { EMPTY_STARTUP_INPUT } from "../lib/startupCosts";
import IndustryExplorer from "../components/exploration/IndustryExplorer";
import ExplorationTools from "../components/exploration/ExplorationTools";
import "../components/exploration/exploration.css";
import "../components/exploration/browseSections.css";
import usePublicQuery from "../hooks/usePublicQuery";
import { apiFetchJson, describeApiError } from "../lib/api";
import { NAVER_CLIENT_ID, loadNaverMap, featureName, featurePaths, fitBoundsTight } from "../lib/naverMap";

// 기존 서울 프로젝트 MapPage의 핵심 구조를 이식한 공개 상권 탐색 화면.
// 전체화면 지도 + 52px 상단 바 + 좌측 부유 카드를 유지하되, 서울 격자나 개별 점포
// 행위는 가져오지 않는다. 이 프로젝트의 모든 출력은 읍면동 x 업종 집계 단위다.

const fmt = (value, digits = 1) => (
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—"
);
const hasRecommendationEvidence = (item) => Number.isFinite(item?.score) && ["sufficient", "medium"].includes(item?.evidence_key);

const SAVED_INDUSTRY_KEY = "nodaji:browse:industry";
const SAVED_PRESET_KEY = "nodaji:browse:preset";

function remember(key, value) {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // 저장이 막힌 브라우저에서도 현재 탐색은 그대로 동작한다.
  }
}

function recall(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function ServiceLogo() {
  return (
    <svg viewBox="0 0 166 32" aria-hidden="true" className="service-logo">
      <rect x="0" y="2" width="28" height="28" rx="8" fill="#0ea5e9" />
      <text x="14" y="21" textAnchor="middle" fontFamily="Inter, Arial, sans-serif" fontWeight="800" fontSize="10" fill="#ffffff">
        HS
      </text>
      <text x="38" y="21" fontFamily="Noto Sans KR, Inter, Arial, sans-serif" fontWeight="700" fontSize="14" fill="#cde0f0">
        화성시 상권 지원
      </text>
    </svg>
  );
}

function NodajiMapNav() {
  return (
    <header className="nodaji-map-nav">
      <svg viewBox="0 0 1200 52" preserveAspectRatio="none" className="nodaji-nav-wave" aria-hidden="true">
        <path d="M0 36 Q150 26,300 36 Q450 46,600 36 Q750 26,900 36 Q1050 46,1200 32" />
        <path d="M0 42 Q200 30,400 42 Q600 54,800 42 Q1000 30,1200 38" />
      </svg>
      {/* 로고는 홈으로. 자기 자신(/browse)을 가리키면 눌러도 아무 일이 없다. */}
      <Link to="/" className="nodaji-brand" aria-label="서비스 소개로 이동">
        <ServiceLogo />
      </Link>
      <nav aria-label="공개 상권 메뉴" className="nodaji-map-menu">
        <Link to="/browse" className="active">상권 둘러보기</Link>
        <Link to="/trends">상권 트렌드</Link>
        <Link to="/report">요약 보고서</Link>
        <span className="nodaji-menu-divider" />
        <Link to="/login/official">담당자 로그인</Link>
      </nav>
    </header>
  );
}

function MapLegend({ mapData, recommendationVisible, recommendationCount }) {
  if (!mapData?.legend?.length) return null;
  return (
    <div className="nodaji-card-legend" aria-label="최근 1년 누적 폐업률 범례">
      <div className="nodaji-section-label">최근 1년 누적 폐업률</div>
      <div className="nodaji-legend-grid">
        {mapData.legend.map(({ label, color }) => (
          <span key={label}>
            <i style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>
      {recommendationVisible && recommendationCount > 0 && (
        <p><b style={{ color: "#7c3aed" }}>보라색 테두리</b>는 선택 조건에 맞는 추천 {recommendationCount ?? 0}곳입니다.</p>
      )}
    </div>
  );
}

function IndustryPicker({ industries, coverageByIndustry, totalAreaCount, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [menuPosition, setMenuPosition] = useState(null);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const selected = industries.find((industry) => industry.id === value) ?? null;
  const filtered = industries.filter((industry) => industry.name.toLocaleLowerCase("ko").includes(query.trim().toLocaleLowerCase("ko")));

  const updateMenuPosition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const margin = 16;
    const gap = 12;
    const availableRight = window.innerWidth - rect.right - gap - margin;
    const fitsRight = availableRight >= 240;
    const width = fitsRight
      ? Math.min(460, availableRight)
      : Math.min(420, window.innerWidth - margin * 2);
    const left = fitsRight ? rect.right + gap : window.innerWidth - width - margin;
    const top = Math.max(68, Math.min(rect.top, window.innerHeight - 280));
    setMenuPosition({
      left: Math.round(left),
      top: Math.round(top),
      width: Math.round(width),
      maxHeight: Math.max(260, Math.round(window.innerHeight - top - margin)),
      pointsRight: fitsRight,
    });
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [open, updateMenuPosition]);

  const choose = (industryId) => {
    onChange(industryId);
    setOpen(false);
    setQuery("");
  };

  const toggle = () => {
    if (!open) updateMenuPosition();
    setOpen((current) => !current);
  };

  return (
    <div className="nodaji-field">
      <span className="nodaji-step-label"><b>1</b> 어떤 업종을 준비하고 있나요?</span>
      <div className="nodaji-industry-picker" ref={rootRef}>
        <button
          type="button"
          className={`nodaji-industry-trigger${open ? " open" : ""}`}
          onClick={toggle}
          ref={triggerRef}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <span className="nodaji-industry-icon material-symbols-outlined" aria-hidden="true">storefront</span>
          <span className="nodaji-industry-current">
            <small>선택한 업종</small>
            <strong>{selected?.name ?? "업종을 선택해주세요"}</strong>
          </span>
          {selected && <em>전체 {totalAreaCount}곳 확인</em>}
          <span className="nodaji-industry-chevron material-symbols-outlined" aria-hidden="true">expand_more</span>
        </button>

        {open && menuPosition && (
          <div
            className={`nodaji-industry-menu${menuPosition.pointsRight ? " points-right" : ""}`}
            style={{
              left: menuPosition.left,
              top: menuPosition.top,
              width: menuPosition.width,
              maxHeight: menuPosition.maxHeight,
            }}
          >
            <label className="nodaji-industry-search">
              <span className="material-symbols-outlined" aria-hidden="true">search</span>
              <input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="업종 이름으로 검색"
                aria-label="업종 검색"
              />
            </label>
            <div className="nodaji-industry-options" role="listbox" aria-label="업종 목록">
              {filtered.map((industry) => {
                const coverage = coverageByIndustry[industry.id] ?? { observed: 0, sufficient: 0 };
                return (
                  <button
                    key={industry.id}
                    type="button"
                    role="option"
                    aria-selected={industry.id === value}
                    className={industry.id === value ? "active" : ""}
                    onClick={() => choose(industry.id)}
                  >
                    <span>
                      <b>{industry.name}</b>
                      <small>관측 {coverage.observed}곳 · 근거 충분 {coverage.sufficient}곳</small>
                    </span>
                    <span className="material-symbols-outlined" aria-hidden="true">
                      {industry.id === value ? "check_circle" : "arrow_forward"}
                    </span>
                  </button>
                );
              })}
              {!filtered.length && <p>검색 결과가 없습니다.</p>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function PriorityPicker({ data, value, onChange }) {
  const [tooltip, setTooltip] = useState(null); // { text, x, y }

  if (!data?.presets?.length) return null;

  // 좌측 패널이 폭 330px짜리 overflow:auto 카드라 절대배치 툴팁을 카드 안 기준으로 띄우면
  // 사분면 어느 칸이든 카드 경계에 잘린다. position:fixed로 뷰포트 기준 좌표를 직접 계산해
  // 카드의 overflow 클리핑을 아예 우회한다.
  const showTooltip = (event, text) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.min(Math.max(rect.left + rect.width / 2, 100), window.innerWidth - 100);
    setTooltip({ text, x, y: rect.top });
  };
  const hideTooltip = () => setTooltip(null);

  return (
    <fieldset className="nodaji-priority-block">
      <legend><span>2</span> 상권을 고를 때 무엇이 가장 걱정되나요?</legend>
      {/* 기본 추천과 사용자가 실제로 고민하는 세 조건을 2×2로 나란히 놓는다. */}
      <div className="nodaji-priority-grid">
        {data.presets.map((item) => (
          <button
            key={item.key}
            type="button"
            className={item.key === value ? "active" : ""}
            onClick={() => onChange(item.key)}
            aria-pressed={item.key === value}
          >
            <b>{item.label}</b>
            {/* 카드 클릭(선택)과 도움말 호버를 분리 — "?"를 눌러도 선택이 같이 바뀌면
                설명만 보려던 사용자가 의도치 않게 조건을 바꾸게 된다. */}
            <span
              className="nodaji-help-icon"
              aria-hidden="true"
              tabIndex={0}
              onClick={(e) => e.stopPropagation()}
              onMouseEnter={(e) => showTooltip(e, item.description)}
              onMouseLeave={hideTooltip}
              onFocus={(e) => showTooltip(e, item.description)}
              onBlur={hideTooltip}
            >
              ?
            </span>
          </button>
        ))}
      </div>
      {tooltip && (
        <div className="nodaji-help-tip-fixed" role="tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          {tooltip.text}
        </div>
      )}
    </fieldset>
  );
}

function cautionFor(item) {
  if (item.adjustment_note) return item.adjustment_note;
  const weakest = [...(item.breakdown ?? [])].sort((a, b) => a.score - b.score)[0];
  if (weakest?.key === "competition") return "같은 업종 점포가 많은 편이라 실제 경쟁 상황을 확인해야 합니다.";
  if (weakest?.key === "demand") return "예측 수요에 비해 현재 점포 공급이 많은 편이라 현장 수요를 확인해야 합니다.";
  if (weakest?.key === "saturation") return "읍면동 내 업종 비중이 높은 편이라 추가 수요를 확인해야 합니다.";
  return "AI 전망은 상대 비교이므로 임대료와 유동인구 등 현장 조건을 함께 확인해야 합니다.";
}

function RecommendationList({ data, results, areas, areaFilterIds, onAreaFilterChange, priorityLabel, selectedAreaId, onOpenDetail }) {
  if (!data) return null;
  const filtered = areaFilterIds.length > 0;
  const scopeLabel = filtered ? "선택 지역" : "화성시 전체";
  const scored = results.filter((item) => typeof item.score === "number");
  const featured = scored.filter(hasRecommendationEvidence).slice(0, 3);
  const tenure = (quarters) => (
    typeof quarters === "number" ? `${(quarters / 4).toFixed(1)}년` : "—"
  );
  return (
    <div className="nodaji-recommendations">
      <AreaFilter areas={areas} selectedIds={areaFilterIds} onChange={onAreaFilterChange} />
      <div className="nodaji-drawer-heading">
        <div>
          <small>{data.quarter_label} 기준 · {data.industry_name} · {priorityLabel}</small>
          <h2>{featured.length ? `추천 상권 ${featured.length}곳` : filtered ? "선택 범위 내 추천 보류" : "추천 보류 · 전체 지역"}</h2>
        </div>
        <span>점수 비교 {scored.length} / {results.length}곳</span>
      </div>

      <div className="nodaji-comparison-notice">{filtered
        ? `선택한 ${results.length}곳 중 관측값이 있는 ${scored.length}곳을 비교합니다. 점수와 순위는 화성시 전체 기준이며, 필터에 따라 다시 계산하지 않습니다. 점포 ${data.sample_min}곳 미만은 점수를 50점 쪽으로 보정하고 미관측 지역은 순위를 매기지 않습니다.`
        : data.comparison_notice}</div>

      {!featured.length && (
        <div role="alert" className="nodaji-drawer-alert">
          {scopeLabel}에 이 업종의 추천 근거가 충분한 후보가 없습니다. {filtered ? "아래 목록에서 근거 수준을 확인하거나 읍면동 필터를 넓혀주세요." : "아래 목록에서 근거 수준을 확인하거나 다른 업종을 선택해주세요."}
        </div>
      )}

      {data.growth_spread_narrow && (
        <div role="alert" className="nodaji-drawer-alert">
          이 업종은 읍면동 간 예측 차이가 크지 않습니다. 상대점수 차이를 크게 해석하지 마세요.
        </div>
      )}

      <div className="nodaji-result-list">
        {featured.map((item) => (
          <article key={item.area_id} className={`explore-click-card ${item.area_id === selectedAreaId ? "active" : ""}`}
            role="button" tabIndex={0} aria-label={`${item.area_name} 지도 이동 및 상세 보기`}
            onClick={() => onOpenDetail(item.area_id)}
            onKeyDown={(event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); onOpenDetail(item.area_id); } }}>
            <div className="nodaji-result-topline">
              <span className="nodaji-rank">{item.rank}</span>
              <span className="nodaji-result-copy">
                <b>{item.area_name} <i className={`nodaji-evidence evidence-${item.evidence_key}`}>{item.evidence_label}</i></b>
                <small>
                  폐업률 {typeof item.observed.closure_rate_cum4_pct === "number" ? `${fmt(item.observed.closure_rate_cum4_pct)}%` : "—"}
                  · 점포 {item.observed.store_count === 0 ? "0개" : `${item.observed.store_count}개`}
                  · 업력 {tenure(item.observed.tenure_quarters)}
                </small>
                <em>{item.tags.filter((tag) => tag !== item.evidence_label).slice(0, 2).join(" · ")}</em>
              </span>
              <span className="nodaji-result-score">
                <b>{fmt(item.score)}</b>
                <small>조건 적합도</small>
              </span>
            </div>
            <p className="nodaji-result-reason"><b>맞는 이유</b>{item.reason}</p>
            <p className="nodaji-result-caution"><b>확인할 점</b>{cautionFor(item)}</p>
            <span className="explore-card-link">지도와 상세 보기 →</span>
          </article>
        ))}
      </div>

      <details className="nodaji-all-area-list" open={!featured.length}>
        <summary>
          <span>{scopeLabel} {results.length}곳 목록</span>
          <small>관측 {scored.length}곳 · 미관측 {results.length - scored.length}곳</small>
        </summary>
        <div className="nodaji-all-area-head" aria-hidden="true">
          <span>시 순위</span><span>지역과 근거</span><span>점수</span><span>상세</span>
        </div>
        <div className="nodaji-all-area-rows">
          {results.map((item) => {
            const scoreable = typeof item.score === "number";
            return (
              <div key={item.area_id} className={scoreable ? "" : "unobserved"}>
                <span>{item.rank ?? "—"}</span>
                <span>
                  <b>{item.area_name}</b>
                  <small className={`nodaji-evidence evidence-${item.evidence_key}`}>{item.evidence_label}</small>
                </span>
                <strong>{scoreable ? fmt(item.score) : "—"}</strong>
                <button type="button" onClick={() => onOpenDetail(item.area_id)} aria-label={`${item.area_name} 지도 이동 및 상세 보기`}>보기</button>
              </div>
            );
          })}
        </div>
      </details>

      <p className="nodaji-drawer-note">{data.relative_notice.replace("이 목록 안에서", "화성시 전체 지역 안에서")} {data.disclaimer}</p>
    </div>
  );
}

function ObservationSummary({ cell, loading }) {
  if (loading) return <p className="nodaji-empty-copy">관측 자료를 불러오는 중…</p>;
  if (!cell) return null;
  return (
    <div className="nodaji-observation">
      <div className="nodaji-section-label">실제 관측 자료</div>
      {cell.sample_insufficient ? (
        <p>점포가 <b>{cell.store_count}곳</b>이라 비율로 판단하기 어렵습니다. 수치보다 현장 확인이 필요합니다.</p>
      ) : (
        <div className="nodaji-observation-grid">
          <div><span>최근 1년 누적 폐업률</span><b>{fmt(cell.closure_rate_pct)}%</b></div>
          <div><span>같은 기간 폐업</span><b>{cell.closure_count ?? "—"}곳</b></div>
          <div><span>현재 점포</span><b>{cell.store_count ?? "—"}곳</b></div>
        </div>
      )}
    </div>
  );
}

export default function BrowsePage() {
  const location = useLocation();
  const navigate = useNavigate();
  // 랜딩을 거쳐 들어온 경우에만 사용법 팝업을 띄운다. 주소를 직접 친 재방문자는 방해받지 않는다.
  // 마운트 시점의 라우터 state로 한 번만 정한다 — 효과 안에서 setState하면 연쇄 렌더가 된다.
  const [showIntro, setShowIntro] = useState(() => Boolean(location.state?.fromLanding));
  const [options, setOptions] = useState(null);
  const [coverageByIndustry, setCoverageByIndustry] = useState({});
  const [industryId, setIndustryId] = useState(null);
  const [areaId, setAreaId] = useState(null);
  const [presetOptions, setPresetOptions] = useState(null);
  const [preset, setPreset] = useState("균형");
  const [drawerMode, setDrawerMode] = useState(null);
  const [entryMode, setEntryMode] = useState("industry");
  const [areaFilterIds, setAreaFilterIds] = useState([]);
  const [compareAreaIds, setCompareAreaIds] = useState([null, null]);
  const [costDrafts, setCostDrafts] = useState({});
  const [focusVersion, setFocusVersion] = useState(0);
  const [detailTab, setDetailTab] = useState("conditions");
  const [error, setError] = useState("");
  const [mapError, setMapError] = useState("");
  // 지도 인스턴스 생성 완료 신호. 폴리곤·클러스터 효과가 이 값을 기다린다.
  const [mapReady, setMapReady] = useState(false);
  // 경계 파일은 2.8MB다. 내용을 state에 담지 않고 ref에 두고, 도착 사실만 숫자로 알린다.
  const [geojsonVersion, setGeojsonVersion] = useState(0);

  const closeIntro = useCallback(() => {
    setShowIntro(false);
    // state를 지우지 않으면 새로고침·뒤로가기 때 같은 팝업이 다시 뜬다.
    navigate(location.pathname + location.search, { replace: true, state: null });
  }, [navigate, location.pathname, location.search]);
  const [tooltip, setTooltip] = useState(null);

  const mapQuery = usePublicQuery(industryId ? `/api/public/industry-map?industry_id=${industryId}` : null);
  const { data: mapData } = mapQuery;
  const { data: clusterData } = usePublicQuery(industryId ? `/api/recommend/clusters?industry_id=${industryId}` : null);
  const recommendationQuery = usePublicQuery(industryId ? `/api/recommend/areas?industry_id=${industryId}&preset=${encodeURIComponent(preset)}&limit=30` : null);
  const { data: recommendations, loading: recommendationLoading } = recommendationQuery;
  const areaFilterSet = useMemo(() => new Set(areaFilterIds), [areaFilterIds]);
  const recommendationResults = useMemo(() => (recommendations?.results ?? []).filter((item) => (
    !areaFilterSet.size || areaFilterSet.has(item.area_id)
  )), [recommendations, areaFilterSet]);
  const filteredRankedCount = recommendationResults.filter((item) => typeof item.score === "number").length;
  const featuredCount = Math.min(3, recommendationResults.filter(hasRecommendationEvidence).length);
  const showRecommendationScope = entryMode === "industry" || drawerMode === "recommendations";
  const displayedRankedCount = recommendations ? (showRecommendationScope ? filteredRankedCount : recommendations.ranked_count) : "—";
  const displayedTotalCount = showRecommendationScope && recommendations ? recommendationResults.length : mapData?.total_count;
  const showFilteredMap = areaFilterSet.size > 0 && (drawerMode === "recommendations" || (!drawerMode && entryMode === "industry"));
  const hasObservedCell = options?.areas?.find((area) => area.id === areaId)?.industries.some((industry) => industry.id === industryId);
  const cellQuery = usePublicQuery(hasObservedCell ? `/api/public/cell?area_id=${areaId}&industry_id=${industryId}` : null);
  const { data: cell, loading: cellLoading } = cellQuery;
  const scoreQuery = usePublicQuery(areaId && industryId ? `/api/recommend/score?area_id=${areaId}&industry_id=${industryId}&preset=${encodeURIComponent(preset)}` : null);
  const { data: score, loading: scoreLoading } = scoreQuery;
  const queryError = error || mapQuery.error || recommendationQuery.error || cellQuery.error || scoreQuery.error;

  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const polygonsRef = useRef([]);
  const clusterMarkersRef = useRef([]);
  const boundsFitRef = useRef(false);
  const geojsonRef = useRef(null);
  const drawerScrollRef = useRef(null);
  const costKey = `${areaId}:${industryId}`;
  const updateCostDraft = (value) => setCostDrafts((current) => ({ ...current,
    [costKey]: typeof value === "function" ? value(current[costKey] ?? EMPTY_STARTUP_INPUT) : value,
  }));

  const selectArea = useCallback((nextAreaId) => {
    setAreaId(nextAreaId);
    setFocusVersion((value) => value + 1);
    setTooltip(null);
    setDetailTab("conditions");
    setDrawerMode("detail");
  }, []);

  const chooseIndustry = useCallback((nextIndustryId) => {
    if (entryMode !== "direct") setAreaId(null);
    setDrawerMode(null);
    setCompareAreaIds([null, null]);
    setError("");
    setIndustryId(nextIndustryId);
    remember(SAVED_INDUSTRY_KEY, nextIndustryId);
  }, [entryMode]);

  const choosePreset = useCallback((nextPreset) => {
    setPreset(nextPreset);
    remember(SAVED_PRESET_KEY, nextPreset);
  }, []);

  const chooseAreaFirst = useCallback((nextAreaId) => {
    setAreaId(nextAreaId);
    setDrawerMode("industries");
  }, []);

  const chooseIndustryInArea = (nextIndustryId) => {
    setIndustryId(nextIndustryId);
    remember(SAVED_INDUSTRY_KEY, nextIndustryId);
    setCompareAreaIds([null, null]);
    selectArea(areaId);
  };

  const openComparison = () => {
    setCompareAreaIds((current) => current.some(Boolean) ? current : [areaId, null]);
    setDrawerMode("compare");
  };

  useEffect(() => {
    apiFetchJson("/api/recommend/presets")
      .then((data) => {
        const saved = recall(SAVED_PRESET_KEY);
        const initial = data.presets.some((item) => item.key === saved) ? saved : data.default;
        setPresetOptions(data);
        setPreset(initial);
        remember(SAVED_PRESET_KEY, initial);
      })
      .catch((err) => setError(describeApiError(err)));
  }, []);

  useEffect(() => {
    apiFetchJson("/api/public/areas")
      .then((data) => {
        setOptions(data);
        const coverage = new Map();
        (data.areas ?? []).forEach((area) => area.industries.forEach((industry) => {
          const current = coverage.get(industry.id) ?? { observed: 0, sufficient: 0 };
          current.observed += 1;
          if (!industry.sample_insufficient) current.sufficient += 1;
          coverage.set(industry.id, current);
        }));
        setCoverageByIndustry(Object.fromEntries(coverage));
        const best = [...coverage.entries()].sort((a, b) => b[1].sufficient - a[1].sufficient)[0];
        const saved = Number(recall(SAVED_INDUSTRY_KEY));
        const initial = coverage.has(saved) ? saved : best ? best[0] : data.industries?.[0]?.id ?? null;
        setIndustryId(initial);
      })
      .catch((err) => setError(describeApiError(err)));
  }, []);

  const colorByName = useMemo(
    () => Object.fromEntries((mapData?.areas ?? []).map((area) => [area.area_name, area])),
    [mapData],
  );

  const selectedMapArea = useMemo(
    () => mapData?.areas?.find((area) => area.area_id === areaId) ?? null,
    [mapData, areaId],
  );

  const recommendedAreaIds = useMemo(
    () => new Set(
      drawerMode === "recommendations"
        ? recommendationResults.filter(hasRecommendationEvidence).slice(0, 3).map((item) => item.area_id)
        : [],
    ),
    [drawerMode, recommendationResults],
  );

  const focusMapOnArea = useCallback((targetId) => {
    const map = mapInstanceRef.current;
    const name = options?.areas?.find((area) => area.id === targetId)?.name;
    const feature = geojsonRef.current?.features.find((item) => featureName(item) === name);
    if (!map || !feature) return;
    map.autoResize();
    const bounds = new window.naver.maps.LatLngBounds();
    featurePaths(feature).forEach((path) => path.forEach((point) => bounds.extend(point)));
    fitBoundsTight(map, bounds, 24);
  }, [options]);

  useEffect(() => {
    const resize = () => {
      mapInstanceRef.current?.autoResize();
      if (drawerMode === "detail" && areaId) focusMapOnArea(areaId);
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [areaId, drawerMode, focusVersion, focusMapOnArea, mapReady, geojsonVersion]);

  useEffect(() => { drawerScrollRef.current?.scrollTo({ top: 0 }); }, [drawerMode, areaId, industryId]);

  // 폴리곤을 실제로 다시 그릴지 판단하는 비교용 열쇠.
  const styleKeyOf = (options) => (
    `${options.fillColor}|${options.fillOpacity}|${options.strokeColor}|${options.strokeWeight}|${options.clickable}`
  );

  // 한 읍면동이 지금 어떤 모습이어야 하는지. 생성과 갱신이 같은 규칙을 쓰도록 한 곳에 둔다.
  const styleFor = useCallback((name) => {
    const info = colorByName[name];
    const fallbackId = options?.areas?.find((area) => area.name === name)?.id;
    const inScope = !showFilteredMap || areaFilterSet.has(info?.area_id ?? fallbackId);
    const selected = inScope && info?.area_id === areaId;
    const recommended = recommendedAreaIds.has(info?.area_id);
    const baseOpacity = !inScope ? 0.08 : !info ? 0.3 : info.sample_insufficient ? 0.5 : 0.74;
    return {
      info,
      inScope,
      options: {
        fillColor: info?.color || "#c1c6d5",
        fillOpacity: selected ? 0.95 : baseOpacity,
        strokeColor: selected ? "#005db2" : recommended ? "#7c3aed" : "#fff",
        strokeWeight: selected ? 4 : recommended ? 2.5 : 1.5,
        clickable: inScope,
      },
    };
  }, [colorByName, options, showFilteredMap, areaFilterSet, areaId, recommendedAreaIds]);

  // 폴리곤 이벤트 핸들러는 폴리곤을 만들 때 한 번만 붙는다. 그래서 최신 값을 클로저에
  // 가두면 안 되고 ref로 읽어야 한다 — 이 두 효과가 매 렌더 ref를 갱신한다.
  // 선언 순서가 곧 실행 순서라, 아래 폴리곤 효과들보다 반드시 위에 있어야 한다.
  const styleForRef = useRef(styleFor);
  useEffect(() => { styleForRef.current = styleFor; }, [styleFor]);

  const clickContextRef = useRef(null);
  useEffect(() => {
    clickContextRef.current = { colorByName, options, entryMode, selectArea, chooseAreaFirst };
  }, [colorByName, options, entryMode, selectArea, chooseAreaFirst]);

  const drawStoreClusters = useCallback((map) => {
    clusterMarkersRef.current.forEach((marker) => marker.setMap(null));
    clusterMarkersRef.current = [];
    if (showFilteredMap || !clusterData?.clusters?.length || map.getZoom() < 14) return;

    clusterMarkersRef.current = clusterData.clusters.map((item) => {
      const diameter = Math.max(28, Math.min(48, 24 + Math.log2(item.store_count + 1) * 5));
      return new window.naver.maps.Marker({
        map,
        position: new window.naver.maps.LatLng(item.lat, item.lng),
        zIndex: 40,
        icon: {
          content: `<div aria-hidden="true" style="width:${diameter}px;height:${diameter}px;border-radius:999px;background:rgba(0,93,178,.88);border:2px solid white;color:white;display:flex;align-items:center;justify-content:center;font:600 12px Inter,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.18)">${Number(item.store_count)}</div>`,
          anchor: new window.naver.maps.Point(diameter / 2, diameter / 2),
        },
      });
    });
  }, [clusterData, showFilteredMap]);

  const drawClustersRef = useRef(drawStoreClusters);
  useEffect(() => { drawClustersRef.current = drawStoreClusters; }, [drawStoreClusters]);

  // ① 지도 인스턴스 — 화면당 한 번만 만든다.
  useEffect(() => {
    if (!NAVER_CLIENT_ID) return;
    let cancelled = false;
    loadNaverMap().then(() => {
      if (cancelled || !mapRef.current) return;
      if (!mapInstanceRef.current) {
        mapInstanceRef.current = new window.naver.maps.Map(mapRef.current, {
          center: new window.naver.maps.LatLng(37.1997, 126.8312),
          zoom: 11,
          zoomControl: false,
          mapDataControl: false,
          scaleControl: true,
        });
      }
      setMapReady(true);
    }).catch((err) => { if (!cancelled) setMapError(err.message); });
    return () => { cancelled = true; };
  }, []);

  // ② 경계 파일 — 2.8MB에 좌표 6만 개다. 한 번만 받아 ref에 캐시한다.
  //    예전에는 이 fetch가 지도 효과 안에 있어서 지역을 고를 때마다 다시 받고 다시 파싱했다.
  useEffect(() => {
    let cancelled = false;
    fetch("/hwaseong_emd.geojson")
      .then((response) => response.json())
      .then((data) => {
        if (cancelled) return;
        geojsonRef.current = data;
        setGeojsonVersion((value) => value + 1);
      })
      .catch(() => { if (!cancelled) setMapError("지도 경계 파일을 불러오지 못했습니다."); });
    return () => { cancelled = true; };
  }, []);

  // ③ 폴리곤 생성 — 지도와 경계 파일이 준비됐을 때만. 색·선택 상태가 바뀐다고 다시 만들지 않는다.
  useEffect(() => {
    const map = mapInstanceRef.current;
    const geojson = geojsonRef.current;
    if (!mapReady || !map || !geojson) return undefined;

    polygonsRef.current.forEach((entry) => entry.polygon.setMap(null));
    polygonsRef.current = [];

    geojson.features.forEach((feature) => {
      const name = featureName(feature);
      featurePaths(feature).forEach((path) => {
        const polygon = new window.naver.maps.Polygon({
          map,
          paths: [path],
          ...styleForRef.current(name).options,
        });
        polygonsRef.current.push({ polygon, name, styleKey: styleKeyOf(styleForRef.current(name).options) });

        window.naver.maps.Event.addListener(polygon, "mouseover", (event) => {
          const state = styleForRef.current(name);
          if (!state.inScope) return;
          polygon.setOptions({ fillOpacity: 0.94 });
          setTooltip({ name, info: state.info, x: event.pointerEvent.clientX, y: event.pointerEvent.clientY });
        });
        window.naver.maps.Event.addListener(polygon, "mousemove", (event) => {
          setTooltip((current) => current ? { ...current, x: event.pointerEvent.clientX, y: event.pointerEvent.clientY } : null);
        });
        window.naver.maps.Event.addListener(polygon, "mouseout", () => {
          polygon.setOptions({ fillOpacity: styleForRef.current(name).options.fillOpacity });
          setTooltip(null);
        });
        window.naver.maps.Event.addListener(polygon, "click", () => {
          if (!styleForRef.current(name).inScope) return;
          const context = clickContextRef.current;
          if (!context) return;
          const clickedId = context.colorByName[name]?.area_id
            ?? context.options?.areas?.find((item) => item.name === name)?.id;
          if (clickedId) (context.entryMode === "area" ? context.chooseAreaFirst : context.selectArea)(clickedId);
        });
      });
    });

    if (!boundsFitRef.current) {
      const bounds = new window.naver.maps.LatLngBounds();
      geojson.features.forEach((feature) => featurePaths(feature).forEach((path) => path.forEach((point) => bounds.extend(point))));
      map.fitBounds(bounds);
      boundsFitRef.current = true;
    }

    return () => {
      polygonsRef.current.forEach((entry) => entry.polygon.setMap(null));
      polygonsRef.current = [];
    };
  }, [mapReady, geojsonVersion]);

  // ④ 스타일 갱신 — 선택·추천·필터·업종이 바뀌면 옵션만 바꾼다. 폴리곤은 그대로 둔다.
  useEffect(() => {
    if (!mapReady) return;
    polygonsRef.current.forEach((entry) => {
      const next = styleFor(entry.name).options;
      const key = styleKeyOf(next);
      // 업종을 바꿔도 색이 그대로인 읍면동이 대부분이다. 실제로 달라진 것만 다시 그린다.
      if (entry.styleKey === key) return;
      entry.styleKey = key;
      entry.polygon.setOptions(next);
    });
  }, [styleFor, mapReady, geojsonVersion]);

  // ⑤ 점포 클러스터 — 줌 리스너는 한 번만 붙이고, 최신 그리기 함수는 ref로 읽는다.
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!mapReady || !map) return undefined;
    const listener = window.naver.maps.Event.addListener(map, "zoom_changed", () => drawClustersRef.current(map));
    return () => window.naver.maps.Event.removeListener(listener);
  }, [mapReady]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!mapReady || !map) return;
    drawStoreClusters(map);
  }, [mapReady, drawStoreClusters]);

  const resetMap = () => {
    const map = mapInstanceRef.current;
    if (!map) return;
    map.setCenter(new window.naver.maps.LatLng(37.1997, 126.8312));
    map.setZoom(11, true);
  };

  return (
    <div className={`nodaji-map-page ${drawerMode ? "has-drawer" : ""} ${drawerMode === "detail" ? "is-detail" : ""} ${drawerMode === "detail" && detailTab === "costs" ? "is-costs" : ""}`}>
      <div className="nodaji-map-stage">
        <div ref={mapRef} className="nodaji-map-canvas">
          {!NAVER_CLIENT_ID && <div className="nodaji-map-empty">지도를 표시할 수 없습니다.</div>}
        </div>
      </div>

      <NodajiMapNav />

      <section className="nodaji-control-card" aria-label="상권 분석 조건">
        <div className="nodaji-control-heading">
          <b>나에게 맞는 상권 찾기</b>
          <span>{mapData?.quarter_label ?? "데이터 불러오는 중"}</span>
        </div>

        <div className="explore-entry-mode" aria-label="탐색 시작 방법">
          {[["industry", "업종부터 찾기"], ["area", "지역부터 찾기"], ["direct", "적합도 확인"]].map(([key, label]) =>
            <button type="button" key={key} aria-pressed={entryMode === key} onClick={() => {
              setEntryMode(key);
              setDrawerMode(key === "area" && areaId ? "industries" : null);
            }}>{label}</button>)}
        </div>
        {entryMode !== "industry" && <label className="explore-area-picker">{entryMode === "direct" ? "원하는 지역" : "어느 지역에서 시작할까요?"}
          <select value={areaId ?? ""} onChange={(event) => entryMode === "direct" ? setAreaId(Number(event.target.value)) : chooseAreaFirst(Number(event.target.value))}>
            <option value="" disabled>읍면동 선택</option>
            {(options?.areas ?? []).map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}
          </select>
          {mapData && <small className="explore-map-industry">현재 지도 표시 업종: {mapData.industry_name}</small>}
        </label>}
        {entryMode !== "area" && <IndustryPicker
          industries={(options?.industries ?? []).filter((industry) => coverageByIndustry[industry.id]?.observed)}
          coverageByIndustry={coverageByIndustry}
          totalAreaCount={options?.areas?.length ?? 0}
          value={industryId}
          onChange={chooseIndustry}
        />}

        <PriorityPicker data={presetOptions} value={preset} onChange={choosePreset} />

        {mapData && (
          <div className="nodaji-mini-stats">
            <span><small>{showRecommendationScope && areaFilterIds.length ? "선택 지역 점수 비교" : "점수 비교"}</small><b>{displayedRankedCount} / {displayedTotalCount}곳</b></span>
            <span><small>시 전체 근거 충분 평균</small><b>{fmt(mapData.industry_avg_pct)}%</b></span>
          </div>
        )}

        {entryMode === "direct" ? <button type="button" className="nodaji-analyze-button" disabled={!areaId || !industryId} onClick={() => selectArea(areaId)}>적합도 확인하기</button> : entryMode === "area" ? <button type="button" className="nodaji-analyze-button" onClick={() => setDrawerMode("industries")} disabled={!areaId}>이 지역에서 업종 탐색하기</button> : <button type="button" className="nodaji-analyze-button" onClick={() => setDrawerMode("recommendations")} disabled={!recommendations}>
          {featuredCount ? `추천 상권 ${featuredCount}곳 보기` : "지역 목록 보기 · 추천 근거 부족"}
        </button>}

        <button type="button" className="explore-open-comparison" onClick={openComparison} disabled={!industryId}>두 지역 따로 비교하기 →</button>

        {selectedMapArea && (
          <div className="nodaji-selected-summary">
            <small>지도에서 선택한 상권</small>
            <strong>{selectedMapArea.area_name}</strong>
            <span>
              {selectedMapArea.sample_insufficient
                ? `판단보류 · 점포 ${selectedMapArea.store_count}곳`
                : `최근 1년 누적 폐업률 ${fmt(selectedMapArea.closure_rate_pct)}%`}
            </span>
          </div>
        )}

        <MapLegend
          mapData={mapData}
          recommendationVisible={drawerMode === "recommendations"}
          recommendationCount={featuredCount}
        />

        {showFilteredMap && <p className="explore-filter-map-note">지도는 선택한 {areaFilterIds.length}개 읍면동을 강조합니다.</p>}

        {(queryError || mapError) && <div role="alert" className="nodaji-card-error">{queryError || mapError}</div>}
      </section>

      {drawerMode && (
        <aside className="nodaji-map-drawer" data-tool={drawerMode} aria-label={{ recommendations: "맞춤 상권 추천", compare: "지역 비교", industries: "업종 탐색", detail: "선택 상권 상세" }[drawerMode]}>
          <div className="nodaji-drawer-tabs explore-drawer-tabs">
            <button type="button" data-tool="compare" className={drawerMode === "compare" ? "active" : ""} onClick={openComparison}>지역 비교</button>
            <button type="button" data-tool="industries" className={drawerMode === "industries" ? "active" : ""} onClick={() => setDrawerMode("industries")} disabled={!areaId}>업종 탐색</button>
            <button type="button" data-tool="recommendations" className={drawerMode === "recommendations" ? "active" : ""} onClick={() => setDrawerMode("recommendations")}>맞춤 추천</button>
            <button type="button" data-tool="detail" className={drawerMode === "detail" ? "active" : ""} onClick={() => setDrawerMode("detail")} disabled={!areaId}>선택 상권</button>
            <button type="button" className="nodaji-drawer-close" onClick={() => setDrawerMode(null)} aria-label="패널 닫기">×</button>
          </div>
          <div ref={drawerScrollRef} className="nodaji-drawer-scroll">
            {drawerMode === "compare" && <AreaComparison data={recommendations} loading={recommendationLoading} error={recommendationQuery.error}
              areaIds={compareAreaIds} onChange={setCompareAreaIds} onOpenDetail={selectArea} />}
            {drawerMode === "industries" && <IndustryExplorer areaId={areaId} preset={preset} onSelect={chooseIndustryInArea} />}
            {drawerMode === "recommendations" && (
              recommendationLoading
                ? <p className="nodaji-empty-copy">선택한 조건에 맞는 상권을 계산하는 중…</p>
                : <RecommendationList
                    data={recommendations}
                    results={recommendationResults}
                    areas={options?.areas ?? []}
                    areaFilterIds={areaFilterIds}
                    onAreaFilterChange={setAreaFilterIds}
                    priorityLabel={presetOptions?.presets.find((item) => item.key === preset)?.label ?? preset}
                    selectedAreaId={areaId}
                    onOpenDetail={selectArea}
                  />
            )}
            {drawerMode === "detail" && (
              <ExplorationTools key={`${areaId}:${industryId}`} areaId={areaId} industryId={industryId}
                areaName={options?.areas?.find((area) => area.id === areaId)?.name}
                industryName={options?.industries?.find((industry) => industry.id === industryId)?.name}
                preset={preset} onSelect={selectArea} onBroaden={() => { setAreaFilterIds([]); setDrawerMode("recommendations"); }}
                activeTab={detailTab} onTabChange={setDetailTab}
                costInput={costDrafts[costKey] ?? EMPTY_STARTUP_INPUT} onCostChange={updateCostDraft}>
                <FitScorePanel
                  data={score}
                  loading={scoreLoading}
                  preferenceLabel={presetOptions?.presets.find((item) => item.key === preset)?.label}
                />
                <ObservationSummary cell={cell} loading={cellLoading} />
                {cell?.support_notice && <p className="nodaji-drawer-note">{cell.support_notice}</p>}
              </ExplorationTools>
            )}
          </div>
        </aside>
      )}

      {mapData && (
        <div className="nodaji-map-ticker">
          <span>공개 통계</span>
          <b>{mapData.industry_name}</b>
          <em>{showFilteredMap ? `선택 ${recommendationResults.length}곳 · ${filteredRankedCount}곳 점수 비교` : `${recommendations?.ranked_count ?? mapData.total_count}곳 점수 비교 · ${mapData.measured_count}곳 근거 충분`}</em>
        </div>
      )}

      <div className="nodaji-map-buttons" aria-label="지도 조작">
        <button type="button" onClick={resetMap} aria-label="화성시 전체 보기">
          <span className="material-symbols-outlined">my_location</span>
        </button>
        <div />
        <button type="button" onClick={() => mapInstanceRef.current?.setZoom(mapInstanceRef.current.getZoom() + 1, true)} aria-label="확대">+</button>
        <button type="button" onClick={() => mapInstanceRef.current?.setZoom(mapInstanceRef.current.getZoom() - 1, true)} aria-label="축소">−</button>
      </div>

      {mapData && (
        <div className="nodaji-map-source">
          {mapData.quarter_label} · 소상공인시장진흥공단 상가(상권)정보 · 읍면동 x 업종 집계
        </div>
      )}

      {showIntro && <BrowseIntroModal onClose={closeIntro} />}

      {tooltip && (
        <div className="nodaji-map-tooltip" style={{ left: tooltip.x + 12, top: tooltip.y - 34 }}>
          <b>{tooltip.name}</b>
          {tooltip.info && !tooltip.info.sample_insufficient && <span>누적 폐업률 {fmt(tooltip.info.closure_rate_pct)}%</span>}
          {tooltip.info?.sample_insufficient && <span>판단보류 · 점포 {tooltip.info.store_count}곳</span>}
          {!tooltip.info && <span>이 업종 데이터 없음</span>}
        </div>
      )}
    </div>
  );
}
