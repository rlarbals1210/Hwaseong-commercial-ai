import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import FitScorePanel from "../components/FitScorePanel";
import { apiFetchJson, describeApiError } from "../lib/api";
import { NAVER_CLIENT_ID, loadNaverMap, featureName, featurePaths } from "../lib/naverMap";

// 기존 서울 프로젝트 MapPage의 핵심 구조를 이식한 공개 상권 탐색 화면.
// 전체화면 지도 + 52px 상단 바 + 좌측 부유 카드를 유지하되, 서울 격자나 개별 점포
// 행위는 가져오지 않는다. 이 프로젝트의 모든 출력은 읍면동 x 업종 집계 단위다.

const fmt = (value, digits = 1) => (
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—"
);
const hasRecommendationEvidence = (item) => ["sufficient", "medium"].includes(item?.evidence_key);

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

function ComparisonPanel({ data, areaIds }) {
  const items = areaIds.map((id) => data.results.find((item) => item.area_id === id)).filter(Boolean);
  if (!items.length) return null;
  if (items.length === 1) {
    return <div className="nodaji-compare-hint"><b>{items[0].area_name}</b>과 비교할 지역을 한 곳 더 담아주세요.</div>;
  }

  const tenure = (value) => typeof value === "number" ? `${(value / 4).toFixed(1)}년` : "—";
  const pctText = (value) => typeof value === "number" ? `${fmt(value)}%` : "—";
  const rows = [
    ["조건 적합도", `${fmt(items[0].score)}점`, `${fmt(items[1].score)}점`],
    ["근거 수준", items[0].evidence_label, items[1].evidence_label],
    ["최근 1년 폐업률", pctText(items[0].observed.closure_rate_cum4_pct), pctText(items[1].observed.closure_rate_cum4_pct)],
    ["현재 점포", `${items[0].observed.store_count}곳`, `${items[1].observed.store_count}곳`],
    ["평균 업력", tenure(items[0].observed.tenure_quarters), tenure(items[1].observed.tenure_quarters)],
    ["최근 개업률", pctText(items[0].observed.opening_rate_pct), pctText(items[1].observed.opening_rate_pct)],
  ];

  return (
    <section className="nodaji-compare-panel" aria-label="선택 상권 비교">
      <div className="nodaji-section-label">두 지역 비교</div>
      <div className="nodaji-compare-grid">
        <span />
        <b>{items[0].area_name}</b>
        <b>{items[1].area_name}</b>
        {rows.map(([label, left, right]) => (
          <div className="nodaji-compare-row" key={label}>
            <span>{label}</span><strong>{left}</strong><strong>{right}</strong>
          </div>
        ))}
      </div>
      <p>비교 수치는 후보를 좁히는 참고 자료이며, 특정 점포의 성공 가능성을 뜻하지 않습니다.</p>
    </section>
  );
}

function RecommendationList({ data, priorityLabel, selectedAreaId, compareAreaIds, onShowOnMap, onOpenDetail, onToggleCompare }) {
  if (!data) return null;
  const scored = data.results.filter((item) => typeof item.score === "number");
  const featured = scored.filter(hasRecommendationEvidence).slice(0, 3);
  const tenure = (quarters) => (
    typeof quarters === "number" ? `${(quarters / 4).toFixed(1)}년` : "—"
  );
  return (
    <div className="nodaji-recommendations">
      <div className="nodaji-drawer-heading">
        <div>
          <small>{data.quarter_label} 기준 · {data.industry_name} · {priorityLabel}</small>
          <h2>{featured.length ? `추천 ${featured.length}곳과 전체 비교` : "추천 보류 · 전체 비교"}</h2>
        </div>
        <span>점수 비교 {data.ranked_count} / {data.total_count}곳</span>
      </div>

      <div className="nodaji-comparison-notice">{data.comparison_notice}</div>

      {!featured.length && (
        <div role="alert" className="nodaji-drawer-alert">
          이 업종은 근거 보통 이상인 지역이 없어 추천 3곳을 고르지 않았습니다. 아래 전체 비교표에서 근거 부족을 함께 확인해주세요.
        </div>
      )}

      {data.growth_spread_narrow && (
        <div role="alert" className="nodaji-drawer-alert">
          이 업종은 읍면동 간 예측 차이가 크지 않습니다. 상대점수 차이를 크게 해석하지 마세요.
        </div>
      )}

      <div className="nodaji-result-list">
        {featured.map((item) => (
          <article key={item.area_id} className={item.area_id === selectedAreaId ? "active" : ""}>
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
            <div className="nodaji-result-actions">
              <button type="button" onClick={() => onShowOnMap(item.area_id)}>지도에서 보기</button>
              <button type="button" onClick={() => onOpenDetail(item.area_id)}>상세 보기</button>
              <button
                type="button"
                className={compareAreaIds.includes(item.area_id) ? "active" : ""}
                onClick={() => onToggleCompare(item.area_id)}
                disabled={compareAreaIds.length >= 2 && !compareAreaIds.includes(item.area_id)}
              >
                {compareAreaIds.includes(item.area_id) ? "비교 해제" : "비교 담기"}
              </button>
            </div>
          </article>
        ))}
      </div>

      <details className="nodaji-all-area-list" open={!featured.length}>
        <summary>
          <span>화성시 전체 {data.total_count}곳 비교표</span>
          <small>관측 {data.ranked_count}곳 · 미관측 {data.unobserved_count}곳</small>
        </summary>
        <div className="nodaji-all-area-head" aria-hidden="true">
          <span>순위</span><span>지역과 근거</span><span>점수</span><span>비교</span>
        </div>
        <div className="nodaji-all-area-rows">
          {data.results.map((item) => {
            const scoreable = typeof item.score === "number";
            return (
              <div key={item.area_id} className={scoreable ? "" : "unobserved"}>
                <span>{item.rank ?? "—"}</span>
                <span>
                  <b>{item.area_name}</b>
                  <small className={`nodaji-evidence evidence-${item.evidence_key}`}>{item.evidence_label}</small>
                </span>
                <strong>{scoreable ? fmt(item.score) : "—"}</strong>
                <button
                  type="button"
                  className={compareAreaIds.includes(item.area_id) ? "active" : ""}
                  onClick={() => onToggleCompare(item.area_id)}
                  disabled={!scoreable || (compareAreaIds.length >= 2 && !compareAreaIds.includes(item.area_id))}
                  aria-label={`${item.area_name} ${compareAreaIds.includes(item.area_id) ? "비교 해제" : "비교 담기"}`}
                >
                  {compareAreaIds.includes(item.area_id) ? "해제" : "담기"}
                </button>
              </div>
            );
          })}
        </div>
      </details>

      <ComparisonPanel data={data} areaIds={compareAreaIds} />
      <p className="nodaji-drawer-note">{data.relative_notice} {data.disclaimer}</p>
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
  const [options, setOptions] = useState(null);
  const [coverageByIndustry, setCoverageByIndustry] = useState({});
  const [industryId, setIndustryId] = useState(null);
  const [mapData, setMapData] = useState(null);
  const [clusterData, setClusterData] = useState(null);
  const [areaId, setAreaId] = useState(null);
  const [cell, setCell] = useState(null);
  const [cellLoading, setCellLoading] = useState(false);
  const [presetOptions, setPresetOptions] = useState(null);
  const [preset, setPreset] = useState("균형");
  const [recommendations, setRecommendations] = useState(null);
  const [recommendationLoading, setRecommendationLoading] = useState(true);
  const [score, setScore] = useState(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [drawerMode, setDrawerMode] = useState(null);
  const [compareAreaIds, setCompareAreaIds] = useState([]);
  const [error, setError] = useState("");
  const [mapError, setMapError] = useState("");
  const [tooltip, setTooltip] = useState(null);

  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const polygonsRef = useRef([]);
  const clusterMarkersRef = useRef([]);
  const zoomListenerRef = useRef(null);
  const boundsFitRef = useRef(false);

  const selectArea = useCallback((nextAreaId) => {
    setCellLoading(true);
    setScoreLoading(true);
    setAreaId(nextAreaId);
    setDrawerMode("detail");
  }, []);

  const showRecommendationOnMap = useCallback((nextAreaId) => {
    setCellLoading(true);
    setScoreLoading(true);
    setAreaId(nextAreaId);
  }, []);

  const chooseIndustry = useCallback((nextIndustryId) => {
    setAreaId(null);
    setCell(null);
    setScore(null);
    setDrawerMode(null);
    setCompareAreaIds([]);
    setError("");
    setRecommendationLoading(true);
    setIndustryId(nextIndustryId);
    remember(SAVED_INDUSTRY_KEY, nextIndustryId);
  }, []);

  const choosePreset = useCallback((nextPreset) => {
    setRecommendationLoading(true);
    if (areaId) setScoreLoading(true);
    setPreset(nextPreset);
    setCompareAreaIds([]);
    remember(SAVED_PRESET_KEY, nextPreset);
  }, [areaId]);

  const toggleCompareArea = useCallback((nextAreaId) => {
    setCompareAreaIds((current) => (
      current.includes(nextAreaId)
        ? current.filter((id) => id !== nextAreaId)
        : current.length < 2 ? [...current, nextAreaId] : current
    ));
  }, []);

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

  useEffect(() => {
    if (!industryId) return;
    apiFetchJson(`/api/public/industry-map?industry_id=${industryId}`)
      .then(setMapData)
      .catch((err) => { setMapData(null); setError(describeApiError(err)); });
  }, [industryId]);

  useEffect(() => {
    if (!industryId) return;
    apiFetchJson(`/api/recommend/clusters?industry_id=${industryId}`)
      .then(setClusterData)
      .catch(() => setClusterData(null));
  }, [industryId]);

  useEffect(() => {
    if (!industryId) return;
    apiFetchJson(`/api/recommend/areas?industry_id=${industryId}&preset=${encodeURIComponent(preset)}&limit=30`)
      .then(setRecommendations)
      .catch((err) => { setRecommendations(null); setError(describeApiError(err)); })
      .finally(() => setRecommendationLoading(false));
  }, [industryId, preset]);

  useEffect(() => {
    if (!areaId || !industryId) return;
    apiFetchJson(`/api/public/cell?area_id=${areaId}&industry_id=${industryId}`)
      .then(setCell)
      .catch((err) => { setCell(null); setError(describeApiError(err)); })
      .finally(() => setCellLoading(false));
  }, [areaId, industryId]);

  useEffect(() => {
    if (!areaId || !industryId) return;
    apiFetchJson(`/api/recommend/score?area_id=${areaId}&industry_id=${industryId}&preset=${encodeURIComponent(preset)}`)
      .then(setScore)
      .catch((err) => { setScore(null); setError(describeApiError(err)); })
      .finally(() => setScoreLoading(false));
  }, [areaId, industryId, preset]);

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
        ? (recommendations?.results ?? []).filter(hasRecommendationEvidence).slice(0, 3).map((item) => item.area_id)
        : [],
    ),
    [drawerMode, recommendations],
  );

  const drawPolygons = useCallback((map, geojson) => {
    polygonsRef.current.forEach((polygon) => polygon.setMap(null));
    polygonsRef.current = [];

    geojson.features.forEach((feature) => {
      const name = featureName(feature);
      const info = colorByName[name];
      const color = info?.color || "#c1c6d5";
      const selected = info?.area_id === areaId;
      const recommended = recommendedAreaIds.has(info?.area_id);
      const baseOpacity = !info ? 0.3 : info.sample_insufficient ? 0.5 : 0.74;

      featurePaths(feature).forEach((path) => {
        const polygon = new window.naver.maps.Polygon({
          map,
          paths: [path],
          fillColor: color,
          fillOpacity: selected ? 0.95 : baseOpacity,
          strokeColor: selected ? "#005db2" : recommended ? "#7c3aed" : "#fff",
          strokeWeight: selected ? 4 : recommended ? 2.5 : 1.5,
          clickable: true,
        });
        window.naver.maps.Event.addListener(polygon, "mouseover", (event) => {
          polygon.setOptions({ fillOpacity: 0.94 });
          setTooltip({ name, info, x: event.pointerEvent.clientX, y: event.pointerEvent.clientY });
        });
        window.naver.maps.Event.addListener(polygon, "mousemove", (event) => {
          setTooltip((current) => current ? { ...current, x: event.pointerEvent.clientX, y: event.pointerEvent.clientY } : null);
        });
        window.naver.maps.Event.addListener(polygon, "mouseout", () => {
          polygon.setOptions({ fillOpacity: selected ? 0.95 : baseOpacity });
          setTooltip(null);
        });
        window.naver.maps.Event.addListener(polygon, "click", () => {
          if (info) selectArea(info.area_id);
        });
        polygonsRef.current.push(polygon);
      });
    });
  }, [areaId, colorByName, recommendedAreaIds, selectArea]);

  const drawStoreClusters = useCallback((map) => {
    clusterMarkersRef.current.forEach((marker) => marker.setMap(null));
    clusterMarkersRef.current = [];
    if (!clusterData?.clusters?.length || map.getZoom() < 14) return;

    clusterMarkersRef.current = clusterData.clusters.map((item) => {
      const diameter = Math.max(28, Math.min(48, 24 + Math.log2(item.store_count + 1) * 5));
      return new window.naver.maps.Marker({
        map,
        position: new window.naver.maps.LatLng(item.lat, item.lng),
        zIndex: 40,
        icon: {
          content: `<div style="width:${diameter}px;height:${diameter}px;border-radius:999px;background:rgba(0,93,178,.88);border:2px solid white;color:white;display:flex;align-items:center;justify-content:center;font:600 12px Inter,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.18)">${Number(item.store_count)}</div>`,
          anchor: new window.naver.maps.Point(diameter / 2, diameter / 2),
        },
      });
    });
  }, [clusterData]);

  useEffect(() => {
    if (!NAVER_CLIENT_ID || !mapData) return;
    loadNaverMap().then(() => {
      if (!mapRef.current) return;
      if (!mapInstanceRef.current) {
        mapInstanceRef.current = new window.naver.maps.Map(mapRef.current, {
          center: new window.naver.maps.LatLng(37.1997, 126.8312),
          zoom: 11,
          zoomControl: false,
          mapDataControl: false,
          scaleControl: true,
        });
      }
      fetch("/hwaseong_emd.geojson")
        .then((response) => response.json())
        .then((geojson) => {
          drawPolygons(mapInstanceRef.current, geojson);
          if (!boundsFitRef.current) {
            const bounds = new window.naver.maps.LatLngBounds();
            geojson.features.forEach((feature) => featurePaths(feature).forEach((path) => path.forEach((point) => bounds.extend(point))));
            mapInstanceRef.current.fitBounds(bounds);
            boundsFitRef.current = true;
          }
          if (zoomListenerRef.current) window.naver.maps.Event.removeListener(zoomListenerRef.current);
          zoomListenerRef.current = window.naver.maps.Event.addListener(
            mapInstanceRef.current,
            "zoom_changed",
            () => drawStoreClusters(mapInstanceRef.current),
          );
          drawStoreClusters(mapInstanceRef.current);
        })
        .catch(() => setMapError("지도 경계 파일을 불러오지 못했습니다."));
    }).catch((err) => setMapError(err.message));
  }, [drawPolygons, drawStoreClusters, mapData]);

  const resetMap = () => {
    const map = mapInstanceRef.current;
    if (!map) return;
    map.setCenter(new window.naver.maps.LatLng(37.1997, 126.8312));
    map.setZoom(11, true);
  };

  return (
    <div className="nodaji-map-page">
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


        <IndustryPicker
          industries={(options?.industries ?? []).filter((industry) => coverageByIndustry[industry.id]?.observed)}
          coverageByIndustry={coverageByIndustry}
          totalAreaCount={options?.areas?.length ?? 0}
          value={industryId}
          onChange={chooseIndustry}
        />

        <PriorityPicker data={presetOptions} value={preset} onChange={choosePreset} />

        {mapData && (
          <div className="nodaji-mini-stats">
            <span><small>점수 비교</small><b>{recommendations?.ranked_count ?? "—"} / {recommendations?.total_count ?? mapData.total_count}곳</b></span>
            <span><small>근거 충분 지역 평균</small><b>{fmt(mapData.industry_avg_pct)}%</b></span>
          </div>
        )}

        <button type="button" className="nodaji-analyze-button" onClick={() => setDrawerMode("recommendations")} disabled={!recommendations}>
          {recommendations?.results?.some(hasRecommendationEvidence)
            ? `추천 ${Math.min(3, recommendations.results.filter(hasRecommendationEvidence).length)}곳과 전체 비교 보기`
            : "전체 비교 보기 · 추천 근거 부족"}
        </button>

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
          recommendationCount={Math.min(3, recommendations?.results?.filter(hasRecommendationEvidence).length ?? 0)}
        />

        {(error || mapError) && <div role="alert" className="nodaji-card-error">{error || mapError}</div>}
      </section>

      {drawerMode && (
        <aside className="nodaji-map-drawer" aria-label={drawerMode === "recommendations" ? "맞춤 상권 추천" : "선택 상권 상세"}>
          <div className="nodaji-drawer-tabs">
            <button type="button" className={drawerMode === "recommendations" ? "active" : ""} onClick={() => setDrawerMode("recommendations")}>맞춤 추천</button>
            <button type="button" className={drawerMode === "detail" ? "active" : ""} onClick={() => setDrawerMode("detail")} disabled={!areaId}>선택 상권</button>
            <button type="button" className="nodaji-drawer-close" onClick={() => setDrawerMode(null)} aria-label="패널 닫기">×</button>
          </div>
          <div className="nodaji-drawer-scroll">
            {drawerMode === "recommendations" && (
              recommendationLoading
                ? <p className="nodaji-empty-copy">선택한 조건에 맞는 상권을 계산하는 중…</p>
                : <RecommendationList
                    data={recommendations}
                    priorityLabel={presetOptions?.presets.find((item) => item.key === preset)?.label ?? preset}
                    selectedAreaId={areaId}
                    compareAreaIds={compareAreaIds}
                    onShowOnMap={showRecommendationOnMap}
                    onOpenDetail={selectArea}
                    onToggleCompare={toggleCompareArea}
                  />
            )}
            {drawerMode === "detail" && (
              <>
                <FitScorePanel
                  data={score}
                  loading={scoreLoading}
                  preferenceLabel={presetOptions?.presets.find((item) => item.key === preset)?.label}
                />
                <ObservationSummary cell={cell} loading={cellLoading} />
                {cell?.support_notice && <p className="nodaji-drawer-note">{cell.support_notice}</p>}
              </>
            )}
          </div>
        </aside>
      )}

      {mapData && (
        <div className="nodaji-map-ticker">
          <span>공개 통계</span>
          <b>{mapData.industry_name}</b>
          <em>{recommendations?.ranked_count ?? mapData.total_count}곳 점수 비교 · {mapData.measured_count}곳 근거 충분</em>
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
