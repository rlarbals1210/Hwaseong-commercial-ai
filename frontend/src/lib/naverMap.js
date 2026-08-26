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
