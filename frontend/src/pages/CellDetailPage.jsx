import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { apiFetchJson } from "../lib/api";
import ProvisionalNotice from "../components/ProvisionalNotice";

// 세 영역을 절대 섞지 않는다(CLAUDE.md 용어 규칙).
//   ① 확인된 위험 신호   관측 데이터로 직접 계산된 사실
//   ② AI 예측 기여 요인   모델의 내부 근거. 인과 아님
//   ③ 공무원 확인 필요    데이터가 없어 모델이 보지 못한 원인 후보

const TYPE_TONE = {
  고회전: "var(--accent-orange)",
  쇠퇴: "var(--primary)",
  성장: "var(--ink-muted)",
  정체: "var(--ink-muted)",
};

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

/** 누적 폐업률 추이. 외부 차트 라이브러리 없이 SVG로 그린다. */
function TrendChart({ rows }) {
  const points = rows.filter((r) => Number.isFinite(r.cumulative_closure_rate_pct));
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
    </div>
  );
}

/** 3중 비교 — 숫자 하나로는 의미가 없다. 세 방향으로 비교해야 원인의 위치가 좁혀진다. */
function Comparison({ value, comparison }) {
  const rows = [
    { label: "이 상권", value, tone: "var(--primary)" },
    { label: "같은 업종 평균", value: comparison?.industry_avg_pct, tone: "var(--outline-variant)" },
    { label: "같은 행정동 평균", value: comparison?.area_avg_pct, tone: "var(--outline-variant)" },
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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError("");
    Promise.all([
      apiFetchJson(`/api/cells/${areaId}/${industryId}`),
      apiFetchJson(`/api/cells/${areaId}/${industryId}/trend`).catch(() => []),
      apiFetchJson(`/api/cells/${areaId}/${industryId}/programs`).catch(() => null),
    ])
      .then(([detail, series, progs]) => {
        setCell(detail);
        setTrend(Array.isArray(series) ? series : []);
        setPrograms(progs);
        if (detail.prediction_id) {
          apiFetchJson(`/api/alerts/${detail.prediction_id}/contributions`)
            .then(setFactors)
            .catch(() => setFactors(null));
        }
      })
      .catch(() => setError("상권 정보를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
    setNotice(null);
    setCopied(false);
  }, [areaId, industryId]);

  if (loading) return <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>;
  if (error || !cell) {
    return (
      <div>
        <div className="t-title">{error || "상권 정보가 없습니다"}</div>
        <Link to="/dashboard" className="t-caption" style={{ color: "var(--primary)" }}>← 조기경보로 돌아가기</Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <Link to="/dashboard" className="t-caption" style={{ color: "var(--primary)", textDecoration: "none" }}>
        ← 조기경보
      </Link>

      <div style={{ marginTop: 12 }}>
        <ProvisionalNotice />
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
        {cell.cell_type && cell.cell_type !== "유형판정보류" && (
          <span className="badge" style={{ color: TYPE_TONE[cell.cell_type] ?? "var(--ink-muted)" }}>
            {cell.cell_type}
          </span>
        )}
        {cell.risk_grade && (
          <span className={cell.risk_grade === "위험" ? "badge badge-danger" : "badge"}>{cell.risk_grade}</span>
        )}
        {cell.predicted_rank && (
          <span className="badge" style={{ background: "var(--primary-fixed)", color: "var(--primary)" }}>
            예측 #{cell.predicted_rank}
          </span>
        )}
      </div>

      <h1 className="t-h1" style={{ margin: "8px 0 2px" }}>{cell.dong} · {cell.category}</h1>
      <p className="t-caption" style={{ color: "var(--ink-muted)", margin: 0 }}>
        점포 {cell.store_count}곳 · {String(cell.quarter_code).slice(0, 4)}년 {String(cell.quarter_code).slice(-1)}분기 기준
        {cell.industry_rank ? ` · ${cell.category} 중 ${cell.industry_rank}위 / ${cell.industry_total}곳` : ""}
      </p>

      {/* ① 확인된 위험 신호 */}
      <Section
        title="확인된 위험 신호"
        note={`전부 관측된 사실입니다. 최근 ${cell.window_quarters}분기 누적 기준. ${cell.grade_notice ?? ""}`}
      >
        <div className="card" style={{ padding: 20 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
            <span className="t-metric" style={{ fontSize: 38 }}>{fmt(cell.cumulative_closure_rate_pct)}</span>
            <span style={{ fontSize: 16, color: "var(--ink-faint)" }}>%</span>
          </div>
          <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 2, fontVariantNumeric: "tabular-nums" }}>
            {cell.cumulative_closure_count ?? 0}곳 닫힘 / 전체 {cell.store_count}곳
            {" · "}신뢰하한 {fmt(cell.confidence_lower_pct)}%
          </div>
          <div style={{ marginTop: 16 }}>
            <Comparison value={cell.cumulative_closure_rate_pct} comparison={cell.comparison} />
          </div>
          <div
            className="t-caption"
            style={{ display: "flex", gap: 16, flexWrap: "wrap", paddingTop: 12, marginTop: 4, borderTop: "1px solid var(--hairline)", color: "var(--ink-muted)" }}
          >
            <span>개업률 <b style={{ color: "var(--on-surface)" }}>{fmt(cell.opening_rate_pct)}%</b></span>
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
            <div className="t-title" style={{ color: TYPE_TONE[cell.cell_type] ?? "var(--on-surface)" }}>
              {cell.cell_type}
            </div>
            <p style={{ margin: "6px 0 0", color: "var(--on-surface)" }}>{cell.cell_type_summary}</p>
            <p style={{ margin: "8px 0 0", color: "var(--ink-secondary)" }}>{cell.cell_type_advice}</p>
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
                </div>
              )}
            </div>
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
