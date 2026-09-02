// 네이버 지도 스크립트 로더. 공무원 지도(MapPage)와 공개 화면(BrowsePage)이 같이 쓴다.
//
// 원래 MapPage 안에만 있었다. 공개 화면이 지도를 쓰게 되면서 복사하는 대신 꺼냈다 —
// 사본이 둘이면 "도메인 등록을 확인해주세요" 같은 안내 문구가 한쪽에서만 고쳐진다.
//
// onerror가 없으면 스크립트가 실패했을 때 promise가 영원히 pending으로 남고, 화면에는
// 흰 사각형만 남는다. 시연 중 네트워크가 흔들리거나 도메인 등록이 안 됐을 때 정확히 그
// 모양이 된다 — 원인을 화면에 말하게 한다.

export const NAVER_CLIENT_ID = import.meta.env.VITE_NAVER_MAP_CLIENT_ID || "";

let naverMapLoadPromise = null;

export function loadNaverMap() {
  if (window.naver?.maps) return Promise.resolve();
  if (!naverMapLoadPromise) {
    naverMapLoadPromise = new Promise((resolve, reject) => {
      if (!NAVER_CLIENT_ID) {
        reject(new Error("지도 키(VITE_NAVER_MAP_CLIENT_ID)가 설정되지 않았습니다."));
        return;
      }
      const script = document.createElement("script");
      script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${NAVER_CLIENT_ID}`;
      script.onload = () => {
        if (window.naver?.maps) resolve();
        else reject(new Error("지도 스크립트를 불러왔지만 초기화되지 않았습니다. 도메인 등록을 확인해주세요."));
      };
      script.onerror = () => {
        naverMapLoadPromise = null;   // 다음 시도에서 다시 붙일 수 있게
        reject(new Error("지도 스크립트를 불러오지 못했습니다. 네트워크와 지도 키를 확인해주세요."));
      };
      document.head.appendChild(script);
    });
  }
  return naverMapLoadPromise;
}

// 화성시 경계 GeoJSON은 두 화면이 같은 파일을 쓴다. 폴리곤 좌표를 네이버 LatLng 경로로
// 바꾸는 규칙(다중 폴리곤 처리, 첫 링만 사용)도 같아야 해서 여기서 함께 낸다.
export function featurePaths(feature) {
  const coords = feature.geometry.type === "Polygon"
    ? [feature.geometry.coordinates]
    : feature.geometry.coordinates;
  return coords.map((rings) => rings[0].map(([lng, lat]) => new window.naver.maps.LatLng(lat, lng)));
}

export function featureName(feature) {
  return feature.properties.dong_name || feature.properties.EMD_KOR_NM || "";
}


// 경계에 딱 맞게 맞추기.
//
// naver.maps의 fitBounds는 정수 줌 단계로만 맞춘다. 화성시처럼 정확한 맞춤이 zoom 10.6쯤
// 필요한 경우 10으로 내려앉고, 그러면 실제로 필요한 것보다 약 1.5배 넓은 화면이 된다 —
// 화성시가 지도의 3분의 1만 차지하고 나머지는 인천·평택·안성이 채운다.
//
// 예전에는 fitBounds 뒤에 setZoom으로 한 단계씩 올려보며 getBounds()로 확인했다. 결과는
// 맞았지만 지도를 세 번 다시 그리게 만든다. 읍면동 경계는 좌표가 6만 개라 한 번 다시
// 그리는 데만 200ms 넘게 들고, 그래서 지역을 한 번 클릭할 때마다 화면이 885ms 멈췄다.
//
// 지금은 목표 줌을 계산으로 먼저 구하고 setOptions로 중심과 줌을 한 번에 바꾼다 —
// 지도를 다시 그리는 횟수가 세 번에서 한 번으로 준다. 화성시 29개 읍면동 전부에서
// 이 계산이 옛 탐색 루프와 같은 줌을 내는 것을 브라우저에서 대조해 확인했다.
export function fitBoundsTight(map, bounds, padding = 16) {
  try {
    const projection = map.getProjection();
    const size = map.getSize();
    const sw = projection.fromCoordToOffset(bounds.getSW());
    const ne = projection.fromCoordToOffset(bounds.getNE());
    const spanX = Math.abs(ne.x - sw.x);
    const spanY = Math.abs(ne.y - sw.y);
    if (!(spanX > 0 && spanY > 0 && size.width > 0 && size.height > 0)) throw new Error("경계나 지도 크기를 잴 수 없음");

    // 화면 대비 경계 크기의 비율이 곧 줌 배율이다. 줌 한 단계는 배율 2배이므로 log2를 쓴다.
    const scale = Math.min(size.width / spanX, size.height / spanY);
    const target = Math.floor(map.getZoom() + Math.log2(scale));
    if (!Number.isFinite(target)) throw new Error("줌 계산 실패");

    const zoom = Math.min(map.getMaxZoom(), Math.max(map.getMinZoom(), target));
    map.setOptions({ center: bounds.getCenter(), zoom });
  } catch {
    // 투영 API가 없는 버전이거나 계산이 어긋나면 정수 줌으로라도 맞춘다.
    map.fitBounds(bounds, { top: padding, right: padding, bottom: padding, left: padding });
  }
}
