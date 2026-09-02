import { useEffect, useRef, useState } from "react";
import usePublicQuery from "../../hooks/usePublicQuery";
import StartupSimulator from "./StartupSimulator";

function QueryState({ query }) {
  if (query.loading) return <p role="status">자료를 불러오는 중…</p>;
  if (query.error) return <p role="alert">{query.error} <button type="button" onClick={query.retry}>다시 시도</button></p>;
  return null;
}

function NearbyAreas({ areaId, industryId, preset, onCompare, onSelect, onBroaden }) {
  const query = usePublicQuery(`/api/recommend/nearby?area_id=${areaId}&industry_id=${industryId}&preset=${encodeURIComponent(preset)}`);
  const data = query.data;
  return <section className="explore-section">
    <h3>인근 대안 상권</h3><QueryState query={query} />
    {data && <>
      <p>{data.neighbor_count}개 인접 지역 중 근거 충분 {data.eligible_count}곳 · {data.quarter_label}</p>
      {!data.results.length && <p className="explore-status">같은 업종으로 비교할 수 있는 인접 지역의 근거가 부족합니다.</p>}
      {data.results.map((item) => <article className="explore-candidate" key={item.area_id}>
        <header><h4>{item.area_name}</h4><b>{item.score.toFixed(1)}점</b></header>
        <small>화성시 내 {item.rank}위 · 점포 {item.observed.store_count}곳</small>
        <p>{item.reason}</p>
        <div className="explore-actions"><button type="button" onClick={() => onCompare(item.area_id)}>현재 지역과 비교</button>
          <button type="button" onClick={() => onSelect(item.area_id)}>상세 보기</button></div>
      </article>)}
      <p>{data.notice}</p>
      <button type="button" className="explore-secondary" onClick={onBroaden}>화성시 전체로 넓혀 보기</button>
    </>}
  </section>;
}

function WeekdayFlow({ areaId }) {
  const query = usePublicQuery(`/api/exploration/weekday-flow?area_id=${areaId}`);
  const data = query.data;
  const max = Math.max(100, ...(data?.points ?? []).map((point) => point.index));
  return <section className="explore-section">
    <h3>요일별 유동인구 패턴</h3><QueryState query={query} />
    {data && <>
      <p>{data.area_name} 전체 · 기준월 {data.month ?? "자료 없음"} · 요일 평균 100</p>
      {data.status === "ready" && <>
        <div className="explore-week-bars" role="img" aria-label={data.points.map((p) => `${p.label}요일 ${p.index}`).join(", ")}>
          {data.points.map((point) => <div key={point.weekday}>
            <b>{point.index.toFixed(1)}</b><div className="explore-bar-track"><i style={{ height: `${point.index / max * 100}%` }} className={point.weekday > 4 ? "weekend" : ""} /></div><span>{point.label}</span>
          </div>)}
        </div>
        <p className="explore-status">주말 일평균은 평일 일평균보다 {Math.abs(data.weekend_vs_weekday_pct).toFixed(1)}% {data.weekend_vs_weekday_pct >= 0 ? "높습니다" : "낮습니다"}.</p>
      </>}
      <p>{data.notice}</p><a href={data.source_url} target="_blank" rel="noreferrer">{data.source}</a>
    </>}
  </section>;
}

function SearchInterest({ industryId }) {
  const query = usePublicQuery(`/api/exploration/search-trend?industry_id=${industryId}`);
  const data = query.data;
  return <section className="explore-section">
    <h3>업종 검색 트렌드</h3><QueryState query={query} />
    {data && <>
      <p>{data.industry_name} · 전국 · {data.start_date.slice(0, 7)} ~ {data.end_date.slice(0, 7)}</p>
      {data.keywords.length > 0 && <p>대표 검색어: {data.keywords.join(" · ")}</p>}
      <p className="explore-status" role="status">{data.message}</p>
      {data.points.length > 0 && <div className="explore-search-bars" aria-label="월별 검색지수">
        {data.points.map((point) => <div key={point.month}><time>{point.month}</time><span><i style={{ width: `${point.index}%` }} /></span><b>{point.index.toFixed(1)}</b></div>)}
      </div>}
      {data.fetched_at && <p>마지막 수집: {new Date(data.fetched_at).toLocaleString("ko-KR")}{data.status === "stale" && " · 이전 수집 자료"}</p>}
      <p>{data.notice}</p>
      <a href="https://datalab.naver.com/keyword/trendSearch.naver" target="_blank" rel="noreferrer">네이버 데이터랩</a>
      {["unavailable", "stale"].includes(data.status) && <button type="button" className="explore-secondary" onClick={query.retry}>다시 확인</button>}
    </>}
  </section>;
}

export default function ExplorationTools({ areaId, industryId, areaName, industryName, preset, children, comparison, comparisonKey, onCompare, onSelect, onBroaden }) {
  const [tab, setTab] = useState("conditions");
  const comparisonRef = useRef(null);
  useEffect(() => {
    if (comparisonKey) comparisonRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [comparisonKey]);
  return <>
    <h2 className="explore-detail-title">{areaName} <small>{industryName}</small></h2>
    <div className="explore-tabs" aria-label="상세 분석 종류">
      {[["conditions", "입지·인근 비교"], ["visitors", "방문·검색 패턴"], ["costs", "창업비용"]].map(([key, label]) =>
        <button type="button" key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>)}
    </div>
    {tab === "conditions" && <>{children}<div ref={comparisonRef}>{comparison}</div><NearbyAreas {...{ areaId, industryId, preset, onCompare, onSelect, onBroaden }} /></>}
    {tab === "visitors" && <><WeekdayFlow areaId={areaId} /><SearchInterest industryId={industryId} /></>}
    <div hidden={tab !== "costs"}><StartupSimulator areaName={areaName} industryName={industryName} /></div>
  </>;
}
