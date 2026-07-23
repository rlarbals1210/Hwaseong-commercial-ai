import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../lib/api";

const LEVEL = {
  위험: { color: "var(--status-red)", threshold: 70 },
  주의: { color: "var(--status-orange)", threshold: 50 },
  안전: { color: "var(--status-green)", threshold: 0 },
};

function levelOf(score) {
  if (score >= 70) return "위험";
  if (score >= 50) return "주의";
  return "안전";
}

function downloadCsv(rows) {
  if (!rows.length) return;
  const headers = ["순위", "읍면동", "업종", "폐업위험점수", "성장확률", "폐업률", "트렌드이상", "권고사항"];
  const lines = rows.map((r) =>
    [r.rank, r.dong, r.category, r.risk_score, r.growth_prob, r.closure_rate, r.anomaly ? "Y" : "N", r.action]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(",")
  );
  const csv = [headers.join(","), ...lines].join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `화성시_폐업위험_Top10_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function StatCard({ label, value, color }) {
  return (
    <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 20 }}>
      <div style={{ fontSize: 32, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 13, color: "var(--on-surface-variant)", marginTop: 4 }}>{label}</div>
    </div>
  );
}

function RiskCard({ item }) {
  const level = levelOf(item.risk_score);
  const color = LEVEL[level].color;
  return (
    <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "var(--outline)" }}>Rank {String(item.rank).padStart(2, "0")}</span>
        <span style={{ fontSize: 10, fontWeight: 700, color, background: `${color}1A`, padding: "3px 10px", borderRadius: 999 }}>{level}</span>
      </div>
      <div>
        <div style={{ fontSize: 17, fontWeight: 700, color: "var(--on-surface)" }}>{item.dong}</div>
        <div style={{ fontSize: 13, color: "var(--on-surface-variant)" }}>{item.category}</div>
      </div>
      <div style={{ marginTop: "auto" }}>
        <div style={{ fontSize: 12, color: "var(--outline)", marginBottom: 2 }}>위험 지수</div>
        <div>
          <span style={{ fontSize: 28, fontWeight: 700, color }}>{item.risk_score}</span>
          <span style={{ fontSize: 13, color: "var(--outline)" }}> /100</span>
        </div>
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        <span style={{ fontSize: 12, color: "var(--on-surface-variant)" }}>
          성장확률 <b style={{ color: "var(--on-surface)" }}>{item.growth_prob?.toFixed(1)}%</b>
        </span>
        <span style={{ fontSize: 12, color: "var(--on-surface-variant)" }}>
          폐업률 <b style={{ color: "var(--on-surface)" }}>{item.closure_rate?.toFixed(1)}%</b>
        </span>
      </div>
      <div style={{ fontSize: 12, color: "var(--on-surface)", background: "var(--surface-gray)", padding: "8px 10px", borderRadius: 6 }}>
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
  const top = data[0];
  const topActions = data.slice(0, 2);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--primary)", margin: 0 }}>폐업 위험 조기경보</h1>
        <p style={{ fontSize: 14, color: "var(--on-surface-variant)", marginTop: 4 }}>
          AI가 감지한 이번 분기 화성시 고위험 읍면동·업종 Top 10
        </p>
      </div>

      {!loading && data.length > 0 && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 16 }}>
            <StatCard label="위험 지역" value={dangerCount} color="var(--status-red)" />
            <StatCard label="주의 지역" value={cautionCount} color="var(--status-orange)" />
            <StatCard label="트렌드 이상" value={anomalyCount} color="var(--secondary)" />
          </div>

          {top && (
            <div
              style={{
                background: "var(--primary)",
                borderRadius: 8,
                padding: 24,
                marginBottom: 24,
                color: "#fff",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 16,
              }}
            >
              <div>
                <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>최고 위험 지역</div>
                <div style={{ fontSize: 24, fontWeight: 700 }}>
                  화성시 {top.dong} · {top.category}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>폐업위험 지수</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: "var(--status-red)" }}>{top.risk_score}</div>
              </div>
            </div>
          )}
        </>
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
          disabled={!data.length}
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
            cursor: data.length ? "pointer" : "default",
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
            download
          </span>
          CSV 다운로드
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--outline)", fontSize: 14 }}>데이터 로드 중...</div>
      ) : data.length === 0 ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--outline)", fontSize: 14 }}>
          데이터가 없습니다. 먼저 AI 파이프라인을 실행해 DB를 채워주세요.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 16, marginBottom: 24 }}>
          {data.map((item) => (
            <RiskCard key={`${item.dong}-${item.category}`} item={item} />
          ))}
        </div>
      )}

      {topActions.length > 0 && (
        <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 24 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--primary)", margin: "0 0 16px" }}>AI 정책 제안</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
            {topActions.map((item) => (
              <div
                key={`${item.dong}-${item.category}-action`}
                style={{ padding: 12, background: "var(--surface-gray)", borderLeft: `4px solid var(--primary)`, borderRadius: "0 6px 6px 0" }}
              >
                <p style={{ fontSize: 14, fontWeight: 700, color: "var(--primary)", margin: "0 0 4px" }}>
                  {item.dong} · {item.category}
                </p>
                <p style={{ fontSize: 13, color: "var(--on-surface-variant)", margin: 0 }}>{item.action}</p>
              </div>
            ))}
          </div>
          <Link
            to="/policy"
            style={{
              display: "inline-block",
              width: "100%",
              boxSizing: "border-box",
              textAlign: "center",
              border: "1px solid var(--primary)",
              color: "var(--primary)",
              padding: "10px 0",
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 700,
              textDecoration: "none",
            }}
          >
            정책자금 우선순위 매트릭스 보기
          </Link>
        </div>
      )}
    </div>
  );
}
