import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { formatDateTime, formatMonth } from "../lib/format";
import {
  REFLECTION_IS_MOCK,
  fetchReflectionRun,
  fetchReflectionState,
  startReflection,
} from "../lib/reflectionMock";

const POLL_MS = 1200;

const isSettled = (run) => run?.status === "applied" || run?.status === "failed";

const pct = (value, digits = 2) =>
  Number.isFinite(Number(value)) ? `${Number(value).toFixed(digits)}%` : "—";

const num = (value, digits = 3) =>
  Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "—";

function gateRows(gate) {
  if (!gate) return [];
  return [
    {
      label: "시험 구간 MAE 개선",
      result: pct(gate.mae_improvement_pct),
      standard: `${pct(gate.minimum_test_mae_improvement_pct, 1)} 이상`,
      ok: Number(gate.mae_improvement_pct) >= Number(gate.minimum_test_mae_improvement_pct),
    },
    {
      label: "지역 순위 상관",
      result: num(gate.selected_spearman),
      standard: `기준선 ${num(gate.baseline_spearman)} 대비 −${num(gate.maximum_spearman_drop)} 이내`,
      ok:
        Number(gate.selected_spearman) >=
        Number(gate.baseline_spearman) - Number(gate.maximum_spearman_drop),
    },
    {
      label: "상위 5곳 일치율",
      result: num(gate.selected_top5_overlap),
      standard: `기준선 ${num(gate.baseline_top5_overlap)} 대비 −${num(gate.maximum_top5_overlap_drop, 2)} 이내`,
      ok:
        Number(gate.selected_top5_overlap) >=
        Number(gate.baseline_top5_overlap) - Number(gate.maximum_top5_overlap_drop),
    },
  ];
}

function GateTable({ gate }) {
  const rows = gateRows(gate);
  if (!rows.length) return null;
  return (
    <table className="data-reflect-gate">
      <thead>
        <tr>
          <th>검증 항목</th>
          <th>이번 결과</th>
          <th>통과 기준</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <td>{row.label}</td>
            <td>
              <span className={`data-reflect-gate-value is-${row.ok ? "ok" : "bad"}`}>
                <span className="material-symbols-outlined" aria-hidden="true">
                  {row.ok ? "check_circle" : "cancel"}
                </span>
                {row.result}
              </span>
            </td>
            <td>{row.standard}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ReflectionDetail({ run }) {
  if (!run) return null;
  const outputs = run.outputs ?? {};
  const items = [
    { label: "상태", value: run.status === "applied" ? "반영 완료" : "게이트 미달 · 폐기" },
    { label: "시작", value: formatDateTime(run.started_at) },
    { label: "종료", value: formatDateTime(run.finished_at) },
    { label: "실행자", value: run.started_by },
    { label: "선택 모델", value: outputs.selected_model, mono: true },
    {
      label: "예측 기준월 → 대상월",
      value: outputs.source_month
        ? `${formatMonth(outputs.source_month)} → ${formatMonth(outputs.forecast_target_month)}`
        : null,
    },
    {
      label: "갱신 범위",
      value: outputs.score_rows
        ? `${Number(outputs.score_rows).toLocaleString("ko-KR")}개 셀 · 읍면동 ${outputs.area_count} · 업종 ${outputs.industry_count}`
        : null,
    },
  ].filter((item) => item.value !== null && item.value !== undefined && item.value !== "");

  return (
    <>
      {run.inputs?.length > 0 && (
        <div className="data-reflect-inputs">
          <span className="t-eyebrow">사용한 파일</span>
          <ul>
            {run.inputs.map((input) => (
              <li key={input.original_filename}>
                <b>{input.dataset_title}</b>
                <code>{input.original_filename}</code>
              </li>
            ))}
          </ul>
        </div>
      )}
      <dl className="data-history-detail-grid">
        {items.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd className={item.mono ? "is-mono" : undefined}>{item.value}</dd>
          </div>
        ))}
      </dl>
      <GateTable gate={run.gate} />
      {run.failure_reason && (
        <p className="data-reflect-failure-note">{run.failure_reason}</p>
      )}
    </>
  );
}

function ConfirmDialog({ inputs, onCancel, onConfirm }) {
  const panelRef = useRef(null);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onCancel]);

  // HistoryDialog와 같은 이유로 body에 붙인다 — 카드에 남는 transform이
  // position: fixed의 기준 블록이 되어 팝업이 카드 안에 갇힌다.
  return createPortal(
    <div className="data-history-modal" onClick={onCancel}>
      <div
        ref={panelRef}
        className="data-history-modal-panel data-reflect-confirm"
        role="dialog"
        aria-modal="true"
        aria-label="모델 반영 확인"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="data-history-modal-head">
          <div>
            <span className="badge data-status-pending">반영 확인</span>
            <h3 className="t-title">검증한 파일을 모델에 반영할까요?</h3>
            <p className="t-caption">되돌릴 수 있도록 기존 산출물은 백업으로 보관합니다.</p>
          </div>
          <button
            type="button"
            className="data-history-modal-close"
            onClick={onCancel}
            aria-label="닫기"
          >
            <span className="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
        </header>
        <div className="data-history-modal-body">
          <div className="data-reflect-inputs">
            <span className="t-eyebrow">사용할 파일</span>
            <ul>
              {inputs.map((input) => (
                <li key={input.original_filename}>
                  <b>{input.dataset_title}</b>
                  <code>{input.original_filename}</code>
                </li>
              ))}
            </ul>
          </div>
          <div className="data-reflect-scope">
            <div className="data-reflect-scope-item is-change">
              <span className="material-symbols-outlined" aria-hidden="true">sync</span>
              <div>
                <b>바뀌는 것</b>
                <span>상권 탐색 추천의 &lsquo;수요 여건&rsquo; 축과 그 설명 문구</span>
              </div>
            </div>
            <div className="data-reflect-scope-item is-keep">
              <span className="material-symbols-outlined" aria-hidden="true">lock</span>
              <div>
                <b>바뀌지 않는 것</b>
                <span>폐업위험 등급 · 상권 위험 지도 · 조기경보 · 현장점검 우선순위</span>
              </div>
            </div>
          </div>
          <p className="data-reflect-gate-note">
            학습 후 배포 게이트를 통과하지 못하면 새 산출물을 폐기하고 현재 값을 그대로 둡니다.
          </p>
        </div>
        <footer className="data-reflect-confirm-actions">
          <button type="button" className="btn-ghost" onClick={onCancel}>
            취소
          </button>
          <button type="button" className="btn-primary" onClick={onConfirm}>
            <span className="material-symbols-outlined" aria-hidden="true">model_training</span>
            반영 실행
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}

export default function ReflectionPanel({ datasets, onRunsChange }) {
  const [state, setState] = useState(null);
  const [run, setRun] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");

  const pending = (datasets ?? [])
    .map((dataset) => dataset.latest_upload)
    .filter((upload) => upload && (upload.reflection_status ?? "pending") === "pending")
    .map((upload) => ({
      dataset_title: upload.dataset_title,
      original_filename: upload.original_filename,
      uploaded_at_utc: upload.uploaded_at_utc,
    }));

  const publish = useCallback(
    (next) => {
      setState(next);
      onRunsChange?.(next?.runs ?? []);
    },
    [onRunsChange],
  );

  useEffect(() => {
    let active = true;
    fetchReflectionState().then((next) => {
      if (!active) return;
      publish(next);
      if (next.running_run) setRun(next.running_run);
      else if (next.last_run) setRun(next.last_run);
    });
    return () => { active = false; };
  }, [publish]);

  useEffect(() => {
    if (!run || isSettled(run)) return undefined;
    let active = true;
    const timer = setInterval(() => {
      fetchReflectionRun(run.run_id)
        .then((next) => {
          if (!active) return;
          setRun(next);
          if (isSettled(next)) fetchReflectionState().then((s) => active && publish(s));
        })
        .catch((pollError) => active && setError(pollError.message));
    }, POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [run, publish]);

  const launch = () => {
    setConfirming(false);
    setError("");
    startReflection(pending)
      .then(({ run_id }) => fetchReflectionRun(run_id))
      .then(setRun)
      .catch((startError) => setError(startError.message));
  };

  const running = run && !isSettled(run);
  const blockedReason = state?.blocked_reason
    ? state.blocked_reason
    : pending.length === 0
      ? "반영 대기 중인 파일이 없습니다. 먼저 파일을 업로드해 검증하세요."
      : null;
  const disabled = Boolean(running || blockedReason || !state);

  return (
    <section className="data-reflect card">
      <div className="data-upload-section-head">
        <div>
          <h2 className="t-title">모델에 반영</h2>
          <p className="t-body-sm">
            검증을 통과해 대기 중인 파일로 수요 예측을 다시 계산합니다.
          </p>
        </div>
        {REFLECTION_IS_MOCK && (
          <span className="badge data-status-pending">시연 모드 · 실제 실행 없음</span>
        )}
      </div>

      <div className="data-reflect-body">
        <div className="data-reflect-queue">
          <span className="t-eyebrow">반영 대기</span>
          {pending.length ? (
            <ul>
              {pending.map((input) => (
                <li key={input.original_filename}>
                  <span className="material-symbols-outlined" aria-hidden="true">draft</span>
                  <div>
                    <b>{input.dataset_title}</b>
                    <small>{input.original_filename} · {formatDateTime(input.uploaded_at_utc)}</small>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="t-caption">대기 중인 파일이 없습니다.</p>
          )}
        </div>

        <div className="data-reflect-action">
          <button
            type="button"
            className={`btn-primary data-reflect-submit${running ? " is-running" : ""}`}
            disabled={disabled}
            onClick={() => setConfirming(true)}
          >
            <span className="material-symbols-outlined" aria-hidden="true">
              {running ? "progress_activity" : "model_training"}
            </span>
            {running ? "반영 중…" : "모델에 반영하기"}
          </button>
          <p className="t-caption">
            {blockedReason
              ?? "누르면 반영 범위를 확인한 뒤 실행합니다. 게이트 미달 시 자동으로 폐기됩니다."}
          </p>
        </div>
      </div>

      {error && <div className="data-upload-feedback is-error" role="alert">
        <span className="material-symbols-outlined" aria-hidden="true">error</span>
        {error}
      </div>}

      {running && (
        <div className="data-reflect-progress" role="status">
          <div className="data-reflect-progress-bar"><span /></div>
          <div className="data-reflect-progress-text">
            <b>{run.progress_label}</b>
            <small>진행 중에는 현재 지표가 그대로 유지됩니다.</small>
          </div>
        </div>
      )}

      {run && isSettled(run) && (
        <div className={`data-reflect-result is-${run.status}`}>
          <header>
            <span className="material-symbols-outlined" aria-hidden="true">
              {run.status === "applied" ? "task_alt" : "block"}
            </span>
            <div>
              <b>
                {run.status === "applied"
                  ? "반영 완료 — 추천의 수요 여건이 갱신되었습니다"
                  : "게이트 미달 — 새 산출물을 폐기했습니다"}
              </b>
              <small>{formatDateTime(run.finished_at)} · {run.started_by}</small>
            </div>
          </header>
          {run.status === "applied" && run.outputs && (
            <p className="data-reflect-outputs">
              {formatMonth(run.outputs.source_month)}까지의 매출로{" "}
              {formatMonth(run.outputs.forecast_target_month)} 수요를 예측 ·{" "}
              {Number(run.outputs.score_rows).toLocaleString("ko-KR")}개 셀 갱신 ·{" "}
              선택 모델 <code>{run.outputs.selected_model}</code>
            </p>
          )}
          {run.failure_reason && <p className="data-reflect-failure-note">{run.failure_reason}</p>}
          <GateTable gate={run.gate} />
        </div>
      )}

      {confirming && (
        <ConfirmDialog
          inputs={pending}
          onCancel={() => setConfirming(false)}
          onConfirm={launch}
        />
      )}
    </section>
  );
}
