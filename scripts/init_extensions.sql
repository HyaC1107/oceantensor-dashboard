-- TimescaleDB, PostGIS, pgvector 확장 초기화
-- Docker 컨테이너 최초 실행 시 자동으로 실행됨

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- ocean_sensor_raw 는 앱 기동 후 SQLAlchemy가 테이블 생성
-- 이후 하이퍼테이블 변환은 앱에서 처리
