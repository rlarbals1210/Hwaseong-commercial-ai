import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";
import { GradeBadge, TypeBadge } from "../components/Badge";
import { downloadCsv, csvNum } from "../lib/csv";
import useCategories from "../hooks/useCategories";

const CSV_HEADERS = [
  "예측순위", "읍면동", "업종", "등급", "상권유형",
  "최근1년누적_폐업률(%)", "최근1년_폐업건수", "점포수", "개업률(%)", "트렌드이상", "후속조치_검토안",
];

const csvRows = (rows) =>
  rows.map((r) => [
    r.predicted_rank, r.dong, r.category, r.risk_grade, r.cell_type ?? "",
    csvNum(r.cumulative_closure_rate_pct), r.cumulative_closure_count ?? "", r.store_count,
    csvNum(r.open_rate_pct), r.anomaly ? "Y" : "N", r.action,
  ]);

// 화성시 평균은 서버에서 받는다(GET /api/alerts/grade-notice).
// 예전에는 3.22를 상수로 박아뒀는데, 파이프라인을 다시 돌리면 값이 어긋나 화면이 거짓말을 했다.
// 서버 응답 전에는 이 값을 쓰되, 도착하면 즉시 교체된다.
const CITY_AVG_FALLBACK_PCT = 5.9;

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
// "예측 위험 #N"으로만 보여주고, 근거는 실제 관측 폐업률로 뒷받침한다.
//
// 카드는 "어디부터 볼까"만 답한다. 후속 조치·유형 처방·개업률·추세는 셀 상세로 넘겼다 —
// 열 개를 훑는 자리에서 카드마다 네 줄씩 읽게 하면 정작 순위가 눈에 안 들어온다.
// 잘라낸 값은 전부 CSV 내려받기와 셀 상세에 그대로 남아 있다.
function RiskCard({ item }) {
  return (
    <div
      className="card"
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10, transition: "box-shadow .15s ease" }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span className="badge" style={{ background: "var(--primary-fixed)", color: "var(--primary)" }}>
          예측 #{item.predicted_rank}
        </span>
        <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <TypeBadge type={item.cell_type} />
          {/* "안정"도 그린다. 감추면 등급이 없는 셀과 구분되지 않고,
              비교·상세 화면에서는 보이던 것이 여기서만 사라져 화면끼리 어긋났다. */}
          <GradeBadge grade={item.risk_grade} />
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

      {/* "안정인데 왜 조기경보에 있냐"는 질문이 나오는 자리다. 정렬은 모델이 본 2분기 뒤
          위험 순위이고 등급은 이미 관측된 실적이라 둘은 어긋날 수 있다 — 그게 조기경보의
          존재 이유이기도 하다. 화면 위쪽 설명만으로는 카드 단위에서 안 읽혀서 여기 붙인다. */}
      {item.risk_grade === "안정" && (
        <p
          className="t-caption"
          style={{
            margin: 0,
            padding: "6px 8px",
            background: "var(--surface-container-low)",
            borderRadius: "var(--radius-md)",
            color: "var(--ink-secondary)",
            lineHeight: 1.6,
          }}
        >
          지금은 <b>안정</b>이지만 모델이 <b>2분기 뒤</b> 위험 상위로 봅니다.
        </p>
      )}

      <div style={{ marginTop: "auto" }}>
        <div className="t-eyebrow" style={{ color: "var(--ink-faint)", marginBottom: 2 }}>최근 1년 누적 폐업률</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
          <span className="t-metric" style={{ fontSize: 26 }}>{fmtPct(item.cumulative_closure_rate_pct)}</span>
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
  const [error, setError] = useState("");
  const { categories, error: categoryError } = useCategories("alert");
  // 기준선·고지 문구는 서버에서 받는다. 실패해도 화면은 폴백 값으로 그대로 뜬다.
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    apiFetchJson(`/api/alerts/grade-notice`)
      .then(setMeta)
      .catch(() => setMeta(null));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams({ limit: 10 });
    if (category) params.set("category", category);
    apiFetchJson(`/api/alerts/closure-risk?${params}`)
      .then((result) => {
        if (!Array.isArray(result)) throw new Error("Invalid alert response");
        setData(result);
      })
      .catch((err) => {
        setData([]);
        setError(describeApiError(err));
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
        desc="AI가 2분기 뒤 폐업 위험이 높을 것으로 예측한 상권입니다. 절대 확률이 아닌 상대 순위입니다."
      />

      {!loading && data.length > 0 && (
        <>
          {/* 요약 배너 — 개별 셀이 아니라 상위권 집단과 시 전체를 대비시킨다.
              예측은 2분기 뒤를 보므로 개별 상권의 현재 폐업률이 0%일 수 있고,
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
                예측 상위 {data.length}개 상권
              </span>
              <div className="t-h2" style={{ marginTop: 12, lineHeight: 1.35 }}>
                {avgActual === null ? (
                  <>최근 1년 누적 폐업률을 계산할 수 없습니다</>
                ) : (
                  <>
                    최근 1년 누적 폐업률이 평균{" "}
                    <span style={{ color: "var(--primary)" }}>{avgActual}%</span>로
                    <br />
                    화성시 전체({cityAvg}%)의{" "}
                    <span style={{ color: "var(--primary)" }}>{ratio}배</span>입니다
                  </>
                )}
              </div>
              <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "12px 0 0", lineHeight: 1.6 }}>
                예측은 관측 시점 기준 2분기 뒤를 봅니다. 개별 상권의 폐업률이 낮아도 상위 순위에 오를 수 있습니다.
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

          {/* 세 타일 모두 "상위 N개" 안에서 센 값이다. 예전 라벨이 "분석 대상 구역"이라
              화성시 전체에서 10개만 분석한 것처럼 읽혔다 — 실제 표본충분 상권은 231개이고
              사각지대까지 더하면 1,802개다. 자기 강점을 깎아먹는 라벨이었다. */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 8 }}>
            <StatCard label={`예측 상위 ${data.length}개 상권`} value={data.length} unit="개" />
            <StatCard
              label="그중 트렌드 이상"
              value={anomalyCount}
              unit="개"
              tone={anomalyCount > 0 ? "var(--error)" : "var(--on-surface)"}
            />
            <StatCard label="그중 평균 폐업률" value={fmtPct(avgActual)} unit="%" tone="var(--primary)" />
          </div>
          <p className="t-caption" style={{ color: "var(--ink-faint)", margin: "0 0 24px", lineHeight: 1.6 }}>
            위 세 값은 이 화면이 보여주는 상위 {data.length}개 안에서 센 것입니다.
            화성시 전체 분석 대상은 {meta?.eligible_cells ? `표본충분 ${meta.eligible_cells.toLocaleString()}개 상권` : "표본충분 상권"}이며,
            표본이 부족해 판단을 보류한 상권은 <Link to="/blindspots" style={{ color: "var(--primary)" }}>사각지대</Link>에서 따로 관리합니다.
          </p>
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

        <button className="btn-utility" onClick={() =>
            downloadCsv({
              filename: "화성시_조기경보_예측순위",
              subtitle: "조기경보 대시보드 — AI 예측 상위 상권",
              headers: CSV_HEADERS,
              rows: csvRows(data),
              meta,
            })
          } disabled={!data.length}
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
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: 12, marginBottom: 24 }}>
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
            현장 확인 우선순위 보기
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>arrow_forward</span>
          </Link>
        </div>
      )}
    </div>
  );
}
