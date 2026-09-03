"""동일 사업장 후보 연결과 날짜 기반 정답. 미확인은 NaN으로 유지한다."""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

from ai.pit_closure_dataset import quarter_add

FOOD = {"한식", "중식", "일식", "서양식", "동남아시아", "주점", "기타 간이", "비알코올", "구내식당·뷔페"}


def text_normalize(value: str) -> str:
    return unicodedata.normalize("NFC", str(value or "")).strip().lower()


def name_key(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", text_normalize(value))


def address_parts(value: str, kind: str) -> tuple[str, str, str]:
    text = re.sub(r"\s+", " ", text_normalize(value))
    text = re.sub(r"(화성시) (?:효행구|만세구|동탄구|병점구) ", r"\1 ", text)
    # 건물 뒤의 층/호를 버리기 전에 따로 보존한다.
    floors = re.findall(r"(지하\s*\d+|\d+)\s*층", text)
    units = re.findall(r"(\d+(?:-\d+)?)\s*호(?![가-힣])", text)
    floors = sorted({f.replace(" ", "").replace("지하", "b") for f in floors})
    units = sorted(set(units))
    if kind == "road":
        pattern = r"^(.+?(?:대로|로|길)\s*\d+(?:-\d+)?)(?=\s|,|\(|$)"
    else:
        pattern = r"^(.+?(?:동|읍|면|리)\s+(?:산\s*)?\d+(?:-\d+)?)(?=\s|,|\(|$)"
    base = re.match(pattern, text)
    key = re.sub(r"[\s,]", "", base.group(1)) if base else ""
    return key, "/".join(floors), "/".join(units)


def _detail(value: str) -> str:
    value = text_normalize(value).replace("지하", "b").replace("층", "").replace("호", "")
    value = re.sub(r"\.0$", "", value).replace(" ", "")
    if value.startswith("-"):
        value = "b" + value[1:]
    return value


def add_identity(frame: pd.DataFrame, *, sbiz: bool) -> pd.DataFrame:
    work = frame.copy()
    names = work.name.fillna("").map(name_key)
    if sbiz:
        branches = work.branch.fillna("").map(name_key)
        names = pd.Series([n if not b or n.endswith(b) else n + b for n, b in zip(names, branches)], index=work.index)
    work["name_key"] = names
    for kind in ["road", "lot"]:
        values = work[kind].fillna("")
        lookup = {v: address_parts(v, kind) for v in values.unique()}
        for i, column in enumerate([f"{kind}_key", f"{kind}_floor", f"{kind}_unit"]):
            work[column] = values.map(lambda v: lookup[v][i])
    if sbiz:
        for field in ["floor", "unit"]:
            work[f"identity_{field}"] = work[field].fillna("").map(_detail)
            fallback = work[f"road_{field}"].where(work[f"road_{field}"].ne(""), work[f"lot_{field}"])
            work[f"identity_{field}"] = work[f"identity_{field}"].where(work[f"identity_{field}"].ne(""), fallback)
    else:
        for field in ["floor", "unit"]:
            work[f"identity_{field}"] = work[f"road_{field}"].where(work[f"road_{field}"].ne(""), work[f"lot_{field}"])
    return work


def industry_compatible(industry: str, small: str, source: str) -> bool:
    industry, small = industry.strip(), small.strip()
    kind = source.split("_")[1]
    if kind in {"일반음식점", "휴게음식점"}:
        return industry in FOOD
    if kind == "제과점영업":
        return small == "빵/도넛"
    if kind == "미용업":
        return industry == "이용·미용"
    if kind == "이용업":
        return small == "미용실"
    if kind == "세탁업":
        return industry == "세탁"
    return small == {"약국": "약국", "노래연습장업": "노래방",
                     "인터넷컴퓨터게임시설제공업": "PC방", "체력단련장업": "헬스장"}.get(kind, "__unsupported__")


def quarter_end(code: int) -> pd.Timestamp:
    year, q = divmod(int(code), 10)
    if not 1 <= q <= 4:
        raise ValueError("잘못된 분기")
    return pd.Period(f"{year}Q{q}", freq="Q").end_time.normalize()


def link_candidates(snapshots: pd.DataFrame, permits: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    sbiz, registry = add_identity(snapshots, sbiz=True), add_identity(permits, sbiz=False)
    sbiz["row_id"] = np.arange(len(sbiz))
    for kind in ["road", "lot"]:
        registry[f"permit_{kind}_key"] = registry[f"{kind}_key"]
    joins = []
    for kind in ["road", "lot"]:
        keys = ["name_key", f"{kind}_key"]
        left = sbiz[sbiz[keys].ne("").all(axis=1)]
        right = registry[registry[keys].ne("").all(axis=1)]
        cols = [*keys, "permit_key", "source", "open_date", "close_date", "identity_floor", "identity_unit",
                "permit_road_key", "permit_lot_key"]
        joined = left.merge(right[cols], on=keys, suffixes=("", "_permit"))
        joined["address_basis"] = kind
        joins.append(joined)
    joined = pd.concat(joins, ignore_index=True).drop_duplicates(["row_id", "permit_key"])
    audit = {"origin_rows": len(sbiz), "name_address_candidate_rows": int(joined.row_id.nunique()),
             "candidate_pairs": len(joined)}
    compatible = np.array([industry_compatible(i, s, p) for i, s, p in
                           zip(joined.industry, joined.small_industry, joined.source)], dtype=bool)
    joined = joined[compatible].copy()
    audit["industry_compatible_rows"] = int(joined.row_id.nunique())
    conflicts = pd.Series(False, index=joined.index)
    for kind in ["road", "lot"]:
        a, b = joined[f"{kind}_key"], joined[f"permit_{kind}_key"]
        conflicts |= a.ne("") & b.ne("") & a.ne(b)
    audit["address_conflict_pairs"] = int(conflicts.sum())
    joined = joined[~conflicts].copy()
    conflicts = pd.Series(False, index=joined.index)
    for field in ["floor", "unit"]:
        a, b = joined[f"identity_{field}"], joined[f"identity_{field}_permit"]
        conflicts |= a.ne("") & b.ne("") & a.ne(b)
    audit["detail_conflict_pairs"] = int(conflicts.sum())
    joined = joined[~conflicts].copy()
    origin = pd.to_datetime(joined.quarter.map(quarter_end))
    active = joined.open_date.notna() & joined.open_date.le(origin) & (joined.close_date.isna() | joined.close_date.gt(origin))
    audit["outside_origin_operation_pairs"] = int((~active).sum())
    joined = joined[active].copy()
    ambiguity = joined.groupby("row_id").permit_key.transform("nunique").gt(1)
    audit["multiple_permit_rows"] = int(joined.loc[ambiguity, "row_id"].nunique())
    # 한 후보를 임의로 고른 다음 중복을 지우지 않는다. 양방향으로 모두 유일해야 한다.
    shared = joined.groupby(["quarter", "permit_key"]).row_id.transform("nunique").gt(1)
    audit["shared_permit_rows"] = int(joined.loc[shared, "row_id"].nunique())
    joined = joined[~ambiguity & ~shared].copy()
    audit["unique_links"] = len(joined)
    audit["links_with_both_sides_unit"] = int((joined.identity_unit.ne("") & joined.identity_unit_permit.ne("")).sum())
    keep = ["row_id", "store_id", "quarter", "area", "industry", "permit_key", "address_basis"]
    return joined[keep].merge(permits.drop(columns=["name", "road", "lot"]), on="permit_key", validate="many_to_one"), audit


def label_links(links: pd.DataFrame, endpoint_ids: dict[int, set]) -> pd.DataFrame:
    result = links.copy()
    result["target_quarter"] = result.quarter.map(lambda q: quarter_add(q, 2))
    endpoint = pd.to_datetime(result.target_quarter.map(quarter_end))
    origin = pd.to_datetime(result.quarter.map(quarter_end))
    closed = result.status.eq("폐업") & result.detail_status.eq("폐업")
    normal = result.status.eq("영업/정상") & result.detail_status.eq("영업")
    # 상세 상태가 '정상'인 업종도 있으므로 상위 영업/정상과 조합해 제한적으로 허용한다.
    normal |= result.status.eq("영업/정상") & result.detail_status.isin(["정상", "영업/정상"])
    interrupted = result[["pause_start", "pause_end", "reopen_date"]].notna().any(axis=1)
    coherent = ~result.invalid_date & ~interrupted & result.open_date.le(origin)
    coherent &= (closed & result.close_date.gt(origin)) | (normal & result.close_date.isna())
    followed = result.followup_date.ge(endpoint)
    result["target_registry_h2"] = np.where(coherent & followed,
                                           (closed & result.close_date.le(endpoint)).astype(float), np.nan)
    result["target_absence_h2"] = [float(s not in endpoint_ids[q]) if q in endpoint_ids else np.nan
                                   for s, q in zip(result.store_id, result.target_quarter)]
    result["label_status"] = np.select([~coherent, ~followed, result.target_absence_h2.isna()],
                                       ["status_or_dates_uncertain", "followup_incomplete", "snapshot_endpoint_missing"], default="paired")
    return result


def aggregate_labels(labelled: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    paired = labelled[labelled.label_status.eq("paired")]
    keys = ["area", "industry", "quarter"]
    means = paired.groupby(keys).agg(matched_count=("store_id", "size"),
                                     target_registry_h2=("target_registry_h2", "mean"),
                                     target_absence_h2=("target_absence_h2", "mean")).reset_index()
    frame = features.merge(means, on=keys, how="left", validate="one_to_one")
    frame["matched_count"] = frame.matched_count.fillna(0).astype(int)
    frame["coverage"] = frame.matched_count / frame.store_count
    frame["target_quarter"] = frame.quarter.map(lambda q: quarter_add(q, 2))
    return frame
