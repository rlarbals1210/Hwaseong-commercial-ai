import { useState, useEffect } from "react";
import { apiFetch } from "../lib/api";

const RISK_COLOR = { 위험: "#EF4444", 주의: "#F59E0B", 안전: "#10B981" };
const RISK_BG = { 위험: "#FEF2F2", 주의: "#FFFBEB", 안전: "#F0FDF4" };

function RiskBar({ score }) {
  return (
    <div style={{ background: "#E5E7EB", borderRadius: 4, height: 6, marginTop: 6 }}>
      <div style={{
        width: `${Math.min(100, score)}%`, height: "100%", borderRadius: 4,
        background: score >= 70 ? "#EF4444" : score >= 50 ? "#F59E0B" : "#10B981",
        transition: "width 0.5s ease",
      }} />
    </div>
  );
}

function RiskCard({ item }) {
  const level = item.risk_score >= 70 ? "위험" : item.risk_score >= 50 ? "주의" : "안전";
  return (
    <div style={{
      background: "#fff", border: `1px solid ${RISK_COLOR[level]}44`,
      borderRadius: 12, padding: "16px 20px", display: "flex", flexDirection: "column", gap: 6,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{
            background: RISK_BG[level], color: RISK_COLOR[level],
            fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99, marginRight: 8,
          }}>{level}</span>
          {item.anomaly && (
            <span style={{
              background: "#FEF3C7", color: "#92400E",
              fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
            }}>트렌드 이상</span>
          )}
        </div>
        <span style={{ fontSize: 22, fontWeight: 800, color: RISK_COLOR[level] }}>
          {item.risk_score}
        </span>
      </div>
      <div>
        <span style={{ fontSize: 15, fontWeight: 700, color: "#111827" }}>{item.dong}</span>
        <span style={{ fontSize: 13, color: "#6B7280", marginLeft: 6 }}>{item.category}</span>
      </div>
      <RiskBar score={item.risk_score} />
      <div style={{ display: "flex", gap: 16, marginTop: 4 }}>
        <span style={{ fontSize: 12, color: "#6B7280" }}>성장확률 <b style={{ color: "#111827" }}>{item.growth_prob?.toFixed(1)}%</b></span>
        <span style={{ fontSize: 12, color: "#6B7280" }}>폐업률 <b style={{ color: "#111827" }}>{item.closure_rate?.toFixed(1)}%</b></span>
      </div>
      <div style={{ fontSize: 12, color: "#374151", background: "#F9FAFB", padding: "6px 10px", borderRadius: 6, marginTop: 2 }}>
        {item.action}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState([]);

  useEffect(() => {
    apiFetch(`/api/analysis/categories`)
      .then((r) => r.json())
      .then((d) => setCategories(d.categories || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ limit: 10 });
    if (category) params.set("category", category);
    apiFetch(`/api/alerts/closure-risk?${params}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [category]);

  const dangerCount = data.filter((d) => d.risk_score >= 70).length;
  const cautionCount = data.filter((d) => d.risk_score >= 50 && d.risk_score < 70).length;
  const anomalyCount = data.filter((d) => d.anomaly).length;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, color: "#111827", margin: 0 }}>
          폐업 위험 조기경보
        </h1>
        <p style={{ fontSize: 14, color: "#6B7280", marginTop: 4 }}>
          AI가 감지한 이번 분기 화성시 고위험 읍면동·업종 Top 10
        </p>
      </div>

      {/* 요약 카드 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 24 }}>
        {[
          { label: "위험 지역", value: dangerCount, color: "#EF4444", bg: "#FEF2F2" },
          { label: "주의 지역", value: cautionCount, color: "#F59E0B", bg: "#FFFBEB" },
          { label: "트렌드 이상", value: anomalyCount, color: "#7C3AED", bg: "#F5F3FF" },
        ].map(({ label, value, color, bg }) => (
          <div key={label} style={{ background: bg, border: `1px solid ${color}33`, borderRadius: 12, padding: "16px 20px" }}>
            <div style={{ fontSize: 28, fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: 13, color: "#374151", marginTop: 2 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* 필터 */}
      <div style={{ marginBottom: 16, display: "flex", gap: 12, alignItems: "center" }}>
        <label style={{ fontSize: 13, color: "#374151", fontWeight: 600 }}>업종 필터</label>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #D1D5DB", fontSize: 13, background: "#fff" }}
        >
          <option value="">전체 업종</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {/* 경보 카드 목록 */}
      {loading ? (
        <div style={{ textAlign: "center", padding: 60, color: "#9CA3AF", fontSize: 14 }}>
          데이터 로드 중...
        </div>
      ) : data.length === 0 ? (
        <div style={{ textAlign: "center", padding: 60, color: "#9CA3AF", fontSize: 14 }}>
          데이터가 없습니다. 먼저 AI 파이프라인을 실행해 DB를 채워주세요.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
          {data.map((item) => <RiskCard key={`${item.dong}-${item.category}`} item={item} />)}
        </div>
      )}
    </div>
  );
}
