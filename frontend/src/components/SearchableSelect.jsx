import { useId, useRef, useState } from "react";
import "./searchableSelect.css";

export default function SearchableSelect({ label, icon = "filter_alt", options, value, onChange,
  emptyLabel, placeholder = "선택해주세요", unit = "개", disabled = false }) {
  const id = useId();
  const detailsRef = useRef(null);
  const searchRef = useRef(null);
  const [query, setQuery] = useState("");
  const selected = options.find((option) => option.value === value);
  const search = query.trim().normalize("NFKC").toLocaleLowerCase();
  const matches = options.filter((option) => option.label.normalize("NFKC").toLocaleLowerCase().includes(search));
  const close = () => {
    detailsRef.current.open = false;
    detailsRef.current.querySelector("summary").focus();
  };
  const choose = (next) => {
    if (next !== value) onChange(next);
    setQuery("");
    close();
  };

  return <details ref={detailsRef} className={`search-select${disabled ? " is-disabled" : ""}`}
    onToggle={(event) => { if (event.currentTarget.open) searchRef.current?.focus(); }}
    onKeyDown={(event) => {
      if (event.key === "Escape" && detailsRef.current.open) {
        event.preventDefault();
        event.stopPropagation();
        close();
      }
    }}>
    <summary aria-disabled={disabled} onClick={(event) => { if (disabled) event.preventDefault(); }}>
      <span className="search-select-heading"><b><span className="material-symbols-outlined" aria-hidden="true">{icon}</span>{label}</b>
        <small>{selected?.label ?? emptyLabel ?? placeholder}</small></span>
      <span className="search-select-count">{selected ? 1 : options.length}{unit}</span>
    </summary>
    <div className="search-select-content">
      <label htmlFor={id}>{label} 검색</label>
      <input ref={searchRef} id={id} type="search" value={query} onChange={(event) => setQuery(event.target.value)}
        placeholder={`${label} 이름 입력`} autoComplete="off" onKeyDown={(event) => { if (event.key === "Enter") event.preventDefault(); }} />
      {emptyLabel && <button type="button" className="search-select-reset" onClick={() => choose("")}>{emptyLabel}로 초기화</button>}
      <fieldset><legend>{label} 하나 선택</legend><div className="search-select-options">
        {matches.map((option) => <label key={option.value}>
          <input type="radio" name={`${id}-choice`} checked={option.value === value} onChange={() => choose(option.value)} />
          <span>{option.label}{option.hint && <small>{option.hint}</small>}</span>
        </label>)}
        {!matches.length && <p role="status">{options.length ? "검색 결과가 없습니다." : "선택할 항목이 없습니다."}</p>}
      </div></fieldset>
    </div>
  </details>;
}
