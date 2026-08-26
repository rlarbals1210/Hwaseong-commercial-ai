// CSV 내려받기 공용 모듈.
//
// 이 파일들은 화면을 떠나 회의자료·의회 답변으로 돌아다닌다. 그 시점에는 화면의 고지 문구가
// 함께 있지 않으므로 "위험"이 절대 기준처럼 읽힌다. 그래서 파일 맨 위에 기준을 붙인다.
//
// 값은 반드시 화면과 같은 포매터를 통과시킨다. 예전에는 화면이 7.1%인데 CSV가 7.14로 나가
// 같은 상권이 두 문서에서 다른 숫자를 갖고 있었다(2026-08-25 감사).

const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;

/** 숫자를 화면과 같은 자릿수로. 없는 값은 빈 칸으로 둔다(0으로 채우지 않는다). */
export const csvNum = (v, digits = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "";

/**
 * @param {object}   o
 * @param {string}   o.filename   확장자 제외
 * @param {string[]} o.headers
 * @param {Array[]}  o.rows       headers와 같은 길이의 배열들
 * @param {object}   o.meta       /api/alerts/grade-notice 응답 (없으면 고지 생략)
 * @param {string}   o.subtitle   이 파일이 무엇인지 한 줄
 */
export function downloadCsv({ filename, headers, rows, meta, subtitle }) {
  if (!rows?.length) return;

  const today = new Date().toISOString().slice(0, 10);
  // 맨 위 주석행 — 스프레드시트에서 한 열로 열리지만 사람이 읽으면 된다.
  const preamble = [];
  if (subtitle) preamble.push([`# ${subtitle}`]);
  preamble.push([`# 내려받은 날짜: ${today}`]);
  if (meta?.latest_quarter_label) {
    preamble.push([`# 기준 분기: ${meta.latest_quarter_label}`]);
  }
  if (meta?.notice) preamble.push([`# ${meta.notice}`]);
  if (meta?.provisional_notice) preamble.push([`# ${meta.provisional_notice}`]);
  if (meta?.eligible_cells) {
    preamble.push([`# 기준선 산출 모수: 표본충분 ${meta.eligible_cells.toLocaleString()}개 상권`]);
  }
  preamble.push([""]);

  const body = [headers, ...rows].map((line) => line.map(q).join(","));
  const csv = [...preamble.map((line) => line.map(q).join(",")), ...body].join("\n");

  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}_${today}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
