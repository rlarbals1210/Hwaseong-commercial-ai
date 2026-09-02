import { useEffect, useState } from "react";
import { apiFetchJson, describeApiError } from "../lib/api";

export default function useDongs() {
  const [dongs, setDongs] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    apiFetchJson("/api/analysis/dongs")
      .then((data) => {
        if (active) setDongs(Array.isArray(data.dongs) ? data.dongs : Array.isArray(data) ? data : []);
      })
      .catch((err) => { if (active) setError(describeApiError(err)); });
    return () => { active = false; };
  }, []);
  return { dongs, error };
}
