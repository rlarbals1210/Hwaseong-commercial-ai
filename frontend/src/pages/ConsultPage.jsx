import { useState, useEffect } from "react";
import { API } from "../lib/api";

const GRADE_COLOR = { A: "#10B981", B: "#3B82F6", C: "#F59E0B", D: "#EF4444" };
const GRADE_LABEL = { A: "매우 우수", B: "우수", C: "보통", D: "주의 필요" };

function GaugeArc({ prob }) {
  const r = 64, cx = 80, cy = 80;
  const total = Math.PI * r;
  const filled = (prob / 100) * total;
  const color = prob >= 65 ? "#10B981" : prob >= 45 ? "#F59E0B" : "#EF4444";

  return (
    <svg width={160} height={100} viewBox="0 0 160 100">
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="#E5E7EB" strokeWidth={12} />
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke={color} strokeWidth={12}
        strokeDasharray={`${filled} ${total}`}
        strokeLinecap="round"
      />
      <text x={cx} y={cy - 8} textAnchor="middle" fontSize={22} fontWeight={800} fill={color}>{prob.toFixed(0)}%</text>
      <text x={cx} y={cy + 8} textAnchor="middle" fontSize={11} fill="#6B7280">창업 생존 가능성</text>
    </svg>
  );
}

function LevelBadge({ label, value }) {
  const color = value === "높음" ? "#EF4444" : value === "보통" ? "#F59E0B" : "#10B981";
  const bg = value === "높음" ? "#FEF2F2" : value === "보통" ? "#FFFBEB" : "#F0FDF4";
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid #F3F4F6" }}>
      <span style={{ fontSize: 13, color: "#374151" }}>{label}</span>
      <span style={{ background: bg, color, fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 99 }}>{value}</span>
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
    fetch(`${API}/api/analysis/dongs`)
      .then((r) => r.json())
      .then((d) => setDongs(d.dongs || []))
      .catch(() => {});
    fetch(`${API}/api/analysis/categories`)
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
      const r = await fetch(`${API}/api/consultation/startup?dong=${encodeURIComponent(dong)}&category=${encodeURIComponent(category)}`);
      if (!r.ok) throw new Error("데이터 없음");
      setResult(await r.json());
    } catch {
      setError("해당 지역·업종의 데이터가 없습니다. AI 파이프라인 실행 후 재시도해주세요.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 560 }}>
      <h1 style={{ fontSize: 22, fontWeight: 800, color: "#111827", margin: "0 0 8px" }}>창업 상담</h1>
      <p style={{ fontSize: 14, color: "#6B7280", marginBottom: 24 }}>
        원하는 읍면동·업종을 선택하면 AI가 3분 내 창업 적합도를 분석합니다.
      </p>

      <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 24, marginBottom: 20 }}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>읍면동</label>
          <select
            value={dong} onChange={(e) => setDong(e.target.value)}
            style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1px solid #D1D5DB", fontSize: 14, background: "#fff" }}
          >
            <option value="">읍면동 선택...</option>
            {dongs.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>업종</label>
          <select
            value={category} onChange={(e) => setCategory(e.target.value)}
            style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1px solid #D1D5DB", fontSize: 14, background: "#fff" }}
          >
            <option value="">업종 선택...</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        {error && <div style={{ fontSize: 13, color: "#EF4444", marginBottom: 12 }}>{error}</div>}
        <button
          onClick={analyze}
          disabled={loading}
          style={{
            width: "100%", padding: "11px 0", background: loading ? "#93C5FD" : "#2563EB",
            color: "#fff", border: "none", borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: loading ? "default" : "pointer",
          }}
        >
          {loading ? "분석 중..." : "창업 적합도 분석하기"}
        </button>
      </div>

      {result && (
        <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 24 }}>
          <div style={{ textAlign: "center", marginBottom: 20 }}>
            <GaugeArc prob={result.survival_prob} />
            <div style={{ marginTop: 8 }}>
              <span style={{
                background: `${GRADE_COLOR[result.grade]}22`, color: GRADE_COLOR[result.grade],
                fontWeight: 700, fontSize: 13, padding: "4px 14px", borderRadius: 99,
              }}>
                {result.grade}등급 — {GRADE_LABEL[result.grade]}
              </span>
            </div>
            <div style={{ fontSize: 13, color: "#6B7280", marginTop: 6 }}>
              {result.dong} · {result.category}
            </div>
          </div>

          <LevelBadge label="유동인구 수준" value={result.population_level} />
          <LevelBadge label="경쟁 강도" value={result.competition_level} />
          <LevelBadge label="업종 포화도" value={result.saturation_level} />

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 8 }}>AI 분석 근거</div>
            {result.reasons.map((r, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, fontSize: 13, color: "#374151" }}>
                <span style={{ color: "#3B82F6", fontWeight: 700, flexShrink: 0 }}>•</span>
                {r}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
