import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import FitScorePanel from "../components/FitScorePanel";
import { apiFetchJson, describeApiError } from "../lib/api";
import { NAVER_CLIENT_ID, loadNaverMap, featureName, featurePaths, fitBoundsTight } from "../lib/naverMap";

// 서울 노다지 MapPage의 핵심 구조를 이식한 공개 상권 탐색 화면.
// 전체화면 지도 + 52px 상단 바 + 좌측 부유 카드를 유지하되, 서울 격자나 개별 점포
// 행위는 가져오지 않는다. 이 프로젝트의 모든 출력은 읍면동 x 업종 집계 단위다.

const fmt = (value, digits = 1) => (
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—"
);

function NodajiLogo() {
  return (
    <svg viewBox="0 0 108 32" aria-hidden="true" className="nodaji-logo">
      <text x="0" y="24" fontFamily="Arial Black, Helvetica Neue, Arial, sans-serif" fontWeight="900" fontSize="21" letterSpacing="1.1" fill="#cde0f0">
        NODAJI
      </text>
      <g transform="translate(98,5) rotate(35)">
        <circle cx="0" cy="0" r="5.5" fill="none" stroke="#8ab0cc" strokeWidth="0.5" />
        <polygon points="0,-4.5 0.85,0 0,0.9 -0.85,0" fill="#d94e30" />
        <polygon points="0,4.5 0.85,0 0,-0.9 -0.85,0" fill="#b8d0e8" />
        <circle cx="0" cy="0" r="0.7" fill="#1a2440" />
      </g>
    </svg>
  );
}

function NodajiMapNav() {
  return (
    <header className="nodaji-map-nav">
      <svg viewBox="0 0 1200 52" preserveAspectRatio="none" className="nodaji-nav-wave" aria-hidden="true">
        <path d="M0 36 Q150 26,300 36 Q450 46,600 36 Q750 26,900 36 Q1050 46,1200 32" />
        <path d="M0 42 Q200 30,400 42 Q600 54,800 42 Q1000 30,1200 38" />
      </svg>
      <Link to="/browse" className="nodaji-brand" aria-label="노다지 상권 둘러보기">
        <NodajiLogo />
      </Link>
      <nav aria-label="공개 상권 메뉴" className="nodaji-map-menu">
        <Link to="/browse" className="active">상권 둘러보기</Link>
        <Link to="/trends">상권 트렌드</Link>
        <Link to="/report">요약 보고서</Link>
        <span className="nodaji-menu-divider" />
        <Link to="/">담당자 로그인</Link>
      </nav>
    </header>
  );
}

function MapLegend({ mapData, clusterData }) {
  if (!mapData?.legend?.length) return null;
  return (
    <div className="nodaji-card-legend" aria-label="최근 1년 누적 폐업률 범례">
      <div className="nodaji-section-label">최근 1년 누적 폐업률</div>
      <div className="nodaji-legend-grid">
        {mapData.legend.map(({ label, color }) => (
          <span key={label}>
            <i style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>
      <p>업종 내 상대 구간입니다. 진한 색이 더 나쁜 상권을 뜻하지 않습니다.</p>
      {clusterData && <p>줌 14 이상에서 3곳 이상 점포 격자를 표시합니다.</p>}
    </div>
  );
}

function PresetPicker({ data, value, onChange }) {
  if (!data?.presets?.length) return null;
  return (
    <div className="nodaji-preset-block">
      <div className="nodaji-section-label">무엇을 더 중요하게 볼까요?</div>
      <div className="nodaji-preset-row">
        {data.presets.map((item) => (
          <button
            key={item.key}
            type="button"
            className={item.key === value ? "active" : ""}
            onClick={() => onChange(item.key)}
            title={item.description}
          >
            {item.label}
          </button>
        ))}
      </div>
      <p>{data.presets.find((item) => item.key === value)?.description}</p>
    </div>
  );
}

function RecommendationList({ data, selectedAreaId, onSelect }) {
  if (!data) return null;
  const tenure = (quarters) => (
    typeof quarters === "number" ? `${(quarters / 4).toFixed(1)}년` : "—"
  );
  return (
    <div className="nodaji-recommendations">
      <div className="nodaji-drawer-heading">
        <div>
          <small>{data.quarter_label} 기준</small>
          <h2>{data.industry_name} 추천 지역</h2>
        </div>
        <span>판단 가능 {data.measured_count}곳</span>
      </div>

      {data.growth_spread_narrow && (
        <div role="alert" className="nodaji-drawer-alert">
          이 업종은 읍면동 간 예측 차이가 크지 않습니다. 상대점수 차이를 크게 해석하지 마세요.
        </div>
      )}

      <div className="nodaji-result-list">
        {data.results.map((item) => (
          <button
            key={item.area_id}
            type="button"
            className={item.area_id === selectedAreaId ? "active" : ""}
            onClick={() => onSelect(item.area_id)}
          >
            <span className="nodaji-rank">{item.rank}</span>
            <span className="nodaji-result-copy">
              <b>{item.area_name}</b>
              <small>
                폐업률 {typeof item.observed.closure_rate_cum4_pct === "number" ? `${fmt(item.observed.closure_rate_cum4_pct)}%` : "—"}
                · 점포 {item.observed.store_count === 0 ? "0개" : `${item.observed.store_count}개`}
                · 업력 {tenure(item.observed.tenure_quarters)}
              </small>
              <em>{item.tags.slice(0, 2).join(" · ")}</em>
            </span>
            <span className="nodaji-result-score">
              <b>{fmt(item.score)}</b>
              <small>{item.grade}등급</small>
            </span>
          </button>
        ))}
      </div>

      <p className="nodaji-drawer-note">{data.relative_notice} {data.disclaimer}</p>
    </div>
  );
}

function ObservationSummary({ cell, loading }) {
  if (loading) return <p className="nodaji-empty-copy">관측 자료를 불러오는 중…</p>;
  if (!cell) return null;
  return (
    <div className="nodaji-observation">
      <div className="nodaji-section-label">실제 관측 자료</div>
      {cell.sample_insufficient ? (
        <p>점포가 <b>{cell.store_count}곳</b>이라 비율로 판단하기 어렵습니다. 수치보다 현장 확인이 필요합니다.</p>
      ) : (
        <div className="nodaji-observation-grid">
          <div><span>최근 1년 누적 폐업률</span><b>{fmt(cell.closure_rate_pct)}%</b></div>
          <div><span>같은 기간 폐업</span><b>{cell.closure_count ?? "—"}곳</b></div>
          <div><span>현재 점포</span><b>{cell.store_count ?? "—"}곳</b></div>
        </div>
      )}
    </div>
  );
}

export default function BrowsePage() {
  const [options, setOptions] = useState(null);
  const [measuredByIndustry, setMeasuredByIndustry] = useState({});
  const [industryId, setIndustryId] = useState(null);
  const [mapData, setMapData] = useState(null);
  const [clusterData, setClusterData] = useState(null);
  const [areaId, setAreaId] = useState(null);
  const [cell, setCell] = useState(null);
  const [cellLoading, setCellLoading] = useState(false);
  const [presetOptions, setPresetOptions] = useState(null);
  const [preset, setPreset] = useState("균형");
  const [recommendations, setRecommendations] = useState(null);
  const [recommendationLoading, setRecommendationLoading] = useState(false);
  const [score, setScore] = useState(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [drawerMode, setDrawerMode] = useState(null);
  const [error, setError] = useState("");
  const [mapError, setMapError] = useState("");
  const [tooltip, setTooltip] = useState(null);

  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const polygonsRef = useRef([]);
  const clusterMarkersRef = useRef([]);
  const zoomListenerRef = useRef(null);
  const boundsFitRef = useRef(false);

  const selectArea = useCallback((nextAreaId) => {
    setAreaId(nextAreaId);
    setDrawerMode("detail");
  }, []);

  useEffect(() => {
    apiFetchJson("/api/recommend/presets")
      .then((data) => { setPresetOptions(data); setPreset(data.default); })
      .catch((err) => setError(describeApiError(err)));
  }, []);

  useEffect(() => {
    apiFetchJson("/api/public/areas")
      .then((data) => {
        setOptions(data);
        const counts = new Map();
        (data.areas ?? []).forEach((area) => area.industries.forEach((industry) => {
          if (!industry.sample_insufficient) counts.set(industry.id, (counts.get(industry.id) ?? 0) + 1);
        }));
        setMeasuredByIndustry(Object.fromEntries(counts));
        const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
        setIndustryId(best ? best[0] : data.industries?.[0]?.id ?? null);
      })
      .catch((err) => setError(describeApiError(err)));
  }, []);

  useEffect(() => {
    if (!industryId) return;
    setAreaId(null);
    setCell(null);
    setScore(null);
    setDrawerMode(null);
    setError("");
    apiFetchJson(`/api/public/industry-map?industry_id=${industryId}`)
      .then(setMapData)
      .catch((err) => { setMapData(null); setError(describeApiError(err)); });
  }, [industryId]);

  useEffect(() => {
    if (!industryId) return;
    apiFetchJson(`/api/recommend/clusters?industry_id=${industryId}`)
      .then(setClusterData)
      .catch(() => setClusterData(null));
  }, [industryId]);

  useEffect(() => {
    if (!industryId) return;
    setRecommendationLoading(true);
    apiFetchJson(`/api/recommend/areas?industry_id=${industryId}&preset=${encodeURIComponent(preset)}&limit=5`)
      .then(setRecommendations)
      .catch((err) => { setRecommendations(null); setError(describeApiError(err)); })
      .finally(() => setRecommendationLoading(false));
  }, [industryId, preset]);

  useEffect(() => {
    if (!areaId || !industryId) return;
    setCellLoading(true);
    apiFetchJson(`/api/public/cell?area_id=${areaId}&industry_id=${industryId}`)
      .then(setCell)
      .catch((err) => { setCell(null); setError(describeApiError(err)); })
      .finally(() => setCellLoading(false));
  }, [areaId, industryId]);

  useEffect(() => {
    if (!areaId || !industryId) return;
    setScoreLoading(true);
    apiFetchJson(`/api/recommend/score?area_id=${areaId}&industry_id=${industryId}&preset=${encodeURIComponent(preset)}`)
      .then(setScore)
      .catch((err) => { setScore(null); setError(describeApiError(err)); })
      .finally(() => setScoreLoading(false));
  }, [areaId, industryId, preset]);

  const colorByName = useMemo(
    () => Object.fromEntries((mapData?.areas ?? []).map((area) => [area.area_name, area])),
    [mapData],
  );

  const selectedMapArea = useMemo(
    () => mapData?.areas?.find((area) => area.area_id === areaId) ?? null,
    [mapData, areaId],
  );

  const drawPolygons = useCallback((map, geojson) => {
    polygonsRef.current.forEach((polygon) => polygon.setMap(null));
    polygonsRef.current = [];

    geojson.features.forEach((feature) => {
      const name = featureName(feature);
      const info = colorByName[name];
      const color = info?.color || "#c1c6d5";
      const selected = info?.area_id === areaId;
      const baseOpacity = !info ? 0.3 : info.sample_insufficient ? 0.5 : 0.74;

      featurePaths(feature).forEach((path) => {
        const polygon = new window.naver.maps.Polygon({
          map,
          paths: [path],
          fillColor: color,
          fillOpacity: selected ? 0.95 : baseOpacity,
          strokeColor: selected ? "#005db2" : "#fff",
          strokeWeight: selected ? 3 : 1.5,
          clickable: true,
        });
        window.naver.maps.Event.addListener(polygon, "mouseover", (event) => {
          polygon.setOptions({ fillOpacity: 0.94 });
          setTooltip({ name, info, x: event.pointerEvent.clientX, y: event.pointerEvent.clientY });
        });
        window.naver.maps.Event.addListener(polygon, "mousemove", (event) => {
          setTooltip((current) => current ? { ...current, x: event.pointerEvent.clientX, y: event.pointerEvent.clientY } : null);
        });
        window.naver.maps.Event.addListener(polygon, "mouseout", () => {
          polygon.setOptions({ fillOpacity: selected ? 0.95 : baseOpacity });
          setTooltip(null);
        });
        window.naver.maps.Event.addListener(polygon, "click", () => {
          if (info) selectArea(info.area_id);
        });
        polygonsRef.current.push(polygon);
      });
    });
  }, [areaId, colorByName, selectArea]);

  const drawStoreClusters = useCallback((map) => {
    clusterMarkersRef.current.forEach((marker) => marker.setMap(null));
    clusterMarkersRef.current = [];
    if (!clusterData?.clusters?.length || map.getZoom() < 14) return;

    clusterMarkersRef.current = clusterData.clusters.map((item) => {
      const diameter = Math.max(28, Math.min(48, 24 + Math.log2(item.store_count + 1) * 5));
      return new window.naver.maps.Marker({
        map,
        position: new window.naver.maps.LatLng(item.lat, item.lng),
        zIndex: 40,
        icon: {
          content: `<div style="width:${diameter}px;height:${diameter}px;border-radius:999px;background:rgba(0,93,178,.88);border:2px solid white;color:white;display:flex;align-items:center;justify-content:center;font:600 12px Inter,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.18)">${Number(item.store_count)}</div>`,
          anchor: new window.naver.maps.Point(diameter / 2, diameter / 2),
        },
      });
    });
  }, [clusterData]);

  useEffect(() => {
    if (!NAVER_CLIENT_ID || !mapData) return;
    loadNaverMap().then(() => {
      if (!mapRef.current) return;
      if (!mapInstanceRef.current) {
        mapInstanceRef.current = new window.naver.maps.Map(mapRef.current, {
          center: new window.naver.maps.LatLng(37.1997, 126.8312),
          zoom: 11,
          zoomControl: false,
          mapDataControl: false,
          scaleControl: true,
        });
      }
      fetch("/hwaseong_emd.geojson")
        .then((response) => response.json())
        .then((geojson) => {
          drawPolygons(mapInstanceRef.current, geojson);
          if (!boundsFitRef.current) {
            const bounds = new window.naver.maps.LatLngBounds();
            geojson.features.forEach((feature) => featurePaths(feature).forEach((path) => path.forEach((point) => bounds.extend(point))));
            mapInstanceRef.current.fitBounds(bounds);
            boundsFitRef.current = true;
          }
          if (zoomListenerRef.current) window.naver.maps.Event.removeListener(zoomListenerRef.current);
          zoomListenerRef.current = window.naver.maps.Event.addListener(
            mapInstanceRef.current,
            "zoom_changed",
            () => drawStoreClusters(mapInstanceRef.current),
          );
          drawStoreClusters(mapInstanceRef.current);
        })
        .catch(() => setMapError("지도 경계 파일을 불러오지 못했습니다."));
    }).catch((err) => setMapError(err.message));
  }, [drawPolygons, drawStoreClusters, mapData]);

  const resetMap = () => {
    const map = mapInstanceRef.current;
    if (!map) return;
    map.setCenter(new window.naver.maps.LatLng(37.1997, 126.8312));
    map.setZoom(11, true);
  };

  return (
    <div className="nodaji-map-page">
      <div className="nodaji-map-stage">
        <div ref={mapRef} className="nodaji-map-canvas">
          {!NAVER_CLIENT_ID && <div className="nodaji-map-empty">지도를 표시할 수 없습니다.</div>}
        </div>
      </div>

      <NodajiMapNav />

      <section className="nodaji-control-card" aria-label="상권 분석 조건">
        <div className="nodaji-control-heading">
          <b>상권분석</b>
          <span>{mapData?.quarter_label ?? "데이터 불러오는 중"}</span>
        </div>

        {selectedMapArea ? (
          <div className="nodaji-selected-summary">
            <small>경기도 화성시</small>
            <strong>{selectedMapArea.area_name}</strong>
            <span>
              {selectedMapArea.sample_insufficient
                ? `판단보류 · 점포 ${selectedMapArea.store_count}곳`
                : `최근 1년 누적 폐업률 ${fmt(selectedMapArea.closure_rate_pct)}%`}
            </span>
          </div>
        ) : (
          <p className="nodaji-control-intro">지도를 누르거나 조건을 골라 상권을 확인하세요.</p>
        )}

        <label className="nodaji-field">
          <span>읍면동 선택 <em>(선택사항)</em></span>
          <select value={areaId ?? ""} onChange={(event) => event.target.value ? selectArea(Number(event.target.value)) : setAreaId(null)}>
            <option value="">화성시 전체 보기</option>
            {(mapData?.areas ?? []).slice().sort((a, b) => a.area_name.localeCompare(b.area_name, "ko")).map((area) => (
              <option key={area.area_id} value={area.area_id}>{area.area_name}</option>
            ))}
          </select>
        </label>

        <label className="nodaji-field">
          <span>업종 선택</span>
          <select value={industryId ?? ""} onChange={(event) => setIndustryId(Number(event.target.value))}>
            {(options?.industries ?? []).map((industry) => (
              <option key={industry.id} value={industry.id}>
                {industry.name} · {measuredByIndustry[industry.id] ? `판단 가능 ${measuredByIndustry[industry.id]}곳` : "전체 판단보류"}
              </option>
            ))}
          </select>
        </label>

        {mapData && (
          <div className="nodaji-mini-stats">
            <span><small>판단 가능</small><b>{mapData.measured_count} / {mapData.total_count}곳</b></span>
            <span><small>화성시 업종 평균</small><b>{fmt(mapData.industry_avg_pct)}%</b></span>
          </div>
        )}

        <button type="button" className="nodaji-analyze-button" onClick={() => setDrawerMode("recommendations")} disabled={!recommendations}>
          추천 지역 보기
        </button>

        <MapLegend mapData={mapData} clusterData={clusterData} />

        {(error || mapError) && <div role="alert" className="nodaji-card-error">{error || mapError}</div>}
      </section>

      {drawerMode && (
        <aside className="nodaji-map-drawer" aria-label={drawerMode === "recommendations" ? "추천 지역" : "선택 상권 상세"}>
          <div className="nodaji-drawer-tabs">
            <button type="button" className={drawerMode === "recommendations" ? "active" : ""} onClick={() => setDrawerMode("recommendations")}>추천 지역</button>
            <button type="button" className={drawerMode === "detail" ? "active" : ""} onClick={() => setDrawerMode("detail")} disabled={!areaId}>선택 상권</button>
            <button type="button" className="nodaji-drawer-close" onClick={() => setDrawerMode(null)} aria-label="패널 닫기">×</button>
          </div>
          <div className="nodaji-drawer-scroll">
            {drawerMode === "recommendations" && (
              <>
                <PresetPicker data={presetOptions} value={preset} onChange={setPreset} />
                {recommendationLoading
                  ? <p className="nodaji-empty-copy">추천 결과를 계산하는 중…</p>
                  : <RecommendationList data={recommendations} selectedAreaId={areaId} onSelect={selectArea} />}
              </>
            )}
            {drawerMode === "detail" && (
              <>
                <FitScorePanel data={score} loading={scoreLoading} />
                <ObservationSummary cell={cell} loading={cellLoading} />
                {cell?.support_notice && <p className="nodaji-drawer-note">{cell.support_notice}</p>}
              </>
            )}
          </div>
        </aside>
      )}

      {mapData && (
        <div className="nodaji-map-ticker">
          <span>공개 통계</span>
          <b>{mapData.industry_name}</b>
          <em>{mapData.measured_count}곳 판단 가능</em>
        </div>
      )}

      <div className="nodaji-map-buttons" aria-label="지도 조작">
        <button type="button" onClick={resetMap} aria-label="화성시 전체 보기">
          <span className="material-symbols-outlined">my_location</span>
        </button>
        <div />
        <button type="button" onClick={() => mapInstanceRef.current?.setZoom(mapInstanceRef.current.getZoom() + 1, true)} aria-label="확대">+</button>
        <button type="button" onClick={() => mapInstanceRef.current?.setZoom(mapInstanceRef.current.getZoom() - 1, true)} aria-label="축소">−</button>
      </div>

      {mapData && (
        <div className="nodaji-map-source">
          {mapData.quarter_label} · 소상공인시장진흥공단 상가(상권)정보 · 읍면동 x 업종 집계
        </div>
      )}

      {tooltip && (
        <div className="nodaji-map-tooltip" style={{ left: tooltip.x + 12, top: tooltip.y - 34 }}>
          <b>{tooltip.name}</b>
          {tooltip.info && !tooltip.info.sample_insufficient && <span>누적 폐업률 {fmt(tooltip.info.closure_rate_pct)}%</span>}
          {tooltip.info?.sample_insufficient && <span>판단보류 · 점포 {tooltip.info.store_count}곳</span>}
          {!tooltip.info && <span>이 업종 데이터 없음</span>}
        </div>
      )}
    </div>
  );
}
