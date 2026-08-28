import { useEffect, useRef } from "react";

const PRIMARY_TASKS = [
  {
    path: "/dashboard",
    icon: "crisis_alert",
    goal: "먼저 확인할 위험 상권을 찾고 싶어요",
    action: "조기경보에서 상위 지역·업종 카드를 선택하세요.",
    outcome: "AI가 2분기 뒤 위험으로 본 상대 순위와 실제 관측 근거를 확인할 수 있습니다.",
    cta: "조기경보 확인하기",
  },
  {
    path: "/map",
    icon: "map_search",
    goal: "특정 지역의 전체 상황을 알고 싶어요",
    action: "공실위험 지도에서 읍면동을 선택하세요.",
    outcome: "해당 지역의 관측 폐업률, 위험 업종, 표본 범위를 한번에 확인할 수 있습니다.",
    cta: "지도에서 지역 보기",
  },
  {
    path: "/policy",
    icon: "fact_check",
    goal: "어디부터 현장 확인할지 정하고 싶어요",
    action: "현장 확인 우선순위에서 '확인 1순위' 영역을 살펴보세요.",
    outcome: "관측 폐업률과 영향 점포 수를 함께 비교해 현장 확인 순서를 검토할 수 있습니다.",
    cta: "현장 확인 후보 보기",
  },
];

const SECONDARY_TASKS = [
  {
    path: "/compare",
    icon: "compare_arrows",
    goal: "두 상권의 차이를 비교하고 싶어요",
    action: "상권 비교에서 두 지역·업종을 선택하세요.",
    outcome: "폐업률과 주요 지표의 차이, 그 차이가 유의한지 확인할 수 있습니다.",
    cta: "상권 비교하기",
  },
  {
    path: "/blindspots",
    icon: "visibility_off",
    goal: "데이터가 적은 지역도 놓치고 싶지 않아요",
    action: "사각지대에서 판단보류 지역·업종을 확인하세요.",
    outcome: "점포 수가 부족해 일반 순위에서 빠진 상권을 별도로 관리할 수 있습니다.",
    cta: "사각지대 확인하기",
  },
];

function TaskCard({ task, compact = false, onSelect }) {
  return (
    <button
      type="button"
      className={`quickstart-task${compact ? " compact" : ""}`}
      onClick={() => onSelect(task.path)}
    >
      <span className="quickstart-task-icon material-symbols-outlined" aria-hidden="true">
        {task.icon}
      </span>
      <span className="quickstart-task-copy">
        <strong>{task.goal}</strong>
        <span><b>이렇게 하세요</b>{task.action}</span>
        <span><b>할 수 있는 일</b>{task.outcome}</span>
        <em>{task.cta}<span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span></em>
      </span>
    </button>
  );
}

export default function OfficialQuickStart({ open, onClose, onNavigate }) {
  const dialogRef = useRef(null);
  const closeRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;

      const focusable = [...dialogRef.current.querySelectorAll("button:not([disabled])")];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="quickstart-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="quickstart-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quickstart-title"
        aria-describedby="quickstart-description"
      >
        <header className="quickstart-header">
          <div>
            <span className="quickstart-eyebrow">공무원 업무 퀵스타트</span>
            <h2 id="quickstart-title">오늘 어떤 업무를 하시나요?</h2>
            <p id="quickstart-description">하려는 일을 선택하면 필요한 화면으로 바로 이동합니다.</p>
          </div>
          <button ref={closeRef} type="button" className="quickstart-close" onClick={onClose} aria-label="사용법 닫기">
            <span className="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
        </header>

        <div className="quickstart-content">
          <div className="quickstart-section-label">주요 업무</div>
          <div className="quickstart-primary-list">
            {PRIMARY_TASKS.map((task) => <TaskCard key={task.path} task={task} onSelect={onNavigate} />)}
          </div>

          <div className="quickstart-section-label">다른 업무</div>
          <div className="quickstart-secondary-grid">
            {SECONDARY_TASKS.map((task) => (
              <TaskCard key={task.path} task={task} compact onSelect={onNavigate} />
            ))}
          </div>
        </div>

        <footer className="quickstart-footer">
          <p>닫아도 왼쪽 아래 <b>업무별 사용법</b>에서 다시 볼 수 있습니다.</p>
          <button type="button" className="btn-primary" onClick={onClose}>바로 시작하기</button>
        </footer>
      </section>
    </div>
  );
}
