import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { apiFetch, apiFetchJson, describeApiError } from "../lib/api";
import { GradeBadge, TypeBadge } from "../components/Badge";
import ProvisionalNotice from "../components/ProvisionalNotice";

// 세 영역을 절대 섞지 않는다(CLAUDE.md 용어 규칙).
//   ① 확인된 위험 신호   관측 데이터로 직접 계산된 사실
//   ② AI 예측 기여 요인   모델의 내부 근거. 인과 아님
//   ③ 공무원 확인 필요    데이터가 없어 모델이 보지 못한 원인 후보

const WINDOW_LABEL = 4;

const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

function Section({ title, note, children }) {
  return (
    <section style={{ marginTop: 28 }}>
      <h2 className="t-title" style={{ margin: 0 }}>{title}</h2>
      {note && (
        <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "4px 0 12px" }}>{note}</p>
      )}
      <div style={{ marginTop: note ? 0 : 12 }}>{children}</div>
    </section>
  );
}

/** 누적 폐업률 추이. 외부 차트 라이브러리 없이 SVG로 그린다.
 *
 * 누적값은 4분기가 쌓여야 나오므로 셀의 앞 4분기는 값이 없다(null). 예전에는 백엔드가
 * 그 null을 0.0%로 바꿔 내려서 모든 셀의 선이 0%에서 시작해 4분기째 급등하는 모양이
 * 됐다 — "값이 없음"이 "폐업이 없었음"으로 읽혔다(2026-08-25 감사).
 * 지금은 null이 그대로 오므로 걸러내고, 몇 분기가 빠졌는지 아래에 적는다.
 */
function TrendChart({ rows }) {
  const points = rows.filter((r) => Number.isFinite(r.cumulative_closure_rate_pct));
  const skipped = rows.length - points.length;
  if (points.length < 2) {
    return <div className="t-caption" style={{ color: "var(--ink-muted)" }}>추이를 그릴 자료가 부족합니다.</div>;
  }
  const W = 640;
  const H = 160;
  const PAD = 28;
  const max = Math.max(...points.map((p) => p.cumulative_closure_rate_pct), 1) * 1.15;
  const x = (i) => PAD + (i * (W - PAD * 2)) / (points.length - 1);
  const y = (v) => H - PAD - (v / max) * (H - PAD * 2);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.cumulative_closure_rate_pct)}`).join(" ");
  const last = points[points.length - 1];

  return (
    <div style={{ overflowX: "auto" }}>
      <svg width={W} height={H} role="img" aria-label="분기별 누적 폐업률 추이">
        <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="var(--hairline)" />
        <path d={path} fill="none" stroke="var(--primary)" strokeWidth="2" />
        <circle cx={x(points.length - 1)} cy={y(last.cumulative_closure_rate_pct)} r="4" fill="var(--primary)" />
        <text x={PAD} y={16} fontSize="11" fill="var(--ink-faint)">{fmt(max)}%</text>
        <text x={PAD} y={H - 8} fontSize="11" fill="var(--ink-faint)">{points[0].label}</text>
        <text x={W - PAD} y={H - 8} fontSize="11" fill="var(--ink-faint)" textAnchor="end">{last.label}</text>
      </svg>
      {skipped > 0 && (
        <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 4 }}>
          앞 {skipped}개 분기는 누적 {WINDOW_LABEL}분기가 채워지지 않아 값이 없습니다. 0%가 아니라 미산출입니다.
        </div>
      )}
    </div>
  );
}

/** 3중 비교 — 숫자 하나로는 의미가 없다. 세 방향으로 비교해야 원인의 위치가 좁혀진다. */
function Comparison({ value, comparison }) {
  const rows = [
    { label: "이 상권", value, tone: "var(--primary)" },
    { label: "같은 업종 평균", value: comparison?.industry_avg_pct, tone: "var(--outline-variant)" },
    { label: "같은 읍면동 평균", value: comparison?.area_avg_pct, tone: "var(--outline-variant)" },
    { label: "화성시 전체 평균", value: comparison?.city_avg_pct, tone: "var(--outline-variant)" },
  ];
  const max = Math.max(...rows.map((r) => (Number.isFinite(r.value) ? r.value : 0)), 1);
  return (
    <div>
      {rows.map((r) => (
        <div key={r.label} style={{ marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
            <span className="t-caption" style={{ color: "var(--ink-muted)" }}>{r.label}</span>
            <span className="t-metric" style={{ fontSize: 16, fontVariantNumeric: "tabular-nums" }}>{fmt(r.value)}%</span>
          </div>
          <div style={{ height: 7, background: "var(--surface-container)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
            <div style={{
              width: `${Math.min(100, ((Number.isFinite(r.value) ? r.value : 0) / max) * 100)}%`,
              height: "100%", background: r.tone, borderRadius: "var(--radius-full)",
            }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** 지원사업 1건. 매칭 조건(우리 로직)과 자격 요건(공고문 확인 필요)을 시각적으로 분리한다. */
function ProgramCard({ p, tone }) {
  const border =
    tone === "match" ? "1px solid var(--primary)" : "1px solid var(--hairline)";
  const dim = tone === "off" ? 0.6 : 1;
  return (
    <div
      style={{
        border,
        borderRadius: "var(--radius-md)",
        padding: 14,
        marginBottom: 10,
        opacity: dim,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <b style={{ color: "var(--on-surface)" }}>{p.program_name}</b>
        {p.owner_department && (
          <span className="t-caption" style={{ color: "var(--ink-faint)" }}>{p.owner_department}</span>
        )}
      </div>
      {p.description && (
        <p className="t-body-sm" style={{ margin: "4px 0 0", color: "var(--ink-secondary)" }}>{p.description}</p>
      )}
      {tone === "match" && p.match_reason && (
        <p className="t-caption" style={{ margin: "8px 0 0", color: "var(--primary)" }}>
          매칭 근거 — {p.match_reason}
        </p>
      )}
      {tone !== "match" && p.reason && (
        <p className="t-caption" style={{ margin: "8px 0 0", color: "var(--ink-muted)" }}>
          {tone === "low" ? "낮춘 이유" : "조건 불일치"} — {p.reason}
        </p>
      )}
      <div className="t-caption" style={{ marginTop: 8, color: "var(--ink-faint)", lineHeight: 1.7 }}>
        <div>신청 기간 — {p.apply_period || "확인 필요"}</div>
        <div>지원 한도 — {p.support_limit_text || "확인 필요"}</div>
        {p.legal_basis && <div>근거 — {p.legal_basis}</div>}
        {p.exclusion_note && <div>제외 — {p.exclusion_note}</div>}
      </div>
      {p.requires_verification && (
        <div
          className="t-caption"
          style={{
            marginTop: 8,
            padding: "6px 10px",
            borderRadius: "var(--radius-sm)",
            background: "var(--surface-container-low)",
            color: "var(--ink-secondary)",
          }}
        >
          자격 요건은 실제 공고문으로 확인해야 합니다. 아직 입력되지 않았습니다.
        </div>
      )}
    </div>
  );
}

export default function CellDetailPage() {
  const { areaId, industryId } = useParams();
  const [cell, setCell] = useState(null);
  const [trend, setTrend] = useState([]);
  const [factors, setFactors] = useState(null);
  const [error, setError] = useState("");
  const [programs, setPrograms] = useState(null);
  const [notice, setNotice] = useState(null);
  const [noticeLoading, setNoticeLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [contacts, setContacts] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError("");
    Promise.all([
      apiFetchJson(`/api/cells/${areaId}/${industryId}`),
      apiFetchJson(`/api/cells/${areaId}/${industryId}/trend`).catch(() => []),
      apiFetchJson(`/api/cells/${areaId}/${industryId}/programs`).catch(() => null),
      apiFetchJson(`/api/cells/${areaId}/${industryId}/contacts`).catch(() => null),
    ])
      .then(([detail, series, progs, logs]) => {
        setContacts(logs);
        setCell(detail);
        setTrend(Array.isArray(series) ? series : []);
        setPrograms(progs);
        if (detail.prediction_id) {
          apiFetchJson(`/api/alerts/${detail.prediction_id}/contributions`)
            .then(setFactors)
            .catch(() => setFactors(null));
        }
      })
      .catch((err) => setError(describeApiError(err)))
      .finally(() => setLoading(false));
    setNotice(null);
    setCopied(false);
    setFormOpen(false);
    setSaveError("");
  }, [areaId, industryId]);

  // 본인이 남긴 기록만 지운다. 서버에서도 같은 규칙을 강제하지만, 남의 기록에 버튼이
  // 보이지 않아야 "지울 수 있는 것"과 "지우면 안 되는 것"이 화면에서 구분된다.
  const deleteContact = async (id) => {
    if (!window.confirm("이 접촉 기록을 지울까요? 되돌릴 수 없습니다.")) return;
    setSaveError("");
    try {
      const response = await apiFetch(`/api/cells/${areaId}/${industryId}/contacts/${id}`, {
        method: "DELETE",
      });
      if (!response.ok && response.status !== 204) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "기록을 지우지 못했습니다.");
      }
      await reloadContacts();
    } catch (err) {
      setSaveError(err.message);
    }
  };

  const reloadContacts = () =>
    apiFetchJson(`/api/cells/${areaId}/${industryId}/contacts`)
      .then(setContacts)
      .catch(() => {});

  const submitContact = async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const count = form.get("contacted_store_count");
    setSaving(true);
    setSaveError("");
    try {
      const response = await apiFetch(`/api/cells/${areaId}/${industryId}/contacts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contacted_on: form.get("contacted_on"),
          channel: form.get("channel"),
          outcome: form.get("outcome"),
          contacted_store_count: count ? Number(count) : null,
          note: form.get("note") || null,
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "기록을 저장하지 못했습니다.");
      }
      event.target.reset();
      setFormOpen(false);
      await reloadContacts();
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>;
  if (error || !cell) {
    return (
      <div>
        <div className="t-title">{error || "상권 정보가 없습니다"}</div>
        <Link to="/dashboard" className="t-caption" style={{ color: "var(--primary)" }}>← 조기경보로 돌아가기</Link>
      </div>
    );
  }

  // 백엔드는 내려주고 있었는데 이 화면이 한 번도 쓰지 않았다(2026-08-25 감사).
  // 사각지대에서 넘어온 셀이 여기서는 아무 경고 없이 표본충분 셀과 똑같이 보였다.
  const sampleThin = Boolean(cell.sample_insufficient);

  return (
    <div style={{ maxWidth: 760 }}>
      <Link to="/dashboard" className="t-caption" style={{ color: "var(--primary)", textDecoration: "none" }}>
        ← 조기경보
      </Link>

      <div style={{ marginTop: 12 }}>
        <ProvisionalNotice />
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
        <TypeBadge type={cell.cell_type} />
        <GradeBadge grade={cell.risk_grade} />
        {cell.predicted_rank && (
          <span className="badge" style={{ background: "var(--primary-fixed)", color: "var(--primary)" }}>
            예측 #{cell.predicted_rank}
          </span>
        )}
      </div>

      {/* 조기경보 1위를 눌러 들어오면 등급이 "안정"인 경우가 흔하다. 예측은 2분기 뒤를 보고
          등급은 이미 관측된 값이라 그런 것인데, 그 설명이 이 화면에 없어서 "1위인데 안정?"으로
          읽혔다. 현장 확인 화면에는 같은 안내를 붙여뒀다. */}
      {cell.predicted_rank && cell.risk_grade && cell.risk_grade !== "위험" && (
        <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "8px 0 0", lineHeight: 1.7 }}>
          예측 순위와 등급은 서로 다른 것을 봅니다 — <b>예측 #{cell.predicted_rank}</b>은 모델이 본
          <b> 2분기 뒤</b> 위험 순위이고, <b>{cell.risk_grade}</b>은 <b>이미 관측된</b> 최근 1년 실적입니다.
          지금 나빠진 곳과 앞으로 나빠질 곳은 같지 않습니다.
        </p>
      )}

      <h1 className="t-h1" style={{ margin: "8px 0 2px" }}>{cell.dong} · {cell.category}</h1>
      <p className="t-caption" style={{ color: "var(--ink-muted)", margin: 0 }}>
        점포 {cell.store_count}곳 · {String(cell.quarter_code).slice(0, 4)}년 {String(cell.quarter_code).slice(-1)}분기 기준
        {cell.industry_rank ? ` · ${cell.category} 중 ${cell.industry_rank}위 / ${cell.industry_total}곳` : ""}
      </p>

      {sampleThin && (
        <div
          className="t-body-sm"
          style={{
            display: "flex",
            gap: 10,
            alignItems: "flex-start",
            marginTop: 16,
            padding: "12px 14px",
            borderRadius: "var(--radius-md)",
            background: "var(--surface-container-low)",
            border: "1px solid var(--hairline)",
            color: "var(--ink-secondary)",
            lineHeight: 1.7,
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18, color: "var(--ink-faint)", flexShrink: 0, lineHeight: 1.5 }}>
            visibility_off
          </span>
          <span>
            <b style={{ color: "var(--on-surface)" }}>표본부족 상권입니다.</b> 점포 수가 기준에 못 미쳐
            통계 판단을 보류했고 등급을 매기지 않습니다. 폐업률은 점포가 적을수록 크게 튀므로
            판단의 주 근거로 쓰지 마시고 <b>건수</b>를 먼저 보십시오.{" "}
            <Link to={`/blindspots?dong=${encodeURIComponent(cell.dong)}`} style={{ color: "var(--primary)" }}>
              사각지대에서 이 읍면동 보기
            </Link>
          </span>
        </div>
      )}

      {/* ① 확인된 위험 신호 */}
      <Section
        title="확인된 위험 신호"
        note={`전부 관측된 사실입니다. 최근 ${cell.window_quarters}분기 누적 기준. ${cell.grade_notice ?? ""}`}
      >
        <div className="card" style={{ padding: 20 }}>
          {/* 표본부족 셀에서는 대표 숫자를 폐업률이 아니라 건수로 바꾼다.
              사각지대 화면이 "폐업률을 판단의 주 근거로 쓰지 마시고 건수를 먼저 보십시오"라고
              안내해놓고, 링크 한 번 타면 점포 12곳짜리의 16.7%가 38px로 뜨고 있었다.
              률은 점포가 적을수록 크게 튀므로 여기서는 참고값으로 내린다. */}
          {sampleThin ? (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                <span className="t-metric" style={{ fontSize: 38 }}>
                  {Number.isFinite(cell.cumulative_closure_count) ? cell.cumulative_closure_count.toLocaleString() : "—"}
                </span>
                <span style={{ fontSize: 16, color: "var(--ink-faint)" }}>곳 닫힘</span>
              </div>
              <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 2 }}>
                폐업률 {fmt(cell.cumulative_closure_rate_pct)}% (참고) · 점포가 적어 률은 크게 튑니다
              </div>
            </>
          ) : (
          <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
            <span className="t-metric" style={{ fontSize: 38 }}>{fmt(cell.cumulative_closure_rate_pct)}</span>
            <span style={{ fontSize: 16, color: "var(--ink-faint)" }}>%</span>
          </div>
          )}
          <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 2, fontVariantNumeric: "tabular-nums" }}>
            {/* 분모는 현재 점포수가 아니라 4개 분기 직전점포수의 합이다. 예전에는 여기에
                현재 점포수를 병기해서, 눈으로 나눈 값이 큰 숫자와 4배쯤 어긋났다
                (동탄8동 일반 교육: 표시 16.04% vs "47곳 / 53곳" = 89%). */}
            {Number.isFinite(cell.cumulative_closure_count) ? (
              cell.cumulative_denominator ? (
                <>
                  최근 {cell.window_quarters ?? WINDOW_LABEL}분기 연 {cell.cumulative_denominator.toLocaleString()}곳 중{" "}
                  <b style={{ color: "var(--on-surface)" }}>{cell.cumulative_closure_count.toLocaleString()}곳</b> 닫힘
                  {cell.denominator_estimated && <span style={{ color: "var(--ink-faint)" }}> (분모 추정)</span>}
                </>
              ) : (
                <>최근 {cell.window_quarters ?? WINDOW_LABEL}분기 {cell.cumulative_closure_count.toLocaleString()}곳 닫힘</>
              )
            ) : (
              <>누적 폐업 건수 미산출</>
            )}
            {" · 현재 점포 "}{cell.store_count?.toLocaleString() ?? "—"}곳
            {" · "}신뢰하한 {fmt(cell.confidence_lower_pct)}%
          </div>
          {/* 비교 대상(업종·동·시 평균)은 전부 표본충분 셀만으로 낸 값이다.
              점포 12곳짜리를 그 평균과 나란히 그리면 비교 가능한 것처럼 보인다. */}
          {!sampleThin && (
            <div style={{ marginTop: 16 }}>
              <Comparison value={cell.cumulative_closure_rate_pct} comparison={cell.comparison} />
            </div>
          )}
          <div
            className="t-caption"
            style={{ display: "flex", gap: 16, flexWrap: "wrap", paddingTop: 12, marginTop: 4, borderTop: "1px solid var(--hairline)", color: "var(--ink-muted)" }}
          >
            <span title="4분기 이동평균으로 보정한 값입니다. 상권유형 판정도 같은 값을 씁니다.">개업률 <b style={{ color: "var(--on-surface)" }}>{fmt(cell.opening_rate_pct)}%</b></span>
            <span>추세 <b style={{ color: cell.trend_slope > 0 ? "var(--accent-orange)" : "var(--on-surface)" }}>
              {cell.trend_slope > 0 ? "+" : ""}{cell.trend_slope}
            </b></span>
            <span>직전 분기 <b style={{ color: "var(--on-surface)" }}>{fmt(cell.quarter_closure_rate_pct)}%</b></span>
          </div>
        </div>
      </Section>

      <Section title="추이" note="누적 기준이라 분기별 우연에 흔들리지 않습니다.">
        <div className="card" style={{ padding: 16 }}>
          <TrendChart rows={trend} />
        </div>
      </Section>

      {/* ② 유형 판정과 처방 */}
      {cell.cell_type_advice && (
        <Section title="유형 판정과 후속 조치 검토안" note="AI가 지원 대상을 결정하지 않습니다. 최종 판단은 담당자가 합니다.">
          <div className="card" style={{ padding: 20 }}>
            {/* 유형에 색을 주지 않는다. 유형은 위험도가 아니라 성격이고, 색을 주면 등급 축과 섞인다. */}
            <div className="t-title" style={{ color: "var(--on-surface)" }}>
              {cell.cell_type}
            </div>
            <p style={{ margin: "6px 0 0", color: "var(--on-surface)" }}>{cell.cell_type_summary}</p>

            {/* 판정 근거를 숫자로 보여준다. 이게 없으면 유형은 그냥 붙은 라벨로 읽히고,
                "이 상권이 왜 쇠퇴입니까"를 물었을 때 화면으로 답할 수가 없다.
                기준선은 표본충분 상권의 중위값이고 서버에서 받는다(하드코딩 금지). */}
            {Number.isFinite(cell.cell_type_open_cut_pct) &&
              Number.isFinite(cell.cell_type_close_cut_pct) &&
              Number.isFinite(cell.opening_rate_pct) &&
              Number.isFinite(cell.cumulative_closure_rate_pct) && (
                <div
                  className="t-caption"
                  style={{
                    margin: "10px 0 0",
                    padding: "10px 12px",
                    background: "var(--surface-container-low)",
                    borderRadius: "var(--radius-md)",
                    color: "var(--ink-secondary)",
                    lineHeight: 1.8,
                  }}
                >
                  <div style={{ color: "var(--ink-faint)", marginBottom: 4 }}>판정 근거</div>
                  개업률{" "}
                  <b style={{ color: "var(--on-surface)" }}>{fmt(cell.opening_rate_pct)}%</b>
                  {" "}— 기준 {fmt(cell.cell_type_open_cut_pct)}%{" "}
                  {cell.opening_rate_pct >= cell.cell_type_open_cut_pct ? "이상" : "미만"}
                  <br />
                  폐업률{" "}
                  <b style={{ color: "var(--on-surface)" }}>{fmt(cell.cumulative_closure_rate_pct)}%</b>
                  {" "}— 기준 {fmt(cell.cell_type_close_cut_pct)}%{" "}
                  {cell.cumulative_closure_rate_pct >= cell.cell_type_close_cut_pct ? "이상" : "미만"}
                  <div style={{ color: "var(--ink-faint)", marginTop: 6 }}>
                    기준은 표본이 충분한 상권의 중위값입니다. 절대 임계가 아니라 화성시 안에서의 상대 위치입니다.
                  </div>
                </div>
              )}

            <p style={{ margin: "10px 0 0", color: "var(--ink-secondary)" }}>{cell.cell_type_advice}</p>
            {cell.cell_type_avoid && (
              <p className="t-caption" style={{ margin: "8px 0 0", color: "var(--ink-faint)" }}>
                우선순위 낮음 — {cell.cell_type_avoid}
              </p>
            )}
            <div
              className="t-caption"
              style={{ marginTop: 12, padding: "8px 10px", background: "var(--surface-container-low)", borderRadius: "var(--radius-md)", color: "var(--ink-secondary)" }}
            >
              {cell.action}
            </div>
          </div>
        </Section>
      )}

      {/* ③ AI 예측 기여 요인 */}
      <Section title="AI 예측 기여 요인" note={factors?.notice ?? "인과관계를 의미하지 않습니다."}>
        <div className="card" style={{ padding: 20 }}>
          {factors?.contributions?.length ? (
            factors.contributions.map((f) => (
              <div key={f.rank} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                  <span className="t-caption" style={{ color: "var(--ink-muted)" }}>{f.factor_label}</span>
                  <span className="t-metric" style={{ fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{fmt(f.share_pct)}%</span>
                </div>
                <div style={{ height: 7, background: "var(--surface-container)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
                  <div style={{ width: `${Math.min(100, f.share_pct)}%`, height: "100%", background: "var(--primary)", borderRadius: "var(--radius-full)" }} />
                </div>
              </div>
            ))
          ) : (
            <div className="t-caption" style={{ color: "var(--ink-muted)" }}>
              이 상권은 표본이 부족해 기여 요인을 산출하지 않았습니다.
            </div>
          )}
        </div>
      </Section>

      {/* ③-2 연결 가능 지원사업 */}
      {programs && (
        <Section
          title="연결 가능 지원사업"
          note={programs.notice}
        >
          <div className="card" style={{ padding: 20 }}>
            {programs.matched.length === 0 && (
              <div className="t-caption" style={{ color: "var(--ink-muted)" }}>
                이 상권 조건({programs.cell_type || "유형 미판정"} · {programs.risk_grade})에
                맞는 사업이 없습니다.
              </div>
            )}

            {programs.matched.map((p) => (
              <ProgramCard key={p.program_code} p={p} tone="match" />
            ))}

            {programs.discouraged.length > 0 && (
              <>
                <div className="t-eyebrow" style={{ color: "var(--ink-faint)", margin: "18px 0 8px" }}>
                  우선순위를 낮춰 검토할 사업
                </div>
                {programs.discouraged.map((p) => (
                  <ProgramCard key={p.program_code} p={p} tone="low" />
                ))}
              </>
            )}

            {programs.not_matched.length > 0 && (
              <details style={{ marginTop: 18 }}>
                <summary className="t-caption" style={{ color: "var(--ink-muted)", cursor: "pointer" }}>
                  조건이 맞지 않는 사업 {programs.not_matched.length}건 보기
                </summary>
                <div style={{ marginTop: 10 }}>
                  {programs.not_matched.map((p) => (
                    <ProgramCard key={p.program_code} p={p} tone="off" />
                  ))}
                </div>
              </details>
            )}

            <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--hairline)" }}>
              <button
                type="button"
                className="btn-utility"
                onClick={() => {
                  setNoticeLoading(true);
                  setCopied(false);
                  apiFetchJson(`/api/cells/${areaId}/${industryId}/notice`)
                    .then(setNotice)
                    .catch(() => setNotice({ text: "안내문을 불러오지 못했습니다.", notice: "" }))
                    .finally(() => setNoticeLoading(false));
                }}
                disabled={noticeLoading}
              >
                {noticeLoading ? "생성 중…" : "안내문 초안 만들기"}
              </button>

              {notice && (
                <div style={{ marginTop: 12 }}>
                  <textarea
                    readOnly
                    value={notice.text}
                    rows={Math.min(20, notice.text.split("\n").length + 1)}
                    style={{
                      width: "100%",
                      fontFamily: "inherit",
                      fontSize: 13,
                      lineHeight: 1.7,
                      padding: 12,
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--hairline)",
                      background: "var(--surface-container-low)",
                      color: "var(--on-surface)",
                      resize: "vertical",
                    }}
                  />
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
                    <button
                      type="button"
                      className="btn-utility"
                      onClick={() => {
                        navigator.clipboard?.writeText(notice.text).then(
                          () => setCopied(true),
                          () => setCopied(false),
                        );
                      }}
                    >
                      {copied ? "복사됨" : "복사"}
                    </button>
                    <span className="t-caption" style={{ color: "var(--ink-faint)" }}>
                      {notice.notice}
                    </span>
                  </div>
                  {copied && (
                    <div className="t-caption" style={{ marginTop: 8, color: "var(--ink-secondary)" }}>
                      발송하셨다면 아래 <b>접촉 이력</b>에 남겨주세요. 다른 부서가 같은 상권에 중복
                      연락하는 것을 막습니다.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </Section>
      )}

      {/* ③-3 접촉 이력 */}
      {contacts && (
        <Section title="접촉 이력" note={contacts.notice}>
          <div className="card" style={{ padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
              <div>
                {contacts.total === 0 ? (
                  <span style={{ color: "var(--ink-muted)" }}>아직 접촉 기록이 없습니다.</span>
                ) : (
                  <span style={{ color: "var(--on-surface)" }}>
                    총 <b>{contacts.total}</b>건 · 마지막 접촉{" "}
                    <b>{contacts.last_contacted_on}</b>
                    {Number.isFinite(contacts.days_since_last_contact) && (
                      <span style={{ color: "var(--ink-muted)" }}>
                        {" "}({contacts.days_since_last_contact}일 전)
                      </span>
                    )}
                  </span>
                )}
              </div>
              <button type="button" className="btn-utility" onClick={() => setFormOpen((v) => !v)}>
                {formOpen ? "취소" : "기록 추가"}
              </button>
            </div>

            {Object.keys(contacts.outcome_counts || {}).length > 0 && (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
                {Object.entries(contacts.outcome_counts).map(([label, n]) => (
                  <span key={label} className="badge badge-neutral">{label} {n}</span>
                ))}
              </div>
            )}

            {formOpen && (
              <form
                onSubmit={submitContact}
                style={{
                  marginTop: 16,
                  padding: 14,
                  borderRadius: "var(--radius-md)",
                  background: "var(--surface-container-low)",
                  display: "grid",
                  gap: 10,
                }}
              >
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <label className="t-caption" style={{ display: "grid", gap: 4, color: "var(--ink-muted)" }}>
                    접촉일
                    <input
                      type="date"
                      name="contacted_on"
                      required
                      max={new Date().toISOString().slice(0, 10)}
                      defaultValue={new Date().toISOString().slice(0, 10)}
                    />
                  </label>
                  <label className="t-caption" style={{ display: "grid", gap: 4, color: "var(--ink-muted)" }}>
                    방법
                    <select name="channel" required defaultValue="visit">
                      {contacts.channels.map((c) => (
                        <option key={c.value} value={c.value}>{c.label}</option>
                      ))}
                    </select>
                  </label>
                  <label className="t-caption" style={{ display: "grid", gap: 4, color: "var(--ink-muted)" }}>
                    결과
                    <select name="outcome" required defaultValue="connected">
                      {contacts.outcomes.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </label>
                  <label className="t-caption" style={{ display: "grid", gap: 4, color: "var(--ink-muted)" }}>
                    접촉 점포 수(선택)
                    <input type="number" name="contacted_store_count" min="0" style={{ width: 110 }} />
                  </label>
                </div>
                <label className="t-caption" style={{ display: "grid", gap: 4, color: "var(--ink-muted)" }}>
                  메모
                  <textarea name="note" rows={2} placeholder="현장에서 확인한 내용, 다음 조치 등" />
                </label>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? "저장 중…" : "저장"}</button>
                  {saveError && (
                    <span className="t-caption" style={{ color: "var(--accent-orange)" }}>{saveError}</span>
                  )}
                </div>
                <div className="t-caption" style={{ color: "var(--ink-faint)" }}>
                  개별 점포의 상호·연락처는 입력하지 마세요. 이 기록은 상권 단위입니다.
                </div>
              </form>
            )}

            {contacts.items.length > 0 && (
              <div style={{ marginTop: 18 }}>
                {contacts.items.map((c) => (
                  <div
                    key={c.id}
                    style={{
                      display: "flex",
                      gap: 12,
                      padding: "10px 0",
                      borderTop: "1px solid var(--hairline)",
                    }}
                  >
                    <div
                      className="t-caption"
                      style={{ minWidth: 88, color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}
                    >
                      {c.contacted_on}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ color: "var(--on-surface)" }}>
                        {c.channel_label} · {c.outcome_label}
                        {Number.isFinite(c.contacted_store_count) && (
                          <span style={{ color: "var(--ink-muted)" }}> · {c.contacted_store_count}곳</span>
                        )}
                      </div>
                      {c.note && (
                        <div className="t-caption" style={{ color: "var(--ink-secondary)", marginTop: 2 }}>{c.note}</div>
                      )}
                      <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 2, display: "flex", gap: 8, alignItems: "center" }}>
                        <span>{c.official}</span>
                        {c.mine && (
                          <button
                            type="button"
                            onClick={() => deleteContact(c.id)}
                            style={{
                              background: "none",
                              border: "none",
                              padding: 0,
                              cursor: "pointer",
                              color: "var(--ink-muted)",
                              textDecoration: "underline",
                              font: "inherit",
                            }}
                          >
                            삭제
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Section>
      )}

      {/* ④ 공무원 확인 필요 항목 */}
      <Section title="공무원 확인 필요 항목" note="데이터가 없어 모델이 보지 못한 것들입니다. 현장에서 확인해주세요.">
        <div className="card" style={{ padding: 20 }}>
          {cell.field_check_items?.map((item) => (
            <div key={item.label} style={{ marginBottom: 10 }}>
              <div style={{ color: "var(--on-surface)" }}>{item.label}</div>
              <div className="t-caption" style={{ color: "var(--ink-muted)" }}>{item.reason}</div>
            </div>
          ))}
        </div>
      </Section>

      {/* ⑤ 근거·출처 */}
      <Section title="근거·출처" note="의회·감사 질의에 대응하기 위한 산출 근거입니다.">
        <div className="card t-caption" style={{ padding: 20, color: "var(--ink-muted)", lineHeight: 1.8 }}>
          <div>원천 — {cell.provenance?.source_name ?? "미기록"}</div>
          <div>산출 방식 — {cell.provenance?.method_version ?? "미기록"}</div>
          <div>
            수집 구간 — {cell.provenance?.source_start_quarter ?? "?"} ~ {cell.provenance?.source_end_quarter ?? "?"}
            {cell.provenance?.row_count ? ` (${cell.provenance.row_count.toLocaleString()}행)` : ""}
          </div>
          {cell.provenance?.quality_notes && <div>품질 메모 — {cell.provenance.quality_notes}</div>}
          <div style={{ marginTop: 8, color: "var(--ink-faint)" }}>{cell.grade_notice}</div>
        </div>
      </Section>
    </div>
  );
}
