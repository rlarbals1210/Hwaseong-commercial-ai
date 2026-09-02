import { useCallback, useEffect, useRef, useState } from "react";

// 검색창이 딸린 목록형 선택기. 트리거 옆으로 떠서 열린다.
//
// 원래 BrowsePage의 업종 선택 전용이었다. 같은 화면의 지역 선택이 기본 <select>라
// 나란히 놓인 둘의 모양이 달랐고, 공무원 화면이 SearchableSelect로 정리되면서
// 시민 화면만 뒤처졌다. 그래서 업종에만 있던 이 컴포넌트를 항목 종류와 무관하게
// 쓰도록 꺼냈다. 스타일은 index.css의 .nodaji-industry-* 를 그대로 쓴다 —
// 클래스 이름은 업종에서 왔지만 이제 지역도 함께 쓴다.
export default function FloatingPicker({
  icon, label, placeholder, badge, options, value, onChange,
  searchPlaceholder, searchLabel, listLabel, emptyText = "검색 결과가 없습니다.",
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [menuPosition, setMenuPosition] = useState(null);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const selected = options.find((option) => option.id === value) ?? null;
  const needle = query.trim().toLocaleLowerCase("ko");
  const filtered = options.filter((option) => option.name.toLocaleLowerCase("ko").includes(needle));

  const updateMenuPosition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const margin = 16;
    const gap = 12;
    const availableRight = window.innerWidth - rect.right - gap - margin;
    const fitsRight = availableRight >= 240;
    const width = fitsRight
      ? Math.min(460, availableRight)
      : Math.min(420, window.innerWidth - margin * 2);
    const left = fitsRight ? rect.right + gap : window.innerWidth - width - margin;
    const top = Math.max(68, Math.min(rect.top, window.innerHeight - 280));
    setMenuPosition({
      left: Math.round(left),
      top: Math.round(top),
      width: Math.round(width),
      maxHeight: Math.max(260, Math.round(window.innerHeight - top - margin)),
      pointsRight: fitsRight,
    });
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [open, updateMenuPosition]);

  const choose = (nextId) => {
    onChange(nextId);
    setOpen(false);
    setQuery("");
  };

  const toggle = () => {
    if (!open) updateMenuPosition();
    setOpen((current) => !current);
  };

  return (
    <div className="nodaji-industry-picker" ref={rootRef}>
      <button
        type="button"
        className={`nodaji-industry-trigger${open ? " open" : ""}`}
        onClick={toggle}
        ref={triggerRef}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="nodaji-industry-icon material-symbols-outlined" aria-hidden="true">{icon}</span>
        <span className="nodaji-industry-current">
          <small>{label}</small>
          <strong>{selected?.name ?? placeholder}</strong>
        </span>
        {selected && badge && <em>{badge}</em>}
        <span className="nodaji-industry-chevron material-symbols-outlined" aria-hidden="true">expand_more</span>
      </button>

      {open && menuPosition && (
        <div
          className={`nodaji-industry-menu${menuPosition.pointsRight ? " points-right" : ""}`}
          style={{
            left: menuPosition.left,
            top: menuPosition.top,
            width: menuPosition.width,
            maxHeight: menuPosition.maxHeight,
          }}
        >
          <label className="nodaji-industry-search">
            <span className="material-symbols-outlined" aria-hidden="true">search</span>
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchPlaceholder}
              aria-label={searchLabel}
            />
          </label>
          <div className="nodaji-industry-options" role="listbox" aria-label={listLabel}>
            {filtered.map((option) => (
              <button
                key={option.id}
                type="button"
                role="option"
                aria-selected={option.id === value}
                className={option.id === value ? "active" : ""}
                onClick={() => choose(option.id)}
              >
                <span>
                  <b>{option.name}</b>
                  {option.hint && <small>{option.hint}</small>}
                </span>
                <span className="material-symbols-outlined" aria-hidden="true">
                  {option.id === value ? "check_circle" : "arrow_forward"}
                </span>
              </button>
            ))}
            {!filtered.length && <p>{emptyText}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
