import usePublicQuery from "../../hooks/usePublicQuery";

export default function IndustryExplorer({ areaId, preset, onSelect }) {
  const query = usePublicQuery(areaId ? `/api/recommend/industries?area_id=${areaId}&preset=${encodeURIComponent(preset)}&limit=5` : null);
  if (!areaId) return <p>지역을 먼저 선택해주세요.</p>;
  if (query.loading) return <p role="status">선택 지역의 업종을 비교하는 중…</p>;
  if (query.error) return <p role="alert">{query.error} <button type="button" onClick={query.retry}>다시 시도</button></p>;
  const data = query.data;
  if (!data) return null;
  return <section className="explore-section">
    <div className="nodaji-section-label">지역에서 업종으로</div>
    <h2>{data.area_name} 업종 탐색</h2>
    <p>{data.quarter_label} · {data.measured_count}개 업종 비교 · 표본 부족 {data.excluded_count}개 제외</p>
    <p>{data.grade_notice}</p>
    {!data.results.length && <p className="explore-status">표본이 충분한 업종이 없습니다. 다른 지역을 선택해보세요.</p>}
    {data.results.map((item) => <article className="explore-candidate" key={item.industry_id}>
      <header><h3>{item.rank}. {item.industry_name}</h3><b>{item.score.toFixed(1)}점</b></header>
      <p>{item.reason}</p>
      <small>해당 업종의 다른 읍면동 대비 조건 적합도 · 점포 {item.observed.store_count}곳</small>
      <button type="button" onClick={() => onSelect(item.industry_id)}>이 업종으로 상세 보기</button>
    </article>)}
    <p>{data.disclaimer}</p>
  </section>;
}
