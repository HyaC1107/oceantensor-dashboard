/**
 * XAI 자연어 설명 데이터 — 젬또리(Gemini CLI) 생성
 *
 * 황백화 원인 변수별로 어가(농민)가 이해하기 쉬운 한국어 설명 + 대처 방법
 * 상태: ABOVE_THRESHOLD(기준치 초과) / BELOW_THRESHOLD(기준치 미달)
 */
export const XAI_EXPLANATIONS = {
  din: {
    label: '용존무기질소 (DIN)',
    unit: 'μmol/L',
    threshold: 5.0,
    icon: '🧪',
    ABOVE: {
      explain: '바닷속 영양분(질소)이 너무 많습니다. 잡조류나 플랑크톤이 번식해 김의 품질이 떨어질 수 있습니다.',
      action: '잡조류 달라붙음 여부를 확인하고, 물 소통이 잘 되도록 시설물을 점검하세요.',
      severity: 'caution',
    },
    BELOW: {
      explain: '김의 먹이가 되는 질소가 부족합니다. 황백화 현상이 발생할 위험이 매우 높으니 각별한 주의가 필요합니다.',
      action: '활성처리제를 사용하거나 수심을 조절해 영양염류를 보충하는 것을 검토하세요.',
      severity: 'danger',
    },
  },
  water_temp: {
    label: '수온',
    unit: '℃',
    threshold: 25.0,
    icon: '🌡️',
    ABOVE: {
      explain: '바닷물 온도가 김이 자라기에 너무 높습니다. 생장이 더뎌지고 병해(구멍갯병 등)에 취약해집니다.',
      action: '김을 공기 중에 노출시키는 시간을 조절하여 열 스트레스를 줄여주세요.',
      severity: 'danger',
    },
    BELOW: {
      explain: '수온이 낮아 김의 활동이 위축되었습니다. 평소보다 천천히 자라 채취 시기가 늦어질 수 있습니다.',
      action: '성장 상태를 주기적으로 확인하며 무리한 채취보다는 안정적인 생육을 유도하세요.',
      severity: 'caution',
    },
  },
  np_ratio: {
    label: 'N:P 비율',
    unit: '',
    threshold: 16.0,
    icon: '⚖️',
    ABOVE: {
      explain: '질소와 인의 균형 중 질소가 너무 과합니다. 영양 불균형으로 김의 세포 조직이 비정상적으로 자랄 수 있습니다.',
      action: '주변 오염물질 유입 여부를 확인하고 물때에 맞춘 환수를 권장합니다.',
      severity: 'caution',
    },
    BELOW: {
      explain: '인에 비해 질소가 턱없이 부족합니다. 김 색깔이 흐려지고 황백화로 이어지기 가장 쉬운 상태입니다.',
      action: '영양 부족 신호이므로 신속하게 영양 보충 대책을 세워야 합니다.',
      severity: 'danger',
    },
  },
  dissolved_oxygen: {
    label: '용존산소 (DO)',
    unit: 'mg/L',
    threshold: 5.0,
    icon: '💧',
    ABOVE: {
      explain: '물속 산소 농도가 필요 이상으로 높습니다. 플랑크톤이 급격히 늘어났다는 신호일 수 있어 주의가 필요합니다.',
      action: '바닷물 색깔 변화를 관찰하고 플랑크톤 번식 여부를 확인하세요.',
      severity: 'caution',
    },
    BELOW: {
      explain: '물속 산소가 부족하여 김이 숨쉬기 힘든 상태입니다. 활력이 떨어지고 심하면 엽체가 녹아내릴 수 있습니다.',
      action: '시설물 간격을 넓히거나 물 소통을 방해하는 부유물을 제거해 주세요.',
      severity: 'danger',
    },
  },
  salinity: {
    label: '염분',
    unit: 'PSU',
    threshold: 32.0,
    icon: '🌊',
    ABOVE: {
      explain: '바닷물의 소금기가 너무 진합니다. 김이 수분을 뺏기는 스트레스를 받아 조직이 손상될 수 있습니다.',
      action: '수심을 깊게 조절하여 염분 변화를 최소화하고 부착 상태를 점검하세요.',
      severity: 'caution',
    },
    BELOW: {
      explain: '비가 많이 오거나 육지 민물이 들어와 소금기가 너무 낮습니다. 김이 힘없이 늘어지거나 성장이 멈출 수 있습니다.',
      action: '염분이 회복될 때까지 노출 시간을 줄이고 시설물을 안정시키세요.',
      severity: 'caution',
    },
  },
  dip: {
    label: '용존무기인 (DIP)',
    unit: 'μmol/L',
    threshold: 0.3,
    icon: '🔬',
    ABOVE: {
      explain: '물속에 녹아있는 인(영양분)이 너무 많습니다. 김 표면에 이물질이 끼고 색택이 나빠질 수 있습니다.',
      action: '어장 주변 청결 상태를 점검하고 이물질 제거에 신경 써주세요.',
      severity: 'caution',
    },
    BELOW: {
      explain: '김 성장에 꼭 필요한 인 성분이 부족합니다. 김이 얇아지고 윤기가 사라지며 성장이 둔화됩니다.',
      action: '전반적인 영양 결핍 여부를 확인하고 필요 시 복합 영양 공급을 고려하세요.',
      severity: 'caution',
    },
  },
  precipitation: {
    label: '강수량 (3일)',
    unit: 'mm',
    threshold: 15.0,
    icon: '🌧️',
    ABOVE: {
      explain: '갑작스러운 많은 비로 어장 환경이 급변했습니다. 육지에서 오염물이나 민물이 흘러들어와 김에게 스트레스를 줍니다.',
      action: '어장 내 부유물을 즉시 제거하고 시설물이 파도에 밀리지 않게 고정하세요.',
      severity: 'caution',
    },
    BELOW: {
      explain: '오랫동안 비가 오지 않아 육지 영양분 공급이 끊겼습니다. 바닷물이 정체되어 영양분이 마를 수 있습니다.',
      action: '바깥쪽 신선한 물이 어장 안으로 잘 들어오도록 물길을 확보하세요.',
      severity: 'info',
    },
  },
  chlorophyll_a: {
    label: '클로로필-a',
    unit: 'μg/L',
    threshold: 5.0,
    icon: '🌿',
    ABOVE: {
      explain: '물속 플랑크톤(클로로필)이 너무 많아 바닷물이 탁해졌습니다. 플랑크톤이 김이 먹어야 할 영양분을 빼앗아 갑니다.',
      action: '영양분 경합이 심한 시기이므로 김의 색깔 변화를 매일 확인하세요.',
      severity: 'danger',
    },
    BELOW: {
      explain: '바닷속의 기초적인 생명력이 매우 낮습니다. 환경이 척박하여 김의 활력이 떨어질 수 있습니다.',
      action: '어장 환경이 전반적으로 침체된 상태이므로 꾸준한 관찰과 영양 점검이 필요합니다.',
      severity: 'caution',
    },
  },
};

/** status 문자열 → 키 변환 */
export function statusToKey(status) {
  if (status === 'ABOVE_THRESHOLD') return 'ABOVE';
  if (status === 'BELOW_THRESHOLD') return 'BELOW';
  return null;
}

/** 심각도 → 색상 */
export const SEVERITY_COLOR = {
  danger:  '#ef4444',
  caution: '#f59e0b',
  info:    '#60a5fa',
};

/** 현장 사진 데이터 (어장 유형별) */
export const FIELD_PHOTOS = {
  buoy: [
    { src: '/field-photos/buoy-tower.png',  caption: '해양 관측 부이 (등대형)' },
    { src: '/field-photos/buoy-deploy.png', caption: '관측 부이 해상 설치 작업' },
    { src: '/field-photos/buoy-diagram.png', caption: '부이 센서 구성도 (수온·DO·염분·유속)' },
  ],
  tide: [
    { src: '/field-photos/tide-station.png', caption: '국립해양조사원 조위관측소' },
    { src: '/field-photos/obs-equipment.png', caption: '연안 관측 장비' },
  ],
  farm: [
    { src: '/field-photos/obs-network.png', caption: '한국 연안 해양관측망 분포' },
    { src: '/field-photos/gis-overview.png', caption: 'AI 김 양식장 공간 데이터 분석 시스템' },
  ],
};
