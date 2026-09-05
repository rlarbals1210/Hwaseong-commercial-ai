/* 반영 실행 API가 아직 없는 상태에서 화면 흐름만 먼저 확인하기 위한 임시 모듈이다.
 *
 * 표시되는 지표는 지어낸 값이 아니라 data/processed/demand_model_results.json에
 * 남아 있는 실제 학습 결과를 옮긴 것이다(선택 모델 rolling_mean_blend, 시험 구간
 * 2025-02~06 기준). 진행 단계 이름과 소요 구간만 시연용으로 압축했다.
 *
 * 백엔드가 붙으면 이 파일을 지우고 apiFetchJson 호출로 바꾼다. 반환 모양은
 * 계획한 응답 스키마 그대로라 호출부는 손대지 않아도 된다.
 *   GET  /api/data-management            -> reflection: fetchReflectionState()
 *   POST /api/data-management/reflect    -> startReflection()
 *   GET  /api/data-management/reflect/:id-> fetchReflectionRun()
 */

export const REFLECTION_IS_MOCK = true;

// 실제 학습에서는 수 분이 걸린다. 시연에서 기다릴 수 없어 단계별 구간만 줄였다.
const STEPS = [
  { until: 2000, status: "running", step: "preparing", label: "입력 파일과 원본 데이터 경로를 확인하는 중" },
  { until: 5000, status: "running", step: "building", label: "수요 패널 구성 · 연속 관측 24개월 추출" },
  { until: 9000, status: "running", step: "training", label: "모델 학습 · 시험 구간 5개월 평가" },
  { until: 11500, status: "verifying", step: "verifying", label: "배포 게이트 검증" },
];

const GATE = {
  minimum_test_mae_improvement_pct: 0.5,
  maximum_spearman_drop: 0.005,
  maximum_top5_overlap_drop: 0.02,
};

const PASSED_GATE = {
  ...GATE,
  passed: true,
  mae_improvement_pct: 3.647546091545576,
  baseline_mae: 0.008380109771825574,
  selected_mae: 0.008074441405376121,
  baseline_spearman: 0.9309332719121374,
  selected_spearman: 0.9334193642754286,
  baseline_top5_overlap: 0.8708433734939759,
  selected_top5_overlap: 0.8732530120481927,
};

// 게이트 실패 화면을 시연하려면 주소에 ?mock=fail 을 붙인다.
const FAILED_GATE = {
  ...GATE,
  passed: false,
  mae_improvement_pct: 0.21,
  baseline_mae: 0.008380109771825574,
  selected_mae: 0.008362504,
  baseline_spearman: 0.9309332719121374,
  selected_spearman: 0.9241802,
  baseline_top5_overlap: 0.8708433734939759,
  selected_top5_overlap: 0.8611044,
};

const OUTPUTS = {
  source_month: "202506",
  forecast_target_month: "202507",
  score_rows: 1802,
  area_count: 29,
  industry_count: 74,
  card_code_count: 83,
  selected_model: "rolling_mean_blend",
  blend: 0.6,
};

let current = null;
let history = [];

const wantsFailure = () => {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("mock") === "fail";
};

const settle = (run) => {
  const gate = run.gate_preview;
  if (gate.passed) {
    return {
      ...run,
      status: "applied",
      step: "applied",
      progress_label: "반영 완료",
      finished_at: new Date().toISOString(),
      gate,
      outputs: OUTPUTS,
    };
  }
  return {
    ...run,
    status: "failed",
    step: "discarded",
    progress_label: "게이트 미달로 폐기",
    finished_at: new Date().toISOString(),
    gate,
    failure_reason:
      "시험 구간 MAE 개선이 기준(0.5%)에 미치지 못해 새 산출물을 폐기했습니다. " +
      "기존 수요 여건 값이 그대로 유지됩니다.",
  };
};

const project = (run) => {
  if (!run) return null;
  if (run.status === "applied" || run.status === "failed") return run;
  const elapsed = Date.now() - new Date(run.started_at).getTime();
  const stage = STEPS.find((item) => elapsed < item.until);
  if (!stage) return settle(run);
  return { ...run, status: stage.status, step: stage.step, progress_label: stage.label };
};

const delay = (value, ms = 240) =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms));

export function fetchReflectionState() {
  current = project(current);
  if (current && (current.status === "applied" || current.status === "failed")) {
    if (!history.some((run) => run.run_id === current.run_id)) history = [current, ...history];
  }
  const running = current && current.status !== "applied" && current.status !== "failed";
  return delay({
    available: !running,
    blocked_reason: null,
    running_run: running ? current : null,
    last_run: history[0] ?? null,
    runs: history,
  });
}

export function startReflection(inputs) {
  const projected = project(current);
  if (projected && projected.status !== "applied" && projected.status !== "failed") {
    const error = new Error("이미 반영이 진행 중입니다");
    error.status = 409;
    return Promise.reject(error);
  }
  current = {
    run_id: `run-${Date.now()}`,
    status: "running",
    step: "preparing",
    progress_label: STEPS[0].label,
    started_at: new Date().toISOString(),
    finished_at: null,
    started_by: "공무원",
    inputs: inputs ?? [],
    gate_preview: wantsFailure() ? FAILED_GATE : PASSED_GATE,
  };
  return delay({ run_id: current.run_id, status: current.status }, 420);
}

export function fetchReflectionRun(runId) {
  const projected = project(current);
  if (projected?.run_id === runId) {
    current = projected;
    if (projected.status === "applied" || projected.status === "failed") {
      if (!history.some((run) => run.run_id === projected.run_id)) history = [projected, ...history];
    }
    return delay(projected, 120);
  }
  const found = history.find((run) => run.run_id === runId);
  if (found) return delay(found, 120);
  const error = new Error("실행 기록을 찾을 수 없습니다");
  error.status = 404;
  return Promise.reject(error);
}
