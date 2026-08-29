import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiFetchJson, describeApiError } from "../lib/api";

/** 데이터 보정 내역.
 *
 *  이 화면이 답하는 질문은 하나다 — "이 시스템의 폐업률은 믿을 수 있는가."
 *
 *  화성시 데이터에는 한 분기에 점포 11,223곳이 한꺼번에 사라진 구간이 있다. 그대로 쓰면
 *  그 분기 폐업률이 26.9%가 되고, 그 숫자로 예산을 짜면 실제와 3.6배 어긋난 판단을 하게 된다.
 *  우리가 무엇을 발견했고 어떻게 걷어냈는지를 공무원이 한 번에 이해하도록 만드는 자리다.
 *
 *  그림 구성 — 숫자의 역할이 셋이라 형태도 셋이다.
 *    ① 3.6배      결론 한 개 → 큰 숫자(도표 아님). 막대 하나짜리 차트로 만들지 않는다.
 *    ② 26.9→7.5%  같은 대상의 전후 → 같은 축 위의 두 막대. 보정 후만 강조색, 전은 회색.
 *    ③ 11,223 분해 부분-전체 → 누적 가로 막대. 두 조각 다 직접 라벨을 단다.
 *
 *  색은 강조(accent 1 + 회색) 방식이다. 계열이 둘이지만 "실제 폐업"만 주인공이고 나머지는
 *  맥락이라, 같은 밝기의 색 두 개로 나누면 오히려 무엇이 중요한지가 사라진다.
 *  값은 전부 토큰으로 쓴다 — 화면 테마가 바뀌면 같이 움직여야 한다.
 */

const fmtInt = (v) => (typeof v === "number" ? v.toLocaleString() : "—");
const fmtPct = (v, d = 1) => (typeof v === "number" ? v.toFixed(d) : "—");

function PageHeader({ title, desc }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h1 className="t-h1" style={{ margin: 0 }}>{title}</h1>
      <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0" }}>{desc}</p>
    </div>
  );
}

/** 전후 비교 — 같은 축 위의 가로 막대 두 개.
 *
 *  축을 공유하는 것이 핵심이다. 막대마다 축이 다르면 길이 비교가 거짓말이 된다.
 *  값은 막대 오른쪽에 직접 붙인다(범례로 색을 찾아 헤매게 하지 않는다).
 */
function BeforeAfter({ rows }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {rows.map((row) => (
        <div key={row.label}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, marginBottom: 7 }}>
            <span className="t-body-sm" style={{ color: row.emphasis ? "var(--on-surface)" : "var(--ink-muted)", fontWeight: row.emphasis ? 700 : 500 }}>
              {row.label}
            </span>
            <span
              className="t-metric"
              style={{ fontSize: row.emphasis ? 24 : 20, color: row.emphasis ? "var(--error)" : "var(--outline)" }}
            >
              {fmtPct(row.value, 1)}%
            </span>
          </div>
          {/* 데이터 끝만 둥글게. 축에 붙는 쪽은 각져 있어야 시작점이 어디인지 흔들리지 않는다. */}
          <div style={{ height: 14, background: "var(--surface-container)", borderRadius: 4, overflow: "hidden" }}>
            <div
              style={{
                width: `${(row.value / max) * 100}%`,
                height: "100%",
                background: row.emphasis ? "var(--error)" : "var(--outline)",
                borderRadius: "0 4px 4px 0",
              }}
            />
          </div>
          <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 5 }}>{row.note}</div>
        </div>
      ))}
    </div>
  );
}

/** 사라진 11,223곳의 분해 — 누적 가로 막대.
 *
 *  두 조각을 2px 띄운다. 붙여 놓으면 경계가 색 차이로만 읽혀서 색각 이상에서 한 덩어리가 된다.
 */
function Breakdown({ reappeared, real, total }) {
  const parts = [
    {
      key: "reappeared",
      label: "다시 나타남",
      value: reappeared,
      color: "var(--outline)",
      note: "폐업이 아니라 데이터에서 일시적으로 누락된 점포",
    },
    {
      key: "real",
      label: "실제 폐업",
      value: real,
      color: "var(--error)",
      note: "이후 분기에도 다시 나타나지 않은 점포",
    },
  ];
  return (
    <div>
      <div style={{ display: "flex", gap: 2, height: 34 }}>
        {parts.map((part, i) => (
          <div
            key={part.key}
            title={`${part.label} ${fmtInt(part.value)}곳`}
            style={{
              flex: `${part.value} 0 0`,
              background: part.color,
              borderRadius: i === 0 ? "4px 0 0 4px" : "0 4px 4px 0",
              minWidth: 4,
            }}
          />
        ))}
      </div>

      {/* 범례이자 직접 라벨. 색만으로 구분되지 않게 이름·건수·비율을 같이 둔다. */}
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 14 }}>
        {parts.map((part) => (
          <div key={part.key} style={{ flex: "1 1 220px", minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: part.color, flex: "0 0 auto" }} />
              <span className="t-body-sm" style={{ fontWeight: 600, color: "var(--on-surface)" }}>{part.label}</span>
              <span className="t-metric" style={{ marginLeft: "auto", fontSize: 18 }}>
                {fmtInt(part.value)}
                <span style={{ fontSize: 13, color: "var(--ink-faint)", fontWeight: 500 }}>곳</span>
              </span>
              <span className="t-caption" style={{ color: "var(--ink-faint)", minWidth: 46, textAlign: "right" }}>
                {total ? `${fmtPct((part.value / total) * 100, 1)}%` : "—"}
              </span>
            </div>
            <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 4, lineHeight: 1.6 }}>{part.note}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Step({ index, title, children }) {
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
      <span
        className="t-caption"
        style={{
          flex: "0 0 auto", width: 24, height: 24, borderRadius: "50%",
          background: "var(--surface-container)", color: "var(--ink-secondary)",
          display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700,
        }}
      >
        {index}
      </span>
      <div style={{ minWidth: 0 }}>
        <div className="t-body-sm" style={{ fontWeight: 700, color: "var(--on-surface)" }}>{title}</div>
        <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 3, lineHeight: 1.7 }}>{children}</div>
      </div>
    </div>
  );
}

export default function MethodPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetchJson("/api/analysis/correction")
      .then((d) => setData(d?.closure ?? null))
      .catch((err) => setError(describeApiError(err)));
  }, []);

  if (error) {
    return (
      <div>
        <PageHeader title="데이터 보정 내역" desc="폐업률 산출에 적용한 보정과 그 근거입니다." />
        <div className="card" style={{ color: "var(--error)" }}>{error}</div>
      </div>
    );
  }
  if (!data) {
    return (
      <div>
        <PageHeader title="데이터 보정 내역" desc="폐업률 산출에 적용한 보정과 그 근거입니다." />
        <div className="card" style={{ color: "var(--ink-faint)" }}>불러오는 중입니다...</div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="데이터 보정 내역"
        desc="이 시스템이 쓰는 폐업률은 원본 그대로가 아닙니다. 무엇을 걷어냈고 왜 걷어냈는지 밝힙니다."
      />

      {/* ① 결론 먼저. 숫자 하나가 결론이면 도표로 만들지 않는다. */}
      <div className="card" style={{ marginBottom: 16, padding: 28 }}>
        <div style={{ display: "flex", gap: 32, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ flex: "0 0 auto" }}>
            <div className="t-caption" style={{ color: "var(--ink-muted)" }}>원본 폐업률은 실제보다</div>
            <div
              style={{
                fontSize: 64, lineHeight: 1.05, fontWeight: 800, letterSpacing: "-0.03em",
                color: "var(--error)", marginTop: 4,
              }}
            >
              {fmtPct(data.overstated_ratio, 1)}
              <span style={{ fontSize: 28, fontWeight: 700, marginLeft: 4 }}>배</span>
            </div>
            <div className="t-caption" style={{ color: "var(--ink-muted)", marginTop: 4 }}>
              높게 나옵니다 ({data.quarter_label} 기준)
            </div>
          </div>
          <p className="t-body-sm" style={{ flex: "1 1 320px", minWidth: 0, color: "var(--ink-secondary)", margin: 0, lineHeight: 1.8 }}>
            {data.base_quarter_label}에 있던 점포 <b>{fmtInt(data.total_stores)}곳</b> 가운데{" "}
            <b>{fmtInt(data.disappeared)}곳</b>이 다음 분기에 한꺼번에 사라졌습니다. 다른 분기 평균
            이탈은 {fmtInt(data.peer_average_disappeared)}곳으로, <b>{fmtPct(data.peer_ratio, 1)}배</b>에
            해당하는 이례적인 값입니다. 그대로 쓰면 이 분기 폐업률이{" "}
            {fmtPct(data.raw_closure_pct, 1)}%가 되고, 그 수치로 지원 대상을 정하면 실제와 크게
            어긋난 판단을 하게 됩니다.
          </p>
        </div>
      </div>

      {/* ② 사라진 것의 정체 */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="t-h3" style={{ margin: 0 }}>사라진 {fmtInt(data.disappeared)}곳을 추적한 결과</h3>
        <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "6px 0 20px", lineHeight: 1.7 }}>
          사라진 점포를 이후 분기에서 상가업소번호로 다시 찾아봤습니다.{" "}
          <b style={{ color: "var(--ink-secondary)" }}>
            {fmtPct(data.reappear_pct, 1)}%가 그대로 영업 중이었습니다.
          </b>{" "}
          문을 닫은 것이 아니라 그 분기 데이터에서 빠져 있었던 것입니다.
        </p>
        <Breakdown reappeared={data.reappeared} real={data.real_closures} total={data.disappeared} />
      </div>

      {/* ③ 전후 비교 */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="t-h3" style={{ margin: 0 }}>{data.quarter_label} 폐업률 — 보정 전후</h3>
        <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "6px 0 20px" }}>
          같은 분기, 같은 점포 {fmtInt(data.total_stores)}곳을 분모로 계산한 값입니다.
        </p>
        <BeforeAfter
          rows={[
            {
              label: "보정 전 (원본 그대로)",
              value: data.raw_closure_pct,
              note: `사라진 ${fmtInt(data.disappeared)}곳을 모두 폐업으로 셈`,
            },
            {
              label: "보정 후 (이 시스템이 쓰는 값)",
              value: data.corrected_closure_pct,
              note: `다시 나타난 ${fmtInt(data.reappeared)}곳을 제외하고 셈`,
              emphasis: true,
            },
          ]}
        />
      </div>

      {/* ④ 방법 */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="t-h3" style={{ margin: 0, marginBottom: 18 }}>어떻게 걷어냈나</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Step index={1} title="사라졌다 다시 나타난 점포는 폐업으로 세지 않습니다">
            분기별 점포 목록을 이어 붙일 때, 중간에 빠졌다가 되돌아온 구간을 메웁니다.
            점포 한 곳이 잠깐 누락된 것을 폐업 한 건으로 세지 않기 위해서입니다.
          </Step>
          <Step index={2} title="한 분기가 아니라 최근 4분기를 묶어서 봅니다">
            점포 50곳짜리 상권은 폐업 한두 건 차이로 폐업률이 1.5%와 9.0%를 오갑니다.
            4개 분기의 폐업 건수와 분모를 각각 합산해 비율을 냅니다. 특정 분기의 데이터 결함이
            순위를 통째로 뒤집지 못하게 하는 장치이기도 합니다.
          </Step>
          <Step index={3} title="등급은 고정 수치가 아니라 상대 순위로 매깁니다">
            "폐업률 10% 이상은 위험" 같은 고정 기준을 쓰면, 아직 규명되지 않은 데이터 급증이
            그대로 정책 판단이 됩니다. 화성시 안에서의 상위 10%·30%를 기준으로 삼으면 모든 상권이
            같이 움직일 때 상대 위치가 보존되어 그 영향을 받지 않습니다.
          </Step>
          <Step index={4} title="개업 방향은 다른 방법을 썼습니다">
            사라진 점포는 되돌아오는지 보면 되지만, 처음 등장한 점포는 비교할 이전 기록이 없어
            같은 방법이 통하지 않습니다. 개업은 인허가를 받은 분기로 시점을 되돌리는 방식으로
            교정했습니다.
          </Step>
        </div>
      </div>

      {/* ⑤ 한계 — 서버가 값과 같이 내려준다. 화면이 임의로 뺄 수 없다. */}
      <div className="card" style={{ marginBottom: 16, background: "var(--surface-container-lowest)" }}>
        <h3 className="t-h3" style={{ margin: 0, marginBottom: 12 }}>이 보정의 한계</h3>
        <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 9 }}>
          {(data.caveats ?? []).map((caveat) => (
            <li key={caveat} className="t-caption" style={{ color: "var(--ink-secondary)", lineHeight: 1.75 }}>
              {caveat}
            </li>
          ))}
        </ul>
        {data.sources?.length > 0 && (
          <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 16, lineHeight: 1.7 }}>
            재현 근거 · {data.sources.join(" · ")}
          </div>
        )}
      </div>

      <Link
        to="/blindspots"
        className="btn-utility"
        style={{
          display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
          textDecoration: "none", color: "var(--primary)", width: "100%", boxSizing: "border-box",
        }}
      >
        보이지 않는 상권은 사각지대에서 확인
        <span className="material-symbols-outlined" style={{ fontSize: 18 }}>arrow_forward</span>
      </Link>
    </div>
  );
}
