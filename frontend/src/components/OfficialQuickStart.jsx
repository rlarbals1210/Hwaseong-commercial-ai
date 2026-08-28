import { useCallback, useEffect, useRef, useState } from "react";

const STEPS = [
  {
    path: "/dashboard",
    menu: "조기경보 대시보드",
    goal: "먼저 확인할 위험 상권을 찾고 싶어요",
    action: "조기경보 대시보드에서 상위 지역·업종 카드를 선택하세요.",
    outcome: "AI가 2분기 뒤 위험으로 본 상대 순위와 실제 관측 근거를 확인할 수 있습니다.",
  },
  {
    path: "/map",
    menu: "상권 위험 지도",
    goal: "특정 지역의 전체 상황을 알고 싶어요",
    action: "상권 위험 지도에서 확인할 읍면동을 선택하세요.",
    outcome: "해당 지역의 관측 폐업률, 위험 업종, 표본 범위를 한번에 확인할 수 있습니다.",
  },
  {
    path: "/policy",
    menu: "현장 확인 우선순위",
    goal: "어디부터 현장 확인할지 정하고 싶어요",
    action: "현장 확인 우선순위에서 '확인 1순위' 영역을 살펴보세요.",
    outcome: "관측 폐업률과 영향 점포 수를 함께 비교해 현장 확인 순서를 검토할 수 있습니다.",
  },
  {
    path: "/blindspots",
    menu: "사각지대",
    goal: "데이터가 적은 지역도 놓치고 싶지 않아요",
    action: "사각지대에서 판단보류 지역·업종을 확인하세요.",
    outcome: "점포 수가 부족해 일반 순위에서 빠진 상권을 별도로 관리할 수 있습니다.",
  },
  {
    path: "/compare",
    menu: "상권 비교",
    goal: "두 상권의 차이를 비교하고 싶어요",
    action: "상권 비교에서 두 지역·업종을 선택하세요.",
    outcome: "폐업률과 주요 지표의 차이, 그 차이가 유의한지 확인할 수 있습니다.",
  },
];

export default function OfficialQuickStart({ open, onClose }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [targetRect, setTargetRect] = useState(null);
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  const step = STEPS[stepIndex];

  const closeTour = useCallback(() => {
    setStepIndex(0);
    onClose();
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;

    const updateTarget = () => {
      const target = document.querySelector(`[data-quickstart-path="${step.path}"]`);
      if (!target) {
        setTargetRect(null);
        return;
      }
      const rect = target.getBoundingClientRect();
      setTargetRect({ top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left, width: rect.width, height: rect.height });
    };

    const frame = window.requestAnimationFrame(updateTarget);
    window.addEventListener("resize", updateTarget);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updateTarget);
    };
  }, [open, step.path]);

  useEffect(() => {
    if (!open) return undefined;

    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeTour();
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
  }, [open, closeTour]);

  if (!open) return null;

  const popoverTop = targetRect
    ? Math.max(24, Math.min(targetRect.top - 26, window.innerHeight - 390))
    : Math.max(24, (window.innerHeight - 360) / 2);
  const popoverLeft = targetRect ? targetRect.right + 20 : 280;

  return (
    <div className="quickstart-tour-layer">
      <button type="button" className="quickstart-tour-blocker" onClick={closeTour} aria-label="사용법 건너뛰기" />

      {targetRect && (
        <div
          className="quickstart-tour-spotlight"
          aria-hidden="true"
          style={{
            top: targetRect.top - 4,
            left: targetRect.left - 4,
            width: targetRect.width + 8,
            height: targetRect.height + 8,
          }}
        />
      )}

      <section
        ref={dialogRef}
        className={`quickstart-tour-popover${targetRect ? "" : " centered"}`}
        style={{ top: popoverTop, left: popoverLeft }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="quickstart-title"
        aria-describedby="quickstart-description"
      >
        <header className="quickstart-tour-header">
          <div>
            <span className="quickstart-tour-count">{stepIndex + 1} / {STEPS.length}</span>
            <span className="quickstart-tour-menu">{step.menu}</span>
          </div>
          <button ref={closeRef} type="button" className="quickstart-tour-close" onClick={closeTour} aria-label="사용법 닫기">
            <span className="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
        </header>

        <div className="quickstart-tour-content">
          <h2 id="quickstart-title">{step.goal}</h2>
          <div id="quickstart-description" className="quickstart-tour-instructions">
            <p><b>이렇게 하세요</b>{step.action}</p>
            <p><b>할 수 있는 일</b>{step.outcome}</p>
          </div>
        </div>

        <footer className="quickstart-tour-footer">
          <button type="button" className="quickstart-tour-skip" onClick={closeTour}>건너뛰기</button>
          <div>
            {stepIndex > 0 && (
              <button type="button" className="btn-utility" onClick={() => setStepIndex((index) => index - 1)}>이전</button>
            )}
            {stepIndex < STEPS.length - 1 ? (
              <button type="button" className="btn-primary" onClick={() => setStepIndex((index) => index + 1)}>
                다음 <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
              </button>
            ) : (
              <button type="button" className="btn-primary" onClick={closeTour}>사용법 마치기</button>
            )}
          </div>
        </footer>
      </section>
    </div>
  );
}
