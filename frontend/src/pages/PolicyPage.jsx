import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";
import { GradeBadge, TypeBadge } from "../components/Badge";
import { downloadCsv, csvNum } from "../lib/csv";
import useCategories from "../hooks/useCategories";
import useGradeNotice from "../hooks/useGradeNotice";

const EMPTY_DATA = {
  Q1: [], Q2: [], Q3: [], Q4: [],
  meta: { danger_threshold_pct: null, median_store_count: null },
};

// 사분면은 "어느 순서로 볼까"이고 등급은 "얼마나 심각한가"다. 서로 다른 축이라
// 사분면 라벨에 "안전"류 표현을 쓰면 안 된다 — 조기경보에서 주의로 뜬 상권이
// 여기서는 안전해 보이는 모순이 실제로 있었다. 하위 사분면은 "중위값 아래"로만 말한다.
// AI는 확인 순서만 제시하고 지원 대상은 결정하지 않는다 — 라벨에 "지원/배분" 표현을 쓰지 않는다.
// 강조는 색 테두리·리본이 아니라 톤 차이로만 한다(디자인 시스템 원칙: 입체감은 hairline과 톤으로).
// 두 축의 기준이 다르다는 점을 문구에서 흐리지 말 것.
//   x축 = 등급(위험 = 화성시 상위 10%)   y축 = 영향 점포 수(결과셋 내 중위값)
// 예전 문구는 x축도 "중위값 아래"라고 썼는데, 그러면 주의 등급(상위 30%) 46개 셀이
// "중위값 아래"로 안내된다. 조기경보에서 주의로 뜬 상권이 여기서 안전해 보이는
// 모순이 문구 쪽에 남아 있었다(2026-08-25 감사).
const QUADRANT_META = {
  Q1: {
    axis: "위험 기준 이상 × 영향 큼",
    label: "우선 현장 확인",
    tone: "var(--error)",
    soft: "var(--error-soft)",
    desc: "위험 등급이고 영향 점포가 중위값 이상인 상권",
  },
  Q2: {
    axis: "위험 기준 이상 × 영향 작음",
    label: "개별 현장 확인",
    tone: "var(--accent-orange)",
    soft: "var(--orange-soft)",
    desc: "위험 등급이고 영향 점포가 중위값 미만인 상권",
  },
  Q3: {
    axis: "위험 기준 미만 × 영향 큼",
    label: "변화 추이 관찰",
    tone: "var(--accent-teal)",
    soft: "var(--teal-soft)",
    desc: "위험 등급 기준 미만이고 영향 점포가 중위값 이상인 상권",
  },
  Q4: {
    axis: "위험 기준 미만 × 영향 작음",
    label: "정기 관찰",
    // 초록 -> 중립 회색(2026-08-29). 두 가지 이유다.
    //   1. 빨강(1순위)과 초록(4순위)이 한 화면에 같이 있으면 적록색맹에서 두 사분면이
    //      구분되지 않는다. 우선순위를 고르는 화면에서 1순위와 4순위가 섞이는 셈이다.
    //   2. 4순위는 "정기 모니터링 유지"다. 초록은 "좋다"는 판정으로 읽히는데 우리가 한
    //      판정은 "지금 볼 순서가 아니다"까지다. 중립색이 그 뜻에 맞는다.
    tone: "var(--outline)",
    soft: "var(--surface-container)",
    desc: "위험 등급 기준 미만이고 영향 점포가 중위값 미만인 상권",
  },
};

const QUADRANT_ORDER = ["Q3", "Q1", "Q4", "Q2"];
const displayPct = (value) => Number.isFinite(Number(value)) ? Number(value).toFixed(1) : "—";
const POINTS_PER_METRIC = 4;

function selectVisibleItems(items) {
  const selected = new Map();
  const add = (item) => selected.set(`${item.area_id}-${item.industry_id}`, item);
  items.slice(0, POINTS_PER_METRIC).forEach(add);
  [...items]
    .sort((a, b) => b.store_count - a.store_count)
    .slice(0, POINTS_PER_METRIC)
    .forEach(add);
  return [...selected.values()];
}

function PageHeader({ title, desc }) {
  return (
    <div className="official-page-header" style={{ marginBottom: 24 }}>
      <h1 className="t-h1" style={{ margin: 0 }}>{title}</h1>
      <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0" }}>{desc}</p>
    </div>
  );
}

function StatCard({ label, value, unit, tone }) {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-muted)", textTransform: "uppercase" }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginTop: 10 }}>
        <span className="t-metric" style={{ fontSize: 28, color: tone ?? "var(--on-surface)" }}>{value}</span>
        {unit && <span style={{ fontSize: 14, color: "var(--ink-faint)", fontWeight: 500 }}>{unit}</span>}
      </div>
    </div>
  );
}

function ScatterPlot({ data, dangerThreshold, medianStores, activeQuadrant, onOpenQuadrant, onOpenPoint }) {
  const WIDTH = 1000;
  const HEIGHT = 610;
  const PAD = { left: 76, right: 34, top: 34, bottom: 70 };
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const allPoints = QUADRANT_ORDER.flatMap((quadrant) =>
    data[quadrant].map((item) => ({ ...item, quadrant }))
  );
  const points = QUADRANT_ORDER.flatMap((quadrant) =>
    selectVisibleItems(data[quadrant]).map((item) => ({ ...item, quadrant }))
  );
  const maxRate = Math.max(dangerThreshold * 1.2, ...allPoints.map((item) => item.actual_closure_rate_pct || 0), 1);
  const maxStores = Math.max(medianStores * 1.25, ...allPoints.map((item) => item.store_count || 0), 1);
  const xMax = Math.ceil(maxRate / 2) * 2;
  const yStep = maxStores > 500 ? 100 : maxStores > 200 ? 50 : 20;
  const yMax = Math.ceil(maxStores / yStep) * yStep;
  const cutX = PAD.left + plotWidth / 2;
  const cutY = PAD.top + plotHeight / 2;
  // 기준선을 정중앙에 고정하되, 각 사분면 안에서는 실제 수치 간 비율을 유지한다.
  // 그래서 네 영역은 같은 크기이고 점의 좌우·상하 순서는 그대로 해석할 수 있다.
  const x = (value) => {
    const clamped = Math.min(Math.max(value, 0), xMax);
    if (clamped <= dangerThreshold) {
      return PAD.left + (clamped / Math.max(dangerThreshold, 1)) * (plotWidth / 2);
    }
    return cutX + ((clamped - dangerThreshold) / Math.max(xMax - dangerThreshold, 1)) * (plotWidth / 2);
  };
  const y = (value) => {
    const clamped = Math.min(Math.max(value, 0), yMax);
    if (clamped <= medianStores) {
      return PAD.top + plotHeight - (clamped / Math.max(medianStores, 1)) * (plotHeight / 2);
    }
    return cutY - ((clamped - medianStores) / Math.max(yMax - medianStores, 1)) * (plotHeight / 2);
  };
  const xTicks = [0, dangerThreshold / 2, dangerThreshold, dangerThreshold + (xMax - dangerThreshold) / 2, xMax];
  const yTicks = [0, medianStores / 2, medianStores, medianStores + (yMax - medianStores) / 2, yMax];
  const quadrantRects = {
    Q3: { x: PAD.left, y: PAD.top, width: cutX - PAD.left, height: cutY - PAD.top },
    Q1: { x: cutX, y: PAD.top, width: PAD.left + plotWidth - cutX, height: cutY - PAD.top },
    Q4: { x: PAD.left, y: cutY, width: cutX - PAD.left, height: PAD.top + plotHeight - cutY },
    Q2: { x: cutX, y: cutY, width: PAD.left + plotWidth - cutX, height: PAD.top + plotHeight - cutY },
  };

  return (
    <div className="policy-scatter-wrap">
      <svg
        className="policy-scatter"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="최근 1년 누적 폐업률과 영향 점포 수로 배치한 행정동·업종 상권 사분면"
      >
        {QUADRANT_ORDER.map((quadrant) => {
          const rect = quadrantRects[quadrant];
          const meta = QUADRANT_META[quadrant];
          const centerX = rect.x + rect.width / 2;
          const titleY = rect.y + 24;
          const selected = activeQuadrant === quadrant;
          return (
            <g
              key={quadrant}
              className={`policy-quadrant-zone${selected ? " is-active" : ""}`}
              role="button"
              tabIndex="0"
              aria-label={`${meta.axis}, ${data[quadrant].length}건 전체보기`}
              onClick={() => onOpenQuadrant(quadrant)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onOpenQuadrant(quadrant);
              }}
            >
              <rect {...rect} fill={meta.soft} />
              <text x={centerX} y={titleY} textAnchor="middle" className="policy-quadrant-zone-title">
                {meta.axis}
              </text>
              <text x={centerX} y={titleY + 20} textAnchor="middle" className="policy-quadrant-zone-count">
                {data[quadrant].length}건 · 클릭해 전체보기
              </text>
            </g>
          );
        })}

        {xTicks.map((tick, index) => (
          <g key={`x-${tick}`}>
            <line x1={x(tick)} y1={PAD.top} x2={x(tick)} y2={PAD.top + plotHeight} className="policy-scatter-grid" />
            <text x={x(tick)} y={HEIGHT - 42} textAnchor="middle" className="policy-scatter-tick">
              {index === 2 ? `기준 ${tick.toFixed(1)}%` : `${tick.toFixed(1)}%`}
            </text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={`y-${tick}`}>
            <line x1={PAD.left} y1={y(tick)} x2={PAD.left + plotWidth} y2={y(tick)} className="policy-scatter-grid" />
            <text x={PAD.left - 12} y={y(tick) + 4} textAnchor="end" className="policy-scatter-tick">{Math.round(tick)}</text>
          </g>
        ))}

        <line x1={cutX} y1={PAD.top} x2={cutX} y2={PAD.top + plotHeight} className="policy-scatter-cut" />
        <line x1={PAD.left} y1={cutY} x2={PAD.left + plotWidth} y2={cutY} className="policy-scatter-cut" />
        <text x={PAD.left + 8} y={cutY - 8} className="policy-scatter-cut-label">영향 기준 {medianStores.toLocaleString()}곳</text>

        {points.map((item) => {
          const key = `${item.area_id}-${item.industry_id}`;
          const meta = QUADRANT_META[item.quadrant];
          const pointX = x(item.actual_closure_rate_pct);
          const pointY = y(item.store_count);
          return (
            <g
              key={key}
              className="policy-scatter-point"
              role="link"
              tabIndex="0"
              aria-label={`${item.dong} ${item.category} 상세 보기`}
              onClick={(event) => {
                event.stopPropagation();
                onOpenPoint(item);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onOpenPoint(item);
              }}
            >
              <circle cx={pointX} cy={pointY} r="5" fill={meta.tone}>
                <title>{`${item.dong} · ${item.category} · 폐업률 ${displayPct(item.actual_closure_rate_pct)}% · 점포 ${item.store_count}곳`}</title>
              </circle>
            </g>
          );
        })}

        <line x1={PAD.left} y1={PAD.top + plotHeight} x2={PAD.left + plotWidth} y2={PAD.top + plotHeight} className="policy-scatter-axis" />
        <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={PAD.top + plotHeight} className="policy-scatter-axis" />
        <text x={PAD.left + plotWidth / 2} y={HEIGHT - 10} textAnchor="middle" className="policy-scatter-axis-label">
          최근 1년 누적 폐업률 →
        </text>
        <text transform={`translate(20 ${PAD.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle" className="policy-scatter-axis-label">
          영향 점포 수 →
        </text>
      </svg>
      <p className="policy-scatter-note">
        기준선을 중앙에 두어 네 영역을 같은 크기로 표시했습니다. 각 영역에는 폐업률 상위 4개와 영향 점포 수 상위 4개만 점으로 표시하며, 전체 목록은 사분면을 클릭해 확인할 수 있습니다.
      </p>
    </div>
  );
}

function QuadrantDrawer({ quadrant, items, onClose }) {
  if (!quadrant) return null;
  const meta = QUADRANT_META[quadrant];
  return (
    <aside className="policy-quadrant-drawer" aria-label={`${meta.axis} 전체 상권`}>
      <div className="policy-quadrant-drawer-head">
        <div>
          <div className="t-eyebrow" style={{ color: meta.tone }}>{meta.axis}</div>
          <h3 className="t-h3">{meta.label}</h3>
          <p>{meta.desc} · 폐업률 높은 순 {items.length}건</p>
        </div>
        <button type="button" onClick={onClose} aria-label="전체 목록 닫기">×</button>
      </div>
      <div className="policy-quadrant-drawer-list">
        {items.map((item) => (
          <Link key={`${item.area_id}-${item.industry_id}`} to={`/cells/${item.area_id}/${item.industry_id}`}>
            <div>
              <div className="policy-quadrant-drawer-title">
                <strong>{item.dong}</strong>
                <GradeBadge grade={item.risk_grade} />
                <TypeBadge type={item.cell_type} />
              </div>
              <span>{item.category}</span>
            </div>
            <div className="policy-quadrant-drawer-metrics">
              <strong style={{ color: meta.tone }}>{displayPct(item.actual_closure_rate_pct)}%</strong>
              <span>점포 {item.store_count}곳</span>
            </div>
          </Link>
        ))}
      </div>
    </aside>
  );
}

function EmptyState({ icon, title, desc, tone }) {
  return (
    <div style={{ background: "var(--surface-container-low)", borderRadius: "var(--radius-lg)", padding: 56, textAlign: "center" }}>
      <span className="material-symbols-outlined" style={{ fontSize: 36, color: tone ?? "var(--ink-faint)" }}>{icon}</span>
      <div className="t-title" style={{ color: tone ?? "var(--on-surface)", marginTop: 10 }}>{title}</div>
      {desc && <div className="t-body-sm" style={{ color: "var(--ink-muted)", marginTop: 6 }}>{desc}</div>}
    </div>
  );
}

const CSV_HEADERS = [
  "사분면", "읍면동", "업종", "등급", "상권유형",
  "최근1년누적_폐업률(%)", "최근1년_폐업건수", "영향 점포 수",
];

// 숫자 순위 대신 화면의 두 축 조건을 그대로 내보낸다. 열 순서도 조기경보 CSV와
// 맞춘다(등급 다음에 상권유형).
const csvRows = (data) =>
  QUADRANT_ORDER.flatMap((q) =>
    data[q].map((item) => [
      QUADRANT_META[q]?.axis ?? q,
      item.dong,
      item.category,
      item.risk_grade,
      item.cell_type ?? "",
      csvNum(item.actual_closure_rate_pct),
      item.cumulative_closure_count ?? "",
      item.store_count,
    ])
  );

export default function PolicyPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");
  const [selectedQuadrant, setSelectedQuadrant] = useState(null);
  const { categories, error: categoryError } = useCategories("policy");
  // CSV 머리말에 붙일 기준선·고지 문구. 화면의 ProvisionalNotice와 같은 출처를 쓴다.
  const { meta: gradeMeta, sampleMin } = useGradeNotice();

  useEffect(() => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    apiFetchJson(`/api/policy/inspection-priority?${params}`)
      .then((result) => {
        if (!["Q1", "Q2", "Q3", "Q4"].every((key) => Array.isArray(result[key]))) {
          throw new Error("Invalid policy response");
        }
        setData({ ...result, meta: result.meta ?? EMPTY_DATA.meta });
      })
      .catch((err) => {
        setData(EMPTY_DATA);
        setError(describeApiError(err));
      })
      .finally(() => setLoading(false));
  }, [category]);

  const allItems = QUADRANT_ORDER.flatMap((key) => data[key]);
  const total = allItems.length;
  const dongCount = new Set(allItems.map((item) => item.dong)).size;
  const affectedStores = [...data.Q1, ...data.Q2].reduce((s, i) => s + (i.store_count || 0), 0);
  const topQ1 = [...data.Q1].sort((a, b) => b.actual_closure_rate_pct - a.actual_closure_rate_pct)[0];
  const sortedStores = allItems.map((item) => item.store_count).sort((a, b) => a - b);
  const middle = Math.floor(sortedStores.length / 2);
  const fallbackMedian = sortedStores.length
    ? (sortedStores.length % 2 ? sortedStores[middle] : (sortedStores[middle - 1] + sortedStores[middle]) / 2)
    : 0;
  const dangerThreshold = Number(data.meta?.danger_threshold_pct ?? gradeMeta?.danger_threshold_pct ?? 0);
  const medianStores = Number(data.meta?.median_store_count ?? fallbackMedian);

  return (
    <div className="official-page official-policy-page">
      <PageHeader
        title="현장 확인 우선순위"
        desc="최근 1년 누적 폐업률(4분기 합산 관측치) × 영향 점포 수 기준 확인 순서입니다. 지원 대상 결정이 아닙니다."
      />

      {/* 대시보드의 예측 순위와 이 화면의 관측 사분면은 서로 다른 질문에 답한다. */}
      <div
        className="t-caption"
        style={{
          color: "var(--ink-secondary)",
          background: "var(--surface-container-low)",
          padding: "10px 14px",
          borderRadius: "var(--radius-md)",
          marginBottom: 12,
          lineHeight: 1.7,
          maxWidth: 680,
        }}
      >
        이 화면은 <b>이미 관측된</b> 폐업률로 줄을 세웁니다.  
        지금 나빠진 곳과 앞으로 나빠질 곳은 같지 않습니다.
      </div>

      {!loading && total > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }}>
          <StatCard label="분석 대상 읍면동" value={dongCount} unit="개" />
          <StatCard label="영향 점포 수" value={affectedStores.toLocaleString()} unit="개소" tone="var(--error)" />
          <StatCard label="우선 현장 확인" value={data.Q1.length} unit="개" tone="var(--primary)" />
          <StatCard label="전체 분석 건수" value={total} unit="건" />
        </div>
      )}

      <div style={{ display: "flex", gap: 16, alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", marginBottom: 16 }}>
        <div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <label className="t-caption" style={{ color: "var(--ink-secondary)", fontWeight: 600 }}>업종</label>
            <select
              value={category}
              onChange={(e) => {
                setLoading(true);
                setError("");
                setSelectedQuadrant(null);
                setCategory(e.target.value);
              }}
              style={{ minWidth: 180 }}
            >
              <option value="">전체 업종</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="t-caption" style={{ marginTop: 7, color: categoryError ? "var(--error)" : "var(--ink-faint)" }}>
            {categoryError
              ? "업종 목록을 불러오지 못했습니다."
              : `최신 분기 점포 수 ${sampleMin}개 이상인 ${categories.length}개 업종`}
          </div>
        </div>

        <button className="btn-utility" onClick={() =>
            downloadCsv({
              filename: "화성시_현장확인_우선순위",
              subtitle: "현장 확인 우선순위 — 관측 폐업률 x 영향 점포 수",
              headers: CSV_HEADERS,
              rows: csvRows(data),
              meta: gradeMeta,
            })
          } disabled={!total}
          style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>download</span>
          CSV 다운로드
        </button>
      </div>

      {loading ? (
        <EmptyState icon="progress_activity" title="분석 결과를 불러오는 중입니다" />
      ) : error ? (
        <EmptyState icon="error" title={error} tone="var(--error)" />
      ) : total === 0 ? (
        category ? (
          <EmptyState
            icon="filter_alt_off"
            title="선택한 업종은 분석 가능 표본이 부족합니다"
            desc={`최신 분기 점포 수가 ${sampleMin}개 미만이라 통계 판단을 보류합니다.`}
          />
        ) : (
          <EmptyState icon="database_off" title="분석 결과가 없습니다" desc="데이터 적재 상태를 확인해주세요." />
        )
      ) : (
        <div className="card policy-scatter-card">
          <ScatterPlot
            data={data}
            dangerThreshold={dangerThreshold}
            medianStores={medianStores}
            activeQuadrant={selectedQuadrant}
            onOpenQuadrant={setSelectedQuadrant}
            onOpenPoint={(item) => navigate(`/cells/${item.area_id}/${item.industry_id}`)}
          />
          <QuadrantDrawer
            quadrant={selectedQuadrant}
            items={selectedQuadrant ? data[selectedQuadrant] : []}
            onClose={() => setSelectedQuadrant(null)}
          />
        </div>
      )}

      {topQ1 && (
        <div
          className="card"
          style={{ marginTop: 16, display: "flex", alignItems: "flex-start", gap: 14, background: "var(--surface-container-low)", border: "1px solid transparent" }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 22, flexShrink: 0, color: "var(--primary)", marginTop: 1 }}>
            lightbulb
          </span>
          <p className="t-body-sm" style={{ margin: 0, color: "var(--ink-secondary)", lineHeight: 1.65 }}>
            우선 현장 확인군 중 <b style={{ color: "var(--on-surface)" }}>{topQ1.dong} · {topQ1.category}</b>의 최근 1년 누적 폐업률이{" "}
            <b style={{ color: "var(--error)", fontVariantNumeric: "tabular-nums" }}>{displayPct(topQ1.actual_closure_rate_pct)}%</b>로 가장 높습니다.
            해당 상권부터 현장 확인을 우선 검토하세요.{" "}
            <span style={{ color: "var(--ink-muted)" }}>지원 여부는 현장 확인 결과에 따라 담당자가 판단합니다.</span>
          </p>
        </div>
      )}
    </div>
  );
}
