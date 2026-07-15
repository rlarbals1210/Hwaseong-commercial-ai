import { useState, useEffect, useRef, useCallback } from "react";
import { API } from "../lib/api";

const NAVER_CLIENT_ID = import.meta.env.VITE_NAVER_MAP_CLIENT_ID || "";

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
    fetch(`${API}/api/alerts/vacancy-risk/map`)
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
      <h1 style={{ fontSize: 22, fontWeight: 800, color: "#111827", margin: "0 0 8px" }}>공실위험 지도</h1>
      <p style={{ fontSize: 14, color: "#6B7280", marginBottom: 16 }}>
        화성시 읍면동별 공실위험지수. 클릭하면 상세 정보를 볼 수 있습니다.
      </p>

      {/* 범례 */}
      <div style={{ display: "flex", gap: 16, marginBottom: 12, fontSize: 13 }}>
        {[["위험", "#EF4444"], ["주의", "#F59E0B"], ["안전", "#10B981"], ["데이터 없음", "#94A3B8"]].map(([label, color]) => (
          <span key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 14, height: 14, borderRadius: 3, background: color, display: "inline-block" }} />
            {label}
          </span>
        ))}
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        <div ref={mapRef} style={{ flex: 1, height: 580, borderRadius: 12, overflow: "hidden", border: "1px solid #E5E7EB" }}>
          {!NAVER_CLIENT_ID && (
            <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "#9CA3AF", flexDirection: "column", gap: 8 }}>
              <span style={{ fontSize: 32 }}>🗺</span>
              <span style={{ fontSize: 14 }}>frontend/.env에 VITE_NAVER_MAP_CLIENT_ID를 설정하세요</span>
            </div>
          )}
        </div>

        {selected && (
          <div style={{ width: 260, background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 20, height: "fit-content" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>{selected.name}</h3>
              <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "#9CA3AF", fontSize: 18 }}>×</button>
            </div>
            {selected.score != null ? (
              <>
                <div style={{ textAlign: "center", margin: "16px 0" }}>
                  <div style={{ fontSize: 40, fontWeight: 800, color: selected.color }}>{selected.score}</div>
                  <div style={{ fontSize: 13, color: "#6B7280" }}>공실위험지수</div>
                </div>
                <div style={{
                  background: selected.risk_level === "위험" ? "#FEF2F2" : selected.risk_level === "주의" ? "#FFFBEB" : "#F0FDF4",
                  color: selected.color, fontWeight: 700, fontSize: 14,
                  textAlign: "center", padding: "8px 0", borderRadius: 8, marginBottom: 12,
                }}>
                  {selected.risk_level}
                </div>
                <div style={{ fontSize: 12, color: "#6B7280" }}>
                  폐업률 추이 기울기: <b style={{ color: "#111827" }}>{selected.trend?.toFixed(3)}</b>
                </div>
              </>
            ) : (
              <div style={{ color: "#9CA3AF", fontSize: 13, textAlign: "center" }}>데이터 없음</div>
            )}
          </div>
        )}
      </div>

      {/* 마우스오버 툴팁 */}
      {tooltip && (
        <div style={{
          position: "fixed", left: tooltip.x + 12, top: tooltip.y - 32, pointerEvents: "none",
          background: "#1F2937", color: "#fff", fontSize: 12, padding: "6px 10px", borderRadius: 6, zIndex: 9999,
        }}>
          <b>{tooltip.name}</b>
          {tooltip.score != null && <span style={{ marginLeft: 8, color: tooltip.color }}>위험도 {tooltip.score}</span>}
        </div>
      )}
    </div>
  );
}
