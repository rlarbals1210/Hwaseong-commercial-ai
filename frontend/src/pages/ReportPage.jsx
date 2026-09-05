import { useEffect, useMemo, useState } from "react";
import PublicNav from "../components/PublicNav";
import SearchableSelect from "../components/SearchableSelect";
import usePublicQuery from "../hooks/usePublicQuery";
import { API, ApiError, apiFetch, apiFetchJson, describeApiError } from "../lib/api";
import "./report.css";

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
  const [optionError, setOptionError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [exportResult, setExportResult] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      apiFetchJson("/api/public/areas", { signal: controller.signal }),
      apiFetchJson("/api/recommend/presets", { signal: controller.signal }),
    ]).then(([optionData, presetData]) => {
      if (controller.signal.aborted) return;
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
    }).catch((err) => {
      if (!controller.signal.aborted) setOptionError(describeApiError(err));
    });
    return () => controller.abort();
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

  const query = areaId && industryId && availableAreas.some((area) => area.id === areaId)
    ? new URLSearchParams({ area_id: areaId, industry_id: industryId, preset }).toString()
    : "";
  const { data: report, loading, error: reportError } = usePublicQuery(query ? `/api/report/summary?${query}` : null);
  const error = optionError || reportError;
  const ready = Boolean(report && !loading && !error);
  const exportMessage = exportResult?.query === query ? exportResult : null;

  async function downloadPdf() {
    if (!ready || downloading) return;
    setDownloading(true);
    setExportResult(null);
    try {
      const response = await apiFetch(`/api/report/summary.pdf?${query}`);
      if (!response.ok) throw new ApiError(response.status);
      if (!response.headers.get("content-type")?.includes("application/pdf")) {
        throw new Error("Unexpected document format");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `상권보고서_${report.area_name}_${report.industry_name}_${report.quarter_label}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setExportResult({ query, text: "PDF 다운로드를 시작했습니다.", error: false });
    } catch (err) {
      setExportResult({ query, text: `PDF를 만들지 못했습니다. ${describeApiError(err)} 다시 시도해주세요.`, error: true });
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>
      <style>{`
        @media print {
          .report-controls, .public-report-nav, .report-actions { display: none !important; }
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
          <div className="report-actions">
            <div className="report-action-buttons">
              <button type="button" className="report-download-button" disabled={!ready || downloading}
                aria-busy={downloading} onClick={downloadPdf}>
                {downloading ? "PDF 만드는 중…" : "PDF 다운로드"}
              </button>
              {ready ? (
                <a className="report-preview-button" href={`${API}/api/report/summary.pdf?${query}&download=false`}
                  target="_blank" rel="noopener noreferrer" aria-label="인쇄용 미리보기 (새 탭)">
                  인쇄용 미리보기
                </a>
              ) : <button type="button" className="report-preview-button" disabled>인쇄용 미리보기</button>}
            </div>
            <p className="t-caption report-export-hint">A4 보고서 · 핵심 지표와 현장 확인표</p>
            {exportMessage && <p className={`t-caption report-export-status${exportMessage.error ? " is-error" : ""}`}
              role={exportMessage.error ? "alert" : "status"}>{exportMessage.text}</p>}
          </div>
        </header>

        <section className="card report-controls" style={{ marginTop: 24, padding: 20 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 10 }}>
            <SearchableSelect label="업종" icon="storefront" placeholder="업종 선택"
              options={(options?.industries ?? []).map((industry) => ({ value: industry.id, label: industry.name }))}
              value={industryId ?? ""} onChange={setIndustryId} />
            <SearchableSelect label="읍면동" icon="location_on" unit="곳" placeholder="읍면동 선택"
              options={availableAreas.map((area) => ({ value: area.id, label: area.name }))}
              value={areaId ?? ""} onChange={setAreaId} />
            <label className="t-caption" style={{ display: "grid", gap: 7, color: "var(--ink-muted)" }}>
              판단 기준
              <select value={preset} onChange={(event) => setPreset(event.target.value)}>
                {(presets?.presets ?? []).map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
              </select>
            </label>
          </div>
        </section>

        {error && <div role="alert" className="t-body-sm" style={{ color: "var(--accent-orange)", marginTop: 18 }}>{error}</div>}
        {(loading || (!options && !optionError)) && <p className="t-body-sm" style={{ color: "var(--ink-muted)", marginTop: 24 }}>보고서를 조합하는 중…</p>}

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
