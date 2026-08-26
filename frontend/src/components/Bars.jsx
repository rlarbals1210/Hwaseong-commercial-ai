export default function Bars({ items = [] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {items.map((item) => {
        const score = Math.max(0, Math.min(100, Number(item.score) || 0));
        return (
          <div key={item.key}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
              <span className="t-body-sm" style={{ color: "var(--on-surface)", fontWeight: 600 }}>
                {item.label}
              </span>
              <span className="t-caption t-metric" style={{ color: "var(--ink-muted)" }}>
                {score.toFixed(1)}점 · 비중 {item.weight_pct}%
              </span>
            </div>
            <div
              style={{
                height: 8,
                borderRadius: "var(--radius-full)",
                background: "var(--surface-container)",
                overflow: "hidden",
                marginTop: 7,
              }}
            >
              <div
                style={{
                  width: `${score}%`,
                  height: "100%",
                  borderRadius: "inherit",
                  background: "var(--primary)",
                }}
              />
            </div>
            <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "6px 0 0", lineHeight: 1.6 }}>
              {item.desc}
            </p>
          </div>
        );
      })}
    </div>
  );
}
