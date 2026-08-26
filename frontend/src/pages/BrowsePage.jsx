import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson } from "../lib/api";

// 상권 둘러보기 — 로그인 없이 열리는 공개 화면.
//
// 노다지(서울 프로젝트)가 예비 창업자의 입지·업종 판단을 도왔고 이 프로젝트는 공무원의 정책
// 판단을 돕는다. 분석 단위가 (행정동 x 업종)으로 같아서 같은 셀을 두 방향에서 읽는 것뿐이다.
//
// 화면 원칙 (서버가 애초에 안 내려주지만 프론트에서도 지킨다)
//   - 위험등급·예측순위·성장확률·상권유형 이름을 쓰지 않는다
//   - "여기 여세요/열지 마세요"라고 쓰지 않는다. 점포 단위 예측 성능이 방어되지 않는다
//   - 표본부족 상권은 비율을 판단 재료로 쓰지 않고 점포 수만 말한다
//   - 분모가 다른 두 수를 슬래시로 묶지 않는다. 폐업률의 분모는 4개 분기 직전점포수의
//     합이고 점포 수는 현재 분기 값이라, 슬래시로 묶으면 눈으로 나눈 값이 4배쯤 어긋난다
//   - 문구는 서버에서 받는다. 평균·기준선을 프론트에 박으면 파이프라인 갱신 후 화면이 거짓말한다

const fmt = (v, d = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

function Compare({ label, value, mine }) {
  if (typeof value !== "number") return null;
  const diff = typeof mine === "number" ? mine - value : null;
  return (
    <div style={{ flex: "1 1 150px" }}>
      <div className="t-caption" style={{ color: "var(--ink-faint)" }}>{label}</div>
      <div style={{ marginTop: 4, fontVariantNumeric: "tabular-nums" }}>
        <span className="t-body">{fmt(value)}%</span>
        {diff !== null && (
          <span className="t-caption" style={{ color: "var(--ink-muted)", marginLeft: 6 }}>
            (이 상권이 {fmt(Math.abs(diff))}%p {diff >= 0 ? "높음" : "낮음"})
          </span>
        )}
      </div>
    </div>
  );
}

export default function BrowsePage() {
  const [options, setOptions] = useState(null);
  const [areaId, setAreaId] = useState(null);
  const [industryId, setIndustryId] = useState(null);
  const [cell, setCell] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const names = useMemo(
    () => Object.fromEntries((options?.industries ?? []).map((i) => [i.id, i.name])),
    [options],
  );
  const area = options?.areas.find((a) => a.id === areaId);

  useEffect(() => {
    apiFetchJson("/api/public/areas")
      .then((d) => {
        setOptions(d);
        const first = d.areas?.[0];
        const pick = first?.industries.find((i) => !i.sample_insufficient) ?? first?.industries[0];
        if (first && pick) { setAreaId(first.id); setIndustryId(pick.id); }
      })
      .catch(() => setError("상권 목록을 불러오지 못했습니다."));
  }, []);

  useEffect(() => {
    if (!areaId || !industryId) return;
    setLoading(true); setError("");
    apiFetchJson(`/api/public/cell?area_id=${areaId}&industry_id=${industryId}`)
      .then(setCell)
      .catch(() => { setCell(null); setError("상권 정보를 불러오지 못했습니다."); })
      .finally(() => setLoading(false));
  }, [areaId, industryId]);

  const onArea = (id) => {
    const next = options?.areas.find((a) => a.id === id);
    const available = next?.industries.map((i) => i.id) ?? [];
    setAreaId(id);
    setIndustryId(available.includes(industryId) ? industryId : available[0]);
  };

  const short = cell?.sample_insufficient;

  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-gray)" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "48px 24px 64px" }}>
        <h1 className="t-h1" style={{ margin: 0 }}>상권 둘러보기</h1>
        <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "8px 0 0", lineHeight: 1.7 }}>
          화성시 읍면동과 업종을 고르면 그 상권에서 최근 실제로 일어난 일을 보여드립니다.
          <br />
          공공데이터로 계산한 상권 단위 통계이며, 특정 가게의 성패를 예측하지 않습니다.
        </p>

        <div className="card" style={{ padding: 18, margin: "24px 0", display: "flex", gap: 10, flexWrap: "wrap" }}>
          <select
            value={areaId ?? ""}
            onChange={(e) => onArea(Number(e.target.value))}
            style={{ flex: "1 1 180px", minWidth: 0 }}
          >
            {(options?.areas ?? []).map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          <select
            value={industryId ?? ""}
            onChange={(e) => setIndustryId(Number(e.target.value))}
            style={{ flex: "1 1 180px", minWidth: 0 }}
          >
            {(area?.industries ?? []).map((i) => (
              <option key={i.id} value={i.id}>{names[i.id]}</option>
            ))}
          </select>
        </div>

        {loading && <div className="t-body-sm" style={{ color: "var(--ink-muted)" }}>불러오는 중…</div>}
        {error && <div className="t-body-sm" style={{ color: "var(--accent-orange)" }}>{error}</div>}

        {!loading && cell && (
          <>
            <div className="card" style={{ padding: 24 }}>
              <div className="t-title">{cell.area_name} · {cell.industry_name}</div>

              {short ? (
                // 점포 4곳짜리 셀이 실제로 있다. 폐업 0건이 "0.0%"로 찍히면 안전해 보이지만
                // 판단 자체가 불가능한 표본이다. 비율을 아예 크게 보여주지 않는다.
                <>
                  <p className="t-body" style={{ margin: "16px 0 0", color: "var(--on-surface)", lineHeight: 1.7 }}>
                    이 상권은 점포가 <b>{cell.store_count}곳</b>뿐이라 비율로 판단하기 어렵습니다.
                    한두 곳만 문을 닫아도 수치가 크게 흔들리기 때문입니다.
                  </p>
                  <p className="t-body-sm" style={{ margin: "10px 0 0", color: "var(--ink-muted)", lineHeight: 1.7 }}>
                    최근 {cell.window_quarters}분기 동안 문을 닫은 곳은 {cell.closure_count ?? 0}곳입니다.
                    수치보다 직접 다녀보시는 편이 낫습니다.
                  </p>
                </>
              ) : (
                <>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 18 }}>
                    <span className="t-metric" style={{ fontSize: 40 }}>{fmt(cell.closure_rate_pct, 1)}</span>
                    <span className="t-body" style={{ color: "var(--ink-muted)" }}>%</span>
                    <span className="t-body-sm" style={{ color: "var(--ink-muted)", marginLeft: 6 }}>
                      최근 1년 누적 폐업률 · 같은 기간 {cell.closure_count}곳 폐업 · 현재 점포 {cell.store_count}곳
                    </span>
                  </div>

                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 20, paddingTop: 18, borderTop: "1px solid var(--hairline)" }}>
                    <Compare label="화성시 평균" value={cell.comparison?.city_avg_pct} mine={cell.closure_rate_pct} />
                    <Compare label={`${cell.industry_name} 전체 평균`} value={cell.comparison?.industry_avg_pct} mine={cell.closure_rate_pct} />
                    <Compare label={`${cell.area_name} 전체 평균`} value={cell.comparison?.area_avg_pct} mine={cell.closure_rate_pct} />
                  </div>

                  <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 18, paddingTop: 18, borderTop: "1px solid var(--hairline)" }}>
                    <div>
                      <div className="t-caption" style={{ color: "var(--ink-faint)" }}>새로 문을 연 비율</div>
                      <div className="t-body" style={{ marginTop: 4, fontVariantNumeric: "tabular-nums" }}>
                        {fmt(cell.opening_rate_pct, 1)}%
                      </div>
                    </div>
                    {cell.observed_rank && (
                      <div>
                        <div className="t-caption" style={{ color: "var(--ink-faint)" }}>
                          {cell.industry_name} 업종 안에서
                        </div>
                        <div className="t-body" style={{ marginTop: 4 }}>
                          {cell.observed_total}개 지역 중 <b>{cell.observed_rank}번째</b>로 자주 닫힘
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}

              {(cell.pattern_summary || cell.founder_note) && (
                <div style={{ marginTop: 20, paddingTop: 18, borderTop: "1px solid var(--hairline)" }}>
                  {cell.pattern_summary && (
                    <p className="t-body" style={{ margin: 0, color: "var(--on-surface)", lineHeight: 1.7 }}>
                      {cell.pattern_summary}
                    </p>
                  )}
                  {cell.founder_note && (
                    <p className="t-body-sm" style={{ margin: "8px 0 0", color: "var(--ink-secondary)", lineHeight: 1.7 }}>
                      {cell.founder_note}
                    </p>
                  )}
                </div>
              )}
            </div>

            <div
              className="t-caption"
              style={{
                color: "var(--ink-secondary)",
                background: "var(--surface-container-low)",
                padding: "12px 16px",
                borderRadius: "var(--radius-md)",
                marginTop: 14,
                lineHeight: 1.7,
              }}
            >
              {cell.support_notice}
            </div>

            <p className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 14, lineHeight: 1.7 }}>
              {cell.scope_notice}
              <br />
              {cell.provisional_notice}
              <br />
              기준 {cell.quarter_label} · 출처 소상공인시장진흥공단 상가(상권)정보
            </p>
          </>
        )}

        <div style={{ borderTop: "1px solid var(--hairline)", marginTop: 32, paddingTop: 20 }}>
          <Link to="/" className="t-caption" style={{ color: "var(--ink-muted)", textDecoration: "none" }}>
            화성시 담당자 로그인
          </Link>
        </div>
      </div>
    </div>
  );
}
