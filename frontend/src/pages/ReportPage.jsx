import { useEffect, useMemo, useState } from "react";
import PublicNav from "../components/PublicNav";
import { apiFetchJson, describeApiError } from "../lib/api";

const SECTION_TONES = {
  overview: { background: "var(--primary-fixed)", accent: "var(--primary)" },
  observed: { background: "var(--surface-container-lowest)", accent: "#2a9d99" },
  strengths: { background: "var(--surface-container-lowest)", accent: "var(--badge-ok-ink)" },
  cautions: { background: "var(--surface-container-lowest)", accent: "var(--badge-warn-ink)" },
  "field-check": { background: "var(--surface-container-lowest)", accent: "var(--ink-muted)" },
};

function ReportSection({ section }) {
  const tone = SECTION_TONES[section.key] ?? SECTION_TONES.observed;
  return (
    <section
      className="card"
      style={{
        padding: 24,
        background: tone.background,
        borderLeft: `4px solid ${tone.accent}`,
        breakInside: "avoid",
      }}
    >
      <h2 className="t-h3">{section.title}</h2>
      <ul style={{ margin: "14px 0 0", paddingLeft: 20, display: "grid", gap: 9 }}>
        {section.body.map((line, index) => (
          <li key={`${section.key}-${index}`} className="t-body-sm" style={{ lineHeight: 1.7 }}>{line}</li>
        ))}
      </ul>
    </section>
  );
}

export default function ReportPage() {
  const [options, setOptions] = useState(null);
  const [presets, setPresets] = useState(null);
  const [areaId, setAreaId] = useState(null);
  const [industryId, setIndustryId] = useState(null);
  const [preset, setPreset] = useState("균형");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiFetchJson("/api/public/areas"),
      apiFetchJson("/api/recommend/presets"),
    ]).then(([optionData, presetData]) => {
      setOptions(optionData);
      setPresets(presetData);
      setPreset(presetData.default);

      const counts = new Map();
      optionData.areas.forEach((area) => area.industries.forEach((industry) => {
        if (!industry.sample_insufficient) counts.set(industry.id, (counts.get(industry.id) ?? 0) + 1);
      }));
      const firstIndustry = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]
        ?? optionData.industries[0]?.id;
      const firstArea = optionData.areas.find((area) =>
        area.industries.some((industry) => industry.id === firstIndustry && !industry.sample_insufficient),
      ) ?? optionData.areas[0];
      setIndustryId(firstIndustry ?? null);
      setAreaId(firstArea?.id ?? null);
    }).catch((err) => setError(describeApiError(err)));
  }, []);

  const availableAreas = useMemo(() => (
    (options?.areas ?? []).filter((area) =>
      area.industries.some((industry) => industry.id === industryId),
    )
  ), [options, industryId]);

  useEffect(() => {
    if (!industryId || !options) return;
    if (!availableAreas.some((area) => area.id === areaId)) {
      const measured = availableAreas.find((area) =>
        area.industries.some((industry) => industry.id === industryId && !industry.sample_insufficient),
      );
      setAreaId(measured?.id ?? availableAreas[0]?.id ?? null);
    }
  }, [areaId, availableAreas, industryId, options]);

  useEffect(() => {
    if (!areaId || !industryId) return;
    setLoading(true);
    setError("");
    apiFetchJson(
      `/api/report/summary?area_id=${areaId}&industry_id=${industryId}&preset=${encodeURIComponent(preset)}`,
    ).then(setReport)
      .catch((err) => { setReport(null); setError(describeApiError(err)); })
      .finally(() => setLoading(false));
  }, [areaId, industryId, preset]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>
      <style>{`
        @media print {
          .report-controls, .public-report-nav, .report-print-button { display: none !important; }
          .report-page { padding: 0 !important; max-width: none !important; }
          .report-grid { gap: 10px !important; }
        }
      `}</style>
      <div className="report-page" style={{ maxWidth: 920, margin: "0 auto", padding: "28px 24px 64px" }}>
        <div className="public-report-nav"><PublicNav /></div>

        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
          <div>
            <h1 className="t-h1">상권 요약 보고서</h1>
            <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "8px 0 0", lineHeight: 1.7 }}>
              관측 사실과 업종 내 상대 적합도를 5개 영역으로 정리합니다.
            </p>
          </div>
          <button
            type="button"
            className="report-print-button"
            onClick={() => window.print()}
            style={{ background: "var(--primary)", color: "white", border: 0, borderRadius: "var(--radius-full)", padding: "10px 17px", cursor: "pointer" }}
          >
            인쇄·PDF 저장
          </button>
        </header>

        <section className="card report-controls" style={{ marginTop: 24, padding: 20 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 10 }}>
            <label className="t-caption" style={{ display: "grid", gap: 7, color: "var(--ink-muted)" }}>
              업종
              <select value={industryId ?? ""} onChange={(event) => setIndustryId(Number(event.target.value))}>
                {(options?.industries ?? []).map((industry) => <option key={industry.id} value={industry.id}>{industry.name}</option>)}
              </select>
            </label>
            <label className="t-caption" style={{ display: "grid", gap: 7, color: "var(--ink-muted)" }}>
              읍면동
              <select value={areaId ?? ""} onChange={(event) => setAreaId(Number(event.target.value))}>
                {availableAreas.map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}
              </select>
            </label>
            <label className="t-caption" style={{ display: "grid", gap: 7, color: "var(--ink-muted)" }}>
              판단 기준
              <select value={preset} onChange={(event) => setPreset(event.target.value)}>
                {(presets?.presets ?? []).map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
              </select>
            </label>
          </div>
        </section>

        {error && <div role="alert" className="t-body-sm" style={{ color: "var(--accent-orange)", marginTop: 18 }}>{error}</div>}
        {loading && <p className="t-body-sm" style={{ color: "var(--ink-muted)", marginTop: 24 }}>보고서를 조합하는 중…</p>}

        {report && !loading && (
          <article style={{ marginTop: 28 }}>
            <div style={{ borderBottom: "1px solid var(--hairline)", paddingBottom: 18, marginBottom: 16 }}>
              <h2 className="t-h2">{report.title}</h2>
              <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "7px 0 0" }}>
                {report.quarter_label} · {report.preset} 기준 · 규칙 버전 {report.generated_by}
              </p>
            </div>

            <div className="report-grid" style={{ display: "grid", gap: 14 }}>
              {report.sections.map((section) => <ReportSection key={section.key} section={section} />)}
            </div>

            <aside className="card" style={{ marginTop: 16, padding: 20, background: "var(--surface-container-low)" }}>
              <h3 className="t-title">AI 사용 공개</h3>
              <p className="t-body-sm" style={{ color: "var(--ink-muted)", lineHeight: 1.7, margin: "8px 0 0" }}>{report.ai_disclosure}</p>
            </aside>
            <p className="t-caption" style={{ color: "var(--ink-faint)", lineHeight: 1.7, margin: "16px 2px 0" }}>
              {report.relative_notice} {report.disclaimer}
            </p>
          </article>
        )}
      </div>
    </div>
  );
}
