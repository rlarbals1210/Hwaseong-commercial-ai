import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import SearchableSelect from "./SearchableSelect";
import "./cellPickerDialog.css";

export default function CellPickerDialog({ title, options, value, onApply, onClose, peers = [] }) {
  const dialogRef = useRef(null);
  const titleId = useId();
  const [draft, setDraft] = useState(() => value ?? { areaId: null, industryId: null });
  const areas = options?.areas ?? [];
  const names = Object.fromEntries((options?.industries ?? []).map((industry) => [industry.id, industry.name]));
  const area = areas.find((item) => item.id === draft.areaId);
  const industries = (area?.industries ?? []).map((industry) => ({
    value: industry.id, label: names[industry.id] ?? "업종명 없음", hint: industry.sample_insufficient ? "표본부족" : undefined,
  }));
  const valid = industries.some((industry) => industry.value === draft.industryId);

  useEffect(() => {
    const dialog = dialogRef.current;
    const previous = document.activeElement;
    // native dialog의 top layer와 초점 관리를 사용해 페이지 애니메이션의 transform을 벗어난다.
    dialog.showModal();
    return () => {
      dialog.close();
      if (previous?.isConnected) previous.focus();
    };
  }, []);

  const chooseArea = (areaId) => {
    const nextArea = areas.find((item) => item.id === areaId);
    const available = nextArea?.industries.some((industry) => industry.id === draft.industryId);
    setDraft({ areaId, industryId: available ? draft.industryId : null });
  };

  return createPortal(<dialog ref={dialogRef} className="cell-picker-dialog" aria-labelledby={titleId}
    onCancel={(event) => { event.preventDefault(); onClose(); }}
    onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <form onSubmit={(event) => { event.preventDefault(); if (valid) { onApply(draft); onClose(); } }}>
      <header><h2 id={titleId}>{title}</h2><button type="button" onClick={onClose} aria-label="선택 창 닫기">
        <span className="material-symbols-outlined" aria-hidden="true">close</span>
      </button></header>
      <div className="cell-picker-fields">
        <SearchableSelect label="읍면동" icon="location_on" unit="곳" options={areas.map((item) => ({ value: item.id, label: item.name }))}
          value={draft.areaId} placeholder="지역을 선택해주세요" onChange={chooseArea} />
        <SearchableSelect key={draft.areaId ?? "none"} label="업종" icon="storefront" options={industries}
          value={draft.industryId} placeholder={area ? "업종을 선택해주세요" : "지역을 먼저 선택해주세요"}
          disabled={!area} onChange={(industryId) => setDraft({ ...draft, industryId })} />
      </div>
      <p className="cell-picker-selection" aria-live="polite">{area?.name ?? "지역 미선택"} · {valid ? names[draft.industryId] : "업종 미선택"}</p>
      {peers.length > 0 && <section className="cell-picker-peers">
        <h3>기준 상권과 같은 업종의 추천 후보</h3>
        <div>{peers.slice(0, 6).map((peer) => <button key={`${peer.area_id}-${peer.industry_id}`} type="button"
          aria-pressed={draft.areaId === peer.area_id && draft.industryId === peer.industry_id}
          onClick={() => setDraft({ areaId: peer.area_id, industryId: peer.industry_id })}>
          <span><b>{peer.area_name}</b><small>{names[peer.industry_id]} · 점포 {peer.store_count?.toLocaleString() ?? "—"}곳</small></span>
          <span>{Number.isFinite(peer.cumulative_closure_rate_pct) ? `${peer.cumulative_closure_rate_pct.toFixed(1)}%` : "—"}</span>
        </button>)}</div>
      </section>}
      <footer><button type="button" onClick={onClose}>취소</button><button type="submit" disabled={!valid}>선택 적용</button></footer>
    </form>
  </dialog>, document.body);
}
