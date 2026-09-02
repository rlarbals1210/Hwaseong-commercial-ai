// 공무원 화면 목록의 단일 출처. 사이드바(App.jsx)와 랜딩 카드가 같은 배열을 쓴다 —
// 경로를 두 곳에 적으면 화면을 추가할 때 한쪽만 늘어난다.
// 화면 컴포넌트는 여기서 import하지 않는다(랜딩은 공개 화면이라 공무원 번들을 끌어올 이유가 없다).
// App.jsx가 path로 짝지어 붙인다.
export const OFFICIAL_ROUTES = [
  {
    path: "/dashboard",
    label: "조기경보 대시보드",
    icon: "dashboard",
    summary: "모델이 2분기 뒤 위험으로 본 상권을 순위로 봅니다.",
  },
  {
    path: "/map",
    label: "상권 위험 지도",
    icon: "map",
    summary: "읍면동별 위험 업종 비율을 지도에서 확인합니다.",
  },
  {
    path: "/policy",
    label: "지원 검토 우선순위",
    icon: "grid_view",
    summary: "관측된 폐업률과 영향 점포 수로 검토 순서를 정합니다.",
  },
  {
    path: "/blindspots",
    label: "사각지대",
    icon: "visibility_off",
    summary: "표본이 적어 통계 판단을 보류한 상권을 따로 봅니다.",
  },
  {
    path: "/compare",
    label: "상권 비교",
    icon: "compare_arrows",
    summary: "두 상권을 나란히 놓고 차이가 유의한지 확인합니다.",
  },
];

// 주요 분석 흐름과 분리된 공무원 전용 유틸리티. 사이드바 하단에 따로 노출한다.
export const DATA_MANAGEMENT_ROUTE = {
  path: "/data-management",
  label: "데이터 관리",
  icon: "database_upload",
};

const ALLOWED = new Set([...OFFICIAL_ROUTES.map((r) => r.path), DATA_MANAGEMENT_ROUTE.path]);

// 로그인 뒤 돌아갈 경로(?next=)는 반드시 이 화이트리스트를 통과해야 한다.
// 외부 주소나 프로토콜 상대 경로(//example.com)가 들어오면 무시하고 기본값으로 보낸다.
export function safeNext(next, fallback = "/dashboard") {
  if (typeof next !== "string" || !ALLOWED.has(next)) return fallback;
  return next;
}

export function officialRoute(path) {
  return OFFICIAL_ROUTES.find((r) => r.path === path) ?? null;
}
