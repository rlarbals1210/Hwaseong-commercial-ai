import { useState, useEffect, Fragment } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";
import { GradeBadge, TypeBadge } from "../components/Badge";
import { downloadCsv, csvNum } from "../lib/csv";
import useCategories from "../hooks/useCategories";
import useGradeNotice from "../hooks/useGradeNotice";

const CSV_HEADERS = [
  "예측순위", "읍면동", "업종", "등급", "상권유형",
  "최근1년누적_폐업률(%)", "구간하한(%)", "구간상한(%)", "최근1년_폐업건수", "점포수", "개업률(%)", "트렌드이상", "검증구간", "후속조치_검토안",
];

// validatedRank — 이 순위까지가 검증 구간이다. 화면에서 끊어 보여주므로 CSV에도 같은 사실을
// 실어야 한다. 열이 없으면 엑셀에서 정렬하는 순간 그 구분이 사라진다.
const csvRows = (rows, validatedRank) =>
  rows.map((r) => [
    r.predicted_rank, r.dong, r.category, r.risk_grade, r.cell_type ?? "",
    csvNum(r.cumulative_closure_rate_pct), csvNum(r.closure_lower_pct), csvNum(r.closure_upper_pct),
    r.cumulative_closure_count ?? "", r.store_count,
    csvNum(r.open_rate_pct), r.anomaly ? "Y" : "N",
    validatedRank == null ? "" : r.predicted_rank <= validatedRank ? "검증" : "참고",
    r.action,
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
function RiskCard({ item, beyondValidated = false }) {
  // 카드 전체를 링크로 둔다. 예전에는 카드마다 "· 상세 →"를 적었는데 10장이면 같은 문구가
  // 열 번 반복되고, 정작 누를 수 있는 곳은 제목 줄뿐이었다.
  const watchOnly = item.risk_grade === "안정";
  return (
    <Link
      to={`/cells/${item.area_id}/${item.industry_id}`}
      className="card"
      style={{
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        textDecoration: "none",
        color: "inherit",
      }}
    >
      {/* 순위는 칩이 아니라 숫자로 둔다. 칩이 셋이면 색이 셋이라 어디를 봐야 할지 흩어진다 —
          색을 쓰는 것은 등급 하나뿐이고 순위와 유형은 글자로만 말한다. */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="t-eyebrow" style={{ color: "var(--ink-faint)", fontVariantNumeric: "tabular-nums" }}>
          #{item.predicted_rank}
        </span>
        <span style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
          <TypeBadge type={item.cell_type} />
          {/* "안정"도 그린다. 감추면 등급이 없는 셀과 구분되지 않고,
              비교·상세 화면에서는 보이던 것이 여기서만 사라져 화면끼리 어긋났다. */}
          <GradeBadge grade={item.risk_grade} />
        </span>
      </div>

      <div>
        <div className="t-title" style={{ color: "var(--on-surface)", lineHeight: 1.3 }}>{item.dong}</div>
        <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 2 }}>{item.category}</div>
      </div>

      <div style={{ marginTop: "auto" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
          <span className="t-metric" style={{ fontSize: 30 }}>{fmtPct(item.cumulative_closure_rate_pct)}</span>
          <span style={{ fontSize: 15, color: "var(--ink-faint)", fontWeight: 500 }}>%</span>
        </div>
        {/* 라벨을 숫자 아래로 내렸다. 위에 두면 카드 열 장에서 같은 문구가 먼저 열 번 읽힌다. */}
        <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 1 }}>최근 1년 누적 폐업률</div>

        {/* 신뢰구간(2026-08-29). 표본 기준을 30으로 내리면서 이 목록의 절반가량이 점포
            50곳 미만 셀이 됐다. 점추정만 30px로 띄우면 점포 34곳의 12.5%가 점포 240곳의
            12.9%와 같은 무게로 읽힌다 — 앞은 구간이 6~24%로 벌어지고 뒤는 10~16%다.
            자리는 항상 잡아 둔다(카드 높이가 어긋나면 한 줄에 늘어선 숫자가 흐트러진다). */}
        <div
          className="t-caption"
          style={{
            color: "var(--ink-faint)",
            marginTop: 3,
            fontVariantNumeric: "tabular-nums",
            whiteSpace: "nowrap",
          }}
        >
          {num(item.closure_lower_pct) !== null && num(item.closure_upper_pct) !== null
            ? `95% 구간 ${fmtPct(item.closure_lower_pct)}~${fmtPct(item.closure_upper_pct)}%${
                item.interval_approximate ? " (근사)" : ""
              }`
            : "\u00a0"}
        </div>

        {/* 비율만 두면 점포 60곳에서 6곳 닫힌 것과 600곳에서 60곳 닫힌 것이 같아 보인다.
            "N곳 / M곳"으로 묶지 않는다 — 위 비율의 분모는 4개 분기 직전점포수의 합이지
            현재 점포수가 아니라서, 슬래시로 묶으면 눈으로 나눈 값이 4배쯤 어긋난다
            (2026-08-25 감사). 가운뎃점으로 갈라 각각의 사실로 읽히게 한다. */}
        {num(item.store_count) !== null && (
          <div
            className="t-caption"
            style={{ color: "var(--ink-muted)", marginTop: 8, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}
          >
            {num(item.cumulative_closure_count) !== null
              ? `${item.cumulative_closure_count.toLocaleString()}곳 닫힘`
              : "건수 미산출"}
            {" · 점포 "}{item.store_count.toLocaleString()}곳
          </div>
        )}

        {/* "안정인데 왜 조기경보에 있냐"는 질문이 나오는 자리다. 정렬은 모델이 본 2분기 뒤
            위험 순위이고 등급은 이미 관측된 실적이라 둘은 어긋날 수 있다 — 그게 조기경보의
            존재 이유이기도 하다. 예전에는 박스로 띄웠는데 그 카드만 키가 달라져 한 줄에
            늘어선 숫자들이 어긋났다. 한 줄로 줄이고 자리를 항상 잡아 둔다. */}
        <div
          className="t-caption"
          style={{
            marginTop: 8,
            paddingTop: 8,
            borderTop: "1px solid var(--hairline)",
            color: watchOnly ? "var(--ink-secondary)" : "var(--ink-faint)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {beyondValidated
            ? "검증 구간 밖 · 순서는 참고용"
            : watchOnly
              ? "지금은 안정 · 2분기 뒤 위험 상위 예측"
              : item.anomaly
                ? "트렌드 이상 감지"
                : "\u00a0"}
        </div>
      </div>
    </Link>
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

// 카드로 띄우는 머리 부분의 크기. 상단 요약 배너·타일도 이 집단 기준으로 센다.
//
// 목록 전체를 받아오게 바뀐 뒤(2026-08-29) 여기가 함정이 됐다. 배너를 data 전체로 계산하면
// "예측 상위 382개의 평균 폐업률은 시 전체의 1.00배"가 되어 배너가 자기 부정을 한다.
// 머리 집단과 전체 목록은 다른 물건이라 계산 대상도 갈라 둔다.
const HEADLINE_COUNT = 10;

export default function DashboardPage() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("");
  const [dong, setDong] = useState("");
  const [dongs, setDongs] = useState([]);
  const [error, setError] = useState("");
  const { categories, error: categoryError } = useCategories("alert");
  // 기준선·고지 문구는 서버에서 받는다. 실패해도 화면은 폴백 값으로 그대로 뜬다.
  const { meta, sampleMin } = useGradeNotice();

  useEffect(() => {
    apiFetchJson("/api/analysis/dongs")
      .then((d) => setDongs(Array.isArray(d.dongs) ? d.dongs : Array.isArray(d) ? d : []))
      .catch(() => setDongs([]));
  }, []);

  useEffect(() => {
    // 전체를 받는다. 예전에는 10개만 받아서 "더 보고 싶다"에 답할 방법이 없었고,
    // CSV 다운로드까지 화면에 뜬 10줄만 나갔다(담당자가 엑셀로 받아 자기 방식대로
    // 정렬하려는 게 제일 흔한 요구인데 10줄짜리가 내려갔다).
    const params = new URLSearchParams({ limit: 500 });
    if (category) params.set("category", category);
    if (dong) params.set("dong", dong);
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
  }, [category, dong]);

  const filtered = Boolean(category || dong);

  // 검증 경계 — 서버가 시 전체 순위 기준으로 내려준다. 필터를 걸어도 이 값은 그대로다.
  const validatedRank = meta?.validated_top_rank ?? null;

  // 기본 화면은 검증 구간까지만 보여준다.
  //
  // 처음에는 전체를 펼치고 38위 자리에 선만 그었는데, 선 아래로도 300줄이 계속 이어지면
  // 선은 장식이 되고 담당자는 47위를 근거로 쓰게 된다. 우리가 검증한 것은 "상위 10% 집단이
  // 나머지보다 실제로 더 많이 닫혔다"는 사실뿐이고 그 안쪽 순서까지가 아니다.
  // 그래서 순위로 줄 세운 화면에서는 검증 구간에서 끊고, 그 밖은 읍면동·업종을 지정했을 때만
  // 연다 — 그때는 "몇 위인가"가 아니라 "우리 동은 어떤가"를 보는 것이라 성격이 다르다.
  // 전체가 필요하면 CSV로 받으면 되고, 거기엔 검증 구간 여부가 열로 붙는다.
  const limitToValidated = !filtered && validatedRank != null;
  const visible = limitToValidated
    ? data.filter((d) => d.predicted_rank <= validatedRank)
    : data;

  // 조회 모드 — 읍면동·업종을 지정하면 카드를 접고 표 하나로 쭉 편다.
  //
  // 순위 화면에서 카드는 "먼저 볼 열 곳"이라는 뜻이다. 그런데 봉담읍을 고른 담당자에게
  // 카드 열 장을 먼저 깔면 화면 위쪽이 카드로 차고 정작 필요한 업종 목록은 아래로 밀린다.
  // 담당 구역을 지정한 순간 질문이 "어디부터 볼까"에서 "우리 동은 어떤가"로 바뀌므로
  // 형태도 목록 하나로 바꾼다.
  const lookupMode = filtered;
  const headline = lookupMode ? [] : visible.slice(0, HEADLINE_COUNT);
  const listRows = lookupMode ? visible : visible.slice(HEADLINE_COUNT);

  // 상단 요약이 세는 집단. 순위 모드에서는 머리 10개, 조회 모드에서는 그 조건 전체다.
  const cohort = lookupMode ? visible : headline;
  const cohortLabel = lookupMode
    ? `${[dong, category].filter(Boolean).join(" · ")} 상권 ${cohort.length}개`
    : `예측 상위 ${headline.length}개 상권`;
  const anomalyCount = cohort.filter((d) => d.anomaly).length;
  const cityAvg = meta?.city_average_pct ?? CITY_AVG_FALLBACK_PCT;
  const cumValues = cohort.map((d) => num(d.cumulative_closure_rate_pct)).filter((v) => v !== null);
  const avgActual = cumValues.length
    ? Number((cumValues.reduce((s, v) => s + v, 0) / cumValues.length).toFixed(1))
    : null;
  const ratio = avgActual !== null && cityAvg ? (avgActual / cityAvg).toFixed(2) : null;

  return (
    <div>
      <PageHeader
        title="폐업 위험 조기경보"
        desc="AI가 2분기 뒤 폐업 확률을 상대 순위로 예측한 상권입니다."
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
                {cohortLabel}
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
                2분기 뒤를 예측한 값입니다. 개별 상권의 폐업률이 낮아도 상위 순위에 오를 수 있습니다.
                {meta?.notice ? ` ${meta.notice}` : ""}
              </p>
            </div>

            {/* 비교 막대 — 숫자 두 개보다 길이 대비가 즉시 읽힌다 */}
            <div style={{ minWidth: 260, flex: "0 0 auto" }}>
              {[
                { label: cohortLabel, value: avgActual ?? 0, tone: "var(--primary)" },
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

          {/* 세 타일 모두 머리 10개 안에서 센 값이다. 예전 라벨이 "분석 대상 구역"이라
              화성시 전체에서 10개만 분석한 것처럼 읽혔다 — 실제 표본충분 상권은 382개이고
              (2026-08-29 표본 기준 30 하향 후) 사각지대까지 더하면 1,802개다.
              자기 강점을 깎아먹는 라벨이었다. */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 8 }}>
            <StatCard label={cohortLabel} value={cohort.length} unit="개" />
            <StatCard
              label="그중 트렌드 이상"
              value={anomalyCount}
              unit="개"
              tone={anomalyCount > 0 ? "var(--error)" : "var(--on-surface)"}
            />
            <StatCard label="평균 폐업률" value={fmtPct(avgActual)} unit="%" tone="var(--primary)" />
          </div>
          <p className="t-caption" style={{ color: "var(--ink-faint)", margin: "0 0 24px" }}>
            {cohortLabel} 안에서 센 값입니다. 전체 분석 대상{" "}
            {meta?.eligible_cells ? `${meta.eligible_cells.toLocaleString()}개 상권` : "상권"} ·
            표본 부족은 <Link to="/blindspots" style={{ color: "var(--primary)" }}>사각지대</Link>에서 관리
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
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
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

            {/* 읍면동 필터 — 봉담읍 담당자는 봉담읍만 본다. 목록 길이를 늘리는 것보다
                "내 담당 구역"으로 좁히는 쪽이 실사용에 가깝다. */}
            <label className="t-caption" style={{ color: "var(--ink-secondary)", fontWeight: 600, marginLeft: 6 }}>읍면동</label>
            <select
              value={dong}
              onChange={(e) => {
                setLoading(true);
                setError("");
                setDong(e.target.value);
              }}
              style={{ minWidth: 150 }}
            >
              <option value="">전체 읍면동</option>
              {dongs.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>

            {filtered && (
              <button
                type="button"
                className="t-caption"
                onClick={() => {
                  setLoading(true);
                  setError("");
                  setCategory("");
                  setDong("");
                }}
                style={{
                  border: "none", background: "transparent", cursor: "pointer",
                  color: "var(--primary)", fontWeight: 600, padding: "4px 2px",
                }}
              >
                필터 해제
              </button>
            )}
          </div>
          <div
            className="t-caption"
            style={{ marginTop: 7, color: categoryError ? "var(--error)" : "var(--ink-faint)" }}
          >
            {categoryError
              ? "업종 목록을 불러오지 못했습니다."
              : `표본 기준을 넘고 AI 순위가 산출된 ${categories.length}개 업종`}
          </div>
        </div>

        {/* CSV는 화면에 접혀 있든 말든 받아온 전체를 내보낸다. 예전에는 10줄만 나갔다. */}
        <button className="btn-utility" onClick={() =>
            downloadCsv({
              filename: "화성시_조기경보_예측순위",
              subtitle: `조기경보 대시보드 — AI 예측 순위 ${data.length}개${
                filtered ? ` (필터: ${[dong, category].filter(Boolean).join(" · ")})` : ""
              }${validatedRank ? ` · 검증 구간은 ${validatedRank}위까지` : ""}`,
              headers: CSV_HEADERS,
              rows: csvRows(data, validatedRank),
              meta,
            })
          } disabled={!data.length}
          style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>download</span>
          CSV 전체 {data.length ? `(${data.length}개)` : ""} 다운로드
        </button>
      </div>

      {loading ? (
        <EmptyState icon="progress_activity" title="데이터를 불러오는 중입니다" />
      ) : error ? (
        <EmptyState icon="error" title={error} tone="var(--error)" />
      ) : data.length === 0 ? (
        filtered ? (
          <EmptyState
            icon="filter_alt_off"
            title={`${[category, dong].filter(Boolean).join(" · ")} 조건에 해당하는 상권이 없습니다`}
            desc={`최신 분기 점포 수가 ${sampleMin}개 미만이면 통계 판단을 보류합니다. 표본이 부족한 상권은 사각지대에서 확인할 수 있습니다.`}
          />
        ) : (
          <EmptyState
            icon="database_off"
            title="AI 분석 결과가 없습니다"
            desc="데이터 적재 상태를 확인해주세요."
          />
        )
      ) : (
        <>
          {/* 면책 문구는 '후속 조치 검토안' 카드에 있었다(2026-08-29 제거). 그 카드는 상위 2개를
              다시 보여주며 등급에서 기계적으로 파생된 문구 5종을 붙일 뿐이라 새 정보가 없었다.
              문구 자체는 심사·감사에서 방어선이므로 목록 머리로 옮겨 살린다. */}
          <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "0 0 14px", lineHeight: 1.6 }}>
            AI가 지원 대상을 결정하지 않습니다. 확인 순서를 제안할 뿐이며 최종 판단은 담당자가 합니다.
          </p>

          {/* 머리 10개는 카드 — "먼저 볼 곳"과 "쭉 훑을 목록"은 다른 물건이라 형태를 나눈다.
              카드 50장은 스크롤 벽이 되고, 표 10줄은 우선순위가 안 읽힌다. */}
          {!lookupMode && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(242px, 1fr))", gap: 14, marginBottom: listRows.length ? 20 : 24 }}>
            {/* 필터를 걸면 순위가 듬성듬성해진다(봉담읍만 보면 7위 다음이 45위다).
                그러면 카드에도 검증 구간 밖이 올라오므로 카드 쪽에서도 표시한다. */}
            {headline.map((item) => (
              <RiskCard
                key={`${item.dong}-${item.category}`}
                item={item}
                beyondValidated={validatedRank != null && item.predicted_rank > validatedRank}
              />
            ))}
          </div>
          )}

          {listRows.length > 0 && (
            <div className="card" style={{ marginBottom: 24 }}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <h3 className="t-h3" style={{ margin: 0 }}>
                  {filtered
                    ? `${[dong, category].filter(Boolean).join(" · ")} 상권 ${visible.length}곳`
                    : `폐업 위험 상위 ${meta?.validated_top_pct ?? 10}% 상권`}
                </h3>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span
                    className="badge"
                    style={{ background: "var(--surface-container-lowest)", color: "var(--ink-secondary)" }}
                  >
                    {/* 셀 = 읍면동 x 업종이라, 읍면동 하나로 좁히면 각 줄이 곧 업종이고
                        업종 하나로 좁히면 각 줄이 곧 읍면동이다. 단위를 조건에 맞춰 부른다. */}
                    {!lookupMode
                      ? `${HEADLINE_COUNT + 1}~${visible.length}위`
                      : dong && !category
                        ? `${visible.length}개 업종`
                        : category && !dong
                          ? `${visible.length}개 읍면동`
                          : `${visible.length}개 상권`}
                  </span>
                  {lookupMode && (
                    <button
                      type="button"
                      className="t-caption"
                      onClick={() => {
                        setLoading(true);
                        setError("");
                        setCategory("");
                        setDong("");
                      }}
                      style={{
                        border: "none", background: "transparent", cursor: "pointer",
                        color: "var(--primary)", fontWeight: 600, padding: "4px 2px",
                      }}
                    >
                      순위 화면으로
                    </button>
                  )}
                </div>
              </div>
              <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "8px 0 0", lineHeight: 1.65 }}>
                {lookupMode ? (
                  <>
                    해당 조건의 상권을 순위와 무관하게 모두 표시합니다. 시 전체 예측 순위 기준
                    상위 {meta?.validated_top_pct ?? 10}%
                    {validatedRank ? `(${validatedRank}위)` : ""} 밖에 해당하는 상권은 흐리게
                    표시하였으며, 해당 구간의 순서는 검증 대상이 아닙니다.
                  </>
                ) : (
                  <>
                    AI가 2분기 뒤를 예측한{" "}
                    {meta?.ranked_cells ? `${meta.ranked_cells.toLocaleString()}개` : "전체"} 상권 중
                    상위 {visible.length}곳입니다.{" "}
                    <b style={{ color: "var(--ink-secondary)" }}>
                      이 집단이 나머지보다 실제로 더 많이 닫힌다는 것까지가 검증된 범위입니다
                      {meta?.validated_lift ? ` (리프트 ${meta.validated_lift}배)` : ""}.
                    </b>{" "}
                    아래 순위 안쪽의 순서는 참고 자료로만 보시기 바랍니다.
                    {data.length > visible.length && (
                      <>
                        {" "}그 외 {(data.length - visible.length).toLocaleString()}개 상권은 위에서
                        읍면동 또는 업종을 선택하시면 조회하실 수 있습니다.
                      </>
                    )}
                  </>
                )}
              </p>

              <div style={{ overflowX: "auto", marginTop: 14 }}>
                <table style={{ minWidth: 620 }}>
                  <thead>
                    <tr>
                      <th style={{ fontWeight: 600 }}>순위</th>
                      <th style={{ fontWeight: 600 }}>읍면동</th>
                      <th style={{ fontWeight: 600 }}>업종</th>
                      <th style={{ fontWeight: 600 }}>등급</th>
                      <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>최근 1년 누적 폐업률</th>
                      <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>점포수</th>
                    </tr>
                  </thead>
                  <tbody>
                    {listRows.map((item, index) => {
                      // 검증 경계를 넘는 첫 줄 바로 앞에 선을 긋는다. 필터가 걸려 있어도
                      // 기준은 시 전체 순위(predicted_rank)라 경계 자체는 움직이지 않는다.
                      // 앞줄이 없을 때(조회 모드의 첫 줄)는 경계 안쪽으로 친다 — 순위 모드에서
                      // 앞은 항상 카드 10장이고 그건 경계 안쪽이며, 조회 모드에서 첫 줄이
                      // 이미 경계 밖이면 목록 맨 위에 선이 서는 게 맞다.
                      const beyond = validatedRank != null && item.predicted_rank > validatedRank;
                      const previousBeyond =
                        index > 0 &&
                        validatedRank != null &&
                        listRows[index - 1].predicted_rank > validatedRank;
                      const crossing = beyond && !previousBeyond;
                      return (
                        <Fragment key={`${item.dong}-${item.category}`}>
                          {crossing && (
                            <tr>
                              <td colSpan={6} style={{ padding: "14px 4px 10px" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                  <span style={{ flex: 1, height: 1, background: "var(--hairline)" }} />
                                  <span
                                    className="t-caption"
                                    style={{ color: "var(--ink-muted)", whiteSpace: "nowrap", fontWeight: 600 }}
                                  >
                                    검증된 구간은 여기까지 (상위 {meta?.validated_top_pct ?? 10}%
                                    {meta?.validated_lift ? ` · 리프트 ${meta.validated_lift}배` : ""})
                                  </span>
                                  <span style={{ flex: 1, height: 1, background: "var(--hairline)" }} />
                                </div>
                                <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 6, lineHeight: 1.6 }}>
                                  아래부터는 참고용입니다. 검증한 것은 상위 {meta?.validated_top_pct ?? 10}%
                                  집단이 나머지보다 실제로 더 많이 닫혔다는 사실이지, 이 구간 안의 순서가
                                  맞는다는 것이 아닙니다. 예산·지원 대상 선정의 근거로는 위쪽 구간을 쓰고,
                                  아래는 목록 확인 용도로만 보시기 바랍니다.
                                </div>
                              </td>
                            </tr>
                          )}
                          <tr style={beyond ? { opacity: 0.62 } : undefined}>
                            <td style={{ padding: "8px 4px", color: "var(--outline)" }}>{item.predicted_rank}</td>
                            <td style={{ padding: "8px 4px", fontWeight: 600 }}>
                              <Link
                                to={`/cells/${item.area_id}/${item.industry_id}`}
                                style={{ color: "var(--on-surface)", textDecoration: "none" }}
                              >
                                {item.dong}
                              </Link>
                            </td>
                            <td style={{ color: "var(--ink-muted)" }}>{item.category}</td>
                            <td><GradeBadge grade={item.risk_grade} /></td>
                            <td className="t-metric" style={{ textAlign: "right" }}>
                              {fmtPct(item.cumulative_closure_rate_pct)}%
                              {num(item.closure_lower_pct) !== null && num(item.closure_upper_pct) !== null && (
                                <div className="t-caption" style={{ color: "var(--ink-faint)", fontWeight: 400, marginTop: 2 }}>
                                  {fmtPct(item.closure_lower_pct)}~{fmtPct(item.closure_upper_pct)}%
                                </div>
                              )}
                            </td>
                            <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-muted)" }}>
                              {item.store_count?.toLocaleString() ?? "—"}
                            </td>
                          </tr>
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>

            </div>
          )}

          {/* '그 외 상권 조회' 안내 카드는 제거했다(2026-08-29). 같은 읍면동 셀렉트가 바로 위
              필터 바에 이미 있어서 같은 컨트롤이 한 화면에 두 번 놓였다. */}
          {/* 조기경보에서 현장확인으로 넘어가는 동선. 제거한 카드에 있던 것을 옮겨 살렸다.
              표가 없는 경우(필터 결과가 10건 이하)에도 남아야 해서 표 바깥에 둔다. */}
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
              marginBottom: 24,
            }}
          >
            현장 확인 우선순위 보기
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>arrow_forward</span>
          </Link>
        </>
      )}
    </div>
  );
}
