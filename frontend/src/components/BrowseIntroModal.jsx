import { useEffect, useRef } from "react";
import "./browseIntroModal.css";

// 랜딩에서 상권 둘러보기로 넘어올 때 뜨는 사용법 안내.
//
// 문구는 본선 발표의 시민 페르소나와 같은 대사를 쓴다 — 업종은 정했지만 자리를 못 정한
// 첫 창업자. 발표에서 들은 문장을 화면에서 다시 만나야 서사가 이어진다(랜딩 주석의
// "화면과 대본이 다른 표현이면 심사위원이 같은 것을 두 번 배워야 한다"와 같은 원칙).
//
// 파이프라인 산출값(등급·기준선·분기)은 여기에 적지 않는다. 재실행하면 바뀌는데 이
// 컴포넌트는 그 값을 다시 읽지 않아 낡은 숫자를 계속 말하게 된다. '29개 읍면동'은
// 행정구역 사실이라 예외다.

const STEPS = [
  {
    num: "1",
    title: "업종 고르기",
    desc: "준비 중인 업종 하나면 29개 읍면동 후보가 한 번에 뜹니다",
  },
  {
    num: "2",
    title: "가장 걱정되는 조건 고르기",
    desc: "수요 · 폐업 부담 · 경쟁 중 지금 제일 신경 쓰이는 것",
  },
  {
    num: "3",
    title: "후보 3곳 비교",
    desc: "추천 이유와 지표, 계약 전 현장에서 볼 항목까지",
  },
];

export default function BrowseIntroModal({ onClose }) {
  const startRef = useRef(null);

  useEffect(() => {
    startRef.current?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="bim-backdrop" onClick={onClose}>
      <div
        className="bim-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bim-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" className="bim-close" onClick={onClose} aria-label="안내 닫기">
          <span className="material-symbols-outlined">close</span>
        </button>

        <p className="bim-quote">
          장사는 하고 싶은데, 어느 지역에서 시작해야 할지 모르겠어요.
        </p>

        <h2 id="bim-title" className="bim-title">업종은 정했는데, 자리가 안 정해졌다면</h2>
        <p className="bim-lead">
          부동산·지인·블로그 말이 서로 다를 때, 화성시 29개 읍면동을 <b>같은 기준으로</b> 세워
          봅니다. 계약하기 전에요.
        </p>

        <ol className="bim-steps">
          {STEPS.map((step) => (
            <li key={step.num}>
              <span className="bim-step-num" aria-hidden="true">{step.num}</span>
              <div className="bim-step-body">
                <b>{step.title}</b>
                <span>{step.desc}</span>
              </div>
            </li>
          ))}
        </ol>

        <button type="button" className="bim-start" ref={startRef} onClick={onClose}>
          둘러보기 시작
        </button>
      </div>
    </div>
  );
}
