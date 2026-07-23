import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../lib/api";

const NAVER_CLIENT_ID = import.meta.env.VITE_NAVER_MAP_CLIENT_ID || "";

const LEGEND = [
  { label: "위험", color: "var(--status-red)" },
  { label: "주의", color: "var(--status-orange)" },
  { label: "안전", color: "var(--status-green)" },
  { label: "데이터 없음", color: "#94A3B8" },
];

function loadNaverMap(callback) {
  if (window.naver?.maps) { callback(); return; }
  const script = document.createElement("script");
  script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${NAVER_CLIENT_ID}`;
  script.onload = callback;
  document.head.appendChild(script);
}

export default function MapPage() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const polygonsRef = useRef([]);
  const [riskData, setRiskData] = useState([]);
  const [selected, setSelected] = useState(null);
  const [tooltip, setTooltip] = useState(null);

  useEffect(() => {
    apiFetch(`/api/alerts/vacancy-risk/map`)
      .then((r) => r.json())
      .then(setRiskData)
      .catch(() => {});
  }, []);

  const drawPolygons = useCallback((map, geojson, riskMap) => {
    polygonsRef.current.forEach((p) => p.setMap(null));
    polygonsRef.current = [];

    geojson.features.forEach((feat) => {
      const name = feat.properties.dong_name || feat.properties.EMD_KOR_NM || "";
      const risk = riskMap[name];
      const color = risk?.color || "#94A3B8";
      const score = risk?.score ?? null;

      const coords = feat.geometry.type === "Polygon"
        ? [feat.geometry.coordinates]
        : feat.geometry.coordinates;

      coords.forEach((rings) => {
        const path = rings[0].map(([lng, lat]) => new window.naver.maps.LatLng(lat, lng));
        const polygon = new window.naver.maps.Polygon({
          map, paths: [path], fillColor: color, fillOpacity: 0.5,
          strokeColor: "#fff", strokeWeight: 1,
        });

        window.naver.maps.Event.addListener(polygon, "mouseover", (e) => {
          polygon.setOptions({ fillOpacity: 0.8 });
          setTooltip({ name, score, color, x: e.pointerEvent.clientX, y: e.pointerEvent.clientY });
        });
        window.naver.maps.Event.addListener(polygon, "mousemove", (e) => {
          setTooltip((t) => t ? { ...t, x: e.pointerEvent.clientX, y: e.pointerEvent.clientY } : null);
        });
        window.naver.maps.Event.addListener(polygon, "mouseout", () => {
          polygon.setOptions({ fillOpacity: 0.5 });
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

    loadNaverMap(() => {
      if (!mapRef.current) return;
      if (!mapInstanceRef.current) {
        mapInstanceRef.current = new window.naver.maps.Map(mapRef.current, {
          center: new window.naver.maps.LatLng(37.1997, 126.8312),
          zoom: 11,
        });
      }
      fetch("/hwaseong_emd.geojson")
        .then((r) => r.json())
        .then((geojson) => drawPolygons(mapInstanceRef.current, geojson, riskMap))
        .catch(() => console.warn("GeoJSON 없음 — 먼저 hwaseong_emd.geojson을 생성하세요"));
    });
  }, [riskData, drawPolygons]);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--primary)", margin: 0 }}>공실위험 지도</h1>
        <p style={{ fontSize: 14, color: "var(--on-surface-variant)", marginTop: 4 }}>
          화성시 읍면동별 공실위험지수. 클릭하면 상세 정보를 볼 수 있습니다.
        </p>
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ position: "relative", flex: 1 }}>
          <div
            ref={mapRef}
            style={{ height: 580, borderRadius: 8, overflow: "hidden", border: "1px solid var(--border-subtle)" }}
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
              width: 180,
              background: "var(--surface-container-lowest)",
              border: "1px solid var(--border-subtle)",
              borderRadius: 8,
              padding: 16,
              zIndex: 10,
            }}
          >
            <p style={{ fontSize: 14, fontWeight: 600, color: "var(--primary)", margin: "0 0 12px" }}>공실 위험도 범례</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {LEGEND.map(({ label, color }) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 14, height: 14, borderRadius: 3, background: color, display: "inline-block", flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: "var(--on-surface-variant)" }}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ width: 280, flexShrink: 0, background: "var(--surface-container-lowest)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 24, height: "fit-content" }}>
          {selected ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "var(--primary)" }}>{selected.name}</h3>
                <button
                  onClick={() => setSelected(null)}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--outline)", fontSize: 18, lineHeight: 1, padding: 0 }}
                >
                  ×
                </button>
              </div>

              {selected.score != null ? (
                <>
                  <div style={{ textAlign: "center", margin: "16px 0 20px" }}>
                    <div style={{ fontSize: 40, fontWeight: 700, color: selected.color }}>{selected.score}</div>
                    <div style={{ fontSize: 13, color: "var(--on-surface-variant)", marginTop: 4 }}>공실위험지수 / 100</div>
                    <span
                      style={{
                        display: "inline-block",
                        marginTop: 10,
                        fontSize: 12,
                        fontWeight: 700,
                        color: selected.color,
                        background: `${selected.color}1A`,
                        padding: "4px 12px",
                        borderRadius: 999,
                      }}
                    >
                      {selected.risk_level}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: "var(--on-surface-variant)", padding: "12px 0", borderTop: "1px solid var(--border-subtle)" }}>
                    폐업률 추이 기울기 <b style={{ color: "var(--on-surface)" }}>{selected.trend?.toFixed(3)}</b>
                  </div>
                  <Link
                    to="/dashboard"
                    style={{
                      display: "block",
                      textAlign: "center",
                      marginTop: 16,
                      border: "1px solid var(--primary)",
                      color: "var(--primary)",
                      padding: "10px 0",
                      borderRadius: 8,
                      fontSize: 14,
                      fontWeight: 700,
                      textDecoration: "none",
                    }}
                  >
                    조기경보 대시보드에서 보기
                  </Link>
                </>
              ) : (
                <div style={{ color: "var(--outline)", fontSize: 13, textAlign: "center", padding: "24px 0" }}>데이터 없음</div>
              )}
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "40px 0" }}>
              <span className="material-symbols-outlined" style={{ fontSize: 40, color: "var(--outline)", display: "block", marginBottom: 12 }}>
                touch_app
              </span>
              <p style={{ fontSize: 15, fontWeight: 600, color: "var(--on-surface-variant)", margin: "0 0 8px" }}>구역을 선택하십시오</p>
              <p style={{ fontSize: 13, color: "var(--outline)", margin: 0, lineHeight: 1.6 }}>
                지도에서 상세 분석이 필요한 구역을 클릭하면 위험 지표가 표시됩니다.
              </p>
            </div>
          )}
        </div>
      </div>

      {tooltip && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x + 12,
            top: tooltip.y - 32,
            pointerEvents: "none",
            background: "var(--primary)",
            color: "#fff",
            fontSize: 12,
            padding: "6px 10px",
            borderRadius: 6,
            zIndex: 9999,
          }}
        >
          <b>{tooltip.name}</b>
          {tooltip.score != null && <span style={{ marginLeft: 8, color: tooltip.color }}>위험도 {tooltip.score}</span>}
        </div>
      )}
    </div>
  );
}
