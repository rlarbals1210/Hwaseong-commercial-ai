export const SQM_PER_PYEONG = 3.305785;

export const EMPTY_STARTUP_INPUT = Object.freeze({ area: "", areaUnit: "pyeong", deposit: "",
  interiorPerPyeong: "", equipment: "", inventory: "", otherStartup: "", reserve: "",
  rent: "", payroll: "", utilities: "", otherMonthly: "", variableRate: "", revenue: "" });

// 돈의 단위는 모두 만원. 시세/매출 추정 없이 사용자가 입력한 시나리오만 계산한다.
export function calculateStartupCosts(input) {
  const errors = {};
  const read = (key, required = false) => {
    const raw = input[key];
    if (required && (raw === "" || raw == null)) errors[key] = "값을 입력해주세요.";
    const value = Number(raw ?? 0);
    if (!Number.isFinite(value) || value < 0 || value > 1e9) errors[key] = "0 이상 유효한 숫자를 입력해주세요.";
    return value;
  };
  const area = read("area", true);
  if (area <= 0) errors.area = "면적은 0보다 커야 합니다.";
  const pyeong = input.areaUnit === "sqm" ? area / SQM_PER_PYEONG : area;
  const variableRate = read("variableRate", true);
  if (variableRate >= 100) errors.variableRate = "변동비율은 100% 미만이어야 합니다.";
  const deposit = read("deposit");
  const reserve = read("reserve");
  const interior = read("interiorPerPyeong") * pyeong;
  const spent = interior + read("equipment") + read("inventory") + read("otherStartup");
  const fixed = read("rent") + read("payroll") + read("utilities") + read("otherMonthly");
  const revenue = input.revenue === "" || input.revenue == null ? null : read("revenue");
  if (Object.keys(errors).length) return { errors };
  return {
    errors, pyeong, sqm: pyeong * SQM_PER_PYEONG, interior, deposit, reserve,
    spent, initialCapital: spent + deposit + reserve, fixed,
    breakEven: fixed / (1 - variableRate / 100),
    surplus: revenue === null ? null : revenue * (1 - variableRate / 100) - fixed,
  };
}
