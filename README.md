# 어텐션플리즈 — 김 황백화 조기경보 대시보드

> 서해·남해 김 양식장 **황백화(백화현상) 미래 7일 조기경보** 웹 대시보드
> ST-MMT v13 (Spatio-Temporal Multi-Modal Transformer) 예측 서빙 + 실측 해양관측 연동
> 🌐 배포: https://oceantensor.ai.kr/app/ (Grafana 좌측 메뉴 "황백화 AI 관제"에서도 접근)

---

## 구성

```
app/          FastAPI 백엔드
  routers/
    v7.py         v13 예측팩 서빙 · 양식시즌 게이팅 · onset(전이) 위험등급
    predict.py    v13 예측 / What-if 시뮬레이션(WBI 공식)
    realdata.py   실측 센서 — 어장 최근접 관측소(KOEM·KMA) 조회
    explain.py    XAI 자연어 보고서 (Gemini)
    rag.py        해양 문서 RAG Q&A
  data/
    v13_predictions_all.json   v13 사전계산 예측 (어장 1194 × 354일)
    farms_geo.json             어장 좌표

ml/           ST-MMT 모델 정의 · 학습 · 데이터 파이프라인
frontend/     React + Vite 대시보드 (어텐션맵 / XAI / 시뮬레이터 / Q&A)
deploy/       배포 구성 (Docker / nginx / 슬림 의존성)
```

## 화면

| 탭 | 내용 |
|----|------|
| 🔴 어텐션 맵 | 전국 김양식장 **1194개** 지도 + v13 실예측. 지역 검색/포커싱, 어장 클릭 시 상세 |
| 🧠 XAI 분석 | 어장별 기여도 분석 + Gemini 자연어 진단 |
| 🧪 시뮬레이션 | 수질 지표를 조정해 황백화 위험 변화를 체감하는 What-if |
| 💬 AI Q&A | 해양 문서 기반 RAG |

---

## 핵심 설계 (읽지 않으면 오해하기 쉬운 것들)

### 1. 지도 색상 = **onset(전이)** 기준 — `stage`가 아님
`stage`는 ADI **회귀헤드**에서 파생되는데, 이 헤드는 모든 평가에서 persistence(전일 유지)에 열세인
**모델의 약점**이다. 그걸로 칠하면 1년 내내 ~40% 어장이 빨갛게 나온다(실제 사건은 11~1월 집중).

모델의 검증된 강점은 **warn onset**(전이 탐지 — 무누수 홀드아웃에서 persistence 대비 **+3.3pt**)이므로,
지도는 **전일 대비 발생확률 급등(Δwarn ≥ 0.15)** 을 경보로 쓴다.

| 등급 | 의미 |
|------|------|
| 🔴 급등 경보 | 전일 대비 7일내 발생확률 급등 — **AI가 새로 포착한 위험** |
| 🟠 고위험 지속 | 이미 높은 상태 유지 (관성 — 규칙기반으로도 포착 가능) |
| 🟡 주의 / 🟢 정상 | |

### 2. 비양식기(6~10월)에는 예측을 표시하지 않는다
SSOT: `ml/data/channel_builder.py::_is_harvest_season` — *"수확기 11~5월, 6~10월=IGNORE"*.
6~10월은 **학습 시 라벨이 IGNORE로 마스킹된 구간**이라 그 기간 예측은 무의미한 외삽이다.
대시보드는 **오늘** 기준으로 판단해 비양식기면 위험 예측을 끄고, 지난 시즌은 별도 열람 모드로 본다.

### 3. 실측 데이터의 단위·신선도
- KOEM 영양염은 **μg/L**, WBI 공식/라벨러는 **μmol/L** → `DIN÷14.007`, `DIP÷30.974` 변환 필수.
  변환을 빠뜨리면 위험도가 완전히 뒤틀린다.
- 영양염은 기관 **QC 발행 지연**으로 최신 관측이 수개월 전일 수 있다.
  → 화면에 **관측일을 반드시 함께 표시**한다(실시간처럼 보이면 오도).

### 4. 어장 체계는 하나로 통일 (`frontend/src/data/realFarms.js`)
지도·XAI·시뮬레이터·예측팩·실측 조회가 **모두 같은 어장 id(gid)** 를 쓴다.
과거엔 화면마다 어장 데이터가 갈라져 있어(가짜 데모 어장 46개 등) 서로 매치되지 않았다.

---

## 로컬 실행

```bash
# 백엔드 (mock 모드 — DB 없이 v13 예측팩만으로 동작)
uv run uvicorn app.main:app --port 8000

# 실측 데이터까지 붙이려면
USE_MOCK_DATA=true DATABASE_URL="postgresql+asyncpg://<user>:<pw>@<host>:5432/oceantensor_db" \
  uv run uvicorn app.main:app --port 8000

# 프론트
cd frontend && npm install && npm run dev     # http://localhost:5173
```

`.env.example` 참고해 `.env` 작성 (Gemini 키 없으면 XAI는 템플릿 폴백).

## 배포

`deploy/DEPLOY.md` 참조. 프로덕션은 nginx가 한 도메인에서 셋을 서빙한다:

```
oceantensor.ai.kr/       → Grafana
                 /app/   → 이 대시보드 (정적 빌드)
                 /hbapi/ → FastAPI 백엔드
```
> ⚠️ 우리 API 프리픽스가 `/api/`면 **Grafana 자체 API와 충돌**한다(`/api/dashboards` 등). `/hbapi/`를 쓰는 이유.

## Git에 없는 것 (용량/보안)

- `checkpoints/` — 모델 가중치. 원본: H100 `/data/tta/cheolyoung/checkpoints/v13/`
- `output/` — 학습 큐브(수십 GB). H100에서 생성
- `.env`, `*.pem` — 시크릿
