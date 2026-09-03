export default function TabStrip({ tabs, value, onChange, ariaLabel = "보기 선택" }) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="seg"
      style={{ display: "grid", gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}
    >
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={tab.key === value}
          onClick={() => onChange(tab.key)}
          className="seg-item"
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
