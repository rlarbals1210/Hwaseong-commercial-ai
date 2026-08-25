import { useEffect, useState } from "react";
import { apiFetchJson } from "../lib/api";

// 최신 분기 잠정 고지. 문구·분기 라벨은 서버(/api/alerts/grade-notice)에서 받는다 —
// 프론트에 분기나 기준선을 상수로 박으면 파이프라인 재실행 때마다 화면이 거짓말을 한다
// (CITY_AVG_PCT = 3.22가 그렇게 남아 있었다).
export default function ProvisionalNotice({ meta: metaProp }) {
  const [meta, setMeta] = useState(metaProp ?? null);

  useEffect(() => {
    if (metaProp) {
      setMeta(metaProp);
      return;
    }
    let alive = true;
    apiFetchJson("/api/alerts/grade-notice")
      .then((d) => alive && setMeta(d))
      .catch(() => alive && setMeta(null));
    return () => {
      alive = false;
    };
  }, [metaProp]);

  if (!meta?.provisional_notice) return null;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        padding: "10px 12px",
        border: "1px solid var(--hairline)",
        borderRadius: "var(--radius-lg)",
        background: "var(--surface-muted, rgba(0,0,0,0.02))",
      }}
    >
      <span
        className="material-symbols-outlined"
        style={{ fontSize: 18, color: "var(--ink-faint)", flexShrink: 0, lineHeight: 1.4 }}
      >
        schedule
      </span>
      <span className="t-caption" style={{ color: "var(--ink-muted)", lineHeight: 1.6 }}>
        {meta.latest_quarter_label && (
          <b style={{ color: "var(--on-surface)" }}>{meta.latest_quarter_label} 잠정 </b>
        )}
        {meta.provisional_notice}
      </span>
    </div>
  );
}
