import { useCallback, useEffect, useState } from "react";
import { apiFetchJson, describeApiError } from "../lib/api";

// 조건이 바뀐 순간 이전 결과를 숨기고, 늦게 온 응답은 적용하지 않는다.
export default function usePublicQuery(url) {
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState(null);
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    apiFetchJson(url, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ url, revision, data, error: "" });
      })
      .catch((err) => {
        if (!controller.signal.aborted) setResult({ url, revision, data: null, error: describeApiError(err) });
      });
    return () => controller.abort();
  }, [url, revision]);
  const current = result?.url === url && result?.revision === revision;
  const retry = useCallback(() => setRevision((value) => value + 1), []);
  return { data: url && current ? result.data : null, loading: Boolean(url && !current),
    error: url && current ? result.error : "", retry };
}
