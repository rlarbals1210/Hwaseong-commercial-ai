"""실제 관측 행으로 예측 시점별 폐업 대리지표를 복원한다.

미래 재등장이나 기존 label_h2/인허가 업력은 입력으로 읽지 않는다.
원본 식별자는 메모리에서만 사용하고 산출물은 셀 집계다.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

RENAME = {
    "상가업소번호": "store_id", "기준분기": "quarter",
    "행정동명": "area", "상권업종중분류명": "industry",
}
INPUT_COLUMNS = list(RENAME) + ["is_filled"]
FEATURES = ["store_count", "observed_tenure_quarters", "closure_rate_1q", "closure_rate_4q"]
KEY = ["area", "industry"]
HORIZON = 2
METHOD_VERSION = "observed-prefix-one-gap-v1"


def quarter_code(label: str) -> int:
    year, quarter = str(label).split("Q")
    code = int(year) * 10 + int(quarter)
    quarter_add(code, 0)
    return code


def quarter_add(code: int, count: int) -> int:
    year, quarter = divmod(int(code), 10)
    if not 1 <= quarter <= 4:
        raise ValueError("분기는 1~4여야 합니다")
    offset = year * 4 + quarter - 1 + count
    return (offset // 4) * 10 + offset % 4 + 1


def read_observed_rows(path: Path) -> tuple[pd.DataFrame, dict]:
    frame = pd.read_csv(path, usecols=INPUT_COLUMNS, dtype={"상가업소번호": str})
    if frame.is_filled.isna().any() or not frame.is_filled.isin([0, 1]).all():
        raise ValueError("실제 관측/보정 여부를 확인할 수 없는 행이 있습니다")
    observed = frame[frame.is_filled.eq(0)].drop(columns="is_filled").rename(columns=RENAME)
    observed["quarter"] = observed.quarter.map(quarter_code)
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    metadata = {
        "method_version": METHOD_VERSION, "source_file": path.name, "source_sha256": digest,
        "observed_rows": len(observed), "removed_filled_rows": int(frame.is_filled.eq(1).sum()),
        "observed_rows_by_quarter": observed.groupby("quarter").size().to_dict(),
        "calendar_release_dates_verified": False,
        "target_definition": "share of origin cohort absent from the citywide snapshot at B+2",
        "target_is_confirmed_business_closure": False,
        "tenure_definition": "quarters since first observed, left censored at the first snapshot",
    }
    return observed, metadata


def _group_ids(locations: dict[str, tuple]) -> dict[tuple, set]:
    result = defaultdict(set)
    for store_id, key in locations.items():
        result[key].add(store_id)
    return dict(result)


class SnapshotHistory:
    def __init__(self, observed: pd.DataFrame):
        required = ["store_id", "quarter", *KEY]
        if observed[required].isna().any().any():
            raise ValueError("관측 스냅샷 필수 값에 결측이 있습니다")
        if observed.duplicated(["store_id", "quarter"]).any():
            raise ValueError("점포·분기 키가 중복됩니다")
        self.quarters = sorted(int(q) for q in observed.quarter.unique())
        if len(self.quarters) < 1 or any(quarter_add(a, 1) != b for a, b in zip(self.quarters, self.quarters[1:])):
            raise ValueError("스냅샷 분기가 비어 있거나 연속되지 않습니다")
        self.locations, self.groups, self.ids = [], [], []
        self.first_seen = {}
        for i, q in enumerate(self.quarters):
            group = observed[observed.quarter.eq(q)]
            locations = {row.store_id: (row.area, row.industry) for row in group.itertuples()}
            self.locations.append(locations)
            self.groups.append(_group_ids(locations))
            self.ids.append(set(locations))
            for store_id in locations:
                self.first_seen.setdefault(store_id, i)

    def known_groups(self, index: int, asof: int) -> dict[tuple, set]:
        """현재까지 재등장이 확인된 1분기 공백만 이전 소속으로 채운다."""
        if not 0 <= index <= asof < len(self.quarters):
            raise ValueError("입력에서 미래 스냅샷을 요청했습니다")
        groups = self.groups[index]
        if index == 0 or index == asof:
            return groups
        # index+1 <= asof를 먼저 보장하므로 미래 행 추가로 이 보정은 바뀌지 않는다.
        returns = (self.ids[index - 1] & self.ids[index + 1]) - self.ids[index]
        if not returns:
            return groups
        augmented = dict(groups)
        by_key = _group_ids({store_id: self.locations[index - 1][store_id] for store_id in returns})
        for key, ids in by_key.items():
            augmented[key] = groups.get(key, set()) | ids
        return augmented

    def features_at(self, asof: int) -> pd.DataFrame:
        if not 0 <= asof < len(self.quarters):
            raise ValueError("존재하지 않는 예측 시점입니다")
        origin = self.quarters[asof]
        vintage = {i: self.known_groups(i, asof) for i in range(max(0, asof - 4), asof + 1)}
        rows = []
        for key, cohort in self.groups[asof].items():
            exits, denominators = [], []
            for i in range(max(1, asof - 3), asof + 1):
                previous = vintage[i - 1].get(key, set())
                current = vintage[i].get(key, set())
                exits.append(len(previous - current) if previous else np.nan)
                denominators.append(len(previous) if previous else np.nan)
            complete = len(exits) == 4 and np.isfinite(denominators).all()
            rate_1q = exits[-1] / denominators[-1] if exits and denominators[-1] > 0 else np.nan
            rate_4q = sum(exits) / sum(denominators) if complete else np.nan
            rows.append({
                "area": key[0], "industry": key[1], "quarter": origin,
                "feature_cutoff_quarter": origin, "store_count": len(cohort),
                "observed_tenure_quarters": float(np.mean([asof - self.first_seen[s] + 1 for s in cohort])),
                "closure_rate_1q": rate_1q, "closure_rate_4q": rate_4q,
                "history_quarters": len(exits) if complete else int(np.isfinite(denominators).sum()),
            })
        return pd.DataFrame(rows)

    def labels_at(self, asof: int) -> pd.DataFrame:
        if not 0 <= asof < len(self.quarters):
            raise ValueError("존재하지 않는 예측 시점입니다")
        origin = self.quarters[asof]
        target = quarter_add(origin, HORIZON)
        endpoint = self.ids[asof + HORIZON] if asof + HORIZON < len(self.ids) else None
        return pd.DataFrame([{
            "area": key[0], "industry": key[1], "quarter": origin,
            "target_quarter": target, "label_available_quarter": target,
            "target_absence_h2": len(cohort - endpoint) / len(cohort) if endpoint is not None else np.nan,
        } for key, cohort in self.groups[asof].items()])

    def endpoint_reappearance_audit(self, origins: tuple[int, ...]) -> dict:
        """사후 품질 점검. 이 결과로 입력·정답·학습 표본을 다시 고르지 않는다."""
        result = {}
        for quarter in origins:
            i = self.quarters.index(quarter)
            target = i + HORIZON
            if target >= len(self.ids):
                raise ValueError("품질 점검에 필요한 정답 시점이 없습니다")
            cohort = self.ids[i]
            absent = cohort - self.ids[target]
            followup = self.ids[target + 1:target + 3]
            complete = len(followup) == 2
            returned = absent & set().union(*followup) if complete else set()
            result[quarter] = {
                "origin_stores": len(cohort), "absent_at_B_plus_2": len(absent),
                "two_quarter_followup_complete": complete,
                "returned_after_endpoint": len(returned) if complete else None,
                "returned_share_pct": len(returned) / len(absent) * 100 if complete and absent else None,
            }
        return result

    def dataset(self) -> pd.DataFrame:
        return pd.concat([
            self.features_at(i).merge(self.labels_at(i), on=[*KEY, "quarter"], validate="one_to_one")
            for i in range(len(self.quarters))
        ], ignore_index=True)
