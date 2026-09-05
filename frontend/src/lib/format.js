export const formatBytes = (bytes) => {
  const value = Number(bytes);
  if (!Number.isFinite(value)) return "—";
  if (value < 1024) return `${value.toLocaleString()} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
};

export const formatDateTime = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

// 202506 -> '2025년 6월'. 카드매출 원본이 월 단위라 분기 라벨과 섞이면 안 된다.
export const formatMonth = (value) => {
  const text = String(value ?? "");
  if (!/^\d{6}$/.test(text)) return "—";
  return `${text.slice(0, 4)}년 ${Number(text.slice(4))}월`;
};
