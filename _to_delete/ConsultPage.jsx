import { useState, useEffect } from "react";
import { apiFetch } from "../lib/api";

const GRADE_COLOR = { A: "var(--status-green)", B: "var(--secondary)", C: "var(--status-orange)", D: "var(--status-red)" };
const GRADE_LABEL = { A: "매우 우수", B: "우수", C: "보통", D: "주의 필요" };

const LEVEL_TONE = {
  population_level: { 높음: "var(--status-green)", 보통: "var(--status-orange)", 낮음: "var(--status-red)" },
  competition_level: { 높음: "var(--status-red)", 보통: "var(--status-orange)", 낮음: "var(--status-green)" },
  saturation_level: { 높음: "var(--status-red)", 보통: "var(--status-orange)", 낮음: "var(--status-green)" },
};

function GaugeArc({ prob, color }) {
  const r = 64, cx = 80, cy = 80;
  const total = Math.PI * r;
  const filled = (prob / 100) * total;
  const arc = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;

  return (
    <svg width={160} height={100} viewBox="0 0 160 100">
      <path d={arc} fill="none" stroke="var(--border-subtle)" strokeWidth={12} />
      <path d={arc} fill="none" stroke={color} strokeWidth={12} strokeDasharray={`${filled} ${total}`} strokeLinecap="round" />
      <text x={cx} y={cy - 8} textAnchor="middle" fontSize={22} fontWeight={800} fill={color}>
        {prob.toFixed(0)}%
      </text>
      <text x={cx} y={cy + 8} textAnchor="middle" fontSize={11} fill="var(--on-surface-variant)">
        창업 생존 가능성
      </text>
    </svg>
  );
}

function LevelBadge({ field, label, value }) {
  const color = LEVEL_TONE[field]?.[value] || "var(--status-orange)";
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--border-subtle)" }}>
      <span style={{ fontSize: 13, color: "var(--on-surface-variant)" }}>{label}</span>
      <span style={{ background: `${color}1A`, color, fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 99 }}>{value}</span>
    </div>
  );
}

export default function ConsultPage() {
  const [dong, setDong] = useState("");
  const [category, setCategory] = useState("");
  const [dongs, setDongs] = useState([]);
  const [categories, setCategories] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch(`/api/analysis/dongs`)
      .then((r) => r.json())
      .then((d) => setDongs(d.dongs || []))
      .catch(() => {});
    apiFetch(`/api/analysis/categories`)
      .then((r) => r.json())
      .then((d) => setCategories(d.categories || []))
      .catch(() => {});
  }, []);

  const analyze = async () => {
    if (!dong || !category) { setError("읍면동과 업종을 모두 선택해주세요."); return; }
    setError("");
    setLoading(true);
    setResult(null);
    try {
      const r = await apiFetch(`/api/consultation/startup?dong=${encodeURIComponent(dong)}&category=${encodeURIComponent(category)}`);
      if (!r.ok) throw new Error("데이터 없음");
      setResult(await r.json());
    } catch {
      setError("해당 지역·업종의 데이터가 없습니다. AI 파이프라인 실행 후 재시도해주세요.");
    } finally {
      setLoading(false);
    }
  };

  const gradeColor = result ? GRADE_COLOR[result.grade] : "var(--primary)";

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--primary)", margin: 0 }}>창업 생존 전략 분석</h1>
        <p style={{ fontSize: 14, color: "var(--on-surface-variant)", marginTop: 4 }}>
          원하는 읍면동·업종을 선택하면 AI가 정밀 분석한 창업 적합도 리포트를 보여줍니다.
        </p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr auto",
          gap: 16,
          alignItems: "end",
          background: "var(--surface-container-lowest)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 8,
          padding: 20,
          marginBottom: 20,
        }}
      >
        <div>
          <label style={{ fontSize: 13, fontWeight: 600, color: "var(--on-surface-variant)", display: "block", marginBottom: 6 }}>분석 지역</label>
          <select
            value={dong}
            onChange={(e) => setDong(e.target.value)}
            style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1px solid var(--border-subtle)", fontSize: 14, background: "var(--surface-gray)", boxSizing: "border-box" }}
          >
            <option value="">읍면동 선택...</option>
            {dongs.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 13, fontWeight: 600, color: "var(--on-surface-variant)", display: "block", marginBottom: 6 }}>창업 업종</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1px solid var(--border-subtle)", fontSize: 14, background: "var(--surface-gray)", boxSizing: "border-box" }}
          >
            <option value="">업종 선택...</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <button
          onClick={analyze}
          disabled={loading}
          style={{
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            padding: "10px 20px", background: "var(--primary)", color: "#fff",
            border: "none", borderRadius: 8, fontSize: 14, fontWeight: 700,
            cursor: loading ? "default" : "pointer", opacity: loading ? 0.7 : 1, whiteSpace: "nowrap",
          }}
        >
          <span className={`material-symbols-outlined${loading ? " spin" : ""}`} style={{ fontSize: 18 }}>
            {loading ? "sync" : "analytics"}
          </span>
          {loading ? "분석 중..." : "분석 업데이트"}
        </button>
      </div>

      {error && <div style={{ fontSize: 13, color: "var(--status-red)", marginBottom: 16 }}>{error}</div>}

      {result ? (
        <div style={{ display: "grid", gridTemplateColumns: "5fr 7fr", gap: 20 }}>
          <div
            style={{
              position: "relative", overflow: "hidden",
              background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8,
              padding: 32, display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center",
            }}
          >
            <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: 4, background: gradeColor }} />
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: gradeColor, marginBottom: 8 }}>
              <span className="material-symbols-outlined" style={{ fontSize: 18, fontVariationSettings: "'FILL' 1" }}>stars</span>
              <span style={{ fontSize: 13, fontWeight: 700 }}>{GRADE_LABEL[result.grade]}</span>
            </div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--on-surface)", margin: "0 0 16px" }}>창업 생존 확률</h2>
            <GaugeArc prob={result.survival_prob} color={gradeColor} />
            <div style={{ fontSize: 13, color: "var(--on-surface-variant)", marginTop: 12, marginBottom: 24 }}>
              {result.dong} · {result.category}
            </div>
            <button
              onClick={() => window.print()}
              style={{
                width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                padding: "12px 0", background: "var(--secondary-container)", color: "var(--on-secondary-container)",
                border: "none", borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: "pointer",
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>download</span>
              결과 인쇄 / PDF 저장
            </button>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 24 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, paddingBottom: 16, borderBottom: "1px solid var(--border-subtle)" }}>
                <div style={{ width: 40, height: 40, borderRadius: "50%", background: "rgba(0,21,62,0.08)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--primary)", flexShrink: 0 }}>
                  <span className="material-symbols-outlined">psychology</span>
                </div>
                <div>
                  <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--on-surface)", margin: 0 }}>AI 분석 근거</h3>
                  <p style={{ fontSize: 13, color: "var(--on-surface-variant)", margin: "2px 0 0" }}>{result.reasons.length}가지 핵심 데이터 지표 기반</p>
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {result.reasons.map((r, i) => (
                  <div key={i} style={{ display: "flex", gap: 12, padding: 12, background: "var(--surface-gray)", border: "1px solid var(--border-subtle)", borderRadius: 8 }}>
                    <span className="material-symbols-outlined" style={{ fontSize: 20, color: "var(--status-green)", fontVariationSettings: "'FILL' 1", flexShrink: 0 }}>check_circle</span>
                    <p style={{ fontSize: 13, color: "var(--on-surface-variant)", margin: 0, lineHeight: 1.6 }}>{r}</p>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--on-surface)", margin: "0 0 4px" }}>주요 지표</h3>
              <LevelBadge field="population_level" label="유동인구 수준" value={result.population_level} />
              <LevelBadge field="competition_level" label="경쟁 강도" value={result.competition_level} />
              <LevelBadge field="saturation_level" label="업종 포화도" value={result.saturation_level} />
            </div>
          </div>
        </div>
      ) : (
        <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: "60px 24px", textAlign: "center" }}>
          <span className="material-symbols-outlined" style={{ fontSize: 40, color: "var(--outline)", display: "block", marginBottom: 12 }}>touch_app</span>
          <p style={{ fontSize: 15, fontWeight: 600, color: "var(--on-surface-variant)", margin: "0 0 8px" }}>지역과 업종을 선택하세요</p>
          <p style={{ fontSize: 13, color: "var(--outline)", margin: 0 }}>분석 업데이트 버튼을 누르면 AI 창업 적합도 리포트가 표시됩니다.</p>
        </div>
      )}
    </div>
  );
}
