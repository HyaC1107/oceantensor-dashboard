"""이상값 탐지 — IQR + Z-score + 황백화 도메인 규칙 기반 복합 탐지.

3단계 파이프라인:
  1. 물리 범위 이탈 탐지 (절대 임계치)
  2. 통계적 이상 탐지 (Z-score, IQR)
  3. 황백화 도메인 규칙 (급격한 DIN 하락, 수온 급상승 등)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque

import numpy as np


# 센서별 물리적 유효 범위
# DIN, DIP 단위: μg/L  (0.07 mg/L = 70 μg/L, 0.016 mg/L = 16 μg/L)
PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    "water_temp":       (-2.0,   35.0),
    "dissolved_oxygen": (0.0,    20.0),
    "din":              (0.0,  1500.0),   # μg/L (한국 연안 최대치 고려)
    "dip":              (0.0,   200.0),   # μg/L
    "np_ratio":         (0.0,   200.0),
    "salinity":         (0.0,    45.0),
    "chlorophyll_a":    (0.0,   200.0),
    "turbidity":        (0.0,   500.0),
    "ph":               (4.0,    10.0),
}

# 황백화 위험 임계치
# 출처: NIFS 공식 기준 + JKOSMEE 2018/2023 논문
# DIN: 0.07 mg/L = 70 μg/L 이하 위험 / 0.10 mg/L = 100 μg/L 이하 주의
# DIP: 0.016 mg/L = 16 μg/L 이하 주의 / 0.006 mg/L = 6 μg/L 이하 위험
# N:P: 몰비 6:1 이하 위험 / 16:1 이하 주의
HWANGBAEK_THRESHOLDS: dict[str, dict] = {
    "din":              {"caution": 100.0, "danger":  70.0, "direction": "low"},
    "dip":              {"caution":  16.0, "danger":   6.0, "direction": "low"},
    "water_temp":       {"caution":  22.0, "danger":  25.0, "direction": "high"},
    "np_ratio":         {"caution":  16.0, "danger":   6.0, "direction": "low"},
    "dissolved_oxygen": {"caution":   6.0, "danger":   4.0, "direction": "low"},
}


@dataclass
class AnomalyFlag:
    """이상값 탐지 결과."""
    field:     str
    value:     float
    anomaly_type: str       # "physical_range" | "z_score" | "iqr" | "domain_rule" | "spike"
    severity:  str          # "info" | "warning" | "critical"
    message:   str
    threshold: float | None = None


@dataclass
class OutlierReport:
    """전체 레코드에 대한 이상값 보고서."""
    record_id:  str
    flags:      list[AnomalyFlag] = field(default_factory=list)
    is_anomaly: bool = False
    max_severity: str = "none"

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "warning")


class OutlierDetector:
    """복합 이상값 탐지기.

    Args:
        window_size:  Z-score / IQR 계산용 슬라이딩 윈도우 크기
        z_threshold:  Z-score 이상 임계값 (기본 3.0)
        iqr_factor:   IQR 이상 배수 (기본 1.5)
        spike_factor: 직전 값 대비 급변 배수 (기본 3.0)
    """

    def __init__(
        self,
        window_size: int = 50,
        z_threshold: float = 3.0,
        iqr_factor:  float = 1.5,
        spike_factor: float = 3.0,
    ):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.iqr_factor  = iqr_factor
        self.spike_factor = spike_factor

        # 필드별 슬라이딩 윈도우
        self._windows: dict[str, deque] = {}
        self._prev: dict[str, float] = {}

    def detect(self, record: dict, record_id: str = "?") -> OutlierReport:
        """단일 레코드 이상값 탐지.

        Args:
            record:    {field: value} dict
            record_id: 로깅용 식별자

        Returns:
            OutlierReport
        """
        report = OutlierReport(record_id=record_id)

        for field_name, value in record.items():
            if value is None or not isinstance(value, (int, float)):
                continue

            fval = float(value)
            flags = []

            # 1. 물리 범위 이탈
            bounds = PHYSICAL_BOUNDS.get(field_name)
            if bounds:
                lo, hi = bounds
                if fval < lo or fval > hi:
                    flags.append(AnomalyFlag(
                        field=field_name, value=fval,
                        anomaly_type="physical_range", severity="critical",
                        message=f"{field_name}={fval} 물리 범위({lo}~{hi}) 이탈",
                        threshold=hi if fval > hi else lo,
                    ))

            # 2. 슬라이딩 윈도우 통계 (Z-score, IQR)
            win = self._get_window(field_name)
            if len(win) >= 10:
                arr = np.array(win)
                mean, std = arr.mean(), arr.std()

                # Z-score
                if std > 1e-6:
                    z = abs(fval - mean) / std
                    if z > self.z_threshold:
                        sev = "critical" if z > self.z_threshold * 1.5 else "warning"
                        flags.append(AnomalyFlag(
                            field=field_name, value=fval,
                            anomaly_type="z_score", severity=sev,
                            message=f"{field_name}={fval} Z-score={z:.1f} (>{self.z_threshold})",
                            threshold=self.z_threshold,
                        ))

                # IQR
                q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
                iqr = q3 - q1
                lo_iqr = q1 - self.iqr_factor * iqr
                hi_iqr = q3 + self.iqr_factor * iqr
                if fval < lo_iqr or fval > hi_iqr:
                    if not any(f.anomaly_type == "z_score" for f in flags):
                        flags.append(AnomalyFlag(
                            field=field_name, value=fval,
                            anomaly_type="iqr", severity="warning",
                            message=f"{field_name}={fval} IQR 범위({lo_iqr:.2f}~{hi_iqr:.2f}) 이탈",
                        ))

            # 3. 급변 탐지 (Spike)
            prev = self._prev.get(field_name)
            if prev is not None and abs(prev) > 1e-6:
                ratio = abs(fval - prev) / abs(prev)
                if ratio > self.spike_factor:
                    flags.append(AnomalyFlag(
                        field=field_name, value=fval,
                        anomaly_type="spike", severity="warning",
                        message=f"{field_name} 급변: {prev:.2f}→{fval:.2f} ({ratio*100:.0f}% 변화)",
                        threshold=self.spike_factor,
                    ))

            # 4. 황백화 도메인 규칙
            hw_rule = HWANGBAEK_THRESHOLDS.get(field_name)
            if hw_rule:
                direction = hw_rule["direction"]
                if direction == "low":
                    if fval <= hw_rule["danger"]:
                        flags.append(AnomalyFlag(
                            field=field_name, value=fval,
                            anomaly_type="domain_rule", severity="critical",
                            message=f"⚠️ {field_name}={fval} 황백화 위험 임계치({hw_rule['danger']}) 이하",
                            threshold=hw_rule["danger"],
                        ))
                    elif fval <= hw_rule["caution"]:
                        flags.append(AnomalyFlag(
                            field=field_name, value=fval,
                            anomaly_type="domain_rule", severity="warning",
                            message=f"🔶 {field_name}={fval} 황백화 주의 임계치({hw_rule['caution']}) 이하",
                            threshold=hw_rule["caution"],
                        ))
                else:  # "high"
                    if fval >= hw_rule["danger"]:
                        flags.append(AnomalyFlag(
                            field=field_name, value=fval,
                            anomaly_type="domain_rule", severity="critical",
                            message=f"⚠️ {field_name}={fval} 황백화 위험 임계치({hw_rule['danger']}) 초과",
                            threshold=hw_rule["danger"],
                        ))
                    elif fval >= hw_rule["caution"]:
                        flags.append(AnomalyFlag(
                            field=field_name, value=fval,
                            anomaly_type="domain_rule", severity="warning",
                            message=f"🔶 {field_name}={fval} 황백화 주의 임계치({hw_rule['caution']}) 초과",
                            threshold=hw_rule["caution"],
                        ))

            report.flags.extend(flags)

            # 윈도우 업데이트
            win.append(fval)
            self._prev[field_name] = fval

        # 전체 severity 집계
        if report.flags:
            report.is_anomaly = True
            severities = [f.severity for f in report.flags]
            if "critical" in severities:
                report.max_severity = "critical"
            elif "warning" in severities:
                report.max_severity = "warning"
            else:
                report.max_severity = "info"

        return report

    def _get_window(self, field: str) -> deque:
        if field not in self._windows:
            self._windows[field] = deque(maxlen=self.window_size)
        return self._windows[field]

    def reset(self):
        self._windows.clear()
        self._prev.clear()
