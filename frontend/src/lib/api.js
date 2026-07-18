// Vite proxy(/api → :8000)를 사용하므로 개발/프로덕션 모두 빈 문자열이 기본값.
// 외부 배포 시 VITE_API_BASE=https://yourdomain.com 으로 오버라이드 가능.
export const API = import.meta.env.VITE_API_BASE ?? "";

const AUTH_STORAGE_KEY = "hcai_auth";

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

// 인증 토큰을 자동으로 Authorization 헤더에 실어 보내는 fetch 래퍼.
// 공무원/시민 로그인 이후 접근하는 모든 페이지는 raw fetch 대신 이 함수를 사용해야 함.
export function apiFetch(path, options = {}) {
  const auth = getStoredAuth();
  const headers = { ...(options.headers || {}) };
  if (auth?.token) headers.Authorization = `Bearer ${auth.token}`;
  return fetch(`${API}${path}`, { ...options, headers });
}
