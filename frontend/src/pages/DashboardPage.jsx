import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson } from "../lib/api";
import ProvisionalNotice from "../components/ProvisionalNotice";

function downloadCsv(rows) {
  if (!rows.length) return;
  const headers = [
    "예측순위", "읍면동", "업종", "등급", "상권유형",
    "최근1년_폐업률(%)", "최근1년_폐업건수", "점포수", "개업률(%)", "트렌드이상", "후속조치_검토안",
  ];
  const lines = rows.map((r) =>
    [
      r.predicted_rank, r.dong, r.category, r.risk_grade, r.cell_type ?? "",
      r.cumulative_closure_rate_pct, r.cumulative_closure_count, r.store_count,
      r.open_rate_pct, r.anomaly ? "Y" : "N", r.action,
    ]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(",")
  );
  const csv = [headers.join(","), ...lines].join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `화성시_조기경보_예측순위_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// 화성시 평균은 서버에서 받는다(GET /api/alerts/grade-notice).
// 예전에는 3.22를 상수로 박아뒀는데, 파이프라인을 다시 돌리면 값이 어긋나 화면이 거짓말을 했다.
// 서버 응답 전에는 이 값을 쓰되, 도착하면 즉시 교체된다.
const CITY_AVG_FALLBACK_PCT = 5.9;

// 응답에 필드가 없거나 null이면 화면이 NaN을 그대로 뿌린다. 서버를 재시작하지 않아
// 옛 응답이 오는 동안 실제로 "평균 NaN%로 화성시 전체의 NaN배"가 노출됐다.
// 값이 없으면 계산을 포기하고 "—"를 보여준다.
// 유형은 위험도가 아니라 성격이다. 등급(빨강)과 색이 겹치지 않게 중립 톤으로 둔다.
const TYPE_TONE = {
  고회전: "var(--accent-orange)",
  쇠퇴: "var(--primary)",
  성장: "var(--ink-muted)",
  정체: "var(--ink-muted)",
};

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const fmtPct = (v, digits = 1) => {
  const n = num(v);
  return n === null ? "—" : n.toFixed(digits);
};

function PageHeader({ title, desc }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h1 className="t-h1" style={{ margin: 0 }}>{title}</h1>
      <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0" }}>{desc}</p>
    </div>
  );
}

// 지표 타일 — 큰 숫자가 주인공. 라벨은 위, 값은 아래로 두어 스캔 시 라벨 먼저 읽히게 한다.
function StatCard({ label, value, unit, tone }) {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-muted)", textTransform: "uppercase" }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginTop: 10 }}>
        <span className="t-metric" style={{ fontSize: 32, color: tone ?? "var(--on-surface)" }}>{value}</span>
        {unit && <span style={{ fontSize: 15, color: "var(--ink-faint)", fontWeight: 500 }}>{unit}</span>}
      </div>
    </div>
  );
}

// AI 예측값(부풀려진 절대 수치)은 화면에 표시하지 않는다 — 순위만 신뢰할 수 있는 정보라
// "예측 위험 #N"으로만 보여주고, 근거는 실제 관측 지표(폐업률·개업률·추세)로 뒷받침한다.
function RiskCard({ item }) {
  const trend = item.trend_slope ?? 0;
  return (
    <div
      className="card"
      style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14, transition: "box-shadow .15s ease" }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span className="badge" style={{ background: "var(--primary-fixed)", color: "var(--primary)" }}>
          예측 #{item.predicted_rank}
        </span>
        <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {item.cell_type && item.cell_type !== "유형판정보류" && (
            <span
              className="badge"
              title={item.cell_type_summary ?? ""}
              style={{ color: TYPE_TONE[item.cell_type] ?? "var(--ink-muted)" }}
            >
              {item.cell_type}
            </span>
          )}
          {item.risk_grade && item.risk_grade !== "안정" && (
            <span className={item.risk_grade === "위험" ? "badge badge-danger" : "badge"}>
              {item.risk_grade}
            </span>
          )}
        </span>
        {item.anomaly && (
          <span className="badge badge-danger">
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>trending_up</span>
            트렌드 이상
          </span>
        )}
      </div>

      <Link
        to={`/cells/${item.area_id}/${item.industry_id}`}
        style={{ textDecoration: "none" }}
      >
        <div className="t-title" style={{ color: "var(--on-surface)" }}>{item.dong}</div>
        <div className="t-caption" style={{ color: "var(--ink-muted)" }}>
          {item.category} <span style={{ color: "var(--primary)" }}>· 상세 →</span>
        </div>
      </Link>

      <div style={{ marginTop: "auto" }}>
        <div className="t-eyebrow" style={{ color: "var(--ink-faint)", marginBottom: 2 }}>최근 1년 폐업률</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
          <span className="t-metric" style={{ fontSize: 30 }}>{fmtPct(item.cumulative_closure_rate_pct)}</span>
          <span style={{ fontSize: 14, color: "var(--ink-faint)", fontWeight: 500 }}>%</span>
        </div>
        {/* 비율만 두면 점포 60곳에서 6곳 닫힌 것과 600곳에서 60곳 닫힌 것이 같아 보인다.
            담당자가 규모를 함께 판단할 수 있도록 원래 건수를 병기한다.

            "N곳 / 전체 M곳"으로 쓰지 않는다. 위 비율의 분모는 4개 분기 직전점포수의 합이지
            현재 점포수가 아니라서, 슬래시로 묶으면 눈으로 나눈 값이 큰 숫자와 4배쯤
            어긋난다(2026-08-25 감사). 두 수를 가운뎃점으로 분리해 각각의 사실로 읽히게 한다.
            분모까지 보여주는 건 셀 상세에서 한다. */}
        {num(item.store_count) !== null && (
          <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 2, fontVariantNumeric: "tabular-nums" }}>
            {num(item.cumulative_closure_count) !== null
              ? `최근 1년 ${item.cumulative_closure_count.toLocaleString()}곳 닫힘`
              : "누적 건수 미산출"}
            {" · 현재 점포 "}{item.store_count.toLocaleString()}곳
          </div>
        )}
      </div>

      {/* 보조 지표는 hairline 위에 얹어 주 지표와 위계를 분리 */}
      <div
        style={{
          display: "flex",
          gap: 14,
          flexWrap: "wrap",
          paddingTop: 10,
          borderTop: "1px solid var(--hairline)",
          fontSize: 13,
          color: "var(--ink-muted)",
        }}
      >
        <span>
          개업률 <b style={{ color: "var(--on-surface)", fontVariantNumeric: "tabular-nums" }}>{item.open_rate_pct?.toFixed(1)}%</b>
        </span>
        <span>
          추세{" "}
          <b style={{ color: trend > 0 ? "var(--accent-orange)" : "var(--on-surface)", fontVariantNumeric: "tabular-nums" }}>
            {trend > 0 ? "+" : ""}{trend}
          </b>
        </span>
      </div>

      <div
        className="t-caption"
        style={{ color: "var(--ink-secondary)", background: "var(--surface-container-low)", padding: "8px 10px", borderRadius: "var(--radius-md)" }}
      >
        {item.action}
        {item.cell_type_advice && (
          <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid var(--hairline)" }}>
            <div style={{ color: "var(--on-surface)" }}>{item.cell_type_summary}</div>
            <div style={{ marginTop: 2 }}>{item.cell_type_advice}</div>
            {item.cell_type_avoid && (
              <div style={{ marginTop: 2, color: "var(--ink-faint)" }}>
                우선순위 낮음 — {item.cell_type_avoid}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState({ icon, title, desc, tone }) {
  return (
    <div
      style={{
        background: "var(--surface-container-low)",
        borderRadius: "var(--radius-lg)",
        padding: 56,
        textAlign: "center",
      }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 36, color: tone ?? "var(--ink-faint)" }}>{icon}</span>
      <div className="t-title" style={{ color: tone ?? "var(--on-surface)", marginTop: 10 }}>{title}</div>
      {desc && <div className="t-body-sm" style={{ color: "var(--ink-muted)", marginTop: 6 }}>{desc}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState([]);
  const [error, setError] = useState("");
  const [categoryError, setCategoryError] = useState(false);
  // 기준선·고지 문구는 서버에서 받는다. 실패해도 화면은 폴백 값으로 그대로 뜬다.
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    apiFetchJson(`/api/alerts/grade-notice`)
      .then(setMeta)
      .catch(() => setMeta(null));
  }, []);

  useEffect(() => {
    apiFetchJson(`/api/analysis/categories?purpose=alert`)
      .then((d) => {
        setCategories(Array.isArray(d.categories) ? d.categories : []);
        setCategoryError(false);
      })
      .catch(() => {
        setCategories([]);
        setCategoryError(true);
      });
  }, []);

  useEffect(() => {
    const params = new URLSearchParams({ limit: 10 });
    if (category) params.set("category", category);
    apiFetchJson(`/api/alerts/closure-risk?${params}`)
      .then((result) => {
        if (!Array.isArray(result)) throw new Error("Invalid alert response");
        setData(result);
      })
      .catch(() => {
        setData([]);
        setError("데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.");
      })
      .finally(() => setLoading(false));
  }, [category]);

  const anomalyCount = data.filter((d) => d.anomaly).length;
  const cityAvg = meta?.city_average_pct ?? CITY_AVG_FALLBACK_PCT;
  const cumValues = data.map((d) => num(d.cumulative_closure_rate_pct)).filter((v) => v !== null);
  const avgActual = cumValues.length
    ? Number((cumValues.reduce((s, v) => s + v, 0) / cumValues.length).toFixed(1))
    : null;
  const ratio = avgActual !== null && cityAvg ? (avgActual / cityAvg).toFixed(2) : null;
  const topReviewItems = data.slice(0, 2);

  return (
    <div>
      <PageHeader
        title="폐업 위험 조기경보"
        desc="AI가 2분기 뒤 폐업 위험이 높을 것으로 예측한 구역입니다. 절대 확률이 아닌 상대 순위입니다."
      />

      <div style={{ marginBottom: 20 }}>
        <ProvisionalNotice meta={meta} />
      </div>

      {!loading && data.length > 0 && (
        <>
          {/* 요약 배너 — 개별 셀이 아니라 상위권 집단과 시 전체를 대비시킨다.
              예측은 2분기 뒤를 보므로 개별 구역의 현재 폐업률이 0%일 수 있고,
              그 한 건이 대표로 뜨면 모델 전체가 틀린 것처럼 읽힌다. */}
          <div
            className="card"
            style={{
              padding: 24,
              marginBottom: 16,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 24,
              background: "var(--surface-container-lowest)",
            }}
          >
            <div style={{ maxWidth: 620 }}>
              <span className="badge" style={{ background: "var(--primary-fixed)", color: "var(--primary)" }}>
                예측 상위 {data.length}개 구역
              </span>
              <div className="t-h2" style={{ marginTop: 12, lineHeight: 1.35 }}>
                {avgActual === null ? (
                  <>최근 1년 폐업률을 계산할 수 없습니다</>
                ) : (
                  <>
                    최근 1년 폐업률이 평균{" "}
                    <span style={{ color: "var(--primary)" }}>{avgActual}%</span>로
                    <br />
                    화성시 전체({cityAvg}%)의{" "}
                    <span style={{ color: "var(--primary)" }}>{ratio}배</span>입니다
                  </>
                )}
              </div>
              <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "12px 0 0", lineHeight: 1.6 }}>
                예측은 관측 시점 기준 2분기 뒤를 봅니다. 개별 구역의 폐업률이 낮아도 상위 순위에 오를 수 있습니다.
                {meta?.notice ? ` ${meta.notice}` : ""}
              </p>
            </div>

            {/* 비교 막대 — 숫자 두 개보다 길이 대비가 즉시 읽힌다 */}
            <div style={{ minWidth: 260, flex: "0 0 auto" }}>
              {[
                { label: `예측 상위 ${data.length}개`, value: avgActual ?? 0, tone: "var(--primary)" },
                { label: "화성시 전체", value: cityAvg, tone: "var(--outline-variant)" },
              ].map((row) => (
                <div key={row.label} style={{ marginBottom: 14 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                    <span className="t-caption" style={{ color: "var(--ink-muted)" }}>{row.label}</span>
                    <span className="t-metric" style={{ fontSize: 18 }}>{fmtPct(row.value)}%</span>
                  </div>
                  <div style={{ height: 8, background: "var(--surface-container)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
                    <div
                      style={{
                        width: `${Math.min(100, (row.value / Math.max(avgActual ?? 0, cityAvg, 1)) * 100)}%`,
                        height: "100%",
                        background: row.tone,
                        borderRadius: "var(--radius-full)",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 24 }}>
            <StatCard label="분석 대상 구역" value={data.length} unit="개" />
            <StatCard
              label="트렌드 이상"
              value={anomalyCount}
              unit="개"
              tone={anomalyCount > 0 ? "var(--error)" : "var(--on-surface)"}
            />
            <StatCard label="상위권 평균 폐업률" value={fmtPct(avgActual)} unit="%" tone="var(--primary)" />
          </div>
        </>
      )}

      {/* 필터 바 */}
      <div
        style={{
          display: "flex",
          gap: 16,
          alignItems: "flex-end",
          justifyContent: "space-between",
          flexWrap: "wrap",
          marginBottom: 16,
        }}
      >
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
          <div
            className="t-caption"
            style={{ marginTop: 7, color: categoryError ? "var(--error)" : "var(--ink-faint)" }}
          >
            {categoryError
              ? "업종 목록을 불러오지 못했습니다."
              : `최신 분기 점포 수 50개 이상이며 AI 순위가 산출된 ${categories.length}개 업종`}
          </div>
        </div>

        <button className="btn-utility" onClick={() => downloadCsv(data)} disabled={!data.length}
          style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>download</span>
          CSV 다운로드
        </button>
      </div>

      {loading ? (
        <EmptyState icon="progress_activity" title="데이터를 불러오는 중입니다" />
      ) : error ? (
        <EmptyState icon="error" title={error} tone="var(--error)" />
      ) : data.length === 0 ? (
        category ? (
          <EmptyState
            icon="filter_alt_off"
            title="선택한 업종은 분석 가능 표본이 부족합니다"
            desc="최신 분기 점포 수가 50개 미만이라 통계 판단을 보류합니다."
          />
        ) : (
          <EmptyState
            icon="database_off"
            title="AI 분석 결과가 없습니다"
            desc="데이터 적재 상태를 확인해주세요."
          />
        )
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(236px, 1fr))", gap: 16, marginBottom: 24 }}>
          {data.map((item) => (
            <RiskCard key={`${item.dong}-${item.category}`} item={item} />
          ))}
        </div>
      )}

      {topReviewItems.length > 0 && (
        <div className="card">
          <h3 className="t-h3" style={{ margin: 0 }}>후속 조치 검토안</h3>
          <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "6px 0 18px" }}>
            AI가 지원 대상을 결정하지 않습니다. 확인 순서를 제안할 뿐이며 최종 판단은 담당자가 합니다.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 18 }}>
            {topReviewItems.map((item) => (
              <div
                key={`${item.dong}-${item.category}-action`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 16,
                  flexWrap: "wrap",
                  padding: "14px 16px",
                  background: "var(--surface-container-low)",
                  borderRadius: "var(--radius-md)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span className="badge" style={{ background: "var(--surface-container-lowest)", color: "var(--primary)" }}>
                    #{item.predicted_rank}
                  </span>
                  <span className="t-body-sm" style={{ fontWeight: 600, color: "var(--on-surface)" }}>
                    {item.dong} · {item.category}
                  </span>
                </div>
                <span className="t-caption" style={{ color: "var(--ink-secondary)" }}>{item.action}</span>
              </div>
            ))}
          </div>

          <Link
            to="/policy"
            className="btn-utility"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              textDecoration: "none",
              color: "var(--primary)",
              width: "100%",
              boxSizing: "border-box",
            }}
          >
            현장점검 우선순위 보기
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>arrow_forward</span>
          </Link>
        </div>
      )}
    </div>
  );
}
