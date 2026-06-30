// Vite proxy(/api → :8000)를 사용하므로 개발/프로덕션 모두 빈 문자열이 기본값.
// 외부 배포 시 VITE_API_BASE=https://yourdomain.com 으로 오버라이드 가능.
export const API = import.meta.env.VITE_API_BASE ?? "";
