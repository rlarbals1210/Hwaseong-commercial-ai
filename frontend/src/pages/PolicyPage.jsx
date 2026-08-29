import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";
import { GradeBadge, TypeBadge } from "../components/Badge";
import { downloadCsv, csvNum } from "../lib/csv";
import useCategories from "../hooks/useCategories";
import useGradeNotice from "../hooks/useGradeNotice";

const EMPTY_DATA = { Q1: [], Q2: [], Q3: [], Q4: [] };

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
    order: "1순위",
    label: "현장 확인 권고",
    tone: "var(--error)",
    soft: "var(--error-soft)",
    desc: "위험 등급(화성시 상위 10%)이고 영향 점포 많음. 가장 먼저 확인",
  },
  Q2: {
    order: "2순위",
    label: "개별 확인 권고",
    tone: "var(--accent-orange)",
    soft: "var(--orange-soft)",
    desc: "위험 등급(화성시 상위 10%)이나 영향 점포 적음. 개별 확인",
  },
  Q3: {
    order: "3순위",
    label: "예방 관찰",
    tone: "var(--accent-teal)",
    soft: "var(--teal-soft)",
    desc: "위험 등급은 아니지만 영향 점포가 많음. 변화 추이 관찰",
  },
  Q4: {
    order: "4순위",
    label: "일반 관찰",
    // 초록 -> 중립 회색(2026-08-29). 두 가지 이유다.
    //   1. 빨강(1순위)과 초록(4순위)이 한 화면에 같이 있으면 적록색맹에서 두 사분면이
    //      구분되지 않는다. 우선순위를 고르는 화면에서 1순위와 4순위가 섞이는 셈이다.
    //   2. 4순위는 "정기 모니터링 유지"다. 초록은 "좋다"는 판정으로 읽히는데 우리가 한
    //      판정은 "지금 볼 순서가 아니다"까지다. 중립색이 그 뜻에 맞는다.
    tone: "var(--outline)",
    soft: "var(--surface-container)",
    desc: "위험 등급이 아니고 영향 점포도 적음. 정기 모니터링 유지",
  },
};

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

function QuadrantPanel({ meta, items, highlight }) {
  return (
    <div
      style={{
        // 1순위만 순백으로 띄우고 나머지는 캔버스 톤에 얹는다 — 색 테두리 없이 위계가 생긴다
        background: highlight ? "var(--surface-container-lowest)" : "var(--surface-container-low)",
        border: `1px solid ${highlight ? "var(--hairline)" : "transparent"}`,
        borderRadius: "var(--radius-lg)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        boxShadow: highlight ? "var(--elev-1)" : "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <span className="badge" style={{ background: meta.soft, color: meta.tone, flexShrink: 0 }}>
            {meta.order}
          </span>
          <span className="t-body-sm" style={{ fontWeight: 600, color: "var(--on-surface)", whiteSpace: "nowrap" }}>
            {meta.label}
          </span>
        </div>
        <span className="t-metric" style={{ fontSize: 16, color: meta.tone, flexShrink: 0 }}>
          {items.length}
        </span>
      </div>

      <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "0 0 12px" }}>{meta.desc}</p>

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6, maxHeight: 210 }}>
        {items.length === 0 ? (
          <div className="t-caption" style={{ color: "var(--ink-faint)", padding: "6px 0" }}>해당 없음</div>
        ) : (
          /* 항목은 반드시 셀 상세로 이어져야 한다. "가장 먼저 확인하세요"라고 써 둔 목록이
             막다른 길이면 담당자의 다음 행동이 그 자리에서 끊긴다. */
          items.map((item, i) => (
            <Link
              key={`${item.area_id}-${item.industry_id}-${i}`}
              to={`/cells/${item.area_id}/${item.industry_id}`}
              style={{
                background: "var(--surface-container-lowest)",
                border: "1px solid var(--hairline)",
                borderRadius: "var(--radius-md)",
                padding: "9px 12px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 10,
                textDecoration: "none",
                color: "inherit",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                  <span className="t-body-sm" style={{ fontWeight: 600, color: "var(--on-surface)" }}>{item.dong}</span>
                  {/* 등급·유형을 캡션 안 평문으로 두면 다른 화면의 배지와 같은 것으로 안 읽힌다. */}
                  <GradeBadge grade={item.risk_grade} />
                  <TypeBadge type={item.cell_type} />
                </div>
                <div className="t-caption" style={{ color: "var(--ink-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {item.category}
                  {" · 최근 1년 "}
                  {/* 폐업률 숫자는 중립 잉크로 둔다(2026-08-29).
                      예전에는 meta.tone을 그대로 입혔는데, 그러면 색이 값이 아니라 이 줄이
                      속한 사분면을 나타내게 된다. 실제 화면에서 16.0%가 주황(2순위),
                      14.1%가 빨강(1순위)으로 찍혀 더 높은 값이 더 안전해 보였다.
                      사분면 소속은 패널 제목과 순위 배지가 이미 말하고 있고, 값의 높낮이는
                      바로 옆 등급 배지가 말한다. 숫자에 색을 또 얹으면 셋이 서로 다른 말을 한다. */}
                  <b style={{ color: "var(--ink-secondary)", fontVariantNumeric: "tabular-nums" }}>{item.actual_closure_rate_pct}%</b>
                  {item.cumulative_closure_count ? (
                    <span style={{ color: "var(--ink-faint)" }}> ({item.cumulative_closure_count}곳)</span>
                  ) : null}
                </div>
              </div>
              <div style={{ textAlign: "right", flexShrink: 0 }}>
                <div className="t-metric" style={{ fontSize: 15 }}>{item.store_count}</div>
                <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>점포</div>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
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
  "우선순위", "읍면동", "업종", "등급", "상권유형",
  "최근1년누적_폐업률(%)", "최근1년_폐업건수", "영향 점포 수",
];

// 우선순위 값은 화면과 같은 말로 쓴다. 예전에는 화면이 "1순위"인데 파일에는 "Q1"이 찍혀
// 두 문서의 어휘가 달랐다. 열 순서도 조기경보 CSV와 맞췄다(등급 다음에 상권유형).
const csvRows = (data) =>
  Object.entries(data).flatMap(([q, items]) =>
    items.map((item) => [
      QUADRANT_META[q]?.order ?? q,
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
  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");
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
        setData(result);
      })
      .catch((err) => {
        setData(EMPTY_DATA);
        setError(describeApiError(err));
      })
      .finally(() => setLoading(false));
  }, [category]);

  const total = Object.values(data).reduce((s, arr) => s + arr.length, 0);
  const dongCount = new Set(Object.values(data).flat().map((i) => i.dong)).size;
  const affectedStores = [...data.Q1, ...data.Q2].reduce((s, i) => s + (i.store_count || 0), 0);
  const topQ1 = [...data.Q1].sort((a, b) => b.actual_closure_rate_pct - a.actual_closure_rate_pct)[0];

  return (
    <div className="official-page official-policy-page">
      <PageHeader
        title="현장 확인 우선순위"
        desc="최근 1년 누적 폐업률(4분기 합산 관측치) × 영향 점포 수 기준 확인 순서입니다. 지원 대상 결정이 아닙니다."
      />

      {/* 대시보드에 "현장 확인 우선순위 보기" 버튼이 있어 시연 동선상 두 화면을 연달아 보게 된다.
          두 화면의 1순위가 다른 것은 정상인데(예측 vs 관측) 그 설명이 도착지에 없었다. */}
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
          <StatCard label="1순위 상권" value={data.Q1.length} unit="개" tone="var(--primary)" />
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
        <div className="card">
          <div style={{ display: "flex", gap: 12 }}>
            <div
              className="t-caption"
              style={{
                // 한글은 vertical-rl에서 글자가 눕지 않고 똑바로 선다. 라틴 문자 기준으로
                // 쓰던 rotate(180deg)를 그대로 얹으면 글자가 물구나무를 선다.
                writingMode: "vertical-rl",
                textOrientation: "upright",
                letterSpacing: 1,
                color: "var(--ink-muted)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              ↑ 영향 점포 수 — 파급 규모
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 12, minHeight: 520 }}>
                <QuadrantPanel meta={QUADRANT_META.Q3} items={data.Q3} />
                <QuadrantPanel meta={QUADRANT_META.Q1} items={data.Q1} highlight />
                <QuadrantPanel meta={QUADRANT_META.Q4} items={data.Q4} />
                <QuadrantPanel meta={QUADRANT_META.Q2} items={data.Q2} />
              </div>
              <div className="t-caption" style={{ display: "flex", justifyContent: "space-between", color: "var(--ink-faint)", marginTop: 10 }}>
                <span>낮음</span>
                <span style={{ color: "var(--ink-muted)" }}>최근 1년 누적 폐업률 →</span>
                <span>높음</span>
              </div>
            </div>
          </div>
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
            1순위 상권 중 <b style={{ color: "var(--on-surface)" }}>{topQ1.dong} · {topQ1.category}</b>의 최근 1년 누적 폐업률이{" "}
            <b style={{ color: "var(--error)", fontVariantNumeric: "tabular-nums" }}>{topQ1.actual_closure_rate_pct}%</b>로 가장 높습니다.
            해당 상권부터 현장 확인을 우선 검토하세요.{" "}
            <span style={{ color: "var(--ink-muted)" }}>지원 여부는 현장 확인 결과에 따라 담당자가 판단합니다.</span>
          </p>
        </div>
      )}
    </div>
  );
}
