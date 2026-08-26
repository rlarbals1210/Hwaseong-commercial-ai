// 등급·상권유형 배지 한 곳.
//
// 예전에는 화면마다 따로 그렸고, 그 결과 5단계 등급 중 "위험" 하나만 색이 칠해졌다.
// "주의"는 배경 없는 검은 글씨라(실측: background transparent / color #1b1b1b) 등급이 아니라
// 그냥 텍스트로 보였고, "안정"은 조기경보에서는 숨겨지고 비교·상세에서는 나타났다.
// 등급 축이 이 도구의 핵심 산출물인데 화면에서 축으로 읽히지 않았다(2026-08-25 감사).
//
// 필요한 CSS는 index.css에 이미 전부 있었다(.badge-warn / .badge-ok / .badge-neutral).
// 정의만 해두고 아무도 쓰지 않고 있었다.

const GRADE_CLASS = {
  위험: "badge badge-danger",
  주의: "badge badge-warn",
  안정: "badge badge-ok",
  표본부족: "badge badge-neutral",
  판단보류: "badge badge-neutral",
};

/** 등급 배지. 값이 없으면 아무것도 그리지 않는다. */
export function GradeBadge({ grade, title }) {
  if (!grade) return null;
  return (
    <span className={GRADE_CLASS[grade] ?? "badge badge-neutral"} title={title}>
      {grade}
    </span>
  );
}

// 유형은 위험도가 아니라 성격이다. 색을 주면 등급 축과 섞여 읽힌다 — 실제로 "고회전"의
// 주황이 "주의" 등급 색이자 오류 텍스트 색과 같아, 색 하나가 세 가지 의미를 갖고 있었다.
// 유형은 무채색으로 통일하고 구분은 글자에 맡긴다(전부 네 글자 이내다).
const TYPE_TITLE = {
  고회전: "폐업 많고 개업도 많음 — 나가는 만큼 새로 들어오는 상권",
  쇠퇴: "폐업 많고 개업 적음 — 나간 자리가 채워지지 않음",
  성장: "폐업 적고 개업 많음 — 새로 들어오는 곳이 더 많음",
  정체: "폐업 적고 개업도 적음 — 드나듦 자체가 적음",
  유형판정보류: "유형을 판정할 자료가 부족합니다",
};

/** 상권유형 배지. 판정보류는 그리지 않는다(자리만 차지하고 정보가 없다). */
export function TypeBadge({ type }) {
  if (!type || type === "유형판정보류") return null;
  return (
    <span className="badge badge-neutral" title={TYPE_TITLE[type]}>
      {type}
    </span>
  );
}
