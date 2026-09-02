import test from "node:test";
import assert from "node:assert/strict";
import { calculateStartupCosts as calc, SQM_PER_PYEONG } from "../src/lib/startupCosts.js";

const scenario = { area: 30, areaUnit: "pyeong", deposit: 2000, interiorPerPyeong: 100,
  equipment: 500, inventory: 100, otherStartup: 200, reserve: 500,
  rent: 200, payroll: 600, utilities: 50, otherMonthly: 150, variableRate: 40, revenue: 2000 };

test("initial capital separates deposit/reserve; monthly break-even honors payroll", () => {
  const result = calc(scenario);
  assert.equal(result.spent, 3800);
  assert.equal(result.initialCapital, 6300);
  assert.equal(result.fixed, 1000);
  assert.ok(Math.abs(result.breakEven - 1666.6666667) < .0001);
  assert.equal(result.surplus, 200);
  assert.equal(calc({ ...scenario, payroll: 800 }).surplus, 0);
  assert.equal(calc({ ...scenario, revenue: 1000 }).surplus, -400);
});
test("sqm and pyeong calculate the same interior estimate", () => {
  assert.equal(calc({ ...scenario, area: 30 * SQM_PER_PYEONG, areaUnit: "sqm" }).initialCapital, 6300);
});
test("missing revenue is not zero revenue; zero costs are valid", () => {
  assert.equal(calc({ ...scenario, revenue: "" }).surplus, null);
  assert.equal(calc({ area: 10, variableRate: 0 }).breakEven, 0);
});
test("invalid rates, amounts and dimensions never produce numeric results", () => {
  for (const [key, value] of [["variableRate", 100], ["variableRate", -1], ["area", 0], ["payroll", -1], ["rent", Infinity], ["area", ""], ["variableRate", ""]]) {
    const result = calc({ ...scenario, [key]: value });
    assert.ok(result.errors[key]);
    assert.equal(result.breakEven, undefined);
  }
});
