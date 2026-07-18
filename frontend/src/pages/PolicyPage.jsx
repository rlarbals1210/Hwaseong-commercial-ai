import { useState, useEffect } from "react";
import { apiFetch } from "../lib/api";

const QUADRANT_META = {
  Q1: { label: "1순위 — 즉시 지원", color: "#EF4444", bg: "#FEF2F2", desc: "위험 높고 수혜 점포 많아 지원 효과 최대" },
  Q2: { label: "2순위 — 긴급 모니터링", color: "#F59E0B", bg: "#FFFBEB", desc: "위험 높지만 수혜 점포 적음. 개별 밀착 지원 우선" },
  Q3: { label: "3순위 — 예방적 지원 검토", color: "#3B82F6", bg: "#EFF6FF", desc: "위험 낮지만 수혜 점포 많음. 확산 방지 차원 검토" },
  Q4: { label: "4순위 — 일반 관찰", color: "#10B981", bg: "#F0FDF4", desc: "안정적 상권. 정기 모니터링 유지" },
};

function QuadrantCard({ qKey, items }) {
  const meta = QUADRANT_META[qKey];
  const [open, setOpen] = useState(qKey === "Q1");

  return (
    <div style={{ background: "#fff", border: `1px solid ${meta.color}44`, borderRadius: 12, overflow: "hidden" }}>
      <div
        onClick={() => setOpen(!open)}
        style={{ background: meta.bg, padding: "14px 20px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <div>
          <span style={{ fontWeight: 700, color: meta.color, fontSize: 14 }}>{meta.label}</span>
          <span style={{ fontSize: 12, color: "#6B7280", marginLeft: 8 }}>{meta.desc}</span>
        </div>
        <span style={{ fontWeight: 700, color: meta.color }}>{items.length}건 {open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div style={{ padding: "12px 20px" }}>
          {items.length === 0 ? (
            <div style={{ color: "#9CA3AF", fontSize: 13, padding: "8px 0" }}>해당 없음</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #E5E7EB" }}>
                  {["읍면동", "업종", "위험점수", "점포수(수혜규모)"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "6px 8px", color: "#6B7280", fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.slice(0, 10).map((item, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid #F3F4F6" }}>
                    <td style={{ padding: "7px 8px", fontWeight: 600 }}>{item.dong}</td>
                    <td style={{ padding: "7px 8px", color: "#374151" }}>{item.category}</td>
                    <td style={{ padding: "7px 8px", color: meta.color, fontWeight: 700 }}>{item.risk_score}</td>
                    <td style={{ padding: "7px 8px", color: "#374151" }}>{item.growth_prob}개</td>
                  </tr>
                ))}
                {items.length > 10 && (
                  <tr><td colSpan={4} style={{ padding: "6px 8px", color: "#9CA3AF", fontSize: 12 }}>+{items.length - 10}개 더...</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

export default function PolicyPage() {
  const [data, setData] = useState({ Q1: [], Q2: [], Q3: [], Q4: [] });
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
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    apiFetch(`/api/policy/fund-priority?${params}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [category]);

  const total = Object.values(data).reduce((s, arr) => s + arr.length, 0);

  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 800, color: "#111827", margin: "0 0 8px" }}>정책자금 우선순위</h1>
      <p style={{ fontSize: 14, color: "#6B7280", marginBottom: 20 }}>
        폐업위험도 × 정책잠재력(점포수 기준 수혜규모) 기반 4단계 지원 우선순위 매트릭스
      </p>

      <div style={{ marginBottom: 16, display: "flex", gap: 12, alignItems: "center" }}>
        <label style={{ fontSize: 13, color: "#374151", fontWeight: 600 }}>업종</label>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #D1D5DB", fontSize: 13, background: "#fff" }}
        >
          <option value="">전체 업종</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <span style={{ fontSize: 13, color: "#6B7280" }}>총 {total}건</span>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 60, color: "#9CA3AF", fontSize: 14 }}>분석 중...</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {Object.keys(QUADRANT_META).map((qKey) => (
            <QuadrantCard key={qKey} qKey={qKey} items={data[qKey] || []} />
          ))}
        </div>
      )}
    </div>
  );
}
