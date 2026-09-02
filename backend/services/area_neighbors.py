"""공개 지도 경계에서 선을 공유하는 읍면동. 중심점 거리와 통행시간을 혼동하지 않는다."""
from functools import lru_cache
import json
from pathlib import Path
from shapely.geometry import shape

BOUNDARY_PATH = Path(__file__).resolve().parents[2] / "frontend/public/hwaseong_emd.geojson"


def build_neighbors(features):
    geometries = {f["properties"]["dong_name"]: shape(f["geometry"]) for f in features}
    if len(geometries) != len(features) or any(not g.is_valid for g in geometries.values()):
        raise ValueError("행정구역 경계의 이름 중복 또는 잘못된 도형")
    neighbors = {name: set() for name in geometries}
    for name, geometry in geometries.items():
        for other, candidate in geometries.items():
            # 점 하나만 접하는 지역은 제외한다. 각도 단위 길이를 거리로 표시하지 않는다.
            if name != other and geometry.boundary.intersection(candidate.boundary).length > 0:
                neighbors[name].add(other)
    return neighbors


@lru_cache(maxsize=1)
def _read_neighbors(path, mtime):
    return build_neighbors(json.loads(Path(path).read_text())["features"])


def area_neighbors():
    return _read_neighbors(str(BOUNDARY_PATH), BOUNDARY_PATH.stat().st_mtime_ns)
