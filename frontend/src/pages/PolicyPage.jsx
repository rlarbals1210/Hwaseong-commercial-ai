import { useState } from "react";
import { useEffect } from "react";
import { apiFetch } from "../lib/api";

const QUADRANT_META = {
  Q1: { label: "1순위 — 즉시 지원", color: "var(--status-red)", desc: "위험 높고 수혜 점포 많아 지원 효과 최대" },
  Q2: { label: "2순위 — 긴급 모니터링", color: "var(--status-orange)", desc: "위험 높지만 수혜 점포 적음. 개별 밀착 지원 우선" },
  Q3: { label: "3순위 — 예방적 지원 검토", color: "var(--secondary)", desc: "위험 낮지만 수혜 점포 많음. 확산 방지 차원 검토" },
  Q4: { label: "4순위 — 일반 관찰", color: "var(--status-green)", desc: "안정적 상권. 정기 모니터링 유지" },
};

function StatCard({ label, value, color }) {
  return (
    <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 16 }}>
      <p style={{ fontSize: 12, color: "var(--on-surface-variant)", margin: "0 0 6px" }}>{label}</p>
      <p style={{ fontSize: 22, fontWeight: 700, color: color || "var(--primary)", margin: 0 }}>{value}</p>
    </div>
  );
}

function QuadrantPanel({ meta, items, highlight }) {
  return (
    <div
      style={{
        position: "relative",
        border: highlight ? `2px solid ${meta.color}` : "1px dashed var(--border-subtle)",
        borderRadius: 8,
        background: highlight ? `${meta.color}0D` : "var(--surface-gray)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {highlight && (
        <div
          style={{
            position: "absolute",
            top: 10,
            right: -30,
            background: meta.color,
            color: "#fff",
            fontSize: 10,
            fontWeight: 700,
            padding: "3px 32px",
            transform: "rotate(45deg)",
          }}
        >
          PRIORITY
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8, gap: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: meta.color, background: `${meta.color}1A`, padding: "3px 10px", borderRadius: 6, whiteSpace: "nowrap" }}>
          {meta.label}
        </span>
        <span style={{ fontSize: 12, fontWeight: 700, color: meta.color, flexShrink: 0 }}>{items.length}건</span>
      </div>
      <p style={{ fontSize: 12, color: "var(--on-surface-variant)", margin: "0 0 12px" }}>{meta.desc}</p>
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, maxHeight: 220 }}>
        {items.length === 0 ? (
          <div style={{ color: "var(--outline)", fontSize: 13, padding: "8px 0" }}>해당 없음</div>
        ) : (
          items.map((item, i) => (
            <div
              key={i}
              style={{
                background: "var(--surface-container-lowest)",
                border: "1px solid var(--border-subtle)",
                borderRadius: 6,
                padding: "8px 10px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--on-surface)" }}>{item.dong}</div>
                <div style={{ fontSize: 11, color: "var(--on-surface-variant)" }}>
                  {item.category} · 위험 {item.risk_score}
                </div>
              </div>
              <span style={{ fontSize: 12, fontWeight: 700, color: meta.color, flexShrink: 0 }}>{item.growth_prob}개</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function downloadCsv(data) {
  const rows = Object.entries(data).flatMap(([q, items]) => items.map((item) => ({ ...item, quadrant: q })));
  if (!rows.length) return;
  const headers = ["우선순위", "읍면동", "업종", "폐업위험점수", "점포수(수혜규모)"];
  const lines = rows.map((r) =>
    [r.quadrant, r.dong, r.category, r.risk_score, r.growth_prob]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(",")
  );
  const csv = [headers.join(","), ...lines].join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `화성시_정책자금_우선순위_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
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
  const dongCount = new Set(Object.values(data).flat().map((i) => i.dong)).size;
  const highRiskStores = [...data.Q1, ...data.Q2].reduce((s, i) => s + (i.growth_prob || 0), 0);
  const topQ1 = [...data.Q1].sort((a, b) => b.risk_score - a.risk_score)[0];

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--primary)", margin: 0 }}>정책자금 우선순위 매트릭스</h1>
        <p style={{ fontSize: 14, color: "var(--on-surface-variant)", marginTop: 4 }}>
          폐업위험도 × 정책잠재력(점포수 기준 수혜규모) 기반 4단계 지원 우선순위
        </p>
      </div>

      {!loading && total > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }}>
          <StatCard label="총 분석 대상 구역" value={`${dongCount}개 읍면동`} />
          <StatCard label="위험군 업체 수" value={`${highRiskStores.toLocaleString()}개소`} color="var(--status-red)" />
          <StatCard label="1순위(Q1) 지구 수" value={`${data.Q1.length}개 지구`} color="var(--secondary)" />
          <StatCard label="전체 분석 건수" value={`${total}건`} />
        </div>
      )}

      <div style={{ marginBottom: 16, display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <label style={{ fontSize: 13, color: "var(--on-surface-variant)", fontWeight: 600 }}>업종 필터</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border-subtle)", fontSize: 13, background: "var(--surface-container-lowest)" }}
          >
            <option value="">전체 업종</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={() => downloadCsv(data)}
          disabled={!total}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "8px 14px",
            borderRadius: 8,
            border: "1px solid var(--border-subtle)",
            background: "var(--surface-container-lowest)",
            fontSize: 13,
            color: "var(--on-surface-variant)",
            cursor: total ? "pointer" : "default",
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
            download
          </span>
          CSV 다운로드
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--outline)", fontSize: 14 }}>분석 중...</div>
      ) : total === 0 ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--outline)", fontSize: 14 }}>
          데이터가 없습니다. 먼저 AI 파이프라인을 실행해 DB를 채워주세요.
        </div>
      ) : (
        <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 24 }}>
          <div style={{ display: "flex", gap: 12 }}>
            <div
              style={{
                writingMode: "vertical-rl",
                transform: "rotate(180deg)",
                fontSize: 12,
                color: "var(--on-surface-variant)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              영향 받는 점포 수 (파급력 규모)
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 12, minHeight: 500 }}>
                <QuadrantPanel meta={QUADRANT_META.Q3} items={data.Q3} />
                <QuadrantPanel meta={QUADRANT_META.Q1} items={data.Q1} highlight />
                <QuadrantPanel meta={QUADRANT_META.Q4} items={data.Q4} />
                <QuadrantPanel meta={QUADRANT_META.Q2} items={data.Q2} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--on-surface-variant)", marginTop: 8 }}>
                <span>Low</span>
                <span>High</span>
              </div>
              <div style={{ textAlign: "center", fontSize: 12, color: "var(--on-surface-variant)", marginTop: 4 }}>
                폐업 위험도 스코어 (Risk Score)
              </div>
            </div>
          </div>
        </div>
      )}

      {topQ1 && (
        <div
          style={{
            marginTop: 16,
            background: "var(--primary)",
            borderRadius: 8,
            padding: 24,
            color: "#fff",
            display: "flex",
            alignItems: "center",
            gap: 16,
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 32, flexShrink: 0, opacity: 0.85 }}>
            lightbulb
          </span>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, opacity: 0.95 }}>
            현재 <b>{topQ1.dong} · {topQ1.category}</b>이(가) 1순위 구역 중 가장 높은 위험도(<b>{topQ1.risk_score}</b>)를 보이고 있습니다.
            해당 구역부터 정책자금 배정을 우선 검토하세요.
          </p>
        </div>
      )}
    </div>
  );
}
