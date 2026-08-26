import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson } from "../lib/api";
import ProvisionalNotice from "../components/ProvisionalNotice";

// 상권 비교 — 서울 프로젝트('노다지')의 지역 비교/업종 비교를 하나로 합친 화면.
//
// 노다지 비교 카드는 두 값을 나란히 놓고 끝냈다. 여기서는 "그 차이를 말해도 되는가"를 먼저
// 따진다. 점포 55곳과 60곳 상권에서 폐업이 1건 다르면 폐업률은 1.7%p 벌어져 보이지만
// 표본 크기의 산물이다. 서버가 두 비율 z검정으로 판정해 comparable=false를 내려주면
// 화면은 숫자 대신 "차이 없음"을 보여준다.
//
// 등급이 "위험"과 "주의"로 갈렸는데도 통계적으로는 구분되지 않는 조합이 실제로 있다.
// 등급은 상위 10%/30%로 자른 상대 순위라 경계 근처에서 필연적으로 생기는 일이고,
// 이 화면이 그걸 드러내는 유일한 곳이다. 숨기지 말 것.

const TYPE_TONE = {
  고회전: "var(--accent-orange)",
  쇠퇴: "var(--primary)",
  성장: "var(--ink-muted)",
  정체: "var(--ink-muted)",
};

const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

function CellPicker({ label, options, areaId, industryId, onChange }) {
  const area = options?.areas.find((a) => a.id === areaId);
  const names = useMemo(
    () => Object.fromEntries((options?.industries ?? []).map((i) => [i.id, i.name])),
    [options],
  );

  return (
    <div style={{ flex: "1 1 240px", minWidth: 0 }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)", marginBottom: 6 }}>{label}</div>
      <div style={{ display: "flex", gap: 8 }}>
        <select
          value={areaId ?? ""}
          onChange={(e) => onChange(Number(e.target.value), null)}
          style={{ flex: "1 1 0", minWidth: 0 }}
        >
          {(options?.areas ?? []).map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
        <select
          value={industryId ?? ""}
          onChange={(e) => onChange(areaId, Number(e.target.value))}
          style={{ flex: "1 1 0", minWidth: 0 }}
        >
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

function CellHead({ cell, align }) {
  if (!cell) return <div />;
  return (
    <div style={{ textAlign: align }}>
      <Link
        to={`/cells/${cell.area_id}/${cell.industry_id}`}
        className="t-title"
        style={{ color: "var(--on-surface)", textDecoration: "none" }}
      >
        {cell.area_name} · {cell.industry_name}
      </Link>
      <div style={{ display: "flex", gap: 6, marginTop: 8, justifyContent: align === "right" ? "flex-end" : "flex-start", flexWrap: "wrap" }}>
        {cell.risk_grade && (
          <span className={cell.risk_grade === "위험" ? "badge badge-danger" : "badge"}>{cell.risk_grade}</span>
        )}
        {cell.cell_type && cell.cell_type !== "유형판정보류" && (
          <span className="badge" style={{ color: TYPE_TONE[cell.cell_type] ?? "var(--ink-muted)" }}>
            {cell.cell_type}
          </span>
        )}
        {cell.industry_rank && (
          <span className="badge" style={{ color: "var(--ink-muted)" }}>
            업종 내 {cell.industry_rank}/{cell.industry_total_areas}위
          </span>
        )}
      </div>
      {cell.interval && (
        <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 8, fontVariantNumeric: "tabular-nums" }}>
          95% 구간 {fmt(cell.interval.lower_pct, 2)}~{fmt(cell.interval.upper_pct, 2)}%
          {cell.interval.approximate && " (근사)"}
        </div>
      )}
    </div>
  );
}

export default function ComparePage() {
  const [options, setOptions] = useState(null);
  const [left, setLeft] = useState(null);    // {areaId, industryId}
  const [right, setRight] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetchJson("/api/compare/options")
      .then((d) => {
        setOptions(d);
        // 기본값은 "같은 업종, 다른 동" — 비교의 가장 흔한 형태다.
        // 양쪽 다 표본충분인 조합을 고른다. 표본부족 셀이 기본으로 걸리면 페이지가 열리자마자
        // "판단보류"만 보여주게 되고, 이 화면이 무엇을 하는 곳인지 전달되지 않는다.
        const areas = d.areas ?? [];
        const ok = (a, industryId) =>
          a.industries.some((x) => x.id === industryId && !x.sample_insufficient);
        for (const a of areas) {
          for (const i of a.industries) {
            if (i.sample_insufficient) continue;
            const other = areas.find((b) => b.id !== a.id && ok(b, i.id));
            if (other) {
              setLeft({ areaId: a.id, industryId: i.id });
              setRight({ areaId: other.id, industryId: i.id });
              return;
            }
          }
        }
        if (areas.length >= 2) {
          setLeft({ areaId: areas[0].id, industryId: areas[0].industries[0]?.id });
          setRight({ areaId: areas[1].id, industryId: areas[1].industries[0]?.id });
        }
      })
      .catch(() => setError("선택지를 불러오지 못했습니다."));
  }, []);

  useEffect(() => {
    if (!left?.areaId || !left?.industryId || !right?.areaId || !right?.industryId) return;
    if (left.areaId === right.areaId && left.industryId === right.industryId) {
      setData(null);
      setError("서로 다른 두 상권을 골라주세요.");
      return;
    }
    setLoading(true);
    setError("");
    const q = new URLSearchParams({
      left: `${left.areaId}:${left.industryId}`,
      right: `${right.areaId}:${right.industryId}`,
    });
    apiFetchJson(`/api/compare?${q}`)
      .then(setData)
      .catch(() => { setData(null); setError("비교 결과를 불러오지 못했습니다."); })
      .finally(() => setLoading(false));
  }, [left, right]);

  // 동을 바꾸면 그 동에 없는 업종이 선택된 채로 남을 수 있다 -> 첫 업종으로 되돌린다
  const pick = (setter, cur) => (areaId, industryId) => {
    const area = options?.areas.find((a) => a.id === areaId);
    const available = area?.industries.map((i) => i.id) ?? [];
    const next = industryId ?? (available.includes(cur?.industryId) ? cur.industryId : available[0]);
    setter({ areaId, industryId: next });
  };

  return (
    <div>
      <h1 className="t-h1" style={{ margin: 0 }}>상권 비교</h1>
      <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0", maxWidth: 660 }}>
        두 상권을 나란히 놓고 봅니다. 폐업률 차이가 <b>표본 크기로 설명될 수 있는 크기</b>면
        어느 쪽이 나쁘다고 말하지 않고 &ldquo;차이 없음&rdquo;으로 표시합니다.
      </p>

      <div style={{ margin: "16px 0 0" }}>
        <ProvisionalNotice />
      </div>

      <div className="card" style={{ padding: 18, margin: "18px 0", display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
        <CellPicker label="왼쪽 상권" options={options} areaId={left?.areaId} industryId={left?.industryId} onChange={pick(setLeft, left)} />
        <div className="t-caption" style={{ color: "var(--ink-faint)", padding: "0 4px 8px" }}>vs</div>
        <CellPicker label="오른쪽 상권" options={options} areaId={right?.areaId} industryId={right?.industryId} onChange={pick(setRight, right)} />
      </div>

      {loading && <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>}
      {error && <div className="t-body-sm" style={{ color: "var(--accent-orange)" }}>{error}</div>}

      {!loading && data && (
        <>
          <div className="card" style={{ padding: 20 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 16, alignItems: "start" }}>
              <CellHead cell={data.left} align="left" />
              <div className="t-caption" style={{ color: "var(--ink-faint)", paddingTop: 4 }}>vs</div>
              <CellHead cell={data.right} align="right" />
            </div>

            <div style={{ overflowX: "auto", marginTop: 18 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 520 }}>
                <tbody>
                  {data.diffs.map((d) => {
                    // 방향 화살표를 쓰지 않는다. 가운데 열에 놓인 ▲/▼는 "왼쪽이 크다"는 뜻인지
                    // "늘었다"는 뜻인지 구별되지 않아 시계열 증감으로 오독된다. 두 값이 바로
                    // 옆에 있으므로 대소는 눈으로 읽으면 되고, 작은 쪽을 흐리게 해서 거든다.
                    // 어느 쪽이 "나쁜지"는 칠하지 않는다 — 폐업률은 높은 쪽이, 개업률은 낮은 쪽이
                    // 나쁘고, 지표마다 방향을 판정해 색을 주면 AI가 판단한다는 인상이 된다.
                    // 판단은 아래 콜아웃 한 곳에서만 한다.
                    const muted = (side) => side?.sample_insufficient && d.kind === "rate";
                    const diffUnit = d.unit === "%" ? "%p" : d.unit;
                    const bigger =
                      d.left === null || d.right === null || d.left === d.right
                        ? null
                        : d.left > d.right ? "left" : "right";
                    const cell = (value, side, which) => (
                      <td
                        style={{
                          padding: "12px 8px",
                          textAlign: which === "left" ? "right" : "left",
                          width: "30%",
                          fontVariantNumeric: "tabular-nums",
                          color: muted(side)
                            ? "var(--ink-faint)"
                            : bigger && bigger !== which
                              ? "var(--ink-muted)"
                              : "var(--on-surface)",
                        }}
                      >
                        <b>{fmt(value, d.decimals)}</b>{d.unit}
                        {muted(side) && (
                          <span className="t-caption" style={{ color: "var(--ink-faint)" }}> (표본부족)</span>
                        )}
                      </td>
                    );
                    return (
                      <tr key={d.metric} style={{ borderTop: "1px solid var(--hairline)" }}>
                        {cell(d.left, data.left, "left")}
                        <td className="t-caption" style={{ padding: "12px 12px", textAlign: "center", color: "var(--ink-faint)", whiteSpace: "nowrap" }}>
                          <div>{d.label}</div>
                          <div style={{ marginTop: 3, color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}>
                            {!d.comparable
                              ? (d.reason === "sample" ? "판단 보류" : "차이 없음")
                              : d.delta === null || d.delta === undefined
                                ? "—"
                                : `차이 ${fmt(Math.abs(d.delta), d.decimals)}${diffUnit}`}
                          </div>
                        </td>
                        {cell(d.right, data.right, "right")}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {data.diffs.find((d) => !d.comparable)?.note && (
              <div
                className="t-caption"
                style={{
                  color: "var(--ink-secondary)",
                  background: "var(--surface-container-low)",
                  padding: "10px 14px",
                  borderRadius: "var(--radius-md)",
                  marginTop: 16,
                  lineHeight: 1.6,
                }}
              >
                {data.diffs.find((d) => !d.comparable).note}
              </div>
            )}
          </div>

          <div
            className="card"
            style={{ padding: "16px 20px", marginTop: 14, borderLeft: "3px solid var(--primary)" }}
          >
            <div className="t-eyebrow" style={{ color: "var(--ink-faint)" }}>판단</div>
            <p className="t-body" style={{ margin: "6px 0 0", color: "var(--on-surface)", lineHeight: 1.7 }}>
              {data.verdict}
            </p>
          </div>

          <p className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 14, maxWidth: 680, lineHeight: 1.7 }}>
            {data.notice}
            <br />
            기준 {data.basis.quarter_label} · 최근 {data.basis.window_quarters}분기 누적 ·
            판정 {data.basis.method} · 신뢰수준 {data.basis.confidence_level}
          </p>
        </>
      )}
    </div>
  );
}
