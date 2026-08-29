import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";
import useGradeNotice from "../hooks/useGradeNotice";

// 매일 여는 업무 화면이다. 산출 방식·한계 고지는 하단 「산출 기준」 한 곳에 모으고
// 본문에는 값과 판정만 둔다. 근거를 본문에 흩으면 두 번째 방문부터는 읽지 않는다.
//
// 커버율에는 위험색을 쓰지 않는다. 커버율이 낮은 것은 해당 지역의 위험도가 아니라
// 판단 근거의 부재를 뜻한다.
// 사각지대 상권에는 등급을 부여하지 않는다.

const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v.toLocaleString() : "—");

const COVERAGE_COLS = "64px 1fr 54px 52px";
const HEAVY_BLINDSPOT_PCT = 50;   // 점포 절반 이상이 사각지대인 읍면동
const COVERAGE_TIERS = [
  { key: "none", label: "5% 미만", test: (v) => v < 5 },
  { key: "some", label: "5~15%", test: (v) => v >= 5 && v < 15 },
  { key: "most", label: "15% 이상", test: (v) => v >= 15 },
];

function SectionHead({ title, count, right }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
      <h2 className="t-title" style={{ margin: 0 }}>{title}</h2>
      {count != null && (
        <span
          className="t-caption"
          style={{
            fontWeight: 600,
            color: "var(--ink-muted)",
            background: "var(--surface-container)",
            borderRadius: "var(--radius-full)",
            padding: "2px 10px",
          }}
        >
          {count}
        </span>
      )}
      {right && <div style={{ marginLeft: "auto" }}>{right}</div>}
    </div>
  );
}

function Stat({ label, value, unit }) {
  return (
    <div className="card" style={{ padding: 18, flex: "1 1 160px" }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 3, marginTop: 6 }}>
        <span className="t-metric" style={{ fontSize: 28 }}>{value}</span>
        {unit && <span style={{ fontSize: 13, color: "var(--ink-faint)" }}>{unit}</span>}
      </div>
    </div>
  );
}

function Hero({ data }) {
  if (!data) return null;
  const blind = data.store_share_pct;
  const visible = Math.max(0, 100 - blind);
  return (
    <div className="card" style={{ padding: "26px 28px 22px", borderLeft: "4px solid var(--primary)" }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>분석 커버리지</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 10, flexWrap: "wrap" }}>
        <span className="t-metric" style={{ fontSize: 56, lineHeight: 1 }}>{fmt(blind)}%</span>
        <span className="t-body" style={{ color: "var(--ink-secondary)" }}>
          점포 {num(data.city_stores)}곳 중 <b>{num(data.total_stores)}곳</b> 판단 보류
        </span>
      </div>
      <div
        style={{
          display: "flex",
          height: 10,
          borderRadius: "var(--radius-full)",
          overflow: "hidden",
          marginTop: 18,
          background: "var(--surface-container-high)",
        }}
        role="img"
        aria-label={`판단 가능 ${fmt(visible)}%, 판단 보류 ${fmt(blind)}%`}
      >
        <div style={{ width: `${visible}%`, background: "var(--primary)" }} />
        <div style={{ width: `${blind}%`, background: "var(--surface-container-highest)" }} />
      </div>
      <div className="t-caption" style={{ display: "flex", justifyContent: "space-between", marginTop: 8, color: "var(--ink-muted)" }}>
        <span style={{ color: "var(--primary)", fontWeight: 600 }}>판단 가능 {fmt(visible)}%</span>
        <span>판단 보류 {fmt(blind)}% · 상권 {num(data.total_cells)}개</span>
      </div>
    </div>
  );
}

function HighlightCards({ items }) {
  const top = (items || []).slice(0, 3);
  if (!top.length) return null;
  return (
    <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
      {top.map((item) => (
        <Link
          key={`${item.area_id}-${item.industry_id}`}
          to={`/cells/${item.area_id}/${item.industry_id}`}
          className="card"
          style={{ padding: 20, textDecoration: "none", display: "block", color: "inherit" }}
        >
          <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>{item.category}</div>
          <div className="t-h3" style={{ marginTop: 2 }}>{item.dong}</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginTop: 16 }}>
            <span className="t-metric" style={{ fontSize: 42, lineHeight: 1 }}>{item.cumulative_closure_count}</span>
            <span className="t-body-sm" style={{ color: "var(--ink-muted)" }}>/ {item.store_count}곳 폐업</span>
          </div>
        </Link>
      ))}
    </div>
  );
}

function CoverageBars({ data, loading }) {
  if (loading) return <div className="t-caption" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>;
  if (!data?.items?.length) return <div className="t-caption" style={{ color: "var(--ink-muted)" }}>자료 없음</div>;

  return (
    <div>
      {COVERAGE_TIERS.map((tier) => {
        const rows = data.items.filter((item) => tier.test(item.coverage_pct));
        if (!rows.length) return null;
        return (
          <div key={tier.key} style={{ marginBottom: 20 }}>
            <div
              className="t-eyebrow"
              style={{
                display: "flex",
                gap: 8,
                paddingBottom: 7,
                marginBottom: 11,
                borderBottom: "1px solid var(--hairline)",
                color: "var(--ink-faint)",
                fontWeight: 500,
              }}
            >
              <span>커버율 {tier.label}</span>
              <span style={{ marginLeft: "auto", color: "var(--ink-muted)", fontWeight: 600 }}>{rows.length}곳</span>
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              {rows.map((item) => (
                <div key={item.dong} style={{ display: "grid", gridTemplateColumns: COVERAGE_COLS, alignItems: "center", gap: 10 }}>
                  <span className="t-caption" style={{ color: "var(--ink-secondary)", whiteSpace: "nowrap" }}>{item.dong}</span>
                  <div
                    style={{ height: 12, background: "var(--surface-container-high)", borderRadius: "var(--radius-sm)", overflow: "hidden" }}
                    title={`안 보이는 점포 ${item.blindspot_store_pct}%`}
                  >
                    <div style={{ width: `${item.coverage_pct}%`, height: "100%", background: "var(--primary)" }} />
                  </div>
                  <span className="t-caption" style={{ textAlign: "right", color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}>
                    {fmt(item.coverage_pct)}%
                  </span>
                  <span className="t-caption" style={{ textAlign: "right", color: "var(--ink-faint)", fontVariantNumeric: "tabular-nums" }}>
                    {item.sufficient_cells}/{item.total_cells}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function IndustryTable({ data, loading }) {
  if (loading) return <div className="t-caption" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>;
  if (!data?.items?.length) return <div className="t-caption" style={{ color: "var(--ink-muted)" }}>자료 없음</div>;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 400 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--hairline)" }}>
            {["업종", "커버율", "점포", "폐업"].map((h, i) => (
              <th
                key={h}
                className="t-eyebrow"
                style={{ textAlign: i === 0 ? "left" : "right", padding: "9px 12px", color: "var(--ink-faint)", fontWeight: 500 }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => (
            <tr key={item.category} style={{ borderBottom: "1px solid var(--hairline)" }}>
              <td className="t-caption" style={{ padding: "9px 12px" }}>
                {item.category}
                {item.sufficient_cells === 0 && (
                  <span className="badge badge-neutral" style={{ marginLeft: 8 }} title="전 읍면동에서 표본 기준 미달">
                    전역 미판정
                  </span>
                )}
              </td>
              <td className="t-caption" style={{ padding: "9px 12px", textAlign: "right", color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}>
                {fmt(item.coverage_pct)}%
                <span style={{ color: "var(--ink-faint)" }}> · {item.sufficient_cells}/{item.total_cells}</span>
              </td>
              <td className="t-caption" style={{ padding: "9px 12px", textAlign: "right", color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}>
                {num(item.total_stores)}
              </td>
              <td className="t-caption" style={{ padding: "9px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
                {num(item.closure_count)}건
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VerdictTile({ label, count, tone, active, onClick }) {
  const TONE = {
    warn: { fg: "var(--badge-warn-ink)", bg: "var(--orange-soft)", bar: "var(--accent-orange)" },
    ok: { fg: "var(--badge-ok-ink)", bg: "var(--green-soft)", bar: "var(--accent-green)" },
    neutral: { fg: "var(--ink-muted)", bg: "var(--surface-container-low)", bar: "var(--outline-variant)" },
  }[tone];
  return (
    <button
      onClick={onClick}
      style={{
        flex: "1 1 130px",
        textAlign: "left",
        cursor: "pointer",
        border: `1px solid ${active ? TONE.bar : "var(--hairline)"}`,
        background: active ? TONE.bg : "var(--surface-container-lowest)",
        borderRadius: "var(--radius-md)",
        padding: "13px 16px",
      }}
    >
      <div style={{ height: 3, width: 24, background: TONE.bar, borderRadius: 2 }} />
      <div className="t-metric" style={{ fontSize: 28, marginTop: 9, color: active ? TONE.fg : "var(--on-surface)" }}>
        {count}<span style={{ fontSize: 14, fontWeight: 400, color: "var(--ink-faint)" }}>곳</span>
      </div>
      <div className="t-caption" style={{ marginTop: 2, color: "var(--ink-muted)" }}>{label}</div>
    </button>
  );
}

/** 읍면동 단위 판정. 업종별 표본이 부족한 지역도 동 전체를 묶으면 분모가 확보된다. */
function PooledVerdict({ data, loading }) {
  const [openGroup, setOpenGroup] = useState("높음");
  if (loading) return <div className="t-caption" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>;
  if (!data?.items?.length) return null;

  const heavy = data.items
    .filter((item) => item.blindspot_store_pct >= HEAVY_BLINDSPOT_PCT && Number.isFinite(item.pooled_closure_rate_pct))
    .sort((a, b) => b.pooled_closure_rate_pct - a.pooled_closure_rate_pct);
  if (!heavy.length) return null;

  const city = data.city_pooled_closure_rate_pct;
  const groups = {
    높음: heavy.filter((item) => item.vs_city === "높음"),
    차이없음: heavy.filter((item) => item.vs_city === "차이없음"),
    낮음: heavy.filter((item) => item.vs_city === "낮음"),
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
        <VerdictTile label="확인 필요" count={groups.높음.length} tone="warn"
          active={openGroup === "높음"} onClick={() => setOpenGroup("높음")} />
        <VerdictTile label="유의차 없음" count={groups.차이없음.length} tone="neutral"
          active={openGroup === "차이없음"} onClick={() => setOpenGroup("차이없음")} />
        <VerdictTile label="시 평균 이하" count={groups.낮음.length} tone="ok"
          active={openGroup === "낮음"} onClick={() => setOpenGroup("낮음")} />
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {groups[openGroup].length === 0 ? (
          <div className="t-caption" style={{ padding: 20, color: "var(--ink-muted)" }}>해당 읍면동 없음</div>
        ) : (
          groups[openGroup].map((item, index) => {
            const diff = item.pooled_closure_rate_pct - city;
            const warn = openGroup === "높음";
            const good = openGroup === "낮음";
            return (
              <div
                key={item.dong}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  flexWrap: "wrap",
                  padding: "15px 20px",
                  borderTop: index ? "1px solid var(--hairline)" : "none",
                  borderLeft: `3px solid ${warn ? "var(--accent-orange)" : "transparent"}`,
                }}
              >
                <div style={{ minWidth: 126 }}>
                  <div className="t-title" style={{ margin: 0, fontSize: 17 }}>{item.dong}</div>
                  <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 2 }}>
                    업종 {item.sufficient_cells}/{item.total_cells} 판단 가능
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 200 }}>
                  <span
                    className="t-metric"
                    style={{ fontSize: 25, color: warn ? "var(--badge-warn-ink)" : good ? "var(--badge-ok-ink)" : "var(--on-surface)" }}
                    title={`누적 폐업 ${num(item.pooled_closure_count)}건 / 분모 ${num(item.pooled_denominator)}`}
                  >
                    {fmt(item.pooled_closure_rate_pct, 2)}%
                  </span>
                  <span className="t-caption" style={{ color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
                    시 평균 대비 <b style={{ color: "var(--on-surface)" }}>{diff > 0 ? "+" : ""}{fmt(diff, 2)}%p</b>
                  </span>
                </div>

                <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
                  <span className="t-caption" style={{ color: "var(--ink-faint)", whiteSpace: "nowrap" }}>
                    점포 {num(item.total_stores)}곳
                  </span>
                  <Link
                    to={`/blindspots?dong=${encodeURIComponent(item.dong)}`}
                    className="t-caption"
                    style={{ color: "var(--primary)", textDecoration: "none", whiteSpace: "nowrap", fontWeight: 600 }}
                  >
                    업종별 목록
                  </Link>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function BandTabs({ band, onChange, allCount, nearCount, nearMin, sampleMin }) {
  const tabs = [
    { key: "all", label: "전체", count: allCount },
    { key: "near", label: `점포 ${nearMin}~${sampleMin - 1}곳`, count: nearCount },
  ];
  return (
    <div style={{ display: "flex", gap: 5, background: "var(--surface-container)", padding: 4, borderRadius: "var(--radius-md)" }}>
      {tabs.map((tab) => {
        const active = band === tab.key;
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className="t-caption"
            style={{
              border: "none",
              cursor: "pointer",
              padding: "7px 14px",
              borderRadius: "var(--radius-sm)",
              fontWeight: active ? 600 : 400,
              background: active ? "var(--surface-container-lowest)" : "transparent",
              color: active ? "var(--on-surface)" : "var(--ink-muted)",
              whiteSpace: "nowrap",
            }}
          >
            {tab.label}
            {typeof tab.count === "number" && (
              <span style={{ color: "var(--ink-faint)", marginLeft: 6, fontVariantNumeric: "tabular-nums" }}>
                {num(tab.count)}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** 산출 기준. 매일 쓰는 화면이라 본문에 두지 않고 접어 둔다. 감사·문의 대응 시 펼친다. */
function MethodNote({ sampleMin, nearMin }) {
  const rows = [
    ["표본 기준", `최신 분기 점포 ${sampleMin}곳 미만은 통계 판단을 보류하며 등급을 부여하지 않습니다.`],
    ["폐업률", "최근 4개 분기 누적 기준입니다(건수 합 ÷ 직전점포수 합). 점포 수가 적을수록 값의 변동이 커집니다."],
    ["정렬", "폐업 건수 순입니다. 점포 수가 적은 상권은 비율이 크게 변동하므로 건수를 우선합니다."],
    ["커버율", "해당 읍면동에서 표본 기준을 충족한 업종의 비율입니다. 커버율이 낮은 것은 위험도가 아니라 판단 근거의 부재를 의미합니다."],
    ["읍면동 단위 판정", "업종 구분 없이 읍면동 전체를 집계한 폐업률을, 해당 읍면동을 제외한 나머지 지역과 비교한 결과입니다(두 비율 차이 검정, 양측 p<0.05). 등급 기준선은 상권 단위 분포의 분위수이므로 읍면동 단위 값에는 적용하지 않았습니다."],
    ["대상 선정", `점포의 ${HEAVY_BLINDSPOT_PCT}% 이상이 사각지대인 읍면동을 대상으로 했습니다.`],
    ["신뢰구간", `점포 ${nearMin}곳 이상 구간에 한해 95% 신뢰구간을 병기합니다. 그 미만은 구간 폭이 과도하여 표기하지 않습니다. * 표시는 폐업 0건으로 분모를 근사한 경우입니다.`],
  ];
  return (
    <details style={{ marginTop: 32 }}>
      <summary className="t-caption" style={{ cursor: "pointer", color: "var(--ink-muted)", padding: "8px 0" }}>
        산출 기준
      </summary>
      <div className="card" style={{ marginTop: 8, padding: 20 }}>
        <dl style={{ margin: 0, display: "grid", gap: 12 }}>
          {rows.map(([term, desc]) => (
            <div key={term} style={{ display: "grid", gridTemplateColumns: "132px 1fr", gap: 14, alignItems: "start" }}>
              <dt className="t-caption" style={{ color: "var(--ink-faint)", fontWeight: 600 }}>{term}</dt>
              <dd className="t-caption" style={{ margin: 0, color: "var(--ink-secondary)", lineHeight: 1.7 }}>{desc}</dd>
            </div>
          ))}
        </dl>
      </div>
    </details>
  );
}

export default function BlindspotPage() {
  // 지도의 "사각지대에서 이 동 보기"가 ?dong= 를 붙여 보낸다.
  const [params, setParams] = useSearchParams();
  const dong = params.get("dong") ?? "";
  const band = params.get("band") === "near" ? "near" : "all";
  const setParam = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const { meta: thresholds, sampleMin: fallbackSampleMin } = useGradeNotice();
  const [data, setData] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [industries, setIndustries] = useState(null);
  const [dongs, setDongs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [shapeLoading, setShapeLoading] = useState(true);
  const [error, setError] = useState("");
  const [allCount, setAllCount] = useState(null);
  const [nearCount, setNearCount] = useState(null);

  useEffect(() => {
    apiFetchJson("/api/analysis/dongs")
      .then((d) => setDongs(Array.isArray(d.dongs) ? d.dongs : Array.isArray(d) ? d : []))
      .catch(() => setDongs([]));

    setShapeLoading(true);
    Promise.all([
      apiFetchJson("/api/alerts/blindspots/coverage").catch(() => null),
      apiFetchJson("/api/alerts/blindspots/industries?limit=20").catch(() => null),
    ])
      .then(([cov, ind]) => { setCoverage(cov); setIndustries(ind); })
      .finally(() => setShapeLoading(false));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ limit: 40, band });
    if (dong) query.set("dong", dong);
    apiFetchJson(`/api/alerts/blindspots?${query}`)
      .then((d) => { setData(d); if (band === "all") setAllCount(d.band_cells); })
      .catch((err) => setError(describeApiError(err)))
      .finally(() => setLoading(false));
  }, [dong, band]);

  // 탭 라벨의 개수는 어느 탭을 보고 있든 필요하다.
  useEffect(() => {
    const query = new URLSearchParams({ limit: 1, band: "near" });
    if (dong) query.set("dong", dong);
    apiFetchJson(`/api/alerts/blindspots?${query}`)
      .then((d) => setNearCount(d.band_cells))
      .catch(() => setNearCount(null));
  }, [dong]);

  const sampleMin = data?.sample_min ?? fallbackSampleMin;
  const nearMin = data?.near_min_stores ?? 30;
  const highlights = band === "all" ? data?.items ?? [] : [];

  return (
    <div className="official-page official-blindspot-page">
      <h1 className="t-h1" style={{ margin: 0 }}>사각지대</h1>
      <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0" }}>
        점포 {sampleMin}곳 미만으로 통계 판단을 보류한 상권입니다. 등급을 부여하지 않으며 폐업 건수 순으로 표시합니다.
      </p>

      <div style={{ marginTop: 20 }}>
        <Hero data={data} />
      </div>

      {data && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          <Stat label="사각지대 상권" value={num(data.total_cells)} unit="개" />
          <Stat label="해당 점포" value={num(data.total_stores)} unit="곳" />
          <Stat label="최근 1년 폐업" value={num(data.total_closures)} unit="건" />
          <Stat label="표본 기준" value={sampleMin} unit="곳" />
        </div>
      )}

      {highlights.length > 0 && (
        <section style={{ marginTop: 32 }}>
          <SectionHead title="폐업 건수 상위" />
          <HighlightCards items={highlights} />
        </section>
      )}

      <section style={{ marginTop: 36 }}>
        <SectionHead
          title="사각지대 분포"
          count={coverage?.items?.length ? `읍면동 ${coverage.items.length} · 업종 ${industries?.industry_total ?? "—"}` : undefined}
        />
        {coverage?.zero_coverage_dongs?.length > 0 && (
          <p className="t-caption" style={{ margin: "0 0 14px", color: "var(--ink-secondary)" }}>
            <b>{coverage.zero_coverage_dongs.join(" · ")}</b>: 판단 가능한 업종 없음.
            {industries?.invisible_count > 0 && (
              <> 업종 {industries.industry_total}개 중 {industries.invisible_count}개는 전 읍면동에서 판단 불가.</>
            )}
          </p>
        )}
        <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))" }}>
          <div className="card">
            <h3 className="t-eyebrow" style={{ margin: "0 0 16px", color: "var(--ink-faint)" }}>읍면동별 커버율</h3>
            <CoverageBars data={coverage} loading={shapeLoading} />
          </div>
          <div className="card">
            <h3 className="t-eyebrow" style={{ margin: "0 0 16px", color: "var(--ink-faint)" }}>업종별 커버율</h3>
            <IndustryTable data={industries} loading={shapeLoading} />
          </div>
        </div>
      </section>

      <section style={{ marginTop: 36 }}>
        <SectionHead title="읍면동 단위 판정" count="점포 절반 이상 사각지대" />
        <PooledVerdict data={coverage} loading={shapeLoading} />
      </section>

      <section style={{ marginTop: 36 }}>
        <SectionHead
          title="상권 목록"
          count={data?.band_cells != null ? num(data.band_cells) : undefined}
          right={
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <BandTabs
                band={band}
                onChange={(value) => setParam("band", value === "all" ? "" : value)}
                allCount={allCount}
                nearCount={nearCount}
                nearMin={nearMin}
                sampleMin={sampleMin}
              />
              <select value={dong} onChange={(e) => setParam("dong", e.target.value)} style={{ minWidth: 130 }}>
                <option value="">읍면동 전체</option>
                {dongs.map((d) => (<option key={d} value={d}>{d}</option>))}
              </select>
            </div>
          }
        />

        {loading && <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>}
        {/* 오류는 --error. --accent-orange는 "주의" 등급 색이라 의미가 겹친다. */}
        {error && <div className="t-body-sm" style={{ color: "var(--error)" }}>{error}</div>}
        {!loading && data?.items?.length === 0 && (
          <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>해당 조건의 상권 없음</div>
        )}

        {!loading && data?.items?.length > 0 && (
          <>
            <div className="card" style={{ padding: 0, overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--hairline)" }}>
                    {(band === "near"
                      ? ["읍면동", "업종", "폐업", "점포", "폐업률 (95% 신뢰구간)"]
                      : ["읍면동", "업종", "폐업", "점포", "폐업률"]
                    ).map((h, i) => (
                      <th
                        key={h}
                        className="t-eyebrow"
                        style={{ textAlign: i >= 2 ? "right" : "left", padding: "12px 16px", color: "var(--ink-faint)", fontWeight: 500 }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr key={`${item.area_id}-${item.industry_id}`} style={{ borderBottom: "1px solid var(--hairline)" }}>
                      <td style={{ padding: "12px 16px" }}>
                        <Link to={`/cells/${item.area_id}/${item.industry_id}`} style={{ color: "var(--on-surface)", textDecoration: "none" }}>
                          {item.dong}
                        </Link>
                      </td>
                      <td className="t-body-sm" style={{ padding: "12px 16px", color: "var(--ink-secondary)" }}>{item.category}</td>
                      <td style={{ padding: "12px 16px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        <b>{item.cumulative_closure_count}</b>곳
                      </td>
                      <td className="t-body-sm" style={{ padding: "12px 16px", textAlign: "right", color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}>
                        {item.store_count}곳
                      </td>
                      <td
                        className="t-body-sm"
                        style={{ padding: "12px 16px", textAlign: "right", color: "var(--ink-faint)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}
                      >
                        {band === "near" && Number.isFinite(item.closure_lower_pct) ? (
                          <>
                            <b style={{ color: "var(--ink-secondary)" }}>{fmt(item.cumulative_closure_rate_pct)}%</b>
                            <span style={{ color: "var(--ink-faint)" }}>
                              {" "}({fmt(item.closure_lower_pct)}~{fmt(item.closure_upper_pct)})
                              {item.interval_approximate && "*"}
                            </span>
                          </>
                        ) : (
                          <>{fmt(item.cumulative_closure_rate_pct)}%</>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.band_cells > data.items.length && (
              <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 10 }}>
                {num(data.band_cells)}개 중 상위 {data.items.length}개 표시
              </div>
            )}
          </>
        )}
      </section>

      <MethodNote sampleMin={sampleMin} nearMin={nearMin} />
    </div>
  );
}
