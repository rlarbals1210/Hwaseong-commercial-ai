// Vite proxy(/api → :8000)를 사용하므로 개발/프로덕션 모두 빈 문자열이 기본값.
// 외부 배포 시 VITE_API_BASE=https://yourdomain.com 으로 오버라이드 가능.
export const API = import.meta.env.VITE_API_BASE ?? "";

const AUTH_STORAGE_KEY = "hcai_auth";
const EXPIRED_FLAG_KEY = "hcai_session_expired";

// 토큰 만료를 앱 전체에 알리는 이벤트. AuthProvider가 듣고 로그아웃 상태로 바꾼다.
// 페이지마다 401 처리를 따로 쓰지 않게 하려고 이벤트로 한 번만 처리한다.
export const UNAUTHORIZED_EVENT = "hcai:unauthorized";

export function getStoredAuth() {
  try {
    return JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || "null");
  } catch {
    return null;
  }
}

export function setStoredAuth(auth) {
  if (auth) localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
  else localStorage.removeItem(AUTH_STORAGE_KEY);
}

/** 로그인 화면이 "세션이 만료되었습니다"를 한 번만 보여주기 위한 플래그. */
export function consumeSessionExpired() {
  try {
    const flag = sessionStorage.getItem(EXPIRED_FLAG_KEY);
    if (flag) sessionStorage.removeItem(EXPIRED_FLAG_KEY);
    return Boolean(flag);
  } catch {
    return false;
  }
}

/** 상태 코드를 실은 에러. 예전에는 상태를 메시지 문자열 안에만 담아서
 *  호출부가 401을 구분할 방법이 없었고, 모든 화면이 "불러오지 못했습니다"만 반복했다. */
export class ApiError extends Error {
  constructor(status, message) {
    super(message ?? `API request failed: ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

/** 사람이 읽을 수 있는 실패 사유. 원래 MapPage에만 있던 처리를 전 화면이 공유한다.
 *  실패를 조용히 빈 배열로 삼키면 담당자가 "데이터가 없다"로 읽고 DB 적재를 의심하게 된다. */
export function describeApiError(err) {
  const status = err?.status;
  if (status === 401 || status === 403) return "로그인이 만료되었습니다. 다시 로그인해주세요.";
  if (status === 404) return "해당 자료를 찾을 수 없습니다.";
  if (status >= 500) return `서버에서 오류가 발생했습니다 (HTTP ${status}).`;
  if (status) return `데이터를 불러오지 못했습니다 (HTTP ${status}).`;
  return "서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해주세요.";
}

// 인증 토큰을 자동으로 Authorization 헤더에 실어 보내는 fetch 래퍼.
// 로그인 이후 접근하는 모든 페이지는 raw fetch 대신 이 함수를 사용해야 함.
export function apiFetch(path, options = {}) {
  const auth = getStoredAuth();
  const headers = { ...(options.headers || {}) };
  if (auth?.token) headers.Authorization = `Bearer ${auth.token}`;
  return fetch(`${API}${path}`, { ...options, headers });
}

export async function apiFetchJson(path, options = {}) {
  let response;
  try {
    response = await apiFetch(path, options);
  } catch {
    // 네트워크 자체가 안 됨(백엔드 꺼짐 등) — status 없는 ApiError로 통일한다.
    throw new ApiError(0, "서버에 연결하지 못했습니다.");
  }
  if (!response.ok) {
    // 토큰이 만료되면 localStorage에는 토큰이 남아 있어 RequireRole이 통과시킨다.
    // 그래서 화면은 "불러오지 못했습니다"만 반복하고, 담당자가 재로그인해야 한다는 것을
    // 알 방법이 없었다. 여기서 한 번에 정리한다.
    if (response.status === 401 || response.status === 403) {
      setStoredAuth(null);
      try {
        sessionStorage.setItem(EXPIRED_FLAG_KEY, "1");
      } catch {
        /* 프라이빗 모드 등 — 안내 문구만 못 볼 뿐 로그아웃은 정상 동작한다 */
      }
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    let message;
    if (response.status < 500) {
      try {
        const payload = await response.json();
        if (typeof payload?.detail === "string") message = payload.detail;
      } catch {
        /* JSON 응답이 아니면 기존 상태 문구를 사용한다 */
      }
    }
    throw new ApiError(response.status, message);
  }
  return response.json();
}

// JWT는 서명만 되어있을 뿐 암호화되지 않으므로, payload는 백엔드 호출 없이 클라이언트에서 바로 읽을 수 있음
// (예: 사이드바에 표시할 공무원 아이디). base64url이라 표준 atob 전에 패딩/문자 치환이 필요.
export function decodeJwtPayload(token) {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    return JSON.parse(atob(padded));
  } catch {
    return null;
  }
}
