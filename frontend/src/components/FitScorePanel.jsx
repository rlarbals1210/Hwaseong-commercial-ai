import { useState } from "react";
import Bars from "./Bars";
import Gauge from "./Gauge";
import TabStrip from "./TabStrip";

const TABS = [
  { key: "summary", label: "종합" },
  { key: "details", label: "세부 지표" },
  { key: "notes", label: "강점·유의점" },
];

function BulletList({ title, items, tone }) {
  if (!items?.length) return null;
  return (
    <div>
      <div className="t-caption" style={{ fontWeight: 600, color: tone }}>{title}</div>
      <ul className="t-body-sm" style={{ color: "var(--ink-secondary)", margin: "8px 0 0", paddingLeft: 20, lineHeight: 1.7 }}>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

export default function FitScorePanel({ data, loading, preferenceLabel }) {
  const [tab, setTab] = useState("summary");

  if (loading) {
    return <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>적합도를 계산하는 중…</div>;
  }
  if (!data) {
    return <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>지도나 추천 목록에서 읍면동을 골라 주세요.</div>;
  }

  const rankLine = data.is_fallback
    ? "표본이 적어 순위와 등급을 매기지 않습니다"
    : `${data.industry_name} ${data.total}개 읍면동 중 ${data.rank}위 · 상위 ${data.percentile}%`;

  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 16 }}>
        <div>
          <div className="t-title">{data.area_name} · {data.industry_name}</div>
          <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 4 }}>
            {preferenceLabel ?? data.preset} 기준
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className={`nodaji-evidence evidence-${data.evidence_key}`}>{data.evidence_label}</span>
          {!data.is_fallback && data.grade && <span className="badge badge-neutral">{data.grade}등급</span>}
        </div>
      </div>

      <TabStrip tabs={TABS} value={tab} onChange={setTab} ariaLabel="적합도 상세 보기" />

      <div role="tabpanel" style={{ paddingTop: 20 }}>
        {tab === "summary" && (
          data.is_fallback ? (
            <>
              <p className="t-body" style={{ color: "var(--on-surface)", lineHeight: 1.7, margin: 0 }}>{data.summary}</p>
              <p className="t-caption" style={{ color: "var(--ink-muted)", lineHeight: 1.7, margin: "12px 0 0" }}>
                현재 점포 {data.observed?.store_count ?? "—"}곳 · 최근 1년 폐업 {data.observed?.closure_count_cum4 ?? "—"}곳
              </p>
            </>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
              <Gauge value={data.score} grade={data.grade} />
              <div className="t-eyebrow" style={{ color: "var(--ink-muted)", marginTop: 12 }}>{rankLine}</div>
              <p className="t-body-sm" style={{ color: "var(--ink-secondary)", lineHeight: 1.7, margin: "12px 0 0" }}>
                {data.summary}
              </p>
            </div>
          )
        )}

        {tab === "details" && (
          data.breakdown?.length ? <Bars items={data.breakdown} /> : (
            <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: 0 }}>표본이 적어 세부 점수를 계산하지 않습니다.</p>
          )
        )}

        {tab === "notes" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <BulletList title="강점" items={data.pros} tone="var(--badge-ok-ink)" />
            <BulletList title="유의점" items={data.cons} tone="var(--badge-warn-ink)" />
          </div>
        )}
      </div>

      {data.score_adjusted && data.adjustment_note && (
        <div role="note" className="t-caption" style={{ color: "var(--primary)", background: "var(--primary-soft)", borderRadius: "var(--radius-md)", padding: "10px 12px", lineHeight: 1.6, marginTop: 10 }}>
          {data.adjustment_note}
        </div>
      )}
    </>
  );
}
