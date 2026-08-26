import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";
import { NAVER_CLIENT_ID, loadNaverMap, featureName, featurePaths, fitBoundsTight } from "../lib/naverMap";

// 상권 둘러보기 — 로그인 없이 열리는 공개 화면.
//
// 노다지(서울 프로젝트)가 예비 창업자의 입지·업종 판단을 도왔고 이 프로젝트는 공무원의 정책
// 판단을 돕는다. 분석 단위가 (행정동 x 업종)으로 같아서 같은 셀을 두 방향에서 읽는 것뿐이다.
//
// 화면 구조도 노다지 메인을 따른다 — 업종 하나를 고르면 화성시 전체가 지도와 순위표로 한 번에
// 선다. 다만 노다지가 "AI 점수가 높은 지역"을 추천했던 자리에 이 화면은 "실제로 자주 닫힌
// 지역"을 놓는다. 방향을 뒤집지 않은 이유는 아래 화면 원칙과 같다.
//
// 화면 원칙 (서버가 애초에 안 내려주지만 프론트에서도 지킨다)
//   - 위험등급·예측순위·성장확률·상권유형 이름을 쓰지 않는다
//   - "여기 여세요/열지 마세요"라고 쓰지 않는다. 점포 단위 예측 성능이 방어되지 않는다
//   - 표본부족 상권은 비율을 판단 재료로 쓰지 않고 점포 수만 말한다
//   - 분모가 다른 두 수를 슬래시로 묶지 않는다. 폐업률의 분모는 4개 분기 직전점포수의
//     합이고 점포 수는 현재 분기 값이라, 슬래시로 묶으면 눈으로 나눈 값이 4배쯤 어긋난다
//   - 문구·색 구간·범례는 서버에서 받는다. 평균·기준선을 프론트에 박으면 파이프라인 갱신
//     후 화면이 거짓말한다

const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

function Compare({ label, value, mine }) {
  if (typeof value !== "number") return null;
  const diff = typeof mine === "number" ? mine - value : null;
  return (
    <div style={{ flex: "1 1 150px" }}>
      <div className="t-caption" style={{ color: "var(--ink-faint)" }}>{label}</div>
      <div style={{ marginTop: 4, fontVariantNumeric: "tabular-nums" }}>
        <span className="t-body">{fmt(value)}%</span>
        {diff !== null && (
          <span className="t-caption" style={{ color: "var(--ink-muted)", marginLeft: 6 }}>
            (이 상권이 {fmt(Math.abs(diff))}%p {diff >= 0 ? "높음" : "낮음"})
          </span>
        )}
      </div>
    </div>
  );
}

// 누적 폐업률 추이. 점 두 개로는 추세가 아니라 선분이라 3개부터 그린다.
// 세로축을 0에서 시작하지 않고 관측 구간에 맞춘다 — 대신 양 끝 값을 숫자로 함께 적어
// 기울기만 보고 크기를 오해하지 않게 한다.
function Sparkline({ points }) {
  if (!points || points.length < 3) return null;
  const w = 248, h = 56, pad = 6;
  const values = points.map((p) => p.closure_rate_pct);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const xy = points.map((p, i) => [
    pad + (i / (points.length - 1)) * (w - pad * 2),
    h - pad - ((p.closure_rate_pct - min) / span) * (h - pad * 2),
  ]);
  const path = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  return (
    <div style={{ marginTop: 20, paddingTop: 18, borderTop: "1px solid var(--hairline)" }}>
      <div className="t-caption" style={{ color: "var(--ink-faint)" }}>최근 누적 폐업률 추이</div>
      <svg width={w} height={h} style={{ display: "block", marginTop: 8, maxWidth: "100%" }} aria-hidden="true">
        <path d={path} fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={xy[xy.length - 1][0]} cy={xy[xy.length - 1][1]} r="3.5" fill="var(--primary)" />
      </svg>
      <div className="t-caption" style={{ color: "var(--ink-muted)", display: "flex", justifyContent: "space-between", fontVariantNumeric: "tabular-nums" }}>
        <span>{first.quarter_label} {fmt(first.closure_rate_pct)}%</span>
        <span>{last.quarter_label} {fmt(last.closure_rate_pct)}%</span>
      </div>
    </div>
  );
}

function CellDetail({ cell }) {
  const short = cell.sample_insufficient;
  return (
    <>
      <div className="t-title">{cell.area_name} · {cell.industry_name}</div>

      {short ? (
        // 점포 4곳짜리 셀이 실제로 있다. 폐업 0건이 "0.0%"로 찍히면 안전해 보이지만
        // 판단 자체가 불가능한 표본이다. 비율을 아예 크게 보여주지 않는다.
        <>
          <p className="t-body" style={{ margin: "16px 0 0", color: "var(--on-surface)", lineHeight: 1.7 }}>
            이 상권은 점포가 <b>{cell.store_count}곳</b>뿐이라 비율로 판단하기 어렵습니다.
            한두 곳만 문을 닫아도 수치가 크게 흔들리기 때문입니다.
          </p>
          <p className="t-body-sm" style={{ margin: "10px 0 0", color: "var(--ink-muted)", lineHeight: 1.7 }}>
            최근 {cell.window_quarters}분기 동안 문을 닫은 곳은 {cell.closure_count ?? 0}곳입니다.
            수치보다 직접 다녀보시는 편이 낫습니다.
          </p>
        </>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 18, flexWrap: "wrap" }}>
            <span className="t-metric" style={{ fontSize: 40 }}>{fmt(cell.closure_rate_pct, 1)}</span>
            <span className="t-body" style={{ color: "var(--ink-muted)" }}>%</span>
            <span className="t-body-sm" style={{ color: "var(--ink-muted)", marginLeft: 6 }}>
              최근 1년 누적 폐업률 · 같은 기간 {cell.closure_count}곳 폐업 · 현재 점포 {cell.store_count}곳
            </span>
          </div>

          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 20, paddingTop: 18, borderTop: "1px solid var(--hairline)" }}>
            <Compare label="화성시 평균" value={cell.comparison?.city_avg_pct} mine={cell.closure_rate_pct} />
            <Compare label={`${cell.industry_name} 전체 평균`} value={cell.comparison?.industry_avg_pct} mine={cell.closure_rate_pct} />
            <Compare label={`${cell.area_name} 전체 평균`} value={cell.comparison?.area_avg_pct} mine={cell.closure_rate_pct} />
          </div>

          <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 18, paddingTop: 18, borderTop: "1px solid var(--hairline)" }}>
            <div>
              <div className="t-caption" style={{ color: "var(--ink-faint)" }}>새로 문을 연 비율</div>
              <div className="t-body" style={{ marginTop: 4, fontVariantNumeric: "tabular-nums" }}>
                {fmt(cell.opening_rate_pct, 1)}%
              </div>
            </div>
            {cell.observed_rank && (
              <div>
                <div className="t-caption" style={{ color: "var(--ink-faint)" }}>
                  {cell.industry_name} 업종 안에서
                </div>
                <div className="t-body" style={{ marginTop: 4 }}>
                  {cell.observed_total}개 지역 중 <b>{cell.observed_rank}번째</b>로 자주 닫힘
                </div>
              </div>
            )}
          </div>

          <Sparkline points={cell.trend} />
        </>
      )}

      {(cell.pattern_summary || cell.founder_note) && (
        <div style={{ marginTop: 20, paddingTop: 18, borderTop: "1px solid var(--hairline)" }}>
          {cell.pattern_summary && (
            <p className="t-body" style={{ margin: 0, color: "var(--on-surface)", lineHeight: 1.7 }}>
              {cell.pattern_summary}
            </p>
          )}
          {cell.founder_note && (
            <p className="t-body-sm" style={{ margin: "8px 0 0", color: "var(--ink-secondary)", lineHeight: 1.7 }}>
              {cell.founder_note}
            </p>
          )}
        </div>
      )}
    </>
  );
}

export default function BrowsePage() {
  const [options, setOptions] = useState(null);
  const [measuredByIndustry, setMeasuredByIndustry] = useState({});
  const [industryId, setIndustryId] = useState(null);
  const [mapData, setMapData] = useState(null);
  const [areaId, setAreaId] = useState(null);
  const [cell, setCell] = useState(null);
  const [cellLoading, setCellLoading] = useState(false);
  const [error, setError] = useState("");
  const [mapError, setMapError] = useState("");
  const [tooltip, setTooltip] = useState(null);

  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const polygonsRef = useRef([]);
  const boundsFitRef = useRef(false);

  useEffect(() => {
    apiFetchJson("/api/public/areas")
      .then((d) => {
        setOptions(d);
        // 첫 업종을 이름순 첫 글자로 고르면 표본부족 업종이 걸려 지도가 통째로 회색이 된다.
        // 표본이 충분한 읍면동이 가장 많은 업종으로 연다.
        const counts = new Map();
        (d.areas ?? []).forEach((a) =>
          a.industries.forEach((i) => {
            if (!i.sample_insufficient) counts.set(i.id, (counts.get(i.id) ?? 0) + 1);
          }),
        );
        setMeasuredByIndustry(Object.fromEntries(counts));
        const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
        setIndustryId(best ? best[0] : d.industries?.[0]?.id ?? null);
      })
      .catch((err) => setError(describeApiError(err)));
  }, []);

  useEffect(() => {
    if (!industryId) return;
    setError("");
    apiFetchJson(`/api/public/industry-map?industry_id=${industryId}`)
      .then((d) => {
        setMapData(d);
        // 업종을 바꾸면 읍면동 선택을 유지하되, 그 동에 이 업종 표본이 없으면 판단 가능한
        // 곳 중 점포가 가장 많은 동으로 옮긴다. 회색 칸을 열어두면 첫 화면이 비어 보인다.
        setAreaId((prev) => {
          const kept = d.areas.find((a) => a.area_id === prev && !a.sample_insufficient);
          if (kept) return prev;
          const pick = [...d.areas]
            .filter((a) => !a.sample_insufficient)
            .sort((a, b) => b.store_count - a.store_count)[0];
          return pick ? pick.area_id : d.areas[0]?.area_id ?? null;
        });
      })
      .catch((err) => { setMapData(null); setError(describeApiError(err)); });
  }, [industryId]);

  useEffect(() => {
    if (!areaId || !industryId) return;
    setCellLoading(true);
    apiFetchJson(`/api/public/cell?area_id=${areaId}&industry_id=${industryId}`)
      .then(setCell)
      .catch((err) => { setCell(null); setError(describeApiError(err)); })
      .finally(() => setCellLoading(false));
  }, [areaId, industryId]);

  const colorByName = useMemo(
    () => Object.fromEntries((mapData?.areas ?? []).map((a) => [a.area_name, a])),
    [mapData],
  );

  const drawPolygons = useCallback((map, geojson) => {
    polygonsRef.current.forEach((p) => p.setMap(null));
    polygonsRef.current = [];

    geojson.features.forEach((feat) => {
      const name = featureName(feat);
      const info = colorByName[name];
      const color = info?.color || "#c1c6d5";

      featurePaths(feat).forEach((path) => {
        const polygon = new window.naver.maps.Polygon({
          map, paths: [path], fillColor: color, fillOpacity: 0.78,
          strokeColor: "#fff", strokeWeight: 1.5, clickable: true,
        });
        window.naver.maps.Event.addListener(polygon, "mouseover", (e) => {
          polygon.setOptions({ fillOpacity: 0.95 });
          setTooltip({ name, info, x: e.pointerEvent.clientX, y: e.pointerEvent.clientY });
        });
        window.naver.maps.Event.addListener(polygon, "mousemove", (e) => {
          setTooltip((t) => (t ? { ...t, x: e.pointerEvent.clientX, y: e.pointerEvent.clientY } : null));
        });
        window.naver.maps.Event.addListener(polygon, "mouseout", () => {
          polygon.setOptions({ fillOpacity: 0.78 });
          setTooltip(null);
        });
        window.naver.maps.Event.addListener(polygon, "click", () => {
          if (info) setAreaId(info.area_id);
        });
        polygonsRef.current.push(polygon);
      });
    });
  }, [colorByName]);

  useEffect(() => {
    if (!NAVER_CLIENT_ID || !mapData) return;
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
          drawPolygons(mapInstanceRef.current, geojson);
          if (!boundsFitRef.current) {
            const bounds = new window.naver.maps.LatLngBounds();
            geojson.features.forEach((feat) =>
              featurePaths(feat).forEach((path) => path.forEach((ll) => bounds.extend(ll))),
            );
            fitBoundsTight(mapInstanceRef.current, bounds);
            boundsFitRef.current = true;
          }
        })
        .catch(() => setMapError(
          "지도 경계 파일(hwaseong_emd.geojson)을 불러오지 못했습니다. " +
          "아래 순위표로도 같은 내용을 보실 수 있습니다.",
        ));
    }).catch((err) => setMapError(err.message));
  }, [mapData, drawPolygons]);

  // 순위표는 잦은 순. 판단보류 읍면동은 지우지 않고 아래에 모아 둔다 — 지우면
  // "왜 우리 동네는 없냐"가 되고, 사각지대 트랙과 같은 원칙이다.
  const ranked = useMemo(() => {
    const rows = mapData?.areas ?? [];
    const measured = rows.filter((a) => !a.sample_insufficient).sort((a, b) => a.rank - b.rank);
    const held = rows.filter((a) => a.sample_insufficient).sort((a, b) => b.store_count - a.store_count);
    return { measured, held };
  }, [mapData]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "48px 24px 64px" }}>
        <h1 className="t-h1" style={{ margin: 0 }}>상권 둘러보기</h1>
        <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "8px 0 0", lineHeight: 1.7 }}>
          업종을 고르면 화성시 읍면동에서 최근 실제로 일어난 일을 한 번에 보여드립니다.
          <br />
          공공데이터로 계산한 상권 단위 통계이며, 특정 가게의 성패를 예측하지 않습니다.
        </p>

        <div className="card" style={{ padding: 18, margin: "24px 0", display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
          <select
            value={industryId ?? ""}
            onChange={(e) => setIndustryId(Number(e.target.value))}
            style={{ flex: "1 1 240px", minWidth: 0 }}
          >
            {(options?.industries ?? []).map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
                {measuredByIndustry[i.id]
                  ? ` · 판단 가능 ${measuredByIndustry[i.id]}곳`
                  : " · 전 읍면동 판단보류"}
              </option>
            ))}
          </select>
          {mapData && (
            <div className="t-caption" style={{ color: "var(--ink-muted)", lineHeight: 1.7 }}>
              읍면동 {mapData.total_count}곳 중 <b style={{ color: "var(--on-surface)" }}>{mapData.measured_count}곳</b>이 비율로 판단 가능
              {typeof mapData.industry_avg_pct === "number" && (
                <> · 이 업종 화성시 평균 <b style={{ color: "var(--on-surface)" }}>{fmt(mapData.industry_avg_pct)}%</b></>
              )}
            </div>
          )}
        </div>

        {/* 오류는 --error. --accent-orange는 "주의" 등급 색이라 의미가 겹친다. */}
        {error && <div className="t-body-sm" style={{ color: "var(--error)", marginBottom: 16 }}>{error}</div>}

        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
          <div style={{ position: "relative", flex: "1 1 520px", minWidth: 320 }}>
            {mapError && (
              <div
                role="alert"
                style={{
                  position: "absolute", top: 16, left: 16, right: 16, zIndex: 20,
                  background: "rgba(255,255,255,0.96)", border: "1px solid var(--error)",
                  borderRadius: "var(--radius-lg)", padding: "12px 14px", boxShadow: "var(--elev-1)",
                }}
              >
                <span className="t-body-sm" style={{ color: "var(--on-surface)" }}>{mapError}</span>
              </div>
            )}
            <div
              ref={mapRef}
              /* 화성시 경계가 가로 56km x 세로 33km(1.7:1)라 거의 정사각형 칸에 맞추면
               위아래로 남의 동네가 들어온다. 공무원 지도와 같은 비율을 쓴다. */
            style={{
              aspectRatio: "1.7 / 1",
              minHeight: 360,
              maxHeight: 620,
              borderRadius: "var(--radius-lg)",
              overflow: "hidden",
              border: "1px solid var(--hairline)",
              background: "var(--surface-container-low)",
            }}
            >
              {!NAVER_CLIENT_ID && (
                <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--ink-faint)", flexDirection: "column", gap: 8, textAlign: "center", padding: 24 }}>
                  <span className="t-body-sm">지도를 표시할 수 없습니다.</span>
                  <span className="t-caption">아래 순위표로 같은 내용을 보실 수 있습니다.</span>
                </div>
              )}
            </div>

            {mapData?.legend?.length > 0 && NAVER_CLIENT_ID && (
              <div
                style={{
                  position: "absolute", bottom: 16, left: 16, maxWidth: 260,
                  background: "rgba(255,255,255,0.94)", backdropFilter: "blur(6px)",
                  border: "1px solid var(--hairline)", borderRadius: "var(--radius-lg)",
                  padding: 14, zIndex: 10, boxShadow: "var(--elev-1)",
                }}
              >
                <p className="t-eyebrow" style={{ color: "var(--ink-muted)", margin: "0 0 10px", textTransform: "uppercase" }}>
                  최근 1년 누적 폐업률
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                  {mapData.legend.map(({ label, color }) => (
                    <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ width: 10, height: 10, borderRadius: "var(--radius-full)", background: color, display: "inline-block", flexShrink: 0 }} />
                      <span className="t-caption" style={{ color: "var(--ink-secondary)" }}>{label}</span>
                    </div>
                  ))}
                </div>
                <p className="t-caption" style={{ color: "var(--ink-faint)", margin: "10px 0 0", lineHeight: 1.6 }}>
                  구간은 이 업종 안에서의 상대적 위치입니다. 색이 진하다고 나쁜 상권이라는 뜻은 아닙니다.
                </p>
              </div>
            )}
          </div>

          <div className="card" style={{ flex: "1 1 340px", minWidth: 300, padding: 24 }}>
            {cellLoading && <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>}
            {!cellLoading && cell && <CellDetail cell={cell} />}
            {!cellLoading && !cell && (
              <div className="t-body-sm" style={{ color: "var(--ink-muted)", lineHeight: 1.7 }}>
                지도에서 읍면동을 클릭하거나 아래 표에서 골라 주세요.
              </div>
            )}
            {cell && (
              <div
                className="t-caption"
                style={{
                  color: "var(--ink-secondary)", background: "var(--surface-container-low)",
                  padding: "12px 16px", borderRadius: "var(--radius-md)", marginTop: 20, lineHeight: 1.7,
                }}
              >
                {cell.support_notice}
              </div>
            )}
          </div>
        </div>

        <div className="card" style={{ marginTop: 16, padding: 24 }}>
          <h2 className="t-h3" style={{ margin: 0 }}>
            {mapData?.industry_name ?? "업종"} · 읍면동별 최근 1년 누적 폐업률
          </h2>
          <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "6px 0 16px", lineHeight: 1.7 }}>
            자주 닫힌 순입니다. 순수 관측치이며 보정·예측이 들어가지 않습니다.
            단일 분기는 폐업 한두 건 차이로 값이 크게 튀어 4분기를 누적해 봅니다.
          </p>
          <div style={{ overflowX: "auto" }}>
            <table style={{ minWidth: 520, width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ fontWeight: 600 }}>순위</th>
                  <th style={{ fontWeight: 600 }}>읍면동</th>
                  <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>누적 폐업률</th>
                  <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>폐업</th>
                  <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>현재 점포</th>
                </tr>
              </thead>
              <tbody>
                {ranked.measured.map((a) => (
                  <tr
                    key={a.area_id}
                    onClick={() => setAreaId(a.area_id)}
                    style={{ cursor: "pointer", background: a.area_id === areaId ? "var(--surface-container-low)" : "transparent" }}
                  >
                    <td style={{ padding: "8px 4px", color: "var(--outline)" }}>{a.rank}</td>
                    <td style={{ padding: "8px 4px", fontWeight: 600 }}>
                      <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "var(--radius-full)", background: a.color, marginRight: 8 }} />
                      {a.area_name}
                    </td>
                    <td className="t-metric" style={{ textAlign: "right" }}>{fmt(a.closure_rate_pct)}%</td>
                    <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-muted)" }}>{a.closure_count ?? "—"}곳</td>
                    <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-muted)" }}>{a.store_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {ranked.measured.length === 0 && (
            <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "16px 0 0", lineHeight: 1.7 }}>
              이 업종은 화성시 어느 읍면동에서도 점포가 50곳을 넘지 않아 비율로 판단하지 않습니다.
              아래에서 읍면동을 고르면 문을 닫은 곳의 수만 보여드립니다.
            </p>
          )}

          {ranked.held.length > 0 && (
            <div style={{ marginTop: 20, paddingTop: 18, borderTop: "1px solid var(--hairline)" }}>
              <div className="t-caption" style={{ color: "var(--ink-faint)", marginBottom: 8 }}>
                점포가 적어 비율로 판단하지 않는 읍면동 {ranked.held.length}곳 — 클릭하면 폐업 건수만 보여드립니다
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {ranked.held.map((a) => (
                  <button
                    key={a.area_id}
                    onClick={() => setAreaId(a.area_id)}
                    className="t-caption"
                    style={{
                      border: "1px solid var(--hairline)", background: a.area_id === areaId ? "var(--surface-container)" : "var(--surface-container-lowest)",
                      color: "var(--ink-secondary)", borderRadius: "var(--radius-full)",
                      padding: "5px 12px", cursor: "pointer",
                    }}
                  >
                    {a.area_name} · 점포 {a.store_count}곳
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {mapData && (
          <p className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 14, lineHeight: 1.7 }}>
            {mapData.scope_notice}
            <br />
            {mapData.provisional_notice}
            <br />
            기준 {mapData.quarter_label} · 출처 소상공인시장진흥공단 상가(상권)정보
          </p>
        )}

        <div style={{ borderTop: "1px solid var(--hairline)", marginTop: 32, paddingTop: 20 }}>
          <Link to="/" className="t-caption" style={{ color: "var(--ink-muted)", textDecoration: "none" }}>
            화성시 담당자 로그인
          </Link>
        </div>
      </div>

      {tooltip && (
        <div
          style={{
            position: "fixed", left: tooltip.x + 12, top: tooltip.y - 32, pointerEvents: "none",
            background: "var(--on-surface)", color: "#fff", fontSize: 12,
            padding: "7px 11px", borderRadius: "var(--radius-md)", boxShadow: "var(--elev-2)", zIndex: 9999,
          }}
        >
          <b>{tooltip.name}</b>
          {tooltip.info && !tooltip.info.sample_insufficient && (
            <span style={{ marginLeft: 8 }}>누적 폐업률 {fmt(tooltip.info.closure_rate_pct)}%</span>
          )}
          {tooltip.info?.sample_insufficient && (
            <span style={{ marginLeft: 8, color: "var(--ink-faint)" }}>판단보류 · 점포 {tooltip.info.store_count}곳</span>
          )}
          {!tooltip.info && <span style={{ marginLeft: 8, color: "var(--ink-faint)" }}>이 업종 데이터 없음</span>}
        </div>
      )}
    </div>
  );
}
