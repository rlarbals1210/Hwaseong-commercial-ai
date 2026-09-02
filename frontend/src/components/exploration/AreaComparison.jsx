import ToolHeading from "./ToolHeading";
import SearchableSelect from "../SearchableSelect";

const number = (value, suffix = "", digits = 1) => (
  typeof value === "number" && Number.isFinite(value) ? `${value.toLocaleString("ko-KR", { maximumFractionDigits: digits })}${suffix}` : "—"
);

export default function AreaComparison({ data, loading, error, areaIds, onChange, onOpenDetail }) {
  const items = areaIds.map((id) => data?.results.find((item) => item.area_id === id));
  const ready = items.length === 2 && items.every(Boolean);
  const metrics = [
    ["조건 적합도", (item) => number(item.score, "점")],
    ["근거 수준", (item) => item.evidence_label],
    ["최근 1년 폐업률", (item) => number(item.observed.closure_rate_cum4_pct, "%")],
    ["현재 점포", (item) => number(item.observed.store_count, "곳", 0)],
    ["평균 업력", (item) => number(item.observed.tenure_quarters == null ? null : item.observed.tenure_quarters / 4, "년")],
    ["최근 개업률", (item) => number(item.observed.opening_rate_pct, "%")],
  ];
  return <section className="explore-section explore-comparison" aria-label="지역 비교">
    <ToolHeading icon="compare_arrows" title="어느 지역이 더 맞을까요?" level="h2"><p>같은 업종 · 두 지역 비교</p></ToolHeading>
    <p>{data ? `${data.industry_name} · ${data.quarter_label}` : "선택 업종의 자료를 불러옵니다."}</p>
    {loading && <p role="status">비교 자료를 불러오는 중…</p>}{error && <p role="alert">{error}</p>}
    {data && <>
      <div className="select-row">{[0, 1].map((index) => <SearchableSelect key={index}
        label={index === 0 ? "기준 지역" : "비교 지역"} icon="location_on" unit="곳" placeholder="지역 선택"
        options={[...data.results].sort((a, b) => a.area_name.localeCompare(b.area_name, "ko"))
          .filter((item) => item.area_id !== areaIds[1 - index])
          .map((item) => ({ value: item.area_id, label: item.area_name }))}
        value={areaIds[index] ?? ""}
        onChange={(next) => { const ids = [...areaIds]; ids[index] = next === "" ? null : next; onChange(ids); }} />)}</div>
      {!ready && <p className="explore-status">두 지역을 고르면 조건과 관측 지표를 나란히 볼 수 있습니다.</p>}
      {ready && <>
        <table className="explore-comparison-table"><caption>{items[0].area_name}과 {items[1].area_name} 비교</caption>
          <thead><tr><th scope="col">비교 항목</th>{items.map((item) => <th scope="col" key={item.area_id}>{item.area_name}</th>)}</tr></thead>
          <tbody>{metrics.map(([label, render]) => <tr key={label}><th scope="row">{label}</th>{items.map((item) => <td key={item.area_id}>{render(item)}</td>)}</tr>)}</tbody>
        </table>
        <div className="explore-form-grid">{items.map((item) => <button key={item.area_id} type="button" onClick={() => onOpenDetail(item.area_id)}>{item.area_name} 상세 →</button>)}</div>
        {items.some((item) => item.evidence_key !== "sufficient") && <p className="explore-status">표본이 작거나 업종이 관측되지 않은 지역이 포함돼 있습니다. 표시되지 않은 값은 0을 뜻하지 않습니다.</p>}
      </>}
      <p>같은 업종의 화성시 전체 점수를 그대로 비교합니다. 특정 점포의 성공 가능성을 뜻하지 않습니다.</p>
    </>}
  </section>;
}
