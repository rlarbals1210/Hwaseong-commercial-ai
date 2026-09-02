import { useState } from "react";
import { calculateStartupCosts, SQM_PER_PYEONG } from "../../lib/startupCosts";

const GROUPS = [
  ["초기 자금", [["deposit", "보증금"], ["interiorPerPyeong", "평당 인테리어 비용"],
    ["equipment", "설비·집기"], ["inventory", "초도 재고"], ["otherStartup", "기타 초기 지출"], ["reserve", "운영 예비자금"]]],
  ["월 고정비", [["rent", "월 임대료"], ["payroll", "월 총인건비"], ["utilities", "공과금"], ["otherMonthly", "기타 월 고정비"]]],
];
const INITIAL = Object.fromEntries(["area", "variableRate", "revenue", ...GROUPS.flatMap(([, fields]) => fields.map(([key]) => key))].map((key) => [key, ""]));
const money = (value) => `${value.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}만원`;

export default function StartupSimulator({ areaName, industryName }) {
  const [input, setInput] = useState({ ...INITIAL, areaUnit: "pyeong" });
  const result = calculateStartupCosts(input);
  const update = (key, value) => setInput((current) => ({ ...current, [key]: value }));
  const changeAreaUnit = (unit) => setInput((current) => ({ ...current, areaUnit: unit,
    area: current.area === "" || unit === current.areaUnit ? current.area
      : String(Number(current.area) * (unit === "sqm" ? SQM_PER_PYEONG : 1 / SQM_PER_PYEONG)),
  }));
  const field = (key, label, unit = "만원") => (
    <label className="explore-input" key={key}>
      <span>{label} <small>({unit})</small></span>
      <input type="number" min="0" step="any" value={input[key]} placeholder="직접 입력"
        onChange={(event) => update(key, event.target.value)} aria-label={`${label} (${unit})`}
        aria-invalid={Boolean(input[key] !== "" && result.errors[key])} />
      {input[key] !== "" && result.errors[key] && <small role="alert">{result.errors[key]}</small>}
    </label>
  );
  return (
    <section className="explore-section" aria-label="창업비용 시뮬레이터">
      <h3>창업비용 시뮬레이터</h3>
      <p>{areaName} · {industryName}의 창업을 가정해 직접 받은 견적을 입력하세요. 실제 시세나 예상 매출을 자동 추정하지 않습니다.</p>
      <div className="explore-form-grid">
        {field("area", "매장 면적", input.areaUnit === "sqm" ? "㎡" : "평")}
        <label className="explore-input"><span>면적 단위</span><select value={input.areaUnit} onChange={(event) => changeAreaUnit(event.target.value)}>
          <option value="pyeong">평</option><option value="sqm">㎡</option>
        </select></label>
      </div>
      {GROUPS.map(([title, fields]) => <fieldset key={title}><legend>{title}</legend><div className="explore-form-grid">{fields.map(([key, label]) => field(key, label))}</div></fieldset>)}
      <div className="explore-form-grid">
        {field("variableRate", "매출 대비 변동비율", "%")}
        {field("revenue", "가정 월매출 · 선택")}
      </div>
      <p>변동비에는 재료비·카드/배달 수수료 등을 포함하세요. 인건비는 인원수가 아닌 월 총액입니다. 빈 비용 항목은 0원으로 계산합니다.</p>
      {!Object.keys(result.errors).length ? <div className="explore-cost-result" aria-live="polite">
        <small>{result.pyeong.toFixed(1)}평 · {result.sqm.toFixed(1)}㎡ / 인테리어 {money(result.interior)}</small>
        <dl>
          <div><dt>필요 초기 자금</dt><dd>{money(result.initialCapital)}</dd></div>
          <div><dt>초기 지출</dt><dd>{money(result.spent)}</dd></div>
          <div><dt>보증금 + 예비자금</dt><dd>{money(result.deposit + result.reserve)}</dd></div>
          <div><dt>월 고정비</dt><dd>{money(result.fixed)}</dd></div>
          <div><dt>월 손익분기 매출</dt><dd>{money(result.breakEven)}</dd></div>
          {result.surplus !== null && <div><dt>가정 매출의 월 영업수지</dt><dd className={result.surplus < 0 ? "negative" : ""}>{money(result.surplus)}</dd></div>}
        </dl>
      </div> : <p className="explore-status">면적과 100% 미만의 변동비율을 입력하면 계산합니다.</p>}
      <p>월 손익분기 매출 = 월 고정비 ÷ (1 − 변동비율). 보증금·예비자금은 초기 지출과 구분했습니다. 세금·감가상각·금융비용 등 입력하지 않은 항목은 반영되지 않으며 투자금 회수기간 계산이 아닙니다. 패널을 닫거나 다른 목록·지역·업종으로 이동하면 입력이 초기화됩니다.</p>
      <button type="button" className="explore-secondary" onClick={() => setInput({ ...INITIAL, areaUnit: "pyeong" })}>입력 초기화</button>
    </section>
  );
}
