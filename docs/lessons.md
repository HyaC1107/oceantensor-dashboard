# lessons.md — 어텐션 프로젝트 누적 교훈

> ttori-core `memory/team-rules.md`에서 어텐션 도메인 특화 교훈을 이관 (2026-07-02).
> ttori-core는 여러 프로젝트를 오가며 매 세션 읽는 파일이라, 이 프로젝트에만 해당하는
> 데이터/파이프라인 트러블슈팅 기록은 여기로 옮겨서 관리한다.

| 번호 | 날짜 | 교훈 | 배경 |
|------|------|------|------|
| 1 | 2026-06-17 | **코드 내 도메인 상수(비수확기 월, 임계값 등)는 반드시 현장 전문가 정의 기준으로** — `skip_offseason`의 6~8월 설정은 직관적으로 맞아 보이지만 실제 서해안 김 양식은 5~9월이 비수확기 (4월 말~5월 초 철거). 도메인 상수 = 항상 검증 대상. | sentinel_ml.py skip_offseason 범위 오류 |
| 2 | 2026-06-18 | **대용량 배열(수 GB 이상)은 절대 전량 메모리에 올리지 말 것** — WSL2는 RAM 50% 한도 초과 시 OOM Killer가 `SIGKILL`로 즉시 사살, nohup도 무력. 해결: 루프 내 "보간 1일치 → 즉시 Zarr 슬라이스 기록 → 메모리 해제" 패턴 필수. 피크 메모리 13GB→35MB로 감소. | build_cube.py Zarr 저장 중 2회 연속 프로세스 사망 (dmesg oom 확인) |
| 3 | 2026-06-18 | **장기 파이프라인은 단계별 체크포인트 파일 저장 필수** — 수집(→parquet) / 보간(→streaming Zarr) / 저장 을 독립 재실행 가능하게 분리. 중간 결과 없으면 2시간 연산이 저장 실패 한 번에 전부 날아감. 단계 분리 원칙: 각 단계 완료 시 파일이 남아있어야 다음 단계 재시작 가능. | build_cube.py 2회 연속 全소멸 |
| 4 | 2026-06-23 | **수집기 fallback이 조용히 0값 반환하는 패턴 → 채널 전체 오염** — kwater_ml.py가 API 실패 시 `_fallback_zero_df()`로 0값 DataFrame을 에러 없이 반환, discharge 채널 전부 0으로 저장됨. 수집기 작성 시 fallback은 반드시 WARNING 로그 + 빈 DataFrame 반환으로 작성할 것 (0값 채우기 금지). | cube_v4 샘플 조회 시 discharge 0값 발견 |
| 5 | 2026-06-23 | **채널 0값 원인 진단 순서** — ① parquet 파일 존재 여부 → ② parquet 내 실제 값 분포 → ③ 수집기 fallback 코드 존재 여부 → ④ API 응답 로그 순으로 확인. parquet이 있어도 값이 0인 경우(fallback)가 있으므로 반드시 값 분포까지 확인. | discharge·current_u/v 0값 원인 분석 |
| 6 | 2026-06-23 | **공공데이터 포털 API 도입 전 응답 형식 반드시 검증** — 국립해양조사원 평균 해류도 API는 수치 데이터가 아닌 이미지 PNG URL만 반환, 서해 지역 코드 자체가 없음. 도입 전 HWP/PDF 활용가이드 파싱 또는 실제 API 호출로 응답 형식 확인. | 평균 해류도 API 검토 → 사용 불가 판정 |
| 7 | 2026-06-23 | **CMEMS 데이터셋 ID는 재분석/인터림/NRT 각각 다르며, 없는 ID는 조용히 실패** — `cmems_mod_glo_phy_myint_0.083deg_P1D-m` ID가 실제로 존재하지 않아 인터림 수집 실패. 새 데이터셋 도입 시 copernicusmarine 패키지로 실제 ID 목록 조회 후 확정. 재분석은 ~4주 지연 있으므로 최신 데이터 공백 발생 가능. | CMEMS 인터림 수집 시도 중 발견 |
| 8 | 2026-06-23 | **KODC 해류 데이터는 수동 다운로드 의존 → 자동화 불가, 누락 시 채널 전체 0** — collect_only.py에 KODC 수집기가 없어 kodc.parquet 자체가 없었음. 수동 의존 데이터는 파이프라인 실행 전 체크리스트로 존재 확인 필수. 장기 대안으로 CMEMS 자동 수집기로 교체 완료. | cube_v4 current_u/v 채널 전부 0 원인 |
| 9 | 2026-06-23 | **deploy_and_build.py는 코드(.py)만 배포 — parquet은 별도 업로드 필수** — H100에 kma/nifs/koem.parquet이 없어 sst·salinity·wind 등 채널 전체 0 발생. `--upload-checkpoints` 옵션 추가됨. 빌드 시 반드시 `--upload-checkpoints output/checkpoints` 함께 지정. | cube_v6 빌드 시 nifs/kma/koem 누락 → 채널 0 |

---

## 참고 — ttori-core에 남은 범용 규칙

H100 원격 실행(sftp+nohup 패턴), zarr keyword-arg 주의 등 범용 기술 팁은 ttori-core `.claude/skills/remote-ssh-executor/SKILL.md`에 통합됨. 새 트러블슈팅 발견 시 "이 프로젝트에만 해당하는가"를 먼저 판단해서 여기(프로젝트) vs ttori-core(범용) 중 맞는 곳에 기록한다.
