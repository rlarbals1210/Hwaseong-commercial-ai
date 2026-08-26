export default function TabStrip({ tabs, value, onChange, ariaLabel = "보기 선택" }) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))`,
        gap: 4,
        padding: 4,
        background: "var(--surface-container-low)",
        borderRadius: "var(--radius-md)",
      }}
    >
      {tabs.map((tab) => {
        const active = tab.key === value;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.key)}
            style={{
              border: active ? "1px solid var(--hairline)" : "1px solid transparent",
              borderRadius: "var(--radius-sm)",
              background: active ? "var(--surface-container-lowest)" : "transparent",
              color: active ? "var(--primary)" : "var(--ink-muted)",
              fontFamily: "inherit",
              fontSize: 13,
              fontWeight: active ? 600 : 400,
              padding: "8px 6px",
              cursor: "pointer",
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
