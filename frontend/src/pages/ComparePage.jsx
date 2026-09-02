import { useEffect, useRef, useState } from "react";
import CellPickerDialog from "../components/CellPickerDialog";
import usePublicQuery from "../hooks/usePublicQuery";
import { apiFetchJson, describeApiError } from "../lib/api";
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

/** 같은 업종 상권 순위.
 *
 *  산점도를 걷어냈다. 두 축을 동시에 읽히게 하려면 담당자가 사분면 규칙을 먼저 외워야
 *  하는데, 정작 알고 싶은 것은 "이 둘이 27곳 중 어디쯤이고 그 사이에 누가 있는가"다.
 *  순위 막대는 위치·간격·이웃을 한 번에 보여준다. 유형은 배지로 옆에 붙인다.
 */
function IndustryRanking({ context, targetAreaId, onPick }) {
  const all = context?.distribution ?? [];
  // 18줄을 항상 펼치면 표 하나가 880px을 먹고, 정작 결론이 그만큼 아래로 밀린다.
  // 기본은 "상위 3 + 내 상권 주변"만 보여주고 나머지는 펼쳐서 본다.
  const [expanded, setExpanded] = useState(false);
  if (all.length < 3) return null;
  const max = Math.max(...all.map((r) => r.cumulative_closure_rate_pct), 1);
  const median = context.industry_median_pct;

  let rows = all;
  let hiddenCount = 0;
  if (!expanded && all.length > 8) {
    const selfIndex = all.findIndex((r) => r.is_self);
    const keep = new Set([0, 1, 2]);
    if (selfIndex >= 0) [selfIndex - 1, selfIndex, selfIndex + 1].forEach((i) => { if (i >= 0 && i < all.length) keep.add(i); });
    if (targetAreaId != null) {
      const t = all.findIndex((r) => r.area_id === targetAreaId);
      if (t >= 0) keep.add(t);
    }
    rows = all.filter((_, i) => keep.has(i));
    hiddenCount = all.length - rows.length;
  }

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
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="t-caption"
          style={{
            width: "100%", marginTop: 8, padding: "8px 0", cursor: "pointer",
            border: "1px dashed var(--hairline)", background: "transparent",
            borderRadius: "var(--radius-sm)", color: "var(--primary)", fontWeight: 600,
          }}
        >
          가운데 {hiddenCount}곳 더 보기 (전체 {all.length}곳)
        </button>
      )}
      <div className="t-body-sm" style={{ color: "var(--ink-faint)", marginTop: 12 }}>
        가는 세로선은 업종 중위값 {fmt(median, 2)}%. 이름을 누르면 그 상권과 비교합니다.
      </div>
    </div>
  );
}

/** 상단 고정 비교 바.
 *
 *  예전에는 드롭다운 두 개와 "아래 후보에서 선택"이 한 카드에 섞여 있었고, 스크롤하면
 *  화면 밖으로 사라졌다. 페이지가 3,400px이라 아래쪽에서는 무엇과 무엇을 비교하는 중인지
 *  알 수 없었다. 지금은 두 상권이 항상 화면 위에 붙어 있고, 슬롯을 누르면 고르는 창이 뜬다.
 */
const CompareSlot = ({ cell, rank, role, onEdit }) => (
    <button
      type="button"
      onClick={onEdit}
      className="compare-slot"
      style={{
        flex: "1 1 240px", minWidth: 0, textAlign: "left", cursor: "pointer",
        border: "1px solid var(--hairline)", borderRadius: "var(--radius-md)",
        background: "var(--surface-container-lowest)", padding: "12px 14px",
      }}
    >
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)", display: "flex", alignItems: "center", gap: 6 }}>
        {role}
        <span className="material-symbols-outlined" style={{ fontSize: 15, marginLeft: "auto", color: "var(--primary)" }}>edit</span>
      </div>
      {cell ? (
        <>
          <div className="t-title" style={{ color: "var(--on-surface)", marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {cell.area_name}
            <span className="t-caption" style={{ color: "var(--ink-muted)", fontWeight: 400, marginLeft: 6 }}>{cell.industry_name}</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
            <span className="t-metric" style={{ fontSize: 20 }}>{fmt(cell.cumulative_closure_rate_pct, 1)}%</span>
            {rank && <span className="t-caption" style={{ color: "var(--ink-faint)" }}>{rank}</span>}
          </div>
        </>
      ) : (
        <div className="t-body-sm" style={{ color: "var(--primary)", marginTop: 8, fontWeight: 600 }}>상권 선택</div>
      )}
    </button>
  );

function CompareBar({ left, right, leftRank, rightRank, onEditLeft, onEditRight, onSwap, onCsv }) {
  return (
    <div
      style={{
        position: "sticky", top: 0, zIndex: 30,
        display: "flex", alignItems: "stretch", gap: 12, flexWrap: "wrap",
        padding: "14px 16px", marginBottom: 18,
        background: "var(--surface-container-low)",
        border: "1px solid var(--hairline)", borderRadius: "var(--radius-lg)",
        boxShadow: "var(--elev-1)",
      }}
    >
      <CompareSlot cell={left} rank={leftRank} role="기준 상권" onEdit={onEditLeft} />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6, flex: "0 0 auto" }}>
        <span className="t-caption" style={{ color: "var(--ink-faint)", fontWeight: 700 }}>VS</span>
        {left && right && (
          <button
            type="button"
            onClick={onSwap}
            aria-label="기준과 비교 상권 바꾸기"
            style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--ink-muted)", padding: 2 }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>swap_horiz</span>
          </button>
        )}
      </div>
      <CompareSlot cell={right} rank={rightRank} role="비교 상권" onEdit={onEditRight} />
      {onCsv && (
        <button className="btn-utility" onClick={onCsv} style={{ flex: "0 0 auto", alignSelf: "center" }}>
          CSV
        </button>
      )}
    </div>
  );
}

/** 결론 한 장.
 *
 *  예전에는 이 문장이 3,300px 지점에 83px짜리 카드로 있었다. 담당자가 알고 싶은 건 이
 *  한 줄인데 네 번 스크롤해야 나왔다. 근거보다 먼저 놓는다.
 */
/** 받침에 따라 조사를 고른다. "동탄8동이 / 기배동이", "새솔동가"가 아니라 "새솔동이".
 *  공문서 투의 "이(가)"보다 읽기 낫고, 읍면동 이름은 숫자로 끝나는 경우까지만 보면 된다. */
const DIGIT_HAS_FINAL = { 0: true, 1: true, 3: true, 6: true, 7: true, 8: true };
function hasFinalConsonant(word) {
  const last = (word ?? "").trim().slice(-1);
  if (/[0-9]/.test(last)) return Boolean(DIGIT_HAS_FINAL[Number(last)]);
  const code = last.charCodeAt(0);
  if (Number.isNaN(code) || code < 0xac00 || code > 0xd7a3) return false;
  return (code - 0xac00) % 28 !== 0;
}
const subject = (word) => `${word}${hasFinalConsonant(word) ? "이" : "가"}`;

function VerdictHeadline({ data }) {
  const l = data.left, r = data.right;
  const lr = l.cumulative_closure_rate_pct, rr = r.cumulative_closure_rate_pct;
  const rateDiff = data.diffs?.find((d) => d.metric === "cumulative_closure_rate_pct");
  const comparable = Boolean(rateDiff?.comparable);
  const delta = comparable && lr != null && rr != null ? rr - lr : null;
  const ratio = comparable && lr > 0 && rr != null ? rr / lr : null;

  // 두 구간이 겹치지 않으면 우연으로 보기 어렵다. 겹치면 "차이가 있다"고 말하지 않는다.
  const li = l.interval, ri = r.interval;
  const separated = li && ri ? !(li.upper_pct >= ri.lower_pct && ri.upper_pct >= li.lower_pct) : null;
  const higher = delta == null ? null : delta > 0 ? r : l;

  return (
    <div
      className="card"
      style={{ padding: "22px 24px", marginBottom: 18, borderLeft: "3px solid var(--primary)" }}
    >
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>비교 결과</div>
      {comparable && delta != null ? (
        <div className="t-h2" style={{ margin: "8px 0 0", lineHeight: 1.4 }}>
          {subject(higher.area_name)} {higher === r ? l.area_name : r.area_name}보다 폐업률이{" "}
          <span style={{ color: "var(--error)" }}>{fmt(Math.abs(delta), 1)}%p</span> 높습니다
          {ratio != null && ratio > 0 && (
            <span className="t-body" style={{ color: "var(--ink-muted)", fontWeight: 500 }}>
              {" "}({fmt(ratio >= 1 ? ratio : 1 / ratio, 1)}배)
            </span>
          )}
        </div>
      ) : (
        <div className="t-h2" style={{ margin: "8px 0 0", lineHeight: 1.4 }}>
          두 상권의 폐업률은 비율로 견주지 않습니다
        </div>
      )}

      {separated != null && comparable && (
        <p className="t-body-sm" style={{ margin: "10px 0 0", color: "var(--ink-secondary)", lineHeight: 1.7 }}>
          {separated
            ? "표본 크기를 감안해도 남는 차이입니다."
            : "다만 표본이 작아 이 수치만으로는 판단하기 어렵습니다. 다른 자료를 함께 보십시오."}
        </p>
      )}

      {data.verdict && (
        <p className="t-body" style={{ margin: "14px 0 0", color: "var(--on-surface)", lineHeight: 1.75 }}>
          {data.verdict}
        </p>
      )}
    </div>
  );
}

/** 근거 구획. 접지 않고 항상 펼쳐 보인다 — 결론과 근거를 한 번에 읽는다. */
function Section({ title, caption, children }) {
  if (!children) return null;
  return (
    <section style={{ marginBottom: 12 }}>
      <div
        style={{
          display: "flex", alignItems: "baseline", gap: 10,
          padding: "12px 16px", background: "var(--surface-container-low)",
          border: "1px solid var(--hairline)", borderRadius: "var(--radius-md)",
        }}
      >
        <span className="t-title" style={{ color: "var(--on-surface)" }}>{title}</span>
        {caption && <span className="t-caption" style={{ color: "var(--ink-faint)" }}>{caption}</span>}
      </div>
      <div style={{ marginTop: 12 }}>{children}</div>
    </section>
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
  const visualRef = useRef(null);
  const rows = [...data.diffs];
  const hasSigma = rows.some((d) => d.sigma != null);
  // 설명 후보를 먼저, 그다음 차이가 큰 순. 이 업종에서 폐업률과 함께 움직이지 않는
  // 지표는 아무리 크게 벌어져 있어도 담당자가 먼저 볼 것이 아니다.
  if (hasSigma) {
    rows.sort((a, b) =>
      (b.explains ? 1 : 0) - (a.explains ? 1 : 0) ||
      Math.abs(b.sigma ?? 0) - Math.abs(a.sigma ?? 0));
  }
  useEffect(() => {
    const node = visualRef.current;
    if (!node) return undefined;
    node.classList.remove("is-visible");

    if (!("IntersectionObserver" in window)) {
      node.classList.add("is-visible");
      return undefined;
    }

    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      node.classList.add("is-visible");
      observer.disconnect();
    }, { threshold: 0.2 });
    observer.observe(node);
    return () => observer.disconnect();
  }, [data.left.area_id, data.right.area_id]);

  return (
    <div ref={visualRef} className="compare-diff-visual">
      <div className="compare-diff-legend" aria-label="양방향 막대 색상 기준">
        <span className="compare-diff-legend-side is-left">
          <i aria-hidden="true" /> {data.left.area_name}
        </span>
        <span className="compare-diff-legend-side is-right">
          {data.right.area_name} <i aria-hidden="true" />
        </span>
      </div>

      <div style={{ display: "grid", gap: 2 }}>
      {rows.map((d, index) => {
        const muted = (side) => side?.sample_insufficient && d.kind === "rate";
        const diffUnit = d.unit === "%" ? "%p" : d.unit;
        const sigma = d.sigma;
        const strength = sigma != null ? Math.min(Math.abs(sigma) / 3, 1) : 0;
        const width = strength * 50;
        const direction = sigma > 0 ? "is-left" : "is-right";
        return (
          <div
            key={d.metric}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 220px 1fr",
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
                <div
                  className="compare-diff-track"
                  role="img"
                  aria-label={`${d.label}: ${sigma > 0 ? data.left.area_name : data.right.area_name} 값이 ${Math.abs(sigma).toFixed(2)} 표준편차만큼 큼`}
                >
                  <div className="compare-diff-center" />
                  <div
                    className={`compare-diff-bar ${direction}`}
                    style={{
                      "--diff-width": `${width}%`,
                      "--diff-opacity": 0.28 + strength * 0.72,
                      "--diff-delay": `${index * 70}ms`,
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

  const LEFT_COLOR = "var(--primary)";
  const RIGHT_COLOR = "#ea580c";
  const W = 680, H = 148;
  const L = 34, R = 10, T = 10, B = 26;
  const plotW = W - L - R;
  const plotH = H - T - B;

  const values = points.flatMap((p) => [p.left_pct, p.right_pct]).filter(Number.isFinite);
  const rawMax = Math.max(...values, 1);
  // 눈금은 1·2·5 단위로 세 칸만. 촘촘한 격자는 선을 읽는 데 방해가 된다.
  const rough = (rawMax * 1.08) / 3;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const max = Math.ceil((rawMax * 1.06) / step) * step;
  const ticks = [];
  for (let v = 0; v <= max + 1e-9; v += step) ticks.push(v);

  const x = (i) => L + (i * plotW) / (points.length - 1);
  const y = (v) => T + plotH - (v / max) * plotH;
  const band = plotW / Math.max(points.length - 1, 1);

  // 값이 빈 분기에서 선을 잇지 않는다. 이어 버리면 미산출 구간이 완만한 변화로 보인다.
  const path = (key) => {
    let d = "", pen = false;
    points.forEach((p, i) => {
      const v = p[key];
      if (!Number.isFinite(v)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
    });
    return d.trim();
  };
  const lastOf = (key) => {
    for (let i = points.length - 1; i >= 0; i -= 1) {
      if (Number.isFinite(points[i][key])) return { i, v: points[i][key] };
    }
    return null;
  };

  const series = [
    { key: "left_pct", name: leftName, color: LEFT_COLOR, last: lastOf("left_pct") },
    { key: "right_pct", name: rightName, color: RIGHT_COLOR, last: lastOf("right_pct") },
  ];
  const xLabelIdx = [0, Math.floor((points.length - 1) / 2), points.length - 1];

  return (
    <div>
      <div className="t-caption" style={{ color: "var(--ink-muted)", marginBottom: 8 }}>
        세로축 — 최근 4분기 누적 폐업률 (%)
      </div>
      {/* 범례를 위에 두고 현재 값을 함께 적는다. 그래프 안에 숫자를 얹으면 선을 가린다. */}
      <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 12 }}>
        {series.map((sr) => (
          <span key={`l${sr.key}`} style={{ display: "inline-flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: sr.color, alignSelf: "center" }} />
            <span className="t-body-sm" style={{ color: "var(--ink-secondary)" }}>{sr.name}</span>
            {sr.last && (
              <b style={{ fontSize: 15, color: "var(--on-surface)", fontVariantNumeric: "tabular-nums" }}>
                {fmt(sr.last.v)}%
              </b>
            )}
          </span>
        ))}
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{ display: "block", maxWidth: W }}
        role="img"
        aria-label="분기별 최근 4분기 누적 폐업률 비교"
      >
        {ticks.map((v, i) => (
          <g key={v}>
            <line
              x1={L}
              y1={y(v)}
              x2={W - R}
              y2={y(v)}
              stroke="var(--hairline)"
              strokeWidth="1"
              strokeDasharray={i === 0 ? undefined : "3 5"}
            />
            <text x={L - 7} y={y(v) + 3.5} fontSize="10" fill="var(--ink-faint)" textAnchor="end">
              {fmt(v, v < 10 ? 1 : 0)}
            </text>
          </g>
        ))}

        {series.map((sr) => (
          <path key={`p${sr.key}`} d={path(sr.key)} fill="none" stroke={sr.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        ))}

        {/* 점은 끝에만. 분기마다 찍으면 선이 구슬 목걸이가 된다 */}
        {series.map((sr) =>
          sr.last ? (
            <circle
              key={`e${sr.key}`}
              cx={x(sr.last.i)}
              cy={y(sr.last.v)}
              r="4"
              fill={sr.color}
              stroke="var(--surface-container-lowest)"
              strokeWidth="2"
            />
          ) : null
        )}

        {xLabelIdx.map((i) => (
          <text
            key={`x${i}`}
            x={x(i)}
            y={T + plotH + 17}
            fontSize="10.5"
            fill="var(--ink-faint)"
            textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}
          >
            {points[i].label}
          </text>
        ))}

        {/* 분기마다 투명한 판을 깔아 마우스를 올리면 두 상권 값이 함께 뜬다 */}
        {points.map((p, i) => (
          <rect key={`h${p.label ?? i}`} x={x(i) - band / 2} y={T} width={band} height={plotH} fill="transparent">
            <title>
              {`${p.label}\n${leftName} ${Number.isFinite(p.left_pct) ? `${fmt(p.left_pct)}%` : "미산출"}` +
                `\n${rightName} ${Number.isFinite(p.right_pct) ? `${fmt(p.right_pct)}%` : "미산출"}`}
            </title>
          </rect>
        ))}
      </svg>
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
    ["배후 여건", "평균 업력과 배후 읍면동 등록인구입니다. 등급·유형 판정에는 쓰지 않습니다 — 폐업률과의 상관이 약하고 방향도 직관과 반대여서 판정 축으로 쓸 근거가 없습니다."],
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
  const [manualTarget, setManualTarget] = useState(null);
  const [manual, setManual] = useState(false);  // 비교 대상을 직접 고르는 모드
  const [picker, setPicker] = useState(null);   // "base" | "target" | null — 열려 있는 선택 창
  const [thresholds, setThresholds] = useState(null);
  const [optionsError, setOptionsError] = useState("");

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
      .catch((err) => setOptionsError(describeApiError(err)));
  }, []);

  const contextQuery = usePublicQuery(base?.areaId && base?.industryId
    ? `/api/compare/context?cell=${base.areaId}:${base.industryId}` : null);
  const context = contextQuery.data;
  const target = manual ? manualTarget : context?.contrast
    ? { areaId: context.contrast.area_id, industryId: context.contrast.industry_id } : null;
  const sameCell = Boolean(base && target && base.areaId === target.areaId && base.industryId === target.industryId);
  const compareParams = base?.industryId && target?.industryId && !sameCell ? new URLSearchParams({
    left: `${base.areaId}:${base.industryId}`, right: `${target.areaId}:${target.industryId}`,
  }) : null;
  const comparisonQuery = usePublicQuery(compareParams ? `/api/compare?${compareParams}` : null);
  const data = comparisonQuery.data;
  const loading = contextQuery.loading || comparisonQuery.loading;
  const error = optionsError || contextQuery.error || (sameCell ? "서로 다른 두 상권을 골라주세요." : comparisonQuery.error);
  const chooseBase = (next) => {
    if (next.areaId === base?.areaId && next.industryId === base?.industryId) return;
    setBase(next);
    setManual(false);
    setManualTarget(null);
  };
  const setTarget = (next) => { setManual(true); setManualTarget(next); };

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

  // 순위는 아래 순위표와 같은 모수를 써야 한다.
  //
  // data.left.industry_rank는 전체 읍면동(29곳) 기준이고, 아래 「같은 업종 안에서의 위치」는
  // 표본 기준을 넘은 셀(18곳) 기준이다. 한 화면에 "29곳 중 19위"와 "18곳 중 17위"가 같이
  // 뜨면 담당자는 둘 중 무엇이 맞는지 알 수 없다. 화면에서는 순위표 쪽으로 통일한다.
  const rankLabelFor = (cell) => {
    const rows = context?.distribution ?? [];
    const total = context?.industry_eligible_cells ?? rows.length;
    if (!cell || !total || cell.industry_id !== context?.industry_id) return null;
    const row = rows.find((r) => r.area_id === cell.area_id);
    return row ? `${total}곳 중 ${row.rank}위` : null;
  };

  const explainHits = data?.diffs?.filter((d) => d.explains) ?? [];

  return (
    /* 3층 구조 (2026-08-29 재편).
     *
     *  예전 배치는 [선택] → [순위표 880px] → [지표 대비 1,085px] → … → [판단 83px] 순서로
     *  전체 3,400px였다. 담당자가 알고 싶은 결론이 제일 아래에 제일 작게 있었고, 비교
     *  페이지인데 비교 결과가 두 번째였다. 스크롤하면 무엇과 무엇을 견주는 중인지도 사라졌다.
     *
     *  지금은 세 층이다.
     *    1층  화면 위에 붙는 비교 바 — 무엇과 무엇인지 항상 보인다. 고르는 건 팝업.
     *    2층  결론 — 몇 %p 차이인지, 그 차이를 믿어도 되는지.
     *    3층  근거 — 전부 접어 둔다. 궁금한 것만 편다.
     */
    <div className="official-page official-compare-page">
      <CompareBar
        left={data?.left ?? (context ? { area_name: context.area_name, industry_name: context.industry_name, cumulative_closure_rate_pct: context.cumulative_closure_rate_pct } : null)}
        right={data?.right}
        leftRank={data ? rankLabelFor(data.left) : rankLabel}
        rightRank={data ? rankLabelFor(data.right) : null}
        onEditLeft={() => setPicker("base")}
        onEditRight={() => setPicker("target")}
        onSwap={() => {
          if (!data) return;
          const nextBase = { areaId: data.right.area_id, industryId: data.right.industry_id };
          const nextTarget = { areaId: data.left.area_id, industryId: data.left.industry_id };
          setManual(true);
          setBase(nextBase);
          setTarget(nextTarget);
        }}
        onCsv={data ? exportCsv : null}
      />

      {error && <div className="t-body-sm" style={{ color: "var(--error)", marginBottom: 14 }}>{error}</div>}
      {loading && <div className="t-body-sm" style={{ color: "var(--ink-muted)", marginBottom: 14 }}>불러오는 중…</div>}

      {!loading && data && <VerdictHeadline data={data} />}

      {!loading && !data && context && (
        <div className="card" style={{ padding: "22px 24px", marginBottom: 18 }}>
          <div className="t-title">비교할 상권을 고르면 결과가 나옵니다</div>
          <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "8px 0 0", lineHeight: 1.7 }}>
            {context.contrast || context.similar
              ? "위 비교 상권 칸을 누르거나, 아래 「비교 후보」에서 추천 상권을 고르시면 됩니다."
              : "이 상권은 점포 규모가 비슷한 후보가 없어 추천을 내지 못했습니다. 아래 목록에서 직접 고르시면 됩니다."}
          </p>
        </div>
      )}

      {/* ── 3층: 근거 ───────────────────────────────────────────────── */}

      {data && (
        <Section title="무엇이 다른가" caption="지표별 차이와 유의성">
          <div className="card" style={{ padding: 22 }}>
            <DiffRows data={data} />
            {data.industry_cells && (
              <div className="t-body-sm" style={{ marginTop: 16, color: "var(--ink-secondary)", lineHeight: 1.8 }}>
                {explainHits.length > 0 ? (
                  <>
                    <span style={{ color: "var(--accent-orange)" }}>●</span>{" "}
                    <b>{explainHits.map((d) => d.label).join(" · ")}</b>
                    {" "}— 이 업종({data.industry_cells}곳)에서 폐업률과 함께 움직였고 두 상권의 차이도 큽니다.
                    현장에서 먼저 확인할 후보입니다.
                  </>
                ) : (
                  <>이 업종({data.industry_cells}곳)에서는 폐업률과 뚜렷하게 함께 움직인 지표가 없습니다. 차이의 원인을 지표로 좁히기 어렵습니다.</>
                )}
              </div>
            )}
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
        </Section>
      )}

      {data?.trend?.length > 2 && (
        <Section title="폐업률 분기별 추이" caption="원래 높았나, 최근 높아졌나">
          <div className="card" style={{ padding: 18 }}>
            <TrendOverlay trend={data.trend} leftName={data.left.area_name} rightName={data.right.area_name} />
          </div>
        </Section>
      )}

      {data && (
        <Section title="배후 여건과 상권 유형" caption="인구·업력·유형">
          <ConditionCard data={data} />
          <PrescriptionCard data={data} />
        </Section>
      )}

      {context && !context.sample_insufficient && (
        <Section title="같은 업종 안에서의 위치" caption={rankLabel ?? undefined}>
          <div className="card" style={{ padding: "20px 24px" }}>
            <IndustryRanking
              context={context}
              targetAreaId={data?.right?.area_id}
              onPick={(row) => setTarget({ areaId: row.area_id, industryId: context.industry_id })}
            />
          </div>
        </Section>
      )}

      {context && (context.contrast || context.similar) && (
        <Section
          title="비교 후보"
          caption={`점포 ${num(context.peer_store_min)}~${num(context.peer_store_max)}곳 · ${context.peers.length}곳`}
        >
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
        </Section>
      )}

      {context?.sample_insufficient && (
        <div className="t-body-sm" style={{ color: "var(--ink-muted)", marginBottom: 14 }}>
          기준 상권이 표본 기준에 미달해 업종 내 순위를 내지 않습니다.
        </div>
      )}

      {picker === "base" && <CellPickerDialog
        title="기준 상권 선택" options={options} value={base}
        onApply={chooseBase}
        onClose={() => setPicker(null)}
      />}
      {picker === "target" && <CellPickerDialog
        title="비교 상권 선택" options={options} value={target}
        onApply={setTarget}
        onClose={() => setPicker(null)} peers={context?.peers ?? []}
      />}

      <MethodNote basis={data?.basis} notice={data?.notice} context={context} />
    </div>
  );
}
