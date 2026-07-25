"""
sbiz_hwaseong_all.csv엔 상호명이 없어서(build_sbiz_labels.py의 USECOLS에서 빠짐),
2023Q1 이탈 코호트 성격 규명(인허가 교차검증)에 필요한 상호명을 원본에서 다시 추출한다.
(상가업소번호, 기준분기) -> 상호명 매핑만 별도 저장 — sbiz_hwaseong_all.csv는 건드리지 않음.

사용법:
    python ai/extract_sbiz_names.py
"""
import glob
import io
import os
import re
import zipfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", str(PROJECT_ROOT)))
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

USECOLS = ["상가업소번호", "시군구명", "기준분기_placeholder"]  # 기준분기는 파일명에서 옴
REAL_USECOLS = ["상가업소번호", "시군구명", "상호명"]

QUARTER_OVERRIDE = {"20251031": "2025Q3"}
OUT_PATH = PROCESSED_DATA_DIR / "sbiz_names.csv"


def find_dataset_dir() -> Path:
    matches = glob.glob(str(RAW_DATA_DIR / "**" / "소상공인시장진흥공단_상가*"), recursive=True)
    dirs = [Path(m) for m in matches if Path(m).is_dir()]
    return dirs[0]


def date_to_quarter(date_str: str) -> str:
    if date_str in QUARTER_OVERRIDE:
        return QUARTER_OVERRIDE[date_str]
    year, month = int(date_str[:4]), int(date_str[4:6])
    q = (month - 1) // 3 + 1
    return f"{year}Q{q}"


def find_quarter_files(dataset_dir: Path):
    out = []
    for f in sorted(dataset_dir.iterdir()):
        if "업종코드" in f.name:
            continue
        m = re.search(r"_(\d{8})\.(zip|csv)$", f.name)
        if not m:
            continue
        out.append((date_to_quarter(m.group(1)), f))
    return out


def _read_gg_csv(fileobj_or_path):
    return pd.read_csv(fileobj_or_path, encoding="utf-8-sig", usecols=REAL_USECOLS, dtype=str, low_memory=False)


def _find_gg_entry(namelist):
    return next(n for n in namelist if "경기" in n and n.endswith(".csv"))


def load_quarter(path: Path) -> pd.DataFrame:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path, metadata_encoding="cp949") as outer:
            nested = [n for n in outer.namelist() if n.endswith(".zip")]
            if nested:
                with zipfile.ZipFile(io.BytesIO(outer.read(nested[0])), metadata_encoding="cp949") as inner:
                    name = _find_gg_entry(inner.namelist())
                    with inner.open(name) as f:
                        return _read_gg_csv(f)
            else:
                name = _find_gg_entry(outer.namelist())
                with outer.open(name) as f:
                    return _read_gg_csv(f)
    return _read_gg_csv(path)


def main():
    dataset_dir = find_dataset_dir()
    print(f"원본 위치: {dataset_dir}")
    quarter_files = find_quarter_files(dataset_dir)

    frames = []
    for quarter, path in quarter_files:
        df = load_quarter(path)
        df = df[df["시군구명"] == "화성시"][["상가업소번호", "상호명"]].copy()
        df["기준분기"] = quarter
        print(f"  {quarter}: {len(df):,}건")
        frames.append(df)

    all_names = pd.concat(frames, ignore_index=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_names.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {OUT_PATH} ({len(all_names):,}행)")


if __name__ == "__main__":
    main()
