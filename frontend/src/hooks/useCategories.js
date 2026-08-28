import { useEffect, useState } from "react";
import { apiFetchJson } from "../lib/api";

// 업종 목록 fetch. 조기경보·현장점검·상권 위험 지도가 각자 같은 코드를 들고 있었다.
//
// purpose는 서버가 목록을 좁히는 기준이다(backend/routers/analysis.py).
//   alert   최신 분기 표본충분 + AI 순위가 산출된 업종
//   policy  최신 분기 표본충분 업종
// 화면이 실제로 조회하는 집합과 다른 purpose를 쓰면 드롭다운에는 뜨는데 결과가 0건인
// 업종이 생긴다. 호출부에서 빈 결과를 안내할 것.
//
// 목록을 못 받아도 화면은 떠야 한다 — 필터가 없을 뿐 표·지도는 전체 기준으로 유효하다.
// 그래서 throw하지 않고 error 플래그로 내린다.
export default function useCategories(purpose) {
  const [categories, setCategories] = useState([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    const query = purpose ? `?purpose=${encodeURIComponent(purpose)}` : "";
    apiFetchJson(`/api/analysis/categories${query}`)
      .then((d) => {
        if (!alive) return;
        setCategories(Array.isArray(d.categories) ? d.categories : []);
        setError(false);
      })
      .catch(() => {
        if (!alive) return;
        setCategories([]);
        setError(true);
      });
    return () => {
      alive = false;
    };
  }, [purpose]);

  return { categories, error };
}
