# OPeNDAP ROI 슬라이싱 수집 워크플로우

> ttori-core `.claude/skills/drafts/opendap-roi-downloader.md` 초안을 이 프로젝트 전용 워크플로우로 이전 (2026-07-02).
> 프로젝트 종속 로직이라 ttori-core 전역 스킬이 아닌 이 저장소에 둔다.

## 목적

OPeNDAP Hyrax 서버(GOCI-II 등)의 대용량 NetCDF 데이터에서 `pydap`으로 관심 영역(ROI) 격자만 원격 슬라이싱해 대역폭/수집 속도를 극대화한다.

## 실제 구현

- `ml/data/collectors/kosc_ml.py` — `_load_ac_pydap()` 메서드
- `nc4.Dataset` OPeNDAP 방식은 이 환경에서 미지원 → `pydap.client.open_url` 방식 사용
- stride=50 저해상도 lat/lon으로 먼저 ROI 경계를 탐지한 뒤, 해당 슬라이스만 다운로드
- 전체 파일(~380MB) 대신 ROI 슬라이스(~22MB/일)만 수집

## 실행 플로우

1. `pydap.client.open_url(url)`로 원격 데이터셋 핸들 오픈 (전체 다운로드 없음)
2. 저해상도 lat/lon 배열로 ROI 경계 인덱스 계산
3. 해당 인덱스 슬라이스만 실제 변수에서 가져오기 (`var[lat_slice, lon_slice]`)
4. daily parquet으로 저장

## 주의사항 (실제 발견된 이슈)

- GOCI-II 파일명 포맷이 기간에 따라 바뀜 (`_LA_S007_ACR.nc` → `_LA_AC.nc`, 2024년 여름 기점) — 구포맷만 시도하면 조용히 404
- 새 데이터셋 도입 전 실제 API 호출로 응답 포맷 확인 필수 (해양조사원 평균 해류도 API처럼 이미지 PNG만 반환하는 경우도 있음)

## 참고

- 2026-06-23 daily 로그: 신포맷 대응 성공 사례 (37,030행, 9시간 백그라운드 수집)
