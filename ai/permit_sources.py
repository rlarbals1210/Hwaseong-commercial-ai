"""SSD 원본 식별 정보 복원. 원본 행은 로그에 출력하지 않는다."""
from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd

from ai.pit_closure_dataset import quarter_code
from eda import paths

OUTPUT = paths.PROCESSED_DATA_DIR / "permit_label_audit"
SBIZ_COLUMNS = {
    "상가업소번호": "store_id", "상호명": "name", "지점명": "branch",
    "시군구코드": "city", "행정동명": "area", "상권업종중분류명": "industry",
    "상권업종소분류명": "small_industry", "도로명주소": "road", "지번주소": "lot",
    "층정보": "floor", "호정보": "unit",
}
PERMIT_COLUMNS = {
    "관리번호": "permit_id", "사업장명": "name", "도로명주소": "road", "지번주소": "lot",
    "인허가일자": "open_date", "폐업일자": "close_date", "영업상태명": "status",
    "상세영업상태명": "detail_status", "휴업시작일자": "pause_start",
    "휴업종료일자": "pause_end", "재개업일자": "reopen_date",
    "데이터갱신시점": "updated_at", "최종수정시점": "modified_at",
}


def csv_read(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, dtype=str, encoding=encoding).fillna("")
        except UnicodeDecodeError:
            continue
    raise ValueError("인허가 원본 인코딩을 확인할 수 없습니다")


def parse_dates(values: pd.Series) -> pd.Series:
    digits = values.fillna("").str.replace(r"\D", "", regex=True).str[:8]
    return pd.to_datetime(digits, format="%Y%m%d", errors="coerce")


def load_permits() -> tuple[pd.DataFrame, list[dict]]:
    frames, inventory = [], []
    for path in sorted(paths.PERMIT_DIR.glob("*.csv")):
        if path.name.startswith("._"):
            continue
        source = unicodedata.normalize("NFC", path.name)
        raw = csv_read(path)
        if not set(["관리번호", "사업장명", "폐업일자"]).issubset(raw.columns):
            inventory.append({"source": source, "rows": len(raw), "usable": False})
            continue
        frame = raw.reindex(columns=list(PERMIT_COLUMNS), fill_value="").rename(columns=PERMIT_COLUMNS)
        frame["source"] = source
        frame["permit_key"] = source + ":" + frame.permit_id
        if frame.permit_id.eq("").any() or frame.permit_key.duplicated().any():
            raise ValueError("인허가 식별자가 누락되거나 중복됩니다")
        date_cols = ["open_date", "close_date", "pause_start", "pause_end", "reopen_date", "updated_at", "modified_at"]
        invalid = pd.Series(False, index=frame.index)
        for column in date_cols:
            parsed = parse_dates(frame[column])
            invalid |= frame[column].ne("") & parsed.isna()
            frame[column] = parsed
        frame["invalid_date"] = invalid
        frame["followup_date"] = frame[["updated_at", "modified_at"]].max(axis=1)
        inventory.append({"source": source, "rows": len(frame), "usable": True,
                          "invalid_date_rows": int(invalid.sum()),
                          "closure_date_rows": int(frame.close_date.notna().sum()),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        frames.append(frame)
    return pd.concat(frames, ignore_index=True), inventory


def _gg_name(archive: zipfile.ZipFile) -> str | None:
    return next((n for n in archive.namelist() if "경기" in unicodedata.normalize("NFC", n)
                 and n.endswith(".csv") and not n.startswith("__MACOSX")), None)


def _read_snapshot(archive: zipfile.ZipFile) -> pd.DataFrame:
    name = _gg_name(archive)
    if name is None:
        nested = next(n for n in archive.namelist() if n.endswith(".zip") and not n.startswith("__MACOSX"))
        with zipfile.ZipFile(io.BytesIO(archive.read(nested)), metadata_encoding="cp949") as inner:
            return _read_snapshot(inner)
    parts = []
    with archive.open(name) as handle:
        for frame in pd.read_csv(handle, encoding="utf-8-sig", dtype=str, chunksize=100_000,
                                 usecols=lambda c: c in SBIZ_COLUMNS):
            parts.append(frame[frame["시군구코드"].eq("41590")])
    return pd.concat(parts, ignore_index=True).rename(columns=SBIZ_COLUMNS).fillna("")


def load_snapshots() -> tuple[pd.DataFrame, dict]:
    archives = sorted(p for p in paths.SBIZ_DIR.glob("*.zip") if not p.name.startswith("._"))
    if not archives:
        raise ValueError("소진공 원본 ZIP이 없습니다")
    manifest = []
    for path in archives:
        with zipfile.ZipFile(path, metadata_encoding="cp949") as archive:
            manifest.append({"source": unicodedata.normalize("NFC", path.name),
                             "size": path.stat().st_size,
                             "members": [(i.filename, i.CRC, i.file_size) for i in archive.infolist()]})
    digest = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cache, meta = OUTPUT / "source_snapshots.pkl", OUTPUT / "source_manifest.json"
    if cache.exists() and meta.exists() and json.loads(meta.read_text())["fingerprint"] == digest:
        frame = pd.read_pickle(cache)
        return frame, {"fingerprint": digest, "rows": len(frame), "archives": len(archives), "cache_reused": True}
    parts = []
    for path in archives:
        date = re.search(r"(\d{8})", path.stem).group(1)
        quarter = 20253 if date == "20251031" else quarter_code(f"{date[:4]}Q{(int(date[4:6])-1)//3+1}")
        with zipfile.ZipFile(path, metadata_encoding="cp949") as archive:
            frame = _read_snapshot(archive)
        frame["quarter"] = quarter
        parts.append(frame)
        print(json.dumps({"loaded_quarter": quarter, "rows": len(frame)}), flush=True)
    frame = pd.concat(parts, ignore_index=True)
    if frame.duplicated(["store_id", "quarter"]).any():
        raise ValueError("원본 점포·분기 키가 중복됩니다")
    frame.to_pickle(cache)
    meta.write_text(json.dumps({"fingerprint": digest, "sources": manifest}, ensure_ascii=False, indent=2))
    return frame, {"fingerprint": digest, "rows": len(frame), "archives": len(archives), "cache_reused": False}


if __name__ == "__main__":
    _, audit = load_snapshots()
    print(json.dumps(audit, ensure_ascii=False))
