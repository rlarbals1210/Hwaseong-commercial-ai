import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson } from "../lib/api";

function downloadCsv(rows) {
  if (!rows.length) return;
  const headers = ["예측순위", "읍면동", "업종", "실제폐업률(%)", "개업률(%)", "트렌드이상", "후속조치_검토안"];
  const lines = rows.map((r) =>
    [r.predicted_rank, r.dong, r.category, r.actual_closure_rate_pct, r.open_rate_pct, r.anomaly ? "Y" : "N", r.action]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(",")
  );
  const csv = [headers.join(","), ...lines].join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `화성시_조기경보_예측순위_${new Date().toISOString().slice(0, 10)}.csv`;
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

// AI 예측값(부풀려진 절대 수치)은 화면에 표시하지 않는다 — 순위만 신뢰할 수 있는 정보라
// "예측 위험 #N"으로만 보여주고, 근거는 실제 관측 지표(폐업률·개업률·추세)로 뒷받침한다.
function RiskCard({ item }) {
  const color = "var(--primary)";
  return (
    <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 10, fontWeight: 700, color, background: `${color}1A`, padding: "3px 10px", borderRadius: 999 }}>
          AI 예측 위험 #{item.predicted_rank}
        </span>
        {item.anomaly && (
          <span style={{ fontSize: 10, fontWeight: 700, color: "var(--status-red)" }}>⚠ 트렌드 이상</span>
        )}
      </div>
      <div>
        <div style={{ fontSize: 17, fontWeight: 700, color: "var(--on-surface)" }}>{item.dong}</div>
        <div style={{ fontSize: 13, color: "var(--on-surface-variant)" }}>{item.category}</div>
      </div>
      <div style={{ marginTop: "auto" }}>
        <div style={{ fontSize: 12, color: "var(--outline)", marginBottom: 2 }}>실제 최근 폐업률</div>
        <div>
          <span style={{ fontSize: 28, fontWeight: 700, color: "var(--on-surface)" }}>{item.actual_closure_rate_pct}</span>
          <span style={{ fontSize: 13, color: "var(--outline)" }}> %</span>
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, color: "var(--on-surface-variant)" }}>
          개업률 <b style={{ color: "var(--on-surface)" }}>{item.open_rate_pct?.toFixed(1)}%</b>
        </span>
        <span style={{ fontSize: 12, color: "var(--on-surface-variant)" }}>
          폐업률 추세 <b style={{ color: "var(--on-surface)" }}>{item.trend_slope > 0 ? "+" : ""}{item.trend_slope}</b>
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
  const [error, setError] = useState("");
  const [categoryError, setCategoryError] = useState(false);

  useEffect(() => {
    apiFetchJson(`/api/analysis/categories?purpose=alert`)
      .then((d) => {
        setCategories(Array.isArray(d.categories) ? d.categories : []);
        setCategoryError(false);
      })
      .catch(() => {
        setCategories([]);
        setCategoryError(true);
      });
  }, []);

  useEffect(() => {
    const params = new URLSearchParams({ limit: 10 });
    if (category) params.set("category", category);
    apiFetchJson(`/api/alerts/closure-risk?${params}`)
      .then((result) => {
        if (!Array.isArray(result)) throw new Error("Invalid alert response");
        setData(result);
      })
      .catch(() => {
        setData([]);
        setError("데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.");
      })
      .finally(() => setLoading(false));
  }, [category]);

  const anomalyCount = data.filter((d) => d.anomaly).length;
  const avgActual = data.length ? (data.reduce((s, d) => s + d.actual_closure_rate_pct, 0) / data.length).toFixed(1) : 0;
  const top = data[0];
  const topReviewItems = data.slice(0, 2);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--primary)", margin: 0 }}>폐업 위험 조기경보</h1>
        <p style={{ fontSize: 14, color: "var(--on-surface-variant)", marginTop: 4 }}>
          AI 예측 기반 조기경보 — 상대 순위 (예측 절대값 아님, 실제값과는 별도 지표)
        </p>
      </div>

      {!loading && data.length > 0 && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 16 }}>
            <StatCard label="AI 예측 상위 셀" value={data.length} color="var(--primary)" />
            <StatCard label="트렌드 이상" value={anomalyCount} color="var(--status-red)" />
            <StatCard label="상위권 평균 실제 폐업률" value={`${avgActual}%`} color="var(--secondary)" />
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
                <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>AI 예측 위험 1순위</div>
                <div style={{ fontSize: 24, fontWeight: 700 }}>
                  화성시 {top.dong} · {top.category}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>실제 최근 폐업률</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: "#fff" }}>{top.actual_closure_rate_pct}%</div>
              </div>
            </div>
          )}
        </>
      )}

      <div style={{ marginBottom: 16, display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <label style={{ fontSize: 13, color: "var(--on-surface-variant)", fontWeight: 600 }}>업종 필터</label>
            <select
              value={category}
              onChange={(e) => {
                setLoading(true);
                setError("");
                setCategory(e.target.value);
              }}
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
          <div style={{ marginTop: 5, fontSize: 11, color: categoryError ? "var(--status-red)" : "var(--outline)" }}>
            {categoryError
              ? "업종 목록을 불러오지 못했습니다."
              : `최신 분기 점포 수 30개 이상이며 AI 순위가 산출된 ${categories.length}개 업종`}
          </div>
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
      ) : error ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--status-red)", fontSize: 14 }}>{error}</div>
      ) : data.length === 0 ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--outline)", fontSize: 14 }}>
          {category
            ? "선택한 업종은 최신 분기의 분석 가능 표본이 부족합니다."
            : "AI 분석 결과가 없습니다. 데이터 적재 상태를 확인해주세요."}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 16, marginBottom: 24 }}>
          {data.map((item) => (
            <RiskCard key={`${item.dong}-${item.category}`} item={item} />
          ))}
        </div>
      )}

      {topReviewItems.length > 0 && (
        <div style={{ background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 24 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--primary)", margin: "0 0 16px" }}>후속 조치 검토안</h3>
          <p style={{ fontSize: 12, color: "var(--outline)", margin: "-8px 0 16px" }}>
            AI가 지원 대상을 결정하지 않습니다. 확인 순서를 제안할 뿐이며 최종 판단은 담당자가 합니다.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
            {topReviewItems.map((item) => (
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
            현장점검 우선순위 보기
          </Link>
        </div>
      )}
    </div>
  );
}
