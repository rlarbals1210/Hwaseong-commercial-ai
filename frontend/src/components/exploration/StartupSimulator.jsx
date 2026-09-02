import { useId, useRef, useState } from "react";
import { calculateStartupCosts, EMPTY_STARTUP_INPUT, SQM_PER_PYEONG } from "../../lib/startupCosts";
import "./startupSimulator.css";

const STEPS = ["매장·초기비용", "월 운영비", "매출·결과"];
const STEP_FIELDS = [["area", "deposit", "interiorPerPyeong", "equipment", "inventory", "otherStartup", "reserve"],
  ["rent", "payroll", "utilities", "otherMonthly"], ["variableRate", "revenue"]];
const money = (value) => value == null ? "—" : `${value.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}만원`;

export default function StartupSimulator({ areaName, industryName, input, onChange }) {
  const [step, setStep] = useState(0);
  const [attempted, setAttempted] = useState(false);
  const sectionRef = useRef(null);
  const id = useId();
  const result = calculateStartupCosts(input);
  const preview = calculateStartupCosts({ ...input, variableRate: 0, revenue: "" });
  const ready = Object.keys(result.errors).length === 0;
  const errorStep = STEP_FIELDS.findIndex((fields) => fields.some((key) => result.errors[key]));
  const firstError = errorStep < 0 ? null : STEP_FIELDS[errorStep].find((key) => result.errors[key]);
  const update = (key, value) => onChange((current) => ({ ...current, [key]: value }));
  const changeAreaUnit = (unit) => onChange((current) => ({ ...current, areaUnit: unit,
    area: current.area === "" || unit === current.areaUnit ? current.area
      : String(Number(current.area) * (unit === "sqm" ? SQM_PER_PYEONG : 1 / SQM_PER_PYEONG)),
  }));
  const go = (next) => {
    setStep(next); setAttempted(false);
    sectionRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  };
  const next = () => {
    const invalid = STEP_FIELDS[step].find((key) => result.errors[key]);
    if (invalid) {
      setAttempted(true);
      const element = document.getElementById(`${id}-${invalid}`);
      const details = element?.closest("details");
      if (details) details.open = true;
      element?.focus();
    }
    else go(step + 1);
  };
  const field = (key, label, { unit = "만원", hint, placeholder = "0" } = {}) => {
    const error = (input[key] !== "" || attempted) && result.errors[key];
    return <label className="cost-field" key={key}>
      <span>{label}</span>
      <div className="cost-number"><input id={`${id}-${key}`} type="number" min="0" step="any" value={input[key]}
        placeholder={placeholder} onChange={(event) => update(key, event.target.value)}
        aria-label={`${label} (${unit})`} aria-invalid={Boolean(error)} aria-describedby={`${id}-${key}-help`} /><span>{unit}</span></div>
      <small id={`${id}-${key}-help`} className={error ? "cost-field-error" : ""} role={error ? "alert" : undefined}>{error || hint}</small>
    </label>;
  };
  return <section ref={sectionRef} className="explore-section startup-wizard" aria-label="창업비용 시뮬레이터">
    <div className="cost-heading"><div><h3>창업비용, 하나씩 계산해볼까요?</h3><p>{areaName} · {industryName}</p></div><span>단위: 만원</span></div>
    <nav className="cost-steps" aria-label="비용 입력 단계">{STEPS.map((label, index) => <button type="button" key={label}
      aria-current={step === index ? "step" : undefined} onClick={() => go(index)}><b>{index + 1}</b><span>{label}</span></button>)}</nav>
    <div className="cost-live-summary" aria-live="polite">
      <div><span>입력한 초기 자금</span><strong>{money(preview.initialCapital)}</strong></div>
      <div><span>월 고정비</span><strong>{money(preview.fixed)}</strong></div>
      <small>입력한 항목 기준 · 빈 비용은 0원으로 반영</small>
    </div>
    <div className="cost-step-content">
      {step === 0 && <>
        <h4>먼저, 매장 규모와 초기 견적을 알려주세요.</h4>
        <div className="explore-form-grid">
          {field("area", "매장 면적", { unit: input.areaUnit === "sqm" ? "㎡" : "평", placeholder: "면적 입력", hint: "평당 인테리어 비용 계산에 사용" })}
          <label className="cost-field"><span>면적 단위</span><select aria-label="면적 단위" value={input.areaUnit} onChange={(event) => changeAreaUnit(event.target.value)}><option value="pyeong">평</option><option value="sqm">㎡</option></select><small>단위를 바꾸면 자동 환산</small></label>
        </div>
        <div className="cost-size-options" aria-label="매장 면적 빠른 입력">{[10, 20, 30, 50].map((size) => <button type="button" key={size}
          onClick={() => onChange((current) => ({ ...current, area: String(size), areaUnit: "pyeong" }))}>{size}평</button>)}</div>
        <div className="explore-form-grid">
          {field("deposit", "임대 보증금", { hint: "초기 지출과 별도로 구분" })}
          {field("equipment", "설비·집기 비용", { hint: "주방기기, 가구 등 총액" })}
        </div>
        {field("interiorPerPyeong", "평당 인테리어 비용", { hint: `인테리어 합계 ${money(preview.interior)}` })}
        <details className="cost-extra"><summary>재고·예비자금 등 추가하기 <small>선택</small></summary><div className="explore-form-grid">
          {field("inventory", "초도 재고")}{field("reserve", "운영 예비자금")}{field("otherStartup", "기타 초기 지출")}
        </div></details>
      </>}
      {step === 1 && <>
        <h4>매달 고정적으로 나가는 비용은 얼마인가요?</h4>
        <p>가게의 매출과 관계없이 지출하는 금액을 입력하세요.</p>
        {field("rent", "월 임대료")}
        {field("payroll", "월 총인건비", { hint: "직원 전체 급여와 사업주 부담 비용의 합계" })}
        <details className="cost-extra"><summary>공과금·기타 고정비 추가하기 <small>선택</small></summary><div className="explore-form-grid">
          {field("utilities", "월 공과금")}{field("otherMonthly", "기타 월 고정비")}
        </div></details>
      </>}
      {step === 2 && <>
        <h4>매출 가정을 넣고 손익을 확인하세요.</h4>
        {field("variableRate", "매출 대비 변동비율", { unit: "%", placeholder: "비율 입력", hint: "재료비·카드/배달 수수료 등 매출에 비례하는 비용" })}
        <label className="cost-range"><span>변동비율 빠른 조정</span><input type="range" min="0" max="99" step="1" value={Math.min(99, Math.max(0, Number(input.variableRate) || 0))}
          aria-label="변동비율 빠른 조정" onChange={(event) => update("variableRate", event.target.value)} /><small>0% ~ 99%</small></label>
        {field("revenue", "가정 월매출", { hint: "선택 입력 · 실제 매출 예측값이 아닙니다", placeholder: "매출 가정 입력" })}
        {ready ? <div className="cost-final-result" aria-live="polite">
          <span>월 손익분기 매출</span><strong>{money(result.breakEven)}</strong><p>이 매출부터 입력한 월 운영비를 충당합니다.</p>
          {result.surplus !== null && <div className={result.surplus < 0 ? "cost-loss" : "cost-profit"}><span>가정 매출의 월 영업수지</span><b>{money(result.surplus)}</b></div>}
          <dl><div><dt>초기 지출</dt><dd>{money(result.spent)}</dd></div><div><dt>보증금·예비자금</dt><dd>{money(result.deposit + result.reserve)}</dd></div></dl>
        </div> : <div className="explore-status"><p>{result.errors[firstError]}</p>
          {errorStep < step && <button type="button" onClick={() => { go(errorStep); setAttempted(true); }}>{errorStep + 1}단계 입력 확인</button>}
        </div>}
      </>}
    </div>
    <div className="cost-step-actions"><button type="button" disabled={step === 0} onClick={() => go(step - 1)}>← 이전</button>
      {step < 2 ? <button type="button" className="cost-next" onClick={next}>{step === 0 ? "월 운영비 입력" : "매출·결과 보기"} →</button>
        : <button type="button" onClick={() => go(0)}>입력 다시 살펴보기</button>}</div>
    <details className="cost-explanation"><summary>계산 방법과 입력 안내</summary><p>손익분기 매출 = 월 고정비 ÷ (1 − 변동비율). 보증금·예비자금은 초기 지출과 구분합니다. 입력하지 않은 세금·감가상각·금융비용 등은 반영하지 않으며 투자금 회수기간 계산이 아닙니다. 실제 시세나 매출을 자동 추정하지 않습니다.</p></details>
    <div className="cost-draft-note"><small>같은 지역·업종의 입력은 페이지를 새로고침하기 전까지 유지됩니다.</small><button type="button" onClick={() => { onChange({ ...EMPTY_STARTUP_INPUT }); go(0); }}>입력 초기화</button></div>
  </section>;
}
