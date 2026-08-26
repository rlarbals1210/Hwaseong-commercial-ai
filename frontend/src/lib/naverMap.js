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
// 그래서 fitBounds 뒤에 한 단계 더 당겨보고, 그래도 경계가 다 들어오면 그 줌을 쓴다.
// 안 들어오면 원래 줌으로 돌린다.
export function fitBoundsTight(map, bounds, padding = 16) {
  map.fitBounds(bounds, { top: padding, right: padding, bottom: padding, left: padding });
  try {
    let zoom = map.getZoom();
    // setZoom의 두 번째 인자는 애니메이션 여부다. true로 주면 직후의 getBounds()가
    // 아직 옛 화면을 돌려줘서 판정이 항상 실패한다 — 그래서 false로 즉시 반영시킨다.
    // 한 단계씩 올려보며 경계가 다 들어오는 마지막 줌을 찾는다(보통 1~2단계).
    for (let step = 0; step < 3; step += 1) {
      const next = zoom + 1;
      if (next > map.getMaxZoom()) break;
      map.setZoom(next, false);
      if (map.getBounds().hasBounds(bounds)) {
        zoom = next;
      } else {
        map.setZoom(zoom, false);
        break;
      }
    }
  } catch {
    /* getBounds/hasBounds가 없는 버전이면 fitBounds 결과를 그대로 쓴다 */
  }
}
