import { createContext, useContext } from "react";

// 화면 안내가 떠 있는 동안 페이지가 자기 모달을 같이 열면 두 개가 겹쳐 보인다.
// 페이지는 이 값을 보고 안내가 닫힐 때까지 자기 모달을 미룬다.
export const QuickStartContext = createContext(false);

export function useQuickStartOpen() {
  return useContext(QuickStartContext);
}
