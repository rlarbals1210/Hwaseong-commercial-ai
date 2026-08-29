import { useEffect, useState } from "react";
import { apiFetchJson } from "../lib/api";

// 등급 기준선·표본 기준을 서버에서 받는다(GET /api/alerts/grade-notice).
//
// 왜 훅으로 뺐나. 표본 기준(점포 수)이 화면 문구에 "50개"로 네 군데 박혀 있었고,
// 2026-08-29에 기준을 30으로 내리면서 전부 거짓말이 됐다. 파이프라인 상수 하나를
// 바꾸면 화면이 따라오게 만드는 것이 요지다. 숫자를 문구에 직접 쓰지 말 것.
//
// 원천은 ai/build_risk_index.py의 SAMPLE_MIN 하나이고, risk_thresholds.json을 거쳐
// 백엔드가 내려준다. 아래 폴백은 서버를 못 부를 때만 쓰이며, 원천이 바뀌면 같이 고쳐야
// 하는 유일한 프론트 지점이다.
const SAMPLE_MIN_FALLBACK = 30;

export default function useGradeNotice() {
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    let alive = true;
    apiFetchJson("/api/alerts/grade-notice")
      .then((d) => { if (alive) setMeta(d); })
      .catch(() => { if (alive) setMeta(null); });
    return () => { alive = false; };
  }, []);

  return { meta, sampleMin: meta?.sample_min ?? SAMPLE_MIN_FALLBACK };
}
