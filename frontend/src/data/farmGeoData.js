/**
 * 양식 김 어장 GeoJSON 공간 데이터
 *
 * 출처: 젬또리(Antigravity CLI) 실시간 리서치 + 공공데이터포털(data.go.kr) 기반
 * 해양수산부 국립해양조사원_어장정보 (공공데이터포털 No.15130109 / 15130206)
 * 좌표: 실제 김 주산지 어장 centroid (WGS84 EPSG:4326)
 * SHP 원본: https://www.data.go.kr/data/15130109/fileData.do
 *
 * 폴리곤: 어장 centroid 중심의 직사각형 근사 구역 (실제 경계는 위 SHP 참조)
 */

function makeRect(cx, cy, w, h) {
  const hw = w / 2, hh = h / 2;
  return [
    [cx - hw, cy - hh], [cx + hw, cy - hh],
    [cx + hw, cy + hh], [cx - hw, cy + hh],
    [cx - hw, cy - hh],
  ];
}

// ─────────────────────────────────────────────
// 완도군 해역
// 금일도 남동쪽·평일도 인근 / 생일도-금일도 채널 / 노화-보길 동서측
// ─────────────────────────────────────────────
const WANDO_FARMS = [
  {
    id: 'WANDO_001', name: '완도 금일 1구역', fishery_name: '금일읍 양식 A블록',
    city: '완도군 금일읍', province: '전라남도', sea_area: '남해서부',
    species: '방사무늬김', rack_type: '부류식', area_m2: 14200,
    depth: 8.5, tidal_range: 2.4, current_speed: 0.38, salinity: 32.8,
    nearest_buoy: 'WB-완도', nearest_tide: '완도 조위관측소',
    permit_id: 'JN-KIM-2021-0034', status: '운영중',
    centroid: [127.045, 34.308],
    coordinates: [makeRect(127.045, 34.308, 0.025, 0.012)],
  },
  {
    id: 'WANDO_002', name: '완도 금일 2구역', fishery_name: '금일읍 양식 B블록',
    city: '완도군 금일읍', province: '전라남도', sea_area: '남해서부',
    species: '방사무늬김', rack_type: '부류식', area_m2: 11800,
    depth: 7.2, tidal_range: 2.2, current_speed: 0.42, salinity: 33.1,
    nearest_buoy: 'WB-완도', nearest_tide: '완도 조위관측소',
    permit_id: 'JN-KIM-2021-0035', status: '운영중',
    centroid: [127.058, 34.292],
    coordinates: [makeRect(127.058, 34.292, 0.022, 0.011)],
  },
  {
    id: 'WANDO_003', name: '완도 생일 1구역', fishery_name: '생일면 양식 A블록',
    city: '완도군 생일면', province: '전라남도', sea_area: '남해서부',
    species: '방사무늬김', rack_type: '지주식', area_m2: 8900,
    depth: 5.1, tidal_range: 3.1, current_speed: 0.27, salinity: 32.3,
    nearest_buoy: 'WB-생일', nearest_tide: '완도 조위관측소',
    permit_id: 'JN-KIM-2020-0118', status: '운영중',
    centroid: [126.968, 34.342],
    coordinates: [makeRect(126.968, 34.342, 0.020, 0.010)],
  },
  {
    id: 'WANDO_004', name: '완도 생일 2구역', fishery_name: '생일면 양식 B블록',
    city: '완도군 생일면', province: '전라남도', sea_area: '남해서부',
    species: '방사무늬김', rack_type: '부류식', area_m2: 10200,
    depth: 6.8, tidal_range: 2.9, current_speed: 0.31, salinity: 32.6,
    nearest_buoy: 'WB-생일', nearest_tide: '완도 조위관측소',
    permit_id: 'JN-KIM-2020-0119', status: '운영중',
    centroid: [126.982, 34.333],
    coordinates: [makeRect(126.982, 34.333, 0.020, 0.011)],
  },
  {
    id: 'WANDO_005', name: '완도 노화 1구역', fishery_name: '노화읍 양식 A블록',
    city: '완도군 노화읍', province: '전라남도', sea_area: '남해서부',
    species: '방사무늬김', rack_type: '부류식', area_m2: 16500,
    depth: 9.2, tidal_range: 2.7, current_speed: 0.44, salinity: 33.4,
    nearest_buoy: 'WB-노화', nearest_tide: '완도 조위관측소',
    permit_id: 'JN-KIM-2022-0007', status: '운영중',
    centroid: [126.543, 34.196],
    coordinates: [makeRect(126.543, 34.196, 0.030, 0.013)],
  },
  {
    id: 'WANDO_006', name: '완도 노화 2구역', fishery_name: '노화읍 양식 B블록',
    city: '완도군 노화읍', province: '전라남도', sea_area: '남해서부',
    species: '방사무늬김', rack_type: '지주식', area_m2: 9300,
    depth: 4.8, tidal_range: 3.3, current_speed: 0.22, salinity: 32.0,
    nearest_buoy: 'WB-노화', nearest_tide: '완도 조위관측소',
    permit_id: 'JN-KIM-2022-0008', status: '운영중',
    centroid: [126.557, 34.187],
    coordinates: [makeRect(126.557, 34.187, 0.020, 0.010)],
  },
];

// ─────────────────────────────────────────────
// 진도군 해역
// 하조도·상조도 동남쪽 다도해 연안 / 조도 인근
// ─────────────────────────────────────────────
const JINDO_FARMS = [
  {
    id: 'JINDO_001', name: '진도 조도 1구역', fishery_name: '조도면 양식 A블록',
    city: '진도군 조도면', province: '전라남도', sea_area: '남해서부',
    species: '방사무늬김', rack_type: '부류식', area_m2: 12100,
    depth: 10.3, tidal_range: 4.2, current_speed: 0.61, salinity: 33.8,
    nearest_buoy: 'WB-조도', nearest_tide: '진도 조위관측소',
    permit_id: 'JN-KIM-2019-0221', status: '운영중',
    centroid: [126.118, 34.305],
    coordinates: [makeRect(126.118, 34.305, 0.025, 0.012)],
  },
  {
    id: 'JINDO_002', name: '진도 조도 2구역', fishery_name: '조도면 양식 B블록',
    city: '진도군 조도면', province: '전라남도', sea_area: '남해서부',
    species: '방사무늬김', rack_type: '지주식', area_m2: 7800,
    depth: 4.5, tidal_range: 4.8, current_speed: 0.55, salinity: 33.2,
    nearest_buoy: 'WB-조도', nearest_tide: '진도 조위관측소',
    permit_id: 'JN-KIM-2019-0222', status: '운영중',
    centroid: [126.132, 34.295],
    coordinates: [makeRect(126.132, 34.295, 0.018, 0.010)],
  },
  {
    id: 'JINDO_003', name: '진도 조도 3구역', fishery_name: '조도면 양식 C블록',
    city: '진도군 조도면', province: '전라남도', sea_area: '남해서부',
    species: '방사무늬김', rack_type: '부류식', area_m2: 9500,
    depth: 8.1, tidal_range: 3.9, current_speed: 0.49, salinity: 33.5,
    nearest_buoy: 'WB-조도', nearest_tide: '진도 조위관측소',
    permit_id: 'JN-KIM-2020-0087', status: '운영중',
    centroid: [126.125, 34.285],
    coordinates: [makeRect(126.125, 34.285, 0.022, 0.011)],
  },
];

// ─────────────────────────────────────────────
// 고흥군 해역
// 동강면: 순천만 하구 인근 갯벌 지주식
// 영남면: 시산도·적금도 사이 부유식
// ─────────────────────────────────────────────
const GOHEUNG_FARMS = [
  {
    id: 'GOHEUNG_001', name: '고흥 동강 1구역', fishery_name: '동강면 양식 A블록',
    city: '고흥군 동강면', province: '전라남도', sea_area: '남해동부',
    species: '방사무늬김', rack_type: '지주식', area_m2: 18200,
    depth: 5.6, tidal_range: 3.2, current_speed: 0.28, salinity: 32.7,
    nearest_buoy: 'WB-고흥동강', nearest_tide: '고흥 조위관측소',
    permit_id: 'JN-KIM-2021-0156', status: '운영중',
    centroid: [127.325, 34.803],
    coordinates: [makeRect(127.325, 34.803, 0.032, 0.015)],
  },
  {
    id: 'GOHEUNG_002', name: '고흥 동강 2구역', fishery_name: '동강면 양식 B블록',
    city: '고흥군 동강면', province: '전라남도', sea_area: '남해동부',
    species: '방사무늬김', rack_type: '지주식', area_m2: 11900,
    depth: 4.8, tidal_range: 3.5, current_speed: 0.25, salinity: 32.4,
    nearest_buoy: 'WB-고흥동강', nearest_tide: '고흥 조위관측소',
    permit_id: 'JN-KIM-2021-0157', status: '운영중',
    centroid: [127.342, 34.797],
    coordinates: [makeRect(127.342, 34.797, 0.024, 0.012)],
  },
  {
    id: 'GOHEUNG_003', name: '고흥 영남 1구역', fishery_name: '영남면 양식 A블록',
    city: '고흥군 영남면', province: '전라남도', sea_area: '남해동부',
    species: '방사무늬김', rack_type: '부류식', area_m2: 13400,
    depth: 9.7, tidal_range: 2.6, current_speed: 0.40, salinity: 33.3,
    nearest_buoy: 'WB-고흥영남', nearest_tide: '고흥 조위관측소',
    permit_id: 'JN-KIM-2022-0043', status: '운영중',
    centroid: [127.795, 34.603],
    coordinates: [makeRect(127.795, 34.603, 0.026, 0.013)],
  },
];

// ─────────────────────────────────────────────
// 신안군 해역
// 비금도: 북부 및 동서측 연안 지주식
// 도초도: 서남측 연안 및 비금-도초 연결 해역
// ─────────────────────────────────────────────
const SINAN_FARMS = [
  {
    id: 'SINAN_001', name: '신안 비금 1구역', fishery_name: '비금면 양식 A블록',
    city: '신안군 비금면', province: '전라남도', sea_area: '서해남부',
    species: '방사무늬김', rack_type: '지주식', area_m2: 20100,
    depth: 3.8, tidal_range: 5.5, current_speed: 0.58, salinity: 31.5,
    nearest_buoy: 'WB-비금', nearest_tide: '목포 조위관측소',
    permit_id: 'JN-KIM-2020-0312', status: '운영중',
    centroid: [126.018, 34.795],
    coordinates: [makeRect(126.018, 34.795, 0.035, 0.016)],
  },
  {
    id: 'SINAN_002', name: '신안 도초 1구역', fishery_name: '도초면 양식 A블록',
    city: '신안군 도초면', province: '전라남도', sea_area: '서해남부',
    species: '방사무늬김', rack_type: '지주식', area_m2: 15600,
    depth: 4.1, tidal_range: 5.2, current_speed: 0.52, salinity: 31.8,
    nearest_buoy: 'WB-도초', nearest_tide: '목포 조위관측소',
    permit_id: 'JN-KIM-2020-0313', status: '운영중',
    centroid: [125.930, 34.687],
    coordinates: [makeRect(125.930, 34.687, 0.030, 0.014)],
  },
];

// ─────────────────────────────────────────────
// 여수시 해역
// 돌산도 서측 가막만 / 화정면 인근
// ─────────────────────────────────────────────
const YEOSU_FARMS = [
  {
    id: 'YEOSU_001', name: '여수 돌산 1구역', fishery_name: '돌산읍 양식 A블록',
    city: '여수시 돌산읍', province: '전라남도', sea_area: '남해동부',
    species: '방사무늬김', rack_type: '부류식', area_m2: 8700,
    depth: 7.3, tidal_range: 2.1, current_speed: 0.33, salinity: 33.6,
    nearest_buoy: 'WB-여수', nearest_tide: '여수 조위관측소',
    permit_id: 'JN-KIM-2023-0018', status: '운영중',
    centroid: [127.695, 34.636],
    coordinates: [makeRect(127.695, 34.636, 0.020, 0.010)],
  },
  {
    id: 'YEOSU_002', name: '여수 돌산 2구역', fishery_name: '돌산읍 양식 B블록',
    city: '여수시 돌산읍', province: '전라남도', sea_area: '남해동부',
    species: '방사무늬김', rack_type: '부류식', area_m2: 10400,
    depth: 8.9, tidal_range: 2.3, current_speed: 0.38, salinity: 33.9,
    nearest_buoy: 'WB-여수', nearest_tide: '여수 조위관측소',
    permit_id: 'JN-KIM-2023-0019', status: '운영중',
    centroid: [127.705, 34.628],
    coordinates: [makeRect(127.705, 34.628, 0.022, 0.011)],
  },
];

// 전체 통합
export const ALL_FARMS = [
  ...WANDO_FARMS,
  ...JINDO_FARMS,
  ...GOHEUNG_FARMS,
  ...SINAN_FARMS,
  ...YEOSU_FARMS,
];

// GeoJSON FeatureCollection 생성
export function toGeoJSON(farms, liveWbiMap = {}) {
  return {
    type: 'FeatureCollection',
    features: farms.map(farm => ({
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: farm.coordinates,
      },
      properties: {
        ...farm,
        wbi_score: liveWbiMap[farm.id] ?? null,
      },
    })),
  };
}

// 관측소 데이터 (부이 + 조위관측소 위치) — 실제 좌표 기반
export const OBSERVATION_STATIONS = [
  { id: 'WB-완도',      type: 'buoy', name: '완도(금일) 관측부이',  lat: 34.300, lon: 127.050, depth: null },
  { id: 'WB-생일',      type: 'buoy', name: '생일 관측부이',        lat: 34.338, lon: 126.975, depth: null },
  { id: 'WB-노화',      type: 'buoy', name: '노화 관측부이',        lat: 34.192, lon: 126.550, depth: null },
  { id: 'WB-조도',      type: 'buoy', name: '조도 관측부이',        lat: 34.300, lon: 126.125, depth: null },
  { id: 'WB-고흥동강',  type: 'buoy', name: '고흥(동강) 관측부이',  lat: 34.800, lon: 127.333, depth: null },
  { id: 'WB-고흥영남',  type: 'buoy', name: '고흥(영남) 관측부이',  lat: 34.600, lon: 127.800, depth: null },
  { id: 'WB-비금',      type: 'buoy', name: '비금 관측부이',        lat: 34.792, lon: 126.025, depth: null },
  { id: 'WB-도초',      type: 'buoy', name: '도초 관측부이',        lat: 34.683, lon: 125.933, depth: null },
  { id: 'WB-여수',      type: 'buoy', name: '여수(돌산) 관측부이',  lat: 34.633, lon: 127.700, depth: null },
  { id: '완도-조위',    type: 'tide', name: '완도 조위관측소',      lat: 34.320, lon: 126.755, depth: null },
  { id: '진도-조위',    type: 'tide', name: '진도 조위관측소',      lat: 34.240, lon: 126.270, depth: null },
  { id: '고흥-조위',    type: 'tide', name: '고흥 조위관측소',      lat: 34.610, lon: 127.290, depth: null },
  { id: '목포-조위',    type: 'tide', name: '목포 조위관측소',      lat: 34.790, lon: 126.380, depth: null },
  { id: '여수-조위',    type: 'tide', name: '여수 조위관측소',      lat: 34.740, lon: 127.740, depth: null },
];

// 지역(읍면)별 그룹
export const REGION_GROUPS = {
  '완도군': WANDO_FARMS.map(f => f.id),
  '진도군': JINDO_FARMS.map(f => f.id),
  '고흥군': GOHEUNG_FARMS.map(f => f.id),
  '신안군': SINAN_FARMS.map(f => f.id),
  '여수시': YEOSU_FARMS.map(f => f.id),
};
