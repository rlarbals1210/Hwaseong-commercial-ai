import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson } from "../lib/api";
import ProvisionalNotice from "../components/ProvisionalNotice";

// 조회 기준(점포 50곳)을 못 넘는 상권은 다른 화면에서 아예 사라진다.
// 그렇게 빠지는 점포가 전체의 38%이고, 기배동·매송면은 커버율이 0%다.
// 통계 판단은 계속 보류하되(등급을 매기지 않는다) 목록에서 지우지는 않는다.
//
// 정렬은 폐업'률'이 아니라 폐업 '건수'다. 점포 12곳에서 2곳이 닫히면 률(16.7%)은 노이즈지만
// 체감은 크고, 반대로 률이 높아도 1곳이면 행정이 움직일 일이 아니다.

const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

function Stat({ label, value, unit }) {
  return (
    <div className="card" style={{ padding: 18, flex: "1 1 160px" }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 3, marginTop: 6 }}>
        <span className="t-metric" style={{ fontSize: 28 }}>{value}</span>
        {unit && <span style={{ fontSize: 13, color: "var(--ink-faint)" }}>{unit}</span>}
      </div>
    </div>
  );
}

export default function BlindspotPage() {
  const [data, setData] = useState(null);
  const [dong, setDong] = useState("");
  const [dongs, setDongs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetchJson("/api/analysis/dongs")
      .then((d) => setDongs(Array.isArray(d.dongs) ? d.dongs : Array.isArray(d) ? d : []))
      .catch(() => setDongs([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ limit: 40 });
    if (dong) params.set("dong", dong);
    apiFetchJson(`/api/alerts/blindspots?${params}`)
      .then(setData)
      .catch(() => setError("사각지대 목록을 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [dong]);

  return (
    <div>
      <h1 className="t-h1" style={{ margin: 0 }}>사각지대</h1>
      <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0", maxWidth: 640 }}>
        점포 수가 적어 통계 판단을 보류한 상권입니다. 다른 화면에서는 목록에 오르지 않습니다.
        모델이 판단하지 않으므로 등급을 매기지 않고, <b>폐업 건수 순</b>으로만 보여줍니다.
      </p>

      <div style={{ margin: "16px 0 0" }}>
        <ProvisionalNotice />
      </div>

      {data && (
        <>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "20px 0 8px" }}>
            <Stat label="사각지대 상권" value={data.total_cells.toLocaleString()} unit="개" />
            <Stat label="여기 속한 점포" value={data.total_stores.toLocaleString()} unit="곳" />
            <Stat label="전체 점포 중 비중" value={fmt(data.store_share_pct)} unit="%" />
            <Stat label="최근 1년 폐업" value={data.total_closures.toLocaleString()} unit="건" />
          </div>

          <div
            className="t-caption"
            style={{
              color: "var(--ink-secondary)",
              background: "var(--surface-container-low)",
              padding: "10px 14px",
              borderRadius: "var(--radius-md)",
              marginBottom: 20,
            }}
          >
            {data.notice} (기준: 최신 분기 점포 {data.sample_min}곳 미만)
          </div>
        </>
      )}

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14 }}>
        <span className="t-caption" style={{ color: "var(--ink-muted)" }}>행정동</span>
        <select value={dong} onChange={(e) => setDong(e.target.value)} style={{ minWidth: 160 }}>
          <option value="">전체</option>
          {dongs.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {loading && <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>}
      {error && <div className="t-body-sm" style={{ color: "var(--accent-orange)" }}>{error}</div>}

      {!loading && data?.items?.length === 0 && (
        <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>
          해당 조건에 사각지대 상권이 없습니다.
        </div>
      )}

      {!loading && data?.items?.length > 0 && (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--hairline)" }}>
                {["행정동", "업종", "폐업", "점포", "폐업률(참고)"].map((h, i) => (
                  <th
                    key={h}
                    className="t-eyebrow"
                    style={{
                      textAlign: i >= 2 ? "right" : "left",
                      padding: "12px 16px",
                      color: "var(--ink-faint)",
                      fontWeight: 500,
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={`${item.area_id}-${item.industry_id}`} style={{ borderBottom: "1px solid var(--hairline)" }}>
                  <td style={{ padding: "12px 16px" }}>
                    <Link
                      to={`/cells/${item.area_id}/${item.industry_id}`}
                      style={{ color: "var(--on-surface)", textDecoration: "none" }}
                    >
                      {item.dong}
                    </Link>
                  </td>
                  <td className="t-body-sm" style={{ padding: "12px 16px", color: "var(--ink-secondary)" }}>
                    {item.category}
                  </td>
                  <td style={{ padding: "12px 16px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    <b>{item.cumulative_closure_count}</b>곳
                  </td>
                  <td
                    className="t-body-sm"
                    style={{ padding: "12px 16px", textAlign: "right", color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}
                  >
                    {item.store_count}곳
                  </td>
                  <td
                    className="t-body-sm"
                    style={{ padding: "12px 16px", textAlign: "right", color: "var(--ink-faint)", fontVariantNumeric: "tabular-nums" }}
                  >
                    {fmt(item.cumulative_closure_rate_pct)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 14, maxWidth: 640, lineHeight: 1.7 }}>
        폐업률 열을 오른쪽 끝에 흐리게 둔 것은 의도한 것입니다. 점포가 적을수록 률은 크게 튀므로
        판단의 주 근거로 쓰지 마시고, 건수를 먼저 보십시오.
      </p>
    </div>
  );
}
