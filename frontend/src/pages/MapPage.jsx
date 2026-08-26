import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../lib/api";
import ProvisionalNotice from "../components/ProvisionalNotice";

// 다른 화면과 같은 정의. 이 파일에만 사본이 없어 백엔드 raw 값(2자리)이 그대로 찍혔다 —
// 같은 상권이 대시보드에서 7.1%, 여기서 7.14%로 보였다.
const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

const NAVER_CLIENT_ID = import.meta.env.VITE_NAVER_MAP_CLIENT_ID || "";

// 범례 색은 백엔드가 폴리곤에 쓰는 색과 반드시 같아야 한다.
// 예전에는 여기가 CSS 변수(--error #ba1a1a)이고 백엔드가 #D51B4C를 보내서, 같은 화면에서
// 폴리곤 색과 범례 점 색이 달랐다(2026-08-25 감사). 지금은 백엔드도 index.css 값을 쓴다.
const LEGEND = [
  { label: "위험", color: "var(--error)" },
  { label: "주의", color: "var(--accent-orange)" },
  { label: "안정", color: "var(--accent-green)" },
  { label: "판단보류", color: "var(--outline-variant)" },
];

// 색은 등급, 진하기는 근거의 두께다. 범례 아래 한 줄로 그 규칙을 밝힌다.
const OPACITY_NOTE = "흐리게 칠해진 동은 표본이 충분한 업종이 10개 미만이라 등급의 근거가 얕습니다.";

let naverMapLoadPromise = null;

function loadNaverMap() {
  if (window.naver?.maps) return Promise.resolve();
  if (!naverMapLoadPromise) {
    naverMapLoadPromise = new Promise((resolve) => {
      const script = document.createElement("script");
      script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${NAVER_CLIENT_ID}`;
      script.onload = resolve;
      document.head.appendChild(script);
    });
  }
  return naverMapLoadPromise;
}

// 실패를 조용히 빈 배열로 삼키면 담당자가 "데이터가 없다"로 읽고 DB 적재를 의심하게 된다.
// (실제로 백엔드가 꺼져 있었을 때 그렇게 진단이 헛돌았다.) 원인을 화면에 그대로 말한다.
function loadErrorMessage(status) {
  if (status === 401 || status === 403) return "로그인이 만료되었습니다. 다시 로그인해주세요.";
  if (status) return `데이터를 불러오지 못했습니다 (HTTP ${status}).`;
  return "서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해주세요.";
}

function RankingTable({ rows, loading, error }) {
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 className="t-h3" style={{ margin: 0 }}>상권 순위표 — 최근 1년 누적 폐업률</h3>
      <p style={{ margin: "0 0 16px", fontSize: 12, color: "var(--outline)" }}>
        순수 관측치 정렬, 보정·예측 없음(표본 50개 이상 업종만 집계).
        단일 분기는 폐업 1~2건 차이로 값이 크게 튀어 4분기 누적으로 봅니다.
      </p>
      {loading ? (
        <div className="t-body-sm" style={{ padding: 24, textAlign: "center", color: "var(--ink-faint)" }}>불러오는 중...</div>
      ) : error ? (
        <div className="t-body-sm" style={{ padding: 24, textAlign: "center", color: "var(--error)" }}>{error}</div>
      ) : rows.length === 0 ? (
        <div className="t-body-sm" style={{ padding: 24, textAlign: "center", color: "var(--ink-faint)" }}>데이터 없음</div>
      ) : (
        /* 사각지대·비교 화면과 같은 패턴. 이 표만 스크롤 래퍼가 없어 1280px에서 헤더가 줄바꿈됐다. */
        <div style={{ overflowX: "auto" }}>
        <table style={{ minWidth: 560 }}>
          <thead>
            <tr>
              <th style={{ fontWeight: 600 }}>순위</th>
              <th style={{ fontWeight: 600 }}>읍면동</th>
              <th style={{ fontWeight: 600 }}>업종</th>
              <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>최근 1년 누적 폐업률</th>
              <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>폐업</th>
              <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>점포수</th>
              <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>업종 내</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.area_id}-${r.industry_id}`}>
                <td style={{ padding: "8px 4px", color: "var(--outline)" }}>{r.rank}</td>
                {/* 읍면동 칸을 셀 상세로 잇는다. 폐업률 최악 목록을 보여주고 클릭할 수 없으면
                    담당자의 다음 행동이 끊긴다(사각지대 표와 같은 처리). */}
                <td style={{ padding: "8px 4px", fontWeight: 600 }}>
                  <Link
                    to={`/cells/${r.area_id}/${r.industry_id}`}
                    style={{ color: "var(--on-surface)", textDecoration: "none" }}
                  >
                    {r.dong}
                  </Link>
                </td>
                <td style={{ color: "var(--ink-muted)" }}>{r.category}</td>
                <td className="t-metric" style={{ textAlign: "right", color: "var(--error)" }}>{fmt(r.closure_rate_pct)}%</td>
                <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-muted)" }}>{r.cumulative_closure_count ?? "—"}곳</td>
                <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-muted)" }}>{r.store_count}</td>
                <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-faint)" }}>
                  {r.industry_rank ? `${r.industry_rank}/${r.industry_total}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}

export default function MapPage() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const polygonsRef = useRef([]);
  const boundsFitRef = useRef(false);
  const [riskData, setRiskData] = useState([]);
  const [selected, setSelected] = useState(null);
  const [tooltip, setTooltip] = useState(null);
  const [ranking, setRanking] = useState([]);
  const [rankingLoading, setRankingLoading] = useState(true);
  const [mapError, setMapError] = useState("");
  const [rankingError, setRankingError] = useState("");

  useEffect(() => {
    apiFetch(`/api/alerts/vacancy-risk/map`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => {
        setRiskData(Array.isArray(d) ? d : []);
        setMapError("");
      })
      .catch((reason) => {
        setRiskData([]);
        setMapError(loadErrorMessage(typeof reason === "number" ? reason : null));
      });
    apiFetch(`/api/alerts/closure-rate-ranking?limit=10`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => {
        // 401 본문은 배열이 아니라 {detail: ...}라 그대로 넣으면 rows.map()에서 터진다
        setRanking(Array.isArray(d) ? d : []);
        setRankingError("");
      })
      .catch((reason) => {
        setRanking([]);
        setRankingError(loadErrorMessage(typeof reason === "number" ? reason : null));
      })
      .finally(() => setRankingLoading(false));
  }, []);

  const drawPolygons = useCallback((map, geojson, riskMap) => {
    polygonsRef.current.forEach((p) => p.setMap(null));
    polygonsRef.current = [];

    geojson.features.forEach((feat) => {
      const name = feat.properties.dong_name || feat.properties.EMD_KOR_NM || "";
      const risk = riskMap[name];
      const color = risk?.color || "#c1c6d5";
      const ratio = risk?.risk_ratio ?? null;
      const coverage = risk?.coverage_pct ?? null;
      // 색은 등급, 진하기는 근거의 두께. 표본충분 업종이 적은 동은 등급을 내되 흐리게 칠해
      // "이 색을 얼마나 믿을지"를 같이 보여준다. 숨기는 것보다 알려주는 쪽을 택했다.
      const thin = Boolean(risk?.evidence_thin);
      const baseOpacity = thin ? 0.22 : 0.5;
      const hoverOpacity = thin ? 0.42 : 0.8;

      const coords = feat.geometry.type === "Polygon"
        ? [feat.geometry.coordinates]
        : feat.geometry.coordinates;

      coords.forEach((rings) => {
        const path = rings[0].map(([lng, lat]) => new window.naver.maps.LatLng(lat, lng));
        const polygon = new window.naver.maps.Polygon({
          map, paths: [path], fillColor: color, fillOpacity: baseOpacity,
          strokeColor: "#fff", strokeWeight: 1, clickable: true,
        });

        window.naver.maps.Event.addListener(polygon, "mouseover", (e) => {
          polygon.setOptions({ fillOpacity: hoverOpacity });
          setTooltip({ name, ratio, coverage, color, thin, x: e.pointerEvent.clientX, y: e.pointerEvent.clientY });
        });
        window.naver.maps.Event.addListener(polygon, "mousemove", (e) => {
          setTooltip((t) => t ? { ...t, x: e.pointerEvent.clientX, y: e.pointerEvent.clientY } : null);
        });
        window.naver.maps.Event.addListener(polygon, "mouseout", () => {
          polygon.setOptions({ fillOpacity: baseOpacity });
          setTooltip(null);
        });
        window.naver.maps.Event.addListener(polygon, "click", () => {
          setSelected(risk ? { name, ...risk } : { name });
        });

        polygonsRef.current.push(polygon);
      });
    });
  }, []);

  useEffect(() => {
    if (!NAVER_CLIENT_ID) return;
    const riskMap = Object.fromEntries(riskData.map((r) => [r.dong, r]));

    loadNaverMap().then(() => {
      if (!mapRef.current) return;
      if (!mapInstanceRef.current) {
        mapInstanceRef.current = new window.naver.maps.Map(mapRef.current, {
          center: new window.naver.maps.LatLng(37.1997, 126.8312),
          zoom: 11,
        });
      }
      fetch("/hwaseong_emd.geojson")
        .then((r) => r.json())
        .then((geojson) => {
          drawPolygons(mapInstanceRef.current, geojson, riskMap);
          if (!boundsFitRef.current) {
            const bounds = new window.naver.maps.LatLngBounds();
            geojson.features.forEach((feat) => {
              const coords = feat.geometry.type === "Polygon"
                ? [feat.geometry.coordinates]
                : feat.geometry.coordinates;
              coords.forEach((rings) => {
                rings[0].forEach(([lng, lat]) => bounds.extend(new window.naver.maps.LatLng(lat, lng)));
              });
            });
            mapInstanceRef.current.fitBounds(bounds);
            boundsFitRef.current = true;
          }
        })
        .catch(() => console.warn("GeoJSON 없음 — 먼저 hwaseong_emd.geojson을 생성하세요"));
    });
  }, [riskData, drawPolygons]);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-h1" style={{ margin: 0 }}>공실위험 지도</h1>
        <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0" }}>
          읍면동별 위험 업종 비율 — 최근 1년 누적 폐업률 기준(4분기 합산, 보정 없음). 읍면동을 클릭하면 상세 지표가 표시됩니다.
        </p>
        <div style={{ marginTop: 12 }}>
          <ProvisionalNotice />
        </div>
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ position: "relative", flex: 1 }}>
          {mapError && (
            <div
              role="alert"
              style={{
                position: "absolute",
                top: 16,
                left: 16,
                right: 16,
                zIndex: 20,
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: "rgba(255,255,255,0.96)",
                border: "1px solid var(--error)",
                borderRadius: "var(--radius-lg)",
                padding: "12px 14px",
                boxShadow: "var(--elev-1)",
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 20, color: "var(--error)" }}>error</span>
              <span className="t-body-sm" style={{ color: "var(--on-surface)" }}>{mapError}</span>
            </div>
          )}
          <div
            ref={mapRef}
            style={{ height: 580, borderRadius: "var(--radius-lg)", overflow: "hidden", border: "1px solid var(--hairline)" }}
          >
            {!NAVER_CLIENT_ID && (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--outline)", flexDirection: "column", gap: 8 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 32 }}>map</span>
                <span style={{ fontSize: 14 }}>frontend/.env에 VITE_NAVER_MAP_CLIENT_ID를 설정하세요</span>
              </div>
            )}
          </div>

          <div
            style={{
              position: "absolute",
              bottom: 16,
              left: 16,
              maxWidth: 240,
              background: "rgba(255,255,255,0.94)",
              backdropFilter: "blur(6px)",
              border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-lg)",
              padding: 14,
              zIndex: 10,
              boxShadow: "var(--elev-1)",
            }}
          >
            <p className="t-eyebrow" style={{ color: "var(--ink-muted)", margin: "0 0 10px", textTransform: "uppercase" }}>
              위험 업종 비율
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {LEGEND.map(({ label, color }) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: "var(--radius-full)", background: color, display: "inline-block", flexShrink: 0 }} />
                  <span className="t-caption" style={{ color: "var(--ink-secondary)" }}>{label}</span>
                </div>
              ))}
            </div>
            <p className="t-caption" style={{ color: "var(--ink-faint)", margin: "10px 0 0", lineHeight: 1.6 }}>
              {OPACITY_NOTE}
            </p>
          </div>
        </div>

        <div className="card" style={{ width: 288, flexShrink: 0, height: "fit-content" }}>
          {selected ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <h3 className="t-h3" style={{ margin: 0 }}>{selected.name}</h3>
                <button
                  onClick={() => setSelected(null)}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--outline)", fontSize: 18, lineHeight: 1, padding: 0 }}
                >
                  ×
                </button>
              </div>

              {selected.risk_ratio != null ? (
                <>
                  <div style={{ textAlign: "center", margin: "18px 0 20px" }}>
                    <div className="t-metric" style={{ fontSize: 44, color: selected.color, lineHeight: 1.1 }}>{fmt(selected.risk_ratio)}%</div>
                    <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 6 }}>위험 업종 비율 (최근 1년 누적 기준)</div>
                    <span
                      style={{
                        display: "inline-block",
                        marginTop: 10,
                        fontSize: 12,
                        fontWeight: 700,
                        color: selected.color,
                        background: `color-mix(in srgb, ${selected.color} 12%, white)`,
                        padding: "4px 12px",
                        borderRadius: "var(--radius-full)",
                      }}
                    >
                      {selected.risk_level}
                    </span>
                  </div>
                  <div className="t-body-sm" style={{ color: "var(--ink-muted)", padding: "12px 0", borderTop: "1px solid var(--hairline)" }}>
                    폐업률 추이 기울기 <b style={{ color: "var(--on-surface)" }}>{selected.trend?.toFixed(3)}</b>
                  </div>
                  <div className="t-body-sm" style={{ color: "var(--ink-muted)", padding: "12px 0", borderTop: "1px solid var(--hairline)" }}>
                    분석 가능 업종 <b style={{ color: "var(--on-surface)" }}>{selected.sample_sufficient_cells}/{selected.total_cells}개</b>
                    <div className="t-caption" style={{ marginTop: 4, color: "var(--ink-faint)" }}>
                      표본 충족률 {selected.coverage_pct}% · 점포 수 50개 이상 기준
                    </div>
                  </div>
                  {selected.evidence_thin && selected.hold_notice && (
                    <div
                      className="t-caption"
                      style={{
                        color: "var(--ink-secondary)",
                        background: "var(--surface-container-low)",
                        padding: "10px 12px",
                        borderRadius: "var(--radius-md)",
                        marginTop: 12,
                        lineHeight: 1.6,
                      }}
                    >
                      {selected.hold_notice}
                    </div>
                  )}
                  <Link
                    to="/dashboard"
                    className="btn-utility"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 6,
                      marginTop: 16,
                      width: "100%",
                      boxSizing: "border-box",
                      color: "var(--primary)",
                      textDecoration: "none",
                    }}
                  >
                    조기경보 대시보드에서 보기
                  </Link>
                </>
              ) : (
                /* 비율을 안 내려준 동. "데이터 없음" 한 줄로 끝내면 담당자가 왜인지 모른다.
                   분모를 보여줘야 "위험하지 않다"가 아니라 "판단할 근거가 없다"로 읽힌다. */
                <div style={{ padding: "20px 0" }}>
                  <div style={{ textAlign: "center" }}>
                    <span className="badge" style={{ color: "var(--ink-muted)" }}>판단보류</span>
                  </div>
                  <div className="t-body-sm" style={{ color: "var(--ink-muted)", marginTop: 14, lineHeight: 1.7 }}>
                    {selected.hold_notice ?? "읍면동 단위 등급을 판정할 표본이 부족합니다."}
                  </div>
                  <div className="t-body-sm" style={{ color: "var(--ink-muted)", padding: "12px 0", marginTop: 8, borderTop: "1px solid var(--hairline)" }}>
                    분석 가능 업종{" "}
                    <b style={{ color: "var(--on-surface)" }}>
                      {selected.sample_sufficient_cells}/{selected.total_cells}개
                    </b>
                    <div className="t-caption" style={{ marginTop: 4, color: "var(--ink-faint)" }}>
                      표본 충족률 {selected.coverage_pct}% · 점포 수 50개 이상 기준
                    </div>
                  </div>
                  <Link
                    to={`/blindspots?dong=${encodeURIComponent(selected.name)}`}
                    className="btn-utility"
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                      marginTop: 16, width: "100%", boxSizing: "border-box",
                      color: "var(--primary)", textDecoration: "none",
                    }}
                  >
                    사각지대에서 이 읍면동 보기
                  </Link>
                </div>
              )}
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "40px 0" }}>
              <span className="material-symbols-outlined" style={{ fontSize: 36, color: "var(--ink-faint)", display: "block", marginBottom: 12 }}>
                touch_app
              </span>
              <p className="t-title" style={{ color: "var(--on-surface)", margin: "0 0 8px" }}>읍면동을 선택하세요</p>
              <p className="t-caption" style={{ color: "var(--ink-muted)", margin: 0, lineHeight: 1.6 }}>
                지도에서 읍면동을 클릭하면 위험 지표가 표시됩니다.
              </p>
            </div>
          )}
        </div>
      </div>

      <RankingTable rows={ranking} loading={rankingLoading} error={rankingError} />

      {tooltip && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x + 12,
            top: tooltip.y - 32,
            pointerEvents: "none",
            background: "var(--on-surface)",
            color: "#fff",
            fontSize: 12,
            padding: "7px 11px",
            borderRadius: "var(--radius-md)",
            boxShadow: "var(--elev-2)",
            zIndex: 9999,
          }}
        >
          <b>{tooltip.name}</b>
          {tooltip.ratio != null && <span style={{ marginLeft: 8, color: tooltip.color }}>위험 업종 비율 {tooltip.ratio}%</span>}
          {tooltip.ratio == null && <span style={{ marginLeft: 8, color: "var(--ink-faint)" }}>판단보류</span>}
          {tooltip.thin && <span style={{ marginLeft: 6, color: "var(--ink-faint)" }}>· 근거 얕음</span>}
          {tooltip.coverage != null && <span style={{ marginLeft: 8 }}>표본 충족 {tooltip.coverage}%</span>}
        </div>
      )}
    </div>
  );
}
