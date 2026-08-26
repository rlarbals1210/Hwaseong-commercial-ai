import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";
import { GradeBadge } from "../components/Badge";
import TabStrip from "../components/TabStrip";
import { NAVER_CLIENT_ID, loadNaverMap, fitBoundsTight } from "../lib/naverMap";
import useCategories from "../hooks/useCategories";

// 다른 화면과 같은 정의. 이 파일에만 사본이 없어 백엔드 raw 값(2자리)이 그대로 찍혔다 —
// 같은 상권이 대시보드에서 7.1%, 여기서 7.14%로 보였다.
const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

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
const OPACITY_NOTE = "흐리게 칠해진 읍면동은 표본이 충분한 업종이 10개 미만이라 등급의 근거가 얕습니다.";

// 이 화면에만 있던 loadErrorMessage를 lib/api.js의 describeApiError로 옮겼다.
// 다른 6개 화면이 같은 처리를 못 갖고 있어서, 토큰이 만료되면 그 화면들은
// "불러오지 못했습니다"만 반복하고 재로그인하라는 안내가 없었다.

function RankingTable({ rows, loading, error, category, categories, categoryError, onCategoryChange }) {
  // 한 업종으로 좁히면 표시 순위와 업종 내 순위가 같은 키로 정렬돼 숫자가 똑같아진다.
  // 같은 값 두 열을 나란히 두는 대신 열을 접고, 모집단 크기는 아래 설명으로 옮긴다.
  const filtered = Boolean(category);
  const industryTotal = filtered ? rows.find((r) => r.industry_total)?.industry_total : null;

  return (
    <div className="card">
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap" }}>
        <h3 className="t-h3" style={{ margin: 0 }}>상권 순위표 — 최근 1년 누적 폐업률</h3>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <label className="t-caption" style={{ color: "var(--ink-secondary)", fontWeight: 600 }}>업종</label>
          <select value={category} onChange={(e) => onCategoryChange(e.target.value)} style={{ minWidth: 180 }}>
            <option value="">전체 업종</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
      </div>
      <p style={{ margin: "6px 0 16px", fontSize: 12, color: "var(--outline)" }}>
        순수 관측치 정렬, 보정·예측 없음(표본 50개 이상 업종만 집계).
        단일 분기는 폐업 1~2건 차이로 값이 크게 튀어 4분기 누적으로 봅니다.
        {/* 위 지도는 동x분기 집계라 업종 축이 없다. 필터가 지도까지 걸린 것으로 읽히면 안 된다. */}
        {" "}<b style={{ color: "var(--ink-secondary)" }}>업종 선택은 이 표에만 적용되며, 위 지도는 전체 업종 기준입니다.</b>
        {categoryError && (
          <span style={{ color: "var(--error)" }}> 업종 목록을 불러오지 못했습니다.</span>
        )}
        {filtered && industryTotal && (
          <> {category} · 분석 가능 {industryTotal}곳 중 상위 {rows.length}</>
        )}
      </p>
      {loading ? (
        <div className="t-body-sm" style={{ padding: 24, textAlign: "center", color: "var(--ink-faint)" }}>불러오는 중...</div>
      ) : error ? (
        <div className="t-body-sm" style={{ padding: 24, textAlign: "center", color: "var(--error)" }}>{error}</div>
      ) : rows.length === 0 ? (
        /* 0으로 채우면 "판단 불가"가 "가장 안전"으로 읽힌다. 없는 이유를 적는다. */
        <div className="t-body-sm" style={{ padding: 24, textAlign: "center", color: "var(--ink-faint)", lineHeight: 1.7 }}>
          {filtered
            ? `${category}은(는) 최근 1년 누적값이 아직 산출되지 않았습니다. 4분기가 쌓여야 값이 나옵니다.`
            : "데이터 없음"}
        </div>
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
              {!filtered && <th style={{ padding: "8px 4px", fontWeight: 600, textAlign: "right" }}>업종 내</th>}
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
                {!filtered && (
                  <td className="t-metric" style={{ textAlign: "right", fontWeight: 400, color: "var(--ink-faint)" }}>
                    {r.industry_rank ? `${r.industry_rank}/${r.industry_total}` : "—"}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}

/** 읍면동 상세 패널.
 *
 *  예전 패널은 "위험 업종 비율 0.0%"와 표본 충족률만 말하고 끝났다. 담당자의 다음 질문은
 *  반드시 "그래서 어느 업종인가"인데 화면에서 동선이 끊겼다.
 *
 *  세 가지를 한 화면에서 답한다 —
 *    ① 어느 업종이 나쁜가   업종 목록(표본충분, 폐업률 순)
 *    ② 동 전체로는 어떤가   업종 구분 없이 묶은 폐업률 + 나머지 지역과의 비교
 *    ③ 무엇이 안 보이는가   사각지대 규모
 *  배후인구는 등급·유형 판정에 관여하지 않는다. 원인의 방향을 좁히는 참고 자료다.
 */
function Row({ label, children, hint }) {
  return (
    <div style={{ padding: "11px 0", borderTop: "1px solid var(--hairline)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="t-caption" style={{ color: "var(--ink-muted)" }}>{label}</span>
        <span className="t-body-sm" style={{ marginLeft: "auto", color: "var(--on-surface)", fontWeight: 600, fontVariantNumeric: "tabular-nums", textAlign: "right" }}>
          {children}
        </span>
      </div>
      {hint && <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 3 }}>{hint}</div>}
    </div>
  );
}

function AreaPanel({ selected, detail, loading, onClose }) {
  if (!selected) return null;
  const judged = selected.risk_ratio != null;
  const industries = detail?.industries ?? [];
  const VS = {
    높음: { label: "시 평균보다 높음", cls: "badge badge-warn" },
    낮음: { label: "시 평균보다 낮음", cls: "badge badge-ok" },
    차이없음: { label: "유의차 없음", cls: "badge badge-neutral" },
  }[detail?.vs_city ?? "차이없음"];

  return (
    <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h3 className="t-h3" style={{ margin: 0 }}>{selected.name}</h3>
          <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 2 }}>
            {detail ? `${detail.quarter_label} 기준 · 점포 ${detail.total_stores.toLocaleString()}곳` : " "}
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="닫기"
          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--outline)", fontSize: 20, lineHeight: 1, padding: 0 }}
        >
          ×
        </button>
      </div>

      {/* 등급 요약 */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, margin: "16px 0 4px", flexWrap: "wrap" }}>
        {judged ? (
          <>
            <span className="t-metric" style={{ fontSize: 38, color: selected.color, lineHeight: 1 }}>
              {fmt(selected.risk_ratio)}%
            </span>
            <span
              style={{
                fontSize: 12, fontWeight: 700, color: selected.color,
                background: `color-mix(in srgb, ${selected.color} 12%, white)`,
                padding: "4px 12px", borderRadius: "var(--radius-full)",
              }}
            >
              {selected.risk_level}
            </span>
            {/* 근거의 두께는 칩 하나로만 말한다. 자세한 내용은 title과 아래
                "분석 가능 업종" 줄, 지도 범례에 이미 있다. */}
            {selected.evidence_thin && (
              <span className="badge badge-neutral" title={selected.hold_notice ?? undefined}>
                근거 얕음
              </span>
            )}
          </>
        ) : (
          <GradeBadge grade="판단보류" />
        )}
      </div>
      <div className="t-caption" style={{ color: "var(--ink-muted)", marginBottom: 12 }}>
        {judged ? "위험 업종 비율 (최근 1년 누적)" : "읍면동 등급을 판정할 표본이 부족합니다"}
      </div>

      {loading && <div className="t-caption" style={{ color: "var(--ink-muted)", padding: "10px 0" }}>상세 불러오는 중…</div>}

      {detail && (
        <>
          {/* 업종별로는 표본이 모자란 동도 동 전체를 묶으면 분모가 수천이 되어 판정할 수 있다.
              이 줄이 "커버율 0% = 아무것도 모른다"를 막는다. */}
          <Row
            label="동 전체 폐업률"
            hint={
              detail.city_pooled_closure_rate_pct != null
                ? `업종 구분 없이 묶은 값 · 화성시 ${fmt(detail.city_pooled_closure_rate_pct, 2)}%`
                : "업종 구분 없이 묶은 값"
            }
          >
            {fmt(detail.pooled_closure_rate_pct, 2)}%{" "}
            <span className={VS.cls} style={{ marginLeft: 4, fontWeight: 600 }}>{VS.label}</span>
          </Row>

          <Row label="위험 · 주의 업종" hint={`표본 기준을 넘은 ${detail.sample_sufficient_cells}개 업종 중`}>
            {detail.risk_cells} · {detail.caution_cells}개
          </Row>

          <Row label="폐업률 추이 기울기">{selected.trend?.toFixed(3)}</Row>

          <Row
            label="분석 가능 업종"
            hint={
              selected.evidence_thin
                ? `표본 충족률 ${detail.coverage_pct}% · 업종 10개 미만이라 읍면동 등급의 근거가 얕습니다`
                : `표본 충족률 ${detail.coverage_pct}% · 점포 50곳 이상 기준`
            }
          >
            {detail.sample_sufficient_cells}/{detail.total_cells}개
          </Row>

          <Row
            label="사각지대"
            hint={`점포 ${detail.blindspot_stores.toLocaleString()}곳 · 전체의 ${
              detail.total_stores ? Math.round(detail.blindspot_stores / detail.total_stores * 100) : 0
            }%`}
          >
            {detail.blindspot_cells}개 업종
          </Row>

          {detail.population != null && (
            <Row
              label="배후인구"
              hint={
                detail.population_change_pct != null
                  ? `${detail.population_from_label} → ${detail.population_to_label} ${detail.population_change_pct > 0 ? "+" : ""}${detail.population_change_pct}%`
                  : null
              }
            >
              {detail.population.toLocaleString()}명
            </Row>
          )}

          {/* "그래서 어느 업종인가" — 이 목록이 이 패널의 존재 이유다 */}
          {industries.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="t-eyebrow" style={{ color: "var(--ink-faint)", marginBottom: 8 }}>
                업종별 폐업률 (표본 기준 충족 {industries.length}개)
              </div>
              <div style={{ maxHeight: 260, overflowY: "auto", margin: "0 -6px" }}>
                {industries.map((item) => (
                  <Link
                    key={item.industry_id}
                    to={`/cells/${item.area_id}/${item.industry_id}`}
                    style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "7px 6px", borderRadius: "var(--radius-sm)",
                      textDecoration: "none", color: "inherit",
                    }}
                  >
                    <span className="t-caption" style={{ color: "var(--on-surface)", flex: "1 1 auto", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {item.category}
                    </span>
                    <span className="t-caption" style={{ color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
                      {fmt(item.cumulative_closure_rate_pct, 1)}%
                    </span>
                    <GradeBadge grade={item.risk_grade} />
                  </Link>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <Link
              to="/dashboard"
              className="btn-utility"
              style={{ flex: 1, textAlign: "center", color: "var(--primary)", textDecoration: "none", boxSizing: "border-box" }}
            >
              조기경보
            </Link>
            <Link
              to={`/blindspots?dong=${encodeURIComponent(selected.name)}`}
              className="btn-utility"
              style={{ flex: 1, textAlign: "center", color: "var(--primary)", textDecoration: "none", boxSizing: "border-box" }}
            >
              사각지대
            </Link>
          </div>
        </>
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
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [tooltip, setTooltip] = useState(null);
  const [ranking, setRanking] = useState([]);
  const [rankingLoading, setRankingLoading] = useState(true);
  const [category, setCategory] = useState("");
  const [tab, setTab] = useState("map");
  // 순위표와 같은 집합(최신 분기·표본충분)을 좁히는 purpose를 쓴다.
  const { categories, error: categoryError } = useCategories("policy");
  const [mapError, setMapError] = useState("");
  const [rankingError, setRankingError] = useState("");

  useEffect(() => {
    // apiFetchJson을 쓴다. 예전처럼 raw fetch로 상태를 직접 처리하면 401이 와도
    // 앱이 로그아웃 상태로 넘어가지 않아, 화면만 오류 문구를 띄운 채 머문다.
    apiFetchJson(`/api/alerts/vacancy-risk/map`)
      .then((d) => {
        // 오류 본문은 배열이 아니라 {detail: ...}라 그대로 넣으면 map()에서 터진다
        setRiskData(Array.isArray(d) ? d : []);
        setMapError("");
      })
      .catch((err) => {
        setRiskData([]);
        setMapError(describeApiError(err));
      });
  }, []);

  // 순위표만 업종 필터에 반응한다. 지도 fetch와 한 effect에 두면 업종을 바꿀 때마다
  // riskData가 새 배열이 되어 폴리곤 29개가 통째로 다시 그려진다.
  useEffect(() => {
    const params = new URLSearchParams({ limit: 10 });
    if (category) params.set("category", category);
    apiFetchJson(`/api/alerts/closure-rate-ranking?${params}`)
      .then((d) => {
        setRanking(Array.isArray(d) ? d : []);
        setRankingError("");
      })
      .catch((err) => {
        setRanking([]);
        setRankingError(describeApiError(err));
      })
      .finally(() => setRankingLoading(false));
  }, [category]);

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
      // 배경 지도 위에서 0.5는 색이 씻겨 보인다. 등급을 색으로 읽는 화면이라 진하기를 올린다.
      // 근거가 얕은 읍면동은 여전히 확실히 옅게 두되(0.22 -> 0.4), 진한 쪽과의 차이는 유지한다.
      const baseOpacity = thin ? 0.4 : 0.72;
      const hoverOpacity = thin ? 0.6 : 0.9;

      const coords = feat.geometry.type === "Polygon"
        ? [feat.geometry.coordinates]
        : feat.geometry.coordinates;

      coords.forEach((rings) => {
        const path = rings[0].map(([lng, lat]) => new window.naver.maps.LatLng(lat, lng));
        const polygon = new window.naver.maps.Polygon({
          map, paths: [path], fillColor: color, fillOpacity: baseOpacity,
          strokeColor: "#fff", strokeWeight: 1.5, clickable: true,
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

  // 읍면동을 고르면 상세를 따로 부른다. 지도 payload는 29개 동을 한 번에 내려주므로
  // 업종 목록까지 얹으면 첫 로딩이 무거워진다 — 고른 동만 그때 가져온다.
  useEffect(() => {
    const areaId = selected?.area_id;
    if (!areaId) { setDetail(null); return; }
    setDetailLoading(true);
    setDetail(null);
    apiFetchJson(`/api/alerts/area/${areaId}/detail`)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [selected?.area_id]);

  // 패널이 열리고 닫힐 때 지도 칸의 폭이 바뀐다. 네이버 지도는 컨테이너 크기 변화를
  // 스스로 알아채지 못해서 타일이 잘린 채 남는다. 레이아웃이 끝난 뒤 resize를 알린다.
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !window.naver?.maps) return;
    const timer = setTimeout(() => {
      window.naver.maps.Event.trigger(map, "resize");
    }, 60);
    return () => clearTimeout(timer);
  }, [selected]);

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
            // fitBounds는 정수 줌으로만 맞춰 한 단계 덜 당겨진다. lib/naverMap 참조.
            fitBoundsTight(mapInstanceRef.current, bounds);
            boundsFitRef.current = true;
          }
        })
        .catch(() => {
          // console.warn만 하면 타일은 뜨는데 폴리곤이 하나도 없는 상태가 되고,
          // 담당자는 "데이터가 없구나"로 읽는다. 원인을 화면에 남긴다.
          setMapError(
            "지도 경계 파일(hwaseong_emd.geojson)을 불러오지 못했습니다. " +
            "frontend/public에 파일이 있는지 확인해주세요."
          );
        });
    }).catch((err) => setMapError(err.message));
  }, [riskData, drawPolygons]);

  // 숨겨진 동안 컨테이너 크기가 0이라, 그 사이 창이 리사이즈되면 지도가 옛 크기를 들고 있다.
  // 돌아올 때 한 번 알려준다. 중심·줌은 건드리지 않는다 — 담당자가 옮겨둔 화면을 되돌리면 안 된다.
  useEffect(() => {
    if (tab !== "map" || !mapInstanceRef.current || !window.naver?.maps) return;
    window.naver.maps.Event.trigger(mapInstanceRef.current, "resize");
  }, [tab]);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-h1" style={{ margin: 0 }}>공실위험 지도</h1>
        <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0" }}>
          읍면동별 위험 업종 비율 — 최근 1년 누적 폐업률 기준(4분기 합산, 보정 없음). 읍면동을 클릭하면 상세 지표가 표시됩니다.
        </p>
      </div>

      {/* 순위표가 지도(620px) 아래라 첫 화면에서 잘렸다. 접기로는 시작 위치가 안 바뀌어
          탭으로 나눈다 — 둘 다 같은 높이에서 시작한다. 라벨에 건수를 붙여 표가 숨은 게
          아니라는 걸 보이게 한다(시연 중 순위표를 지나칠 수 있다). */}
      <div style={{ maxWidth: 320, marginBottom: 16 }}>
        <TabStrip
          tabs={[
            { key: "map", label: "지도" },
            { key: "ranking", label: `순위표${ranking.length ? ` (${ranking.length})` : ""}` },
          ]}
          value={tab}
          onChange={(next) => {
            setTooltip(null);
            setTab(next);
          }}
          ariaLabel="공실위험 보기 선택"
        />
      </div>

      {/* 지도를 옆 패널과 나눠 쓰면 폭이 851px에 묶이는데, 화성시 경계가 그 폭에서
          zoom 10으로만 맞는다(zoom 11은 920px가 필요). 정수 줌만 되는 지도라
          한 단계 차이가 곧 2배 차이여서 화성시가 화면의 절반만 차지했다.
          지도를 본문 전체 폭으로 빼면 zoom 11이 들어가고, 상세 패널은 아래로 내린다. */}
      <div style={{ display: tab === "map" ? "block" : "none" }}>
        <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 620px", minWidth: 0 }}>
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
            /* 화성시 경계는 가로 약 56km x 세로 약 33km(1.7:1)인데 지도 칸이 거의 정사각형이라
               fitBounds가 가로에 맞추느라 위아래로 남의 동네가 잔뜩 들어왔다. 칸 비율을
               데이터 비율에 맞추면 같은 폭에서 화성시가 훨씬 크게 보인다.
               좁은 화면에서 너무 납작해지지 않게 최소 높이를 둔다. */
            style={{
              aspectRatio: "1.7 / 1",
              minHeight: 360,
              maxHeight: 620,
              borderRadius: "var(--radius-lg)",
              overflow: "hidden",
              border: "1px solid var(--hairline)",
            }}
          >
            {!NAVER_CLIENT_ID && (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--outline)", flexDirection: "column", gap: 8 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 32 }}>map</span>
                <span style={{ fontSize: 14 }}>frontend/.env에 VITE_NAVER_MAP_CLIENT_ID를 설정하세요</span>
              </div>
            )}
          </div>

          {/* 범례를 지도 위에 띄우면 좌하단 읍면동을 가린다. 안내 문구가 길어 세로로 커지는
              구조라 더 그렇다. 지도 아래로 빼고 가로로 눕혔다 — 가리는 것도 없고
              좁은 화면에서 접히기만 한다. */}
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 16,
              flexWrap: "wrap",
              marginTop: 10,
              padding: "10px 14px",
              background: "var(--surface-container-low)",
              border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <span className="t-eyebrow" style={{ color: "var(--ink-muted)", textTransform: "uppercase", flexShrink: 0 }}>
              위험 업종 비율
            </span>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
              {LEGEND.map(({ label, color }) => (
                <span key={label} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 10, height: 10, borderRadius: "var(--radius-full)", background: color, display: "inline-block", flexShrink: 0 }} />
                  <span className="t-caption" style={{ color: "var(--ink-secondary)" }}>{label}</span>
                </span>
              ))}
            </div>
            <span className="t-caption" style={{ color: "var(--ink-faint)", lineHeight: 1.6, flex: "1 1 260px", minWidth: 0 }}>
              {OPACITY_NOTE}
            </span>
          </div>
        </div>

        {/* 아무것도 안 고른 상태에서는 패널을 그리지 않는다. 지도가 본문 전체 폭을 쓰고,
            "읍면동을 클릭하면 상세 지표가 표시됩니다" 안내는 화면 설명에 이미 있다. */}
        {selected && (
          <div style={{ flex: "0 0 340px", maxWidth: "100%", position: "sticky", top: 16 }}>
            <AreaPanel
              selected={selected}
              detail={detail}
              loading={detailLoading}
              onClose={() => setSelected(null)}
            />
          </div>
        )}
        </div>
      </div>

      <div style={{ display: tab === "ranking" ? "block" : "none" }}>
        <RankingTable
          rows={ranking}
          loading={rankingLoading}
          error={rankingError}
          category={category}
          categories={categories}
          categoryError={categoryError}
          onCategoryChange={(next) => {
            setRankingLoading(true);
            setRankingError("");
            setCategory(next);
          }}
        />
      </div>

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
