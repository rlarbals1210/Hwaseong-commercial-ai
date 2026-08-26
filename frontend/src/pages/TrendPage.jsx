import { useEffect, useMemo, useState } from "react";
import PublicNav from "../components/PublicNav";
import { apiFetchJson, describeApiError } from "../lib/api";

const COLORS = ["#005db2", "#dd5b00", "#2a9d99", "#4958aa"];

function LineChart({ series = [], metrics }) {
  if (series.length < 2) return <p className="t-body-sm" style={{ color: "var(--ink-muted)" }}>추이를 그릴 분기가 부족합니다.</p>;
  // 맨 오른쪽 분기 레이블이 viewBox 밖으로 잘리지 않도록 글자 반 폭 이상을 남긴다.
  const width = 720, height = 230, left = 42, right = 38, top = 18, bottom = 38;
  const values = series.flatMap((point) => metrics.map((metric) => point[metric.key]).filter((value) => typeof value === "number"));
  const max = Math.max(1, ...values) * 1.12;
  const x = (index) => left + (index / (series.length - 1)) * (width - left - right);
  const y = (value) => top + (1 - value / max) * (height - top - bottom);

  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="분기별 상권 지표 추이" style={{ display: "block", width: "100%", minWidth: 560 }}>
        {[0, 0.5, 1].map((ratio) => {
          const value = max * ratio;
          return (
            <g key={ratio}>
              <line x1={left} x2={width - right} y1={y(value)} y2={y(value)} stroke="var(--hairline)" />
              <text x={left - 8} y={y(value) + 4} textAnchor="end" fontSize="11" fill="var(--ink-faint)">{value.toFixed(1)}%</text>
            </g>
          );
        })}
        {metrics.map((metric, metricIndex) => {
          const points = series.map((point, index) => ({ x: x(index), y: y(point[metric.key] ?? 0) }));
          const path = points.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
          return <path key={metric.key} d={path} fill="none" stroke={COLORS[metricIndex]} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />;
        })}
        {series.map((point, index) => (
          (index === 0 || index === series.length - 1 || index % 2 === 0) && (
            <text key={point.quarter_code} x={x(index)} y={height - 12} textAnchor="middle" fontSize="11" fill="var(--ink-muted)">{point.quarter_label.replace("년 ", ".")}</text>
          )
        ))}
      </svg>
      <div style={{ display: "flex", gap: 18, justifyContent: "center", flexWrap: "wrap" }}>
        {metrics.map((metric, index) => (
          <span key={metric.key} className="t-caption" style={{ color: "var(--ink-muted)" }}>
            <span style={{ width: 9, height: 9, borderRadius: "var(--radius-full)", background: COLORS[index], display: "inline-block", marginRight: 6 }} />
            {metric.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function GroupTable({ data }) {
  if (!data?.groups?.length) return null;
  return (
    <div className="card" style={{ padding: 22 }}>
      <h3 className="t-title">{data.title}</h3>
      <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "6px 0 14px", lineHeight: 1.6 }}>{data.description}</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {data.groups.map((group, index) => {
          const latest = group.series[group.series.length - 1] ?? {};
          const first = group.series[0] ?? {};
          const change = typeof latest.closure_rate_pct === "number" && typeof first.closure_rate_pct === "number"
            ? latest.closure_rate_pct - first.closure_rate_pct : null;
          return (
            <div key={group.key} style={{ borderTop: index ? "1px solid var(--hairline)" : "none", paddingTop: index ? 12 : 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
                <span className="t-body-sm" style={{ fontWeight: 600 }}>{group.label}</span>
                <span className="t-caption t-metric" style={{ color: "var(--ink-muted)" }}>
                  폐업 {latest.closure_rate_pct?.toFixed(1) ?? "—"}% · 개업 {latest.opening_rate_pct?.toFixed(1) ?? "—"}%
                </span>
              </div>
              <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 3 }}>
                {group.series.length}개 분기 변화 {change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(1)}%p`}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Movers({ title, data, nameKey }) {
  const rows = (data?.results ?? []).filter((item) => typeof item.closure_change_pct === "number").slice(0, 8);
  return (
    <div className="card" style={{ padding: 22 }}>
      <h3 className="t-title">{title}</h3>
      <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "6px 0 14px" }}>최근 5개 분기 중 첫 분기 대비 누적 폐업률 변화가 큰 순</p>
      {rows.map((item, index) => (
        <div key={item.key} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "9px 0", borderTop: index ? "1px solid var(--hairline)" : "none" }}>
          <span className="t-body-sm">{item[nameKey] ?? item.label}</span>
          <span className="t-caption t-metric" style={{ color: item.closure_change_pct > 0 ? "var(--badge-warn-ink)" : "var(--badge-ok-ink)" }}>
            {item.closure_change_pct > 0 ? "+" : ""}{item.closure_change_pct.toFixed(1)}%p
          </span>
        </div>
      ))}
      {!rows.length && <p className="t-body-sm" style={{ color: "var(--ink-muted)" }}>비교 가능한 자료가 없습니다.</p>}
    </div>
  );
}

export default function TrendPage() {
  const [options, setOptions] = useState(null);
  const [areaId, setAreaId] = useState(null);
  const [industryId, setIndustryId] = useState(null);
  const [overview, setOverview] = useState(null);
  const [areaTypes, setAreaTypes] = useState(null);
  const [dongtan, setDongtan] = useState(null);
  const [areas, setAreas] = useState(null);
  const [industries, setIndustries] = useState(null);
  const [cell, setCell] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiFetchJson("/api/public/areas"),
      apiFetchJson("/api/trends/overview"),
      apiFetchJson("/api/trends/area-types"),
      apiFetchJson("/api/trends/dongtan"),
    ]).then(([optionData, overviewData, typeData, dongtanData]) => {
      setOptions(optionData); setOverview(overviewData); setAreaTypes(typeData); setDongtan(dongtanData);
      const counts = new Map();
      optionData.areas.forEach((area) => area.industries.forEach((industry) => {
        if (!industry.sample_insufficient) counts.set(industry.id, (counts.get(industry.id) ?? 0) + 1);
      }));
      const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? optionData.industries[0]?.id;
      setIndustryId(best);
      const firstArea = optionData.areas.find((area) => area.industries.some((industry) => industry.id === best && !industry.sample_insufficient));
      setAreaId(firstArea?.id ?? optionData.areas[0]?.id);
    }).catch((err) => setError(describeApiError(err)));
  }, []);

  useEffect(() => {
    if (!industryId || !options) return;
    const supports = (area) => area.industries.some((industry) => industry.id === industryId && !industry.sample_insufficient);
    if (!options.areas.find((area) => area.id === areaId && supports(area))) {
      setAreaId(options.areas.find(supports)?.id ?? null);
    }
    apiFetchJson(`/api/trends/areas?industry_id=${industryId}`)
      .then(setAreas).catch((err) => setError(describeApiError(err)));
  }, [industryId, options, areaId]);

  useEffect(() => {
    if (!areaId) return;
    apiFetchJson(`/api/trends/industries?area_id=${areaId}`)
      .then(setIndustries).catch((err) => setError(describeApiError(err)));
  }, [areaId]);

  useEffect(() => {
    if (!areaId || !industryId) return;
    apiFetchJson(`/api/trends/cell?area_id=${areaId}&industry_id=${industryId}`)
      .then(setCell).catch((err) => { setCell(null); setError(describeApiError(err)); });
  }, [areaId, industryId]);

  const availableAreas = useMemo(() => (
    (options?.areas ?? []).filter((area) => area.industries.some((industry) => industry.id === industryId && !industry.sample_insufficient))
  ), [options, industryId]);

  const metrics = [
    { key: "closure_rate_pct", label: "최근 1년 누적 폐업률" },
    { key: "opening_rate_pct", label: "보정 개업률(4분기 이동평균)" },
  ];

  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 24px 64px" }}>
        <PublicNav />
        <h1 className="t-h1">상권 트렌드</h1>
        <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "8px 0 0", lineHeight: 1.7 }}>
          예측이 아니라 분기별 관측 흐름을 봅니다. 최근 값 하나보다 방향과 표본 범위를 함께 확인하세요.
        </p>
        {error && <div role="alert" className="t-body-sm" style={{ color: "var(--accent-orange)", marginTop: 16 }}>{error}</div>}

        <section className="card" style={{ marginTop: 24, padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div>
              <h2 className="t-h3">화성시 전체 흐름</h2>
              <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "5px 0 0" }}>{overview?.method_notice}</p>
            </div>
            <span className="t-caption" style={{ color: "var(--ink-faint)" }}>표본충분 셀만 집계</span>
          </div>
          <div style={{ marginTop: 18 }}><LineChart series={overview?.series} metrics={metrics} /></div>
        </section>

        <section className="card" style={{ marginTop: 16, padding: 24 }}>
          <h2 className="t-h3">읍면동 × 업종 흐름</h2>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
            <select value={industryId ?? ""} onChange={(event) => setIndustryId(Number(event.target.value))} style={{ flex: "1 1 240px" }}>
              {(options?.industries ?? []).map((industry) => <option key={industry.id} value={industry.id}>{industry.name}</option>)}
            </select>
            <select value={areaId ?? ""} onChange={(event) => setAreaId(Number(event.target.value))} style={{ flex: "1 1 200px" }}>
              {availableAreas.map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}
            </select>
          </div>
          <div style={{ marginTop: 18 }}><LineChart series={cell?.series} metrics={metrics} /></div>
          {cell && <p className="t-caption" style={{ color: "var(--ink-faint)", margin: "12px 0 0" }}>{cell.area_name} · {cell.industry_name}</p>}
        </section>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16, marginTop: 16 }}>
          <Movers title={`${areas?.industry_name ?? "선택 업종"} · 읍면동 변화`} data={areas} />
          <Movers title={`${industries?.area_name ?? "선택 지역"} · 업종 변화`} data={industries} />
        </div>

        <section style={{ marginTop: 32 }}>
          <h2 className="t-h2">화성시 고유 흐름</h2>
          <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "6px 0 14px" }}>도농복합 구조와 동탄 신도시를 별도 관측하되, 우열이나 원인으로 해석하지 않습니다.</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
            <GroupTable data={areaTypes} />
            <GroupTable data={dongtan} />
          </div>
        </section>
      </div>
    </div>
  );
}
