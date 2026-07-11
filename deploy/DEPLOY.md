# 어텐션플리즈 웹앱 배포 런북 (네이버클라우드)

> 대상 서버: `101.79.18.13` (도메인 `oceantensor.ai.kr`, gabia 등록)
> 방식: Docker Compose — 백엔드(FastAPI, mock) + 프론트(nginx 정적서빙 + 리버스프록시)
> 데이터: **mock 모드** (v13 예측팩 JSON 서빙, DB 불필요) — 검증 완료 2026-07-11
> 작성: 클또리 2026-07-11

---

## 0. 🔴 배포 전 PM 확인 필수 (블로커)

| # | 확인 항목 | 상태 |
|---|-----------|------|
| 1 | **`attention-key.pem` SSH 키** — 없으면 서버 셸 접속 불가 → 컨테이너 기동 불가 | ❓ **PM 확인 필요** |
| 2 | 서버 **Docker / docker compose 설치** 여부 (루트 compose가 있으니 있을 가능성 높음) | ❓ 확인 |
| 3 | 서버 **여유 디스크/메모리** (슬림 이미지라 백엔드 ~300MB, 프론트 빌드 일시적 node 필요) | ❓ 확인 |
| 4 | **80/443 포트 방화벽(ACG)** 오픈 | ❓ 확인 |
| 5 | HTTPS 쓸지 (도메인 있으니 certbot 권장) | 결정 필요 |

> pem이 없으면: 네이버클라우드 콘솔에서 키 재발급 또는 비번 SSH 허용 여부를 PM이 먼저 확인해야 함.
> SFTP(FileZilla)는 비번으로 되지만, uvicorn/nginx 기동엔 셸 접속이 필요.

---

## 1. 로컬 런타임 검증 (배포 전 · PM이 브라우저로)

빌드는 통과하지만 **UI 클릭 검증은 사람이 해야 함**(드롭다운 버그도 런타임에서 발견됨). 로컬에서:

```bash
# 백엔드
cd attention/seaweed-hwangbaek
USE_MOCK_DATA=true UV_LINK_MODE=copy uv run uvicorn app.main:app --port 8000
# 프론트(다른 터미널)
cd frontend && npm run dev   # http://localhost:5173
```

체크리스트:
- [ ] 🔴 어텐션 맵 → 양식장 클릭 → 상세패널 **안 잘림** + 헤더 잡고 **드래그 이동** 됨
- [ ] 글씨 대비 OK (라벨 잘 보임)
- [ ] 🧪 시뮬레이션 → 드롭다운 글씨 보임 + 슬라이더 반응 + 7일 궤적
- [ ] 🧠 XAI 분석 → 드롭다운/차트 정상

---

## 2. 배포 (서버에서)

```bash
# (로컬→서버) 코드 전송: git 없으니 rsync/scp 또는 FileZilla
#   node_modules, .venv, checkpoints 큰 것 제외하고 전송
rsync -av --exclude node_modules --exclude .venv --exclude '*.pt' \
  attention/seaweed-hwangbaek/  attention@101.79.18.13:~/seaweed-hwangbaek/

# (서버) 빌드 + 기동 — 프로젝트 루트에서
cd ~/seaweed-hwangbaek
docker compose -f deploy/docker-compose.deploy.yml up -d --build

# 확인
curl -s localhost/predict/ -X POST -H 'Content-Type: application/json' -d '{"farm_id":"F01"}'
curl -s "localhost/predict/v7?date=2025-11-15" | head -c 200
```

접속: `http://101.79.18.13` (또는 도메인 연결 후 `http://oceantensor.ai.kr`)

---

## 3. HTTPS (권장 · 도메인 있음)

`oceantensor.ai.kr` A레코드를 `101.79.18.13`으로 지정 후, 호스트 nginx 또는 certbot 컨테이너로 인증서 발급:

```bash
# 예: 호스트에 certbot 설치 후 (웹 컨테이너를 443으로 확장하거나 앞단 프록시)
sudo certbot --nginx -d oceantensor.ai.kr
```

> 간단히는 web 서비스 앞에 `nginx-proxy`+`acme-companion` 또는 Caddy 한 대를 두는 방식도 있음.
> HTTPS 적용 시 WS는 자동으로 `wss://` (프론트가 상대경로 `/ws/sensor` 사용).

---

## 4. mock → 실제 DB 전환 (나중에)

1. `deploy/docker-compose.deploy.yml`의 backend 환경에 `USE_MOCK_DATA=false` + `DATABASE_URL` (서버 Postgres `oceantensor_db`).
2. 백엔드 이미지에 실제 데이터 파이프라인/모델이 필요하면 슬림 의존성으론 부족 → 풀 의존성 재검토.
3. 백엔드 CORS(`app/main.py` `allow_origins`)에 배포 도메인 추가(같은 오리진 서빙이면 불필요).

---

## 구성 파일

| 파일 | 역할 |
|------|------|
| `Dockerfile.backend` | 슬림 FastAPI 이미지 (torch/GDAL 없음, v13 팩 동봉) |
| `Dockerfile.frontend` | Vite 빌드 → nginx 정적서빙 |
| `nginx.conf` | SPA 서빙 + API/WS 리버스프록시 (같은 오리진) |
| `docker-compose.deploy.yml` | backend + web 오케스트레이션 |
| `requirements-serve.txt` | 서빙 전용 슬림 의존성 14종 (검증됨) |
| `.env.deploy.example` | 배포 환경변수 예시 |

## 검증 근거 (2026-07-11)
- 슬림 14개 의존성만으로 `app.main` import 성공(라우트 13개)
- **DB 없이** `POST /predict/`(v13 stmmt-v13 응답)·`GET /predict/v7?date=`(79어장)·시뮬레이터 formula 경로 정상 응답
- 프론트 `npm run build` 통과, 하드코딩 `localhost:8000` 제거(전부 `VITE_API_BASE_URL` 경유)
