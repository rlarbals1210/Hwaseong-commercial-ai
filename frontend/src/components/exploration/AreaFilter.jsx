import { useId, useState } from "react";
import "./areaFilter.css";

// 빈 선택은 화성시 전체. 목록은 공개 지역 API의 값을 그대로 사용한다.
export default function AreaFilter({ areas, selectedIds, onChange }) {
  const [query, setQuery] = useState("");
  const id = useId();
  const selected = areas.filter((area) => selectedIds.includes(area.id));
  const matches = areas.filter((area) => area.name.includes(query.trim()));
  const summary = selected.length ? `${selected[0].name}${selected.length > 1 ? ` 외 ${selected.length - 1}곳` : ""}` : "화성시 전체";
  const toggle = (areaId) => onChange(selectedIds.includes(areaId)
    ? selectedIds.filter((value) => value !== areaId) : [...selectedIds, areaId]);

  return <details className="explore-area-filter">
    <summary><span><b><span className="material-symbols-outlined" aria-hidden="true">filter_alt</span>읍면동 필터</b><small>{summary}</small></span><span className="area-filter-count">{selected.length || areas.length}곳</span></summary>
    <div className="area-filter-content">
      <label htmlFor={id} className="area-filter-search-label">지역 이름 검색</label>
      <input id={id} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="예: 동탄, 봉담" />
      <button type="button" className="area-filter-reset" aria-pressed={!selectedIds.length} onClick={() => { onChange([]); setQuery(""); }}>화성시 전체로 초기화</button>
      <fieldset><legend>추천받을 읍면동 여러 곳 선택</legend><div className="area-filter-options">
        {matches.map((area) => <label key={area.id}><input type="checkbox" checked={selectedIds.includes(area.id)} onChange={() => toggle(area.id)} /><span>{area.name}</span></label>)}
        {!matches.length && <p role="status">일치하는 읍면동이 없습니다.</p>}
      </div></fieldset>
      <p>선택을 모두 해제하면 화성시 전체를 보여줍니다.</p>
    </div>
  </details>;
}
