import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";
import { GradeBadge, TypeBadge } from "../components/Badge";
import { downloadCsv, csvNum } from "../lib/csv";

// 상권 비교.
//
// 예전 판은 "두 상권을 고르세요"로 시작했다. 비교 대상을 담당자가 이미 알고 있어야 쓸 수
// 있는 도구는 도구가 아니다. 실제 질문은 "이 상권이 왜 나쁜지 알아보려면 어디를 보면
// 되는가"이므로, 기준 상권 하나를 받고 ① 업종 안에서의 위치와 ② 비교 후보를 화면이 낸다.
//
// 차이의 판정은 서버가 한다. 점포 55곳과 60곳에서 폐업이 1건 다르면 폐업률은 1.7%p
// 벌어져 보이지만 표본 크기의 산물이다. 두 비율 z검정으로 comparable=false가 오면
// 화면은 숫자 대신 "차이 없음"을 쓴다.
//
// 지표에 방향 색(빨강/초록)을 주지 않는다. 폐업률은 높은 쪽이, 개업률은 낮은 쪽이 나쁘고,
// 지표마다 방향을 판정해 칠하면 도구가 결론을 내렸다는 인상이 된다. 판단은 하단 콜아웃
// 한 곳에서만 한다.

// 순위표 칸 폭. 머리글과 본문이 같은 값을 써야 세로줄이 맞는다.
const RANK_COLS = "30px 84px 1fr 68px 74px";

const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v.toLocaleString() : "—");

function CellPicker({ label, options, areaId, industryId, onChange, compact }) {
  const area = options?.areas.find((a) => a.id === areaId);
  const names = useMemo(
    () => Object.fromEntries((options?.industries ?? []).map((i) => [i.id, i.name])),
    [options],
  );
  return (
    <div style={{ flex: "1 1 240px", minWidth: 0 }}>
      {label && <div className="t-eyebrow" style={{ color: "var(--ink-faint)", marginBottom: 6 }}>{label}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <select value={areaId ?? ""} onChange={(e) => onChange(Number(e.target.value), null)} style={{ flex: "1 1 0", minWidth: 0 }}>
          {(options?.areas ?? []).map((a) => (<option key={a.id} value={a.id}>{a.name}</option>))}
        </select>
        <select value={industryId ?? ""} onChange={(e) => onChange(areaId, Number(e.target.value))} style={{ flex: compact ? "1 1 0" : "1 1 0", minWidth: 0 }}>
          {(area?.industries ?? []).map((i) => (
            <option key={i.id} value={i.id}>
              {names[i.id]}{i.sample_insufficient ? " (표본부족)" : ""}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

/** 같은 업종 상권 순위.
 *
 *  산점도를 걷어냈다. 두 축을 동시에 읽히게 하려면 담당자가 사분면 규칙을 먼저 외워야
 *  하는데, 정작 알고 싶은 것은 "이 둘이 27곳 중 어디쯤이고 그 사이에 누가 있는가"다.
 *  순위 막대는 위치·간격·이웃을 한 번에 보여준다. 유형은 배지로 옆에 붙인다.
 */
function IndustryRanking({ context, targetAreaId, onPick }) {
  const rows = context?.distribution ?? [];
  if (rows.length < 3) return null;
  const max = Math.max(...rows.map((r) => r.cumulative_closure_rate_pct), 1);
  const median = context.industry_median_pct;

  return (
    <div>
      <div
        className="t-caption"
        style={{
          display: "grid",
          gridTemplateColumns: RANK_COLS,
          gap: 10,
          padding: "0 8px 8px",
          marginBottom: 6,
          borderBottom: "1px solid var(--hairline)",
          color: "var(--ink-faint)",
          fontWeight: 600,
        }}
      >
        <span>순위</span>
        <span>읍면동</span>
        <span>최근 1년 누적 폐업률</span>
        <span style={{ textAlign: "right" }}>%</span>
        <span style={{ textAlign: "right" }}>상권 유형</span>
      </div>

      <div style={{ display: "grid", gap: 5 }}>
        {rows.map((row) => {
          const self = row.is_self;
          const target = row.area_id === targetAreaId;
          const mark = self || target;
          return (
            <button
              key={row.area_id}
              onClick={() => !self && onPick?.(row)}
              style={{
                display: "grid",
                gridTemplateColumns: RANK_COLS,
                alignItems: "center",
                gap: 10,
                width: "100%",
                textAlign: "left",
                border: "none",
                background: mark ? "var(--surface-container-low)" : "transparent",
                borderRadius: "var(--radius-sm)",
                padding: "7px 8px",
                cursor: self ? "default" : "pointer",
              }}
            >
              <span className="t-body-sm" style={{ color: "var(--ink-faint)", fontVariantNumeric: "tabular-nums" }}>
                {row.rank}
              </span>
              <span
                className="t-body-sm"
                style={{ color: self ? "var(--primary)" : target ? "var(--badge-warn-ink)" : "var(--ink-secondary)", fontWeight: mark ? 700 : 400, whiteSpace: "nowrap" }}
              >
                {row.area_name}
              </span>
              <span style={{ position: "relative", height: 14, background: "var(--surface-container-high)", borderRadius: "var(--radius-sm)", overflow: "hidden", display: "block" }}>
                <span
                  style={{
                    position: "absolute", left: 0, top: 0, bottom: 0,
                    width: `${(row.cumulative_closure_rate_pct / max) * 100}%`,
                    background: self ? "var(--primary)" : target ? "var(--accent-orange)" : "var(--outline-variant)",
                  }}
                />
                {median != null && (
                  <span style={{ position: "absolute", left: `${(median / max) * 100}%`, top: 0, bottom: 0, width: 1, background: "var(--ink-faint)" }} />
                )}
              </span>
              <span className="t-body-sm" style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", color: mark ? "var(--on-surface)" : "var(--ink-muted)", fontWeight: mark ? 600 : 400 }}>
                {fmt(row.cumulative_closure_rate_pct, 2)}%
              </span>
              <span className="t-body-sm" style={{ textAlign: "right", color: "var(--ink-faint)", whiteSpace: "nowrap" }}>
                {row.cell_type && row.cell_type !== "유형판정보류" ? row.cell_type : "—"}
              </span>
            </button>
          );
        })}
      </div>
      <div className="t-body-sm" style={{ color: "var(--ink-faint)", marginTop: 12 }}>
        가는 세로선은 업종 중위값 {fmt(median, 2)}%. 이름을 누르면 그 상권과 비교합니다.
      </div>
    </div>
  );
}

/** 비교 후보 한 장. 대조군/유사군을 크게 띄우고 나머지는 목록으로 둔다. */
function PeerCard({ peer, base, tone, caption, onPick }) {
  if (!peer) return null;
  const TONE = {
    contrast: { bar: "var(--accent-orange)", fg: "var(--badge-warn-ink)" },
    similar: { bar: "var(--outline-variant)", fg: "var(--ink-muted)" },
  }[tone];
  return (
    <div className="card" style={{ padding: 18, flex: "1 1 260px", borderLeft: `3px solid ${TONE.bar}` }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>{caption}</div>
      <div className="t-h3" style={{ marginTop: 3 }}>{peer.area_name}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <span className="t-metric" style={{ fontSize: 28, color: TONE.fg }}>
          {fmt(peer.cumulative_closure_rate_pct, 2)}%
        </span>
        <span className="t-body-sm" style={{ color: "var(--ink-muted)" }}>
          {base != null && (
            <>기준 대비 <b style={{ color: "var(--on-surface)" }}>
              {peer.delta_pp > 0 ? "+" : ""}{fmt(peer.delta_pp, 2)}%p
            </b></>
          )}
        </span>
      </div>
      <div className="t-body-sm" style={{ color: "var(--ink-faint)", marginTop: 7 }}>
        점포 {num(peer.store_count)}곳 · {peer.significant ? "통계적으로 구분됨" : "구분되지 않음"}
      </div>
      <button className="btn-utility" style={{ marginTop: 14, width: "100%" }} onClick={() => onPick(peer)}>
        이 상권과 비교
      </button>
    </div>
  );
}

/** 차이를 업종 내 표준편차로 재서 큰 순으로. 단위가 제각각인 지표를 한 자로 재는 유일한 방법. */
function DiffRows({ data }) {
  const rows = [...data.diffs];
  const hasSigma = rows.some((d) => d.sigma != null);
  // 설명 후보를 먼저, 그다음 차이가 큰 순. 이 업종에서 폐업률과 함께 움직이지 않는
  // 지표는 아무리 크게 벌어져 있어도 담당자가 먼저 볼 것이 아니다.
  if (hasSigma) {
    rows.sort((a, b) =>
      (b.explains ? 1 : 0) - (a.explains ? 1 : 0) ||
      Math.abs(b.sigma ?? 0) - Math.abs(a.sigma ?? 0));
  }
  const maxSigma = Math.max(...rows.map((d) => Math.abs(d.sigma ?? 0)), 1);

  return (
    <div style={{ display: "grid", gap: 2 }}>
      {rows.map((d) => {
        const muted = (side) => side?.sample_insufficient && d.kind === "rate";
        const diffUnit = d.unit === "%" ? "%p" : d.unit;
        const sigma = d.sigma;
        const width = sigma != null ? (Math.abs(sigma) / maxSigma) * 50 : 0;
        return (
          <div
            key={d.metric}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 150px 1fr",
              alignItems: "center",
              gap: 12,
              padding: "13px 0",
              borderTop: "1px solid var(--hairline)",
            }}
          >
            <div className="t-body" style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", color: muted(data.left) ? "var(--ink-faint)" : "var(--on-surface)" }}>
              <b>{fmt(d.left, d.decimals)}</b>{d.unit}
            </div>

            <div style={{ textAlign: "center" }}>
              <div className="t-body-sm" style={{ color: d.explains ? "var(--on-surface)" : "var(--ink-secondary)", fontWeight: d.explains ? 600 : 400, whiteSpace: "nowrap" }}>
                {d.label}
                {d.explains && (
                  <span
                    title="이 업종에서 폐업률과 함께 움직인 지표이고, 두 상권의 차이도 큽니다. 인과가 아니라 확인 후보입니다."
                    style={{ color: "var(--accent-orange)", marginLeft: 4 }}
                  >●</span>
                )}
              </div>
              {/* 발산 막대 — 가운데가 0, 왼쪽으로 뻗으면 왼쪽 상권이 크다 */}
              {sigma != null ? (
                <div style={{ position: "relative", height: 8, marginTop: 5 }}>
                  <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--hairline)" }} />
                  <div
                    style={{
                      position: "absolute",
                      top: 1, height: 6,
                      borderRadius: 3,
                      background: "var(--ink-muted)",
                      width: `${width}%`,
                      left: sigma > 0 ? `${50 - width}%` : "50%",
                    }}
                  />
                </div>
              ) : <div style={{ height: 13 }} />}
              <div className="t-caption" style={{ marginTop: 5, color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                {!d.comparable
                  ? (d.reason === "sample" ? "판단 보류" : "차이 없음")
                  : d.delta == null
                    ? "—"
                    : `${fmt(Math.abs(d.delta), d.decimals)}${diffUnit}${sigma != null ? ` · ${Math.abs(sigma).toFixed(2)}σ` : ""}`}
              </div>
              {d.industry_correlation != null && (
                <div className="t-caption" style={{ color: "var(--ink-faint)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                  폐업률 상관 {d.industry_correlation > 0 ? "+" : ""}{d.industry_correlation.toFixed(2)}
                </div>
              )}
            </div>

            <div className="t-body" style={{ fontVariantNumeric: "tabular-nums", color: muted(data.right) ? "var(--ink-faint)" : "var(--on-surface)" }}>
              <b>{fmt(d.right, d.decimals)}</b>{d.unit}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** 배후 여건 — 상권의 성적이 아니라 그 상권이 놓인 조건.
 *
 *  같은 폐업률이라도 점포가 젊은 곳과 오래된 곳, 사람이 느는 곳과 주는 곳은 손댈 지점이
 *  다르다. 배후인구는 등급·유형 판정에 관여하지 않는다 — 인구증감과 폐업률의 순위상관은
 *  +0.238로 약하고 부호도 직관과 반대다. 원인의 방향을 좁히는 참고 자료다.
 */
function ConditionRow({ label, left, right, hint }) {
  if (left == null && right == null) return null;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 168px 1fr",
        alignItems: "center",
        gap: 12,
        padding: "15px 0",
        borderTop: "1px solid var(--hairline)",
      }}
    >
      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        <b className="t-body">{left ?? "—"}</b>
      </div>
      <div style={{ textAlign: "center" }}>
        <div className="t-body-sm" style={{ color: "var(--ink-secondary)" }}>{label}</div>
        {hint && <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 3 }}>{hint}</div>}
      </div>
      <div style={{ fontVariantNumeric: "tabular-nums" }}>
        <b className="t-body">{right ?? "—"}</b>
      </div>
    </div>
  );
}

function ConditionCard({ data }) {
  const l = data.left, r = data.right;
  const years = (q) => (Number.isFinite(q) ? `${(q / 4).toFixed(1)}년` : null);
  const pop = (v) => (Number.isFinite(v) ? v.toLocaleString() : null);
  const chg = (v) => (Number.isFinite(v) ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : null);
  const window = l.population_from_label && l.population_to_label
    ? `${l.population_from_label} → ${l.population_to_label}`
    : null;

  const hasAny =
    l.avg_tenure_quarters != null || r.avg_tenure_quarters != null ||
    l.population != null || r.population != null;
  if (!hasAny) return null;

  return (
    <div className="card" style={{ padding: 22, marginTop: 14 }}>
      <h3 className="t-eyebrow" style={{ margin: "0 0 2px", color: "var(--ink-faint)" }}>배후 여건</h3>
      <p className="t-caption" style={{ margin: "0 0 8px", color: "var(--ink-muted)" }}>
        상권의 성적이 아니라 그 상권이 놓인 조건입니다. 등급 판정에는 쓰지 않습니다.
      </p>
      <ConditionRow
        label="평균 업력"
        hint="점포가 얼마나 오래됐는가"
        left={years(l.avg_tenure_quarters)}
        right={years(r.avg_tenure_quarters)}
      />
      <ConditionRow
        label="배후인구"
        hint="읍면동 등록인구"
        left={pop(l.population)}
        right={pop(r.population)}
      />
      <ConditionRow
        label="배후인구 증감"
        hint={window}
        left={chg(l.population_change_pct)}
        right={chg(r.population_change_pct)}
      />
    </div>
  );
}

/** 유형이 다르면 처방이 다르다. 등급이 같아도 이 칸이 갈리면 할 일이 갈린다. */
function PrescriptionCard({ data }) {
  const sides = [data.left, data.right];
  if (!sides.some((c) => c.cell_type_summary)) return null;
  return (
    <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", marginTop: 14 }}>
      {sides.map((cell, i) => (
        <div key={i} className="card" style={{ padding: 20 }}>
          <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>{cell.area_name}</div>
          <div className="t-title" style={{ marginTop: 3, fontSize: 18 }}>{cell.cell_type ?? "유형 미판정"}</div>
          {cell.cell_type_summary && (
            <p className="t-body-sm" style={{ margin: "9px 0 0", color: "var(--ink-secondary)", lineHeight: 1.7 }}>
              {cell.cell_type_summary}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

/** 두 상권의 분기별 누적 폐업률. 스냅샷만으로는 「원래 나쁜 곳」과 「최근 나빠진 곳」이
 *  구분되지 않는다. 누적 4분기가 안 찬 분기는 값이 없으므로 선을 끊는다. */
function TrendOverlay({ trend, leftName, rightName }) {
  const points = (trend ?? []).filter(
    (p) => Number.isFinite(p.left_pct) || Number.isFinite(p.right_pct),
  );
  if (points.length < 3) return null;

  const W = 660, H = 190, PAD = 34;
  const values = points.flatMap((p) => [p.left_pct, p.right_pct]).filter(Number.isFinite);
  const max = Math.max(...values, 1) * 1.15;
  const x = (i) => PAD + (i * (W - PAD * 2)) / (points.length - 1);
  const y = (v) => H - PAD - (v / max) * (H - PAD * 2);

  // 값이 빈 분기에서 선을 잇지 않는다. 이어 버리면 미산출 구간이 완만한 변화로 보인다.
  const path = (key) => {
    let d = "", pen = false;
    points.forEach((p, i) => {
      const v = p[key];
      if (!Number.isFinite(v)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i)},${y(v)} `;
      pen = true;
    });
    return d.trim();
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <svg width={W} height={H} role="img" aria-label="분기별 누적 폐업률 비교">
        <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="var(--hairline)" />
        <path d={path("right_pct")} fill="none" stroke="var(--outline)" strokeWidth="2" strokeDasharray="4 3" />
        <path d={path("left_pct")} fill="none" stroke="var(--primary)" strokeWidth="2.5" />
        <text x={PAD} y={16} fontSize="11" fill="var(--ink-faint)">{fmt(max)}%</text>
        <text x={PAD} y={H - 8} fontSize="11" fill="var(--ink-faint)">{points[0].label}</text>
        <text x={W - PAD} y={H - 8} fontSize="11" fill="var(--ink-faint)" textAnchor="end">
          {points[points.length - 1].label}
        </text>
      </svg>
      <div className="t-caption" style={{ display: "flex", gap: 18, color: "var(--ink-muted)", marginTop: 4 }}>
        <span><span style={{ display: "inline-block", width: 16, height: 2, background: "var(--primary)", verticalAlign: "middle", marginRight: 6 }} />{leftName}</span>
        <span><span style={{ display: "inline-block", width: 16, height: 2, background: "var(--outline)", verticalAlign: "middle", marginRight: 6 }} />{rightName}</span>
      </div>
    </div>
  );
}

function MethodNote({ basis, notice, context }) {
  const rows = [
    ["기준 분기", `${basis?.quarter_label ?? "—"} · 최근 ${basis?.window_quarters ?? 4}분기 누적`],
    ["차이 판정", `${basis?.method ?? "—"} · 신뢰수준 ${basis?.confidence_level ?? "95%"}`],
    ["표본 처리", "한쪽이라도 표본부족이면 비율 지표의 차이는 판단하지 않습니다. 값은 그대로 표시합니다."],
    ["σ(시그마)", "차이를 같은 업종 분포의 표준편차로 나눈 값입니다. 단위가 다른 지표를 한 자로 재기 위한 것이며, 업종이 서로 다르면 기준이 없어 표시하지 않습니다."],
    ["비교 후보", context ? `같은 업종에서 점포 수가 기준 상권의 ±${context.peer_ratio_pct}% 범위(${num(context.peer_store_min)}~${num(context.peer_store_max)}곳)인 상권만 냅니다. 규모가 크게 다르면 차이의 상당 부분이 규모에서 옵니다.` : "—"],
    ["설명 후보 ●", "같은 업종 상권들에서 그 지표와 폐업률의 순위상관이 0.4 이상이고, 두 상권의 차이가 0.8σ 이상인 경우입니다. 인과가 아니라 현장에서 먼저 확인할 후보이며, 표본이 업종당 9~27곳이라 상관값 자체도 흔들립니다."],
    ["업종 순위", "표본 기준을 넘은 상권만으로 매깁니다. 표본부족 상권을 같은 축에 올리면 점포 4곳짜리 0.0%가 가장 안전한 상권처럼 보입니다."],
    ["배후 여건", "평균 업력과 배후 읍면동 등록인구입니다. 등급·유형 판정에는 쓰지 않습니다. 인구증감과 폐업률의 순위상관은 +0.238로 약하고 부호도 직관과 반대여서 판정 축으로 쓸 근거가 없습니다."],
  ];
  return (
    <details style={{ marginTop: 28 }}>
      <summary className="t-body-sm" style={{ cursor: "pointer", color: "var(--ink-muted)", padding: "8px 0" }}>산출 기준</summary>
      <div className="card" style={{ marginTop: 8, padding: 20 }}>
        <dl style={{ margin: 0, display: "grid", gap: 12 }}>
          {rows.map(([term, desc]) => (
            <div key={term} style={{ display: "grid", gridTemplateColumns: "118px 1fr", gap: 16, alignItems: "start" }}>
              <dt className="t-body-sm" style={{ color: "var(--ink-faint)", fontWeight: 600 }}>{term}</dt>
              <dd className="t-body-sm" style={{ margin: 0, color: "var(--ink-secondary)", lineHeight: 1.7 }}>{desc}</dd>
            </div>
          ))}
          {notice && (
            <div style={{ display: "grid", gridTemplateColumns: "104px 1fr", gap: 14 }}>
              <dt className="t-caption" style={{ color: "var(--ink-faint)", fontWeight: 600 }}>고지</dt>
              <dd className="t-caption" style={{ margin: 0, color: "var(--ink-secondary)", lineHeight: 1.7 }}>{notice}</dd>
            </div>
          )}
        </dl>
      </div>
    </details>
  );
}

export default function ComparePage() {
  const [options, setOptions] = useState(null);
  const [base, setBase] = useState(null);       // 기준 상권 {areaId, industryId}
  const [target, setTarget] = useState(null);   // 비교 상권
  const [manual, setManual] = useState(false);  // 비교 대상을 직접 고르는 모드
  const [context, setContext] = useState(null);
  const [data, setData] = useState(null);
  const [thresholds, setThresholds] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetchJson("/api/alerts/grade-notice").then(setThresholds).catch(() => setThresholds(null));
    apiFetchJson("/api/compare/options")
      .then((d) => {
        setOptions(d);
        // 기본 기준 상권은 표본충분인 첫 조합. 표본부족이 기본으로 걸리면 화면이 열리자마자
        // "판단보류"만 보여주게 되고 이 화면이 무엇을 하는 곳인지 전달되지 않는다.
        for (const a of d.areas ?? []) {
          const industry = a.industries.find((i) => !i.sample_insufficient);
          if (industry) { setBase({ areaId: a.id, industryId: industry.id }); return; }
        }
        const first = (d.areas ?? [])[0];
        if (first) setBase({ areaId: first.id, industryId: first.industries[0]?.id });
      })
      .catch((err) => setError(describeApiError(err)));
  }, []);

  // 기준 상권이 바뀌면 비교 대상을 지우고 추천을 다시 받는다.
  useEffect(() => {
    if (!base?.areaId || !base?.industryId) return;
    setTarget(null);
    setData(null);
    setContext(null);
    setError("");
    apiFetchJson(`/api/compare/context?cell=${base.areaId}:${base.industryId}`)
      .then((d) => {
        setContext(d);
        if (!manual && d.contrast) {
          setTarget({ areaId: d.contrast.area_id, industryId: d.contrast.industry_id });
        }
      })
      .catch((err) => setError(describeApiError(err)));
  }, [base]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!base?.areaId || !target?.areaId) return;
    if (base.areaId === target.areaId && base.industryId === target.industryId) {
      setData(null);
      setError("서로 다른 두 상권을 골라주세요.");
      return;
    }
    setLoading(true);
    setError("");
    const q = new URLSearchParams({
      left: `${base.areaId}:${base.industryId}`,
      right: `${target.areaId}:${target.industryId}`,
    });
    apiFetchJson(`/api/compare?${q}`)
      .then(setData)
      .catch((err) => { setData(null); setError(describeApiError(err)); })
      .finally(() => setLoading(false));
  }, [base, target]);

  const pick = (setter, cur) => (areaId, industryId) => {
    const area = options?.areas.find((a) => a.id === areaId);
    const available = area?.industries.map((i) => i.id) ?? [];
    const next = industryId ?? (available.includes(cur?.industryId) ? cur.industryId : available[0]);
    setter({ areaId, industryId: next });
  };

  const exportCsv = () => {
    if (!data) return;
    downloadCsv({
      filename: `상권비교_${data.left.area_name}_${data.right.area_name}`,
      subtitle: `${data.left.area_name} ${data.left.industry_name} vs ${data.right.area_name} ${data.right.industry_name}`,
      headers: ["지표", data.left.area_name, data.right.area_name, "차이", "시그마", "폐업률 상관", "판정"],
      rows: data.diffs.map((d) => [
        d.label,
        csvNum(d.left, d.decimals),
        csvNum(d.right, d.decimals),
        d.comparable ? csvNum(d.delta, d.decimals) : "",
        d.sigma != null ? csvNum(d.sigma, 2) : "",
        d.industry_correlation != null ? csvNum(d.industry_correlation, 2) : "",
        d.comparable ? (d.explains ? "설명 후보" : "비교 가능") : (d.reason === "sample" ? "판단 보류(표본부족)" : "차이 없음"),
      ]),
      meta: thresholds,
    });
  };

  const rankLabel = context?.industry_rank
    ? `${context.industry_name} ${context.industry_eligible_cells}곳 중 ${context.industry_rank}위`
    : null;

  return (
    <div>
      <h1 className="t-h1" style={{ margin: 0 }}>상권 비교</h1>
      <p className="t-body" style={{ color: "var(--ink-muted)", margin: "8px 0 0" }}>
        기준 상권을 고르면 같은 업종 안에서의 위치와 비교할 만한 상권을 함께 제시합니다.
      </p>

      <div className="card" style={{ padding: 18, marginTop: 18, display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
        <CellPicker label="기준 상권" options={options} areaId={base?.areaId} industryId={base?.industryId} onChange={pick(setBase, base)} />
        <div style={{ flex: "1 1 240px", minWidth: 0 }}>
          <div className="t-eyebrow" style={{ color: "var(--ink-faint)", marginBottom: 6, display: "flex", gap: 8 }}>
            <span>비교 상권</span>
            <button
              onClick={() => setManual((v) => !v)}
              className="t-caption"
              style={{ marginLeft: "auto", border: "none", background: "none", cursor: "pointer", color: "var(--primary)", fontWeight: 600, padding: 0 }}
            >
              {manual ? "추천으로" : "직접 선택"}
            </button>
          </div>
          {manual ? (
            <CellPicker options={options} areaId={target?.areaId} industryId={target?.industryId} onChange={pick(setTarget, target)} />
          ) : (
            <div className="t-body-sm" style={{ color: "var(--ink-muted)", padding: "8px 0" }}>
              {data ? `${data.right.area_name} · ${data.right.industry_name}` : "아래 후보에서 선택"}
            </div>
          )}
        </div>
      </div>

      {/* 오류는 --error. --accent-orange는 "주의" 등급 색이라 의미가 겹친다. */}
      {error && <div className="t-body-sm" style={{ color: "var(--error)" }}>{error}</div>}

      {context && (
        <section style={{ marginTop: 30 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <h2 className="t-title" style={{ margin: 0 }}>같은 업종 상권 순위</h2>
            {rankLabel && (
              <span className="t-caption" style={{ fontWeight: 600, color: "var(--ink-muted)", background: "var(--surface-container)", borderRadius: "var(--radius-full)", padding: "2px 10px" }}>
                {rankLabel}
              </span>
            )}
          </div>
          <div className="card" style={{ padding: "20px 24px" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
              <span className="t-h3">{context.area_name}</span>
              <span className="t-caption" style={{ color: "var(--ink-muted)" }}>
                {context.industry_name} · 점포 {num(context.store_count)}곳
              </span>
              <span style={{ marginLeft: "auto", textAlign: "right" }}>
                <span className="t-metric" style={{ fontSize: 26 }}>
                  {fmt(context.cumulative_closure_rate_pct, 2)}%
                </span>
                <span className="t-caption" style={{ display: "block", color: "var(--ink-muted)", marginTop: 2 }}>
                  최근 1년 누적 폐업률
                </span>
              </span>
            </div>
            {context.sample_insufficient ? (
              <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "14px 0 0" }}>
                표본 기준 미달로 업종 내 순위를 내지 않습니다.
              </p>
            ) : (
              <div style={{ marginTop: 16 }}>
                <IndustryRanking
                  context={context}
                  targetAreaId={data?.right?.area_id}
                  onPick={(row) => setTarget({ areaId: row.area_id, industryId: context.industry_id })}
                />
              </div>
            )}
          </div>
        </section>
      )}

      {context && !manual && (context.contrast || context.similar) && (
        <section style={{ marginTop: 30 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <h2 className="t-title" style={{ margin: 0 }}>비교 후보</h2>
            <span className="t-caption" style={{ color: "var(--ink-faint)" }}>
              점포 {num(context.peer_store_min)}~{num(context.peer_store_max)}곳 · {context.peers.length}곳
            </span>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <PeerCard
              peer={context.contrast}
              base={context.cumulative_closure_rate_pct}
              tone="contrast"
              caption="가장 대조적인 상권"
              onPick={(p) => setTarget({ areaId: p.area_id, industryId: p.industry_id })}
            />
            <PeerCard
              peer={context.similar}
              base={context.cumulative_closure_rate_pct}
              tone="similar"
              caption="가장 비슷한 상권"
              onPick={(p) => setTarget({ areaId: p.area_id, industryId: p.industry_id })}
            />
          </div>

          {context.peers.length > 2 && (
            <details style={{ marginTop: 12 }}>
              <summary className="t-caption" style={{ cursor: "pointer", color: "var(--ink-muted)", padding: "6px 0" }}>
                후보 {context.peers.length}곳 전체
              </summary>
              <div className="card" style={{ marginTop: 8, padding: 0, overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 460 }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--hairline)" }}>
                      {["읍면동", "점포", "폐업률", "기준 대비", ""].map((h, i) => (
                        <th key={h || i} className="t-eyebrow" style={{ textAlign: i === 0 ? "left" : "right", padding: "10px 14px", color: "var(--ink-faint)", fontWeight: 500 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {context.peers.map((p) => (
                      <tr key={p.area_id} style={{ borderBottom: "1px solid var(--hairline)" }}>
                        <td className="t-body-sm" style={{ padding: "12px 14px" }}>
                          {p.area_name}
                          {p.significant && <span className="badge badge-neutral" style={{ marginLeft: 8 }}>구분됨</span>}
                        </td>
                        <td className="t-body-sm" style={{ padding: "12px 14px", textAlign: "right", color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}>{num(p.store_count)}</td>
                        <td className="t-body-sm" style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{fmt(p.cumulative_closure_rate_pct, 2)}%</td>
                        <td className="t-body-sm" style={{ padding: "12px 14px", textAlign: "right", color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}>
                          {p.delta_pp > 0 ? "+" : ""}{fmt(p.delta_pp, 2)}%p
                        </td>
                        <td style={{ padding: "10px 14px", textAlign: "right" }}>
                          <button
                            className="t-caption"
                            style={{ border: "none", background: "none", cursor: "pointer", color: "var(--primary)", fontWeight: 600, padding: 0 }}
                            onClick={() => setTarget({ areaId: p.area_id, industryId: p.industry_id })}
                          >
                            비교
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </section>
      )}

      {loading && <div className="t-body-sm" style={{ color: "var(--ink-muted)", marginTop: 24 }}>불러오는 중…</div>}

      {!loading && data && (
        <section style={{ marginTop: 30 }}>
          <div className="card" style={{ padding: 22 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 16, alignItems: "start" }}>
              {[["left", "left"], ["", ""], ["right", "right"]].map(([key, align], i) =>
                key === "" ? (
                  <div key="vs" className="t-caption" style={{ color: "var(--ink-faint)", paddingTop: 4 }}>vs</div>
                ) : (
                  <div key={key} style={{ textAlign: align }}>
                    <Link
                      to={`/cells/${data[key].area_id}/${data[key].industry_id}`}
                      className="t-title"
                      style={{ color: "var(--on-surface)", textDecoration: "none" }}
                    >
                      {data[key].area_name} · {data[key].industry_name}
                    </Link>
                    <div style={{ display: "flex", gap: 6, marginTop: 8, justifyContent: align === "right" ? "flex-end" : "flex-start", flexWrap: "wrap" }}>
                      <GradeBadge grade={data[key].risk_grade} />
                      <TypeBadge type={data[key].cell_type} />
                    </div>
                    {data[key].interval && (
                      <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 8, fontVariantNumeric: "tabular-nums" }}>
                        95% 구간 {fmt(data[key].interval.lower_pct, 2)}~{fmt(data[key].interval.upper_pct, 2)}%
                        {data[key].interval.approximate && " (근사)"}
                      </div>
                    )}
                  </div>
                ),
              )}
            </div>

            <div style={{ display: "flex", alignItems: "center", marginTop: 22, marginBottom: 4 }}>
              <h3 className="t-eyebrow" style={{ margin: 0, color: "var(--ink-faint)" }}>무엇이 다른가</h3>
              <button className="btn-utility" style={{ marginLeft: "auto" }} onClick={exportCsv}>CSV 내려받기</button>
            </div>
            <div style={{ marginTop: 10 }}>
              <DiffRows data={data} />
            </div>

            {(() => {
              const hits = data.diffs.filter((d) => d.explains);
              if (!data.industry_cells) return null;
              return (
                <div className="t-body-sm" style={{ marginTop: 16, color: "var(--ink-secondary)", lineHeight: 1.8 }}>
                  {hits.length > 0 ? (
                    <>
                      <span style={{ color: "var(--accent-orange)" }}>●</span>{" "}
                      <b>{hits.map((d) => d.label).join(" · ")}</b>
                      {" "}— 이 업종({data.industry_cells}곳)에서 폐업률과 함께 움직였고 두 상권의 차이도 큽니다.
                      현장에서 먼저 확인할 후보입니다.
                    </>
                  ) : (
                    <>이 업종({data.industry_cells}곳)에서는 폐업률과 뚜렷하게 함께 움직인 지표가 없습니다. 차이의 원인을 지표로 좁히기 어렵습니다.</>
                  )}
                </div>
              );
            })()}

            {data.diffs.find((d) => !d.comparable)?.note && (
              <div
                className="t-caption"
                style={{
                  color: "var(--ink-secondary)", background: "var(--surface-container-low)",
                  padding: "10px 14px", borderRadius: "var(--radius-md)", marginTop: 16, lineHeight: 1.6,
                }}
              >
                {data.diffs.find((d) => !d.comparable).note}
              </div>
            )}
          </div>

          {data.trend?.length > 2 && (
            <div className="card" style={{ padding: 22, marginTop: 14 }}>
              <h3 className="t-eyebrow" style={{ margin: "0 0 4px", color: "var(--ink-faint)" }}>분기별 누적 폐업률</h3>
              <p className="t-body-sm" style={{ margin: "0 0 14px", color: "var(--ink-muted)" }}>
                최신 분기만으로는 원래 높았던 상권과 최근 높아진 상권이 구분되지 않습니다.
              </p>
              <TrendOverlay trend={data.trend} leftName={data.left.area_name} rightName={data.right.area_name} />
            </div>
          )}

          <ConditionCard data={data} />
          <PrescriptionCard data={data} />

          <div className="card" style={{ padding: "16px 20px", marginTop: 14, borderLeft: "3px solid var(--primary)" }}>
            <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>판단</div>
            <p className="t-body" style={{ margin: "6px 0 0", color: "var(--on-surface)", lineHeight: 1.7 }}>{data.verdict}</p>
          </div>
        </section>
      )}

      <MethodNote basis={data?.basis} notice={data?.notice} context={context} />
    </div>
  );
}
