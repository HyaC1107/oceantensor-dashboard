# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter
import httpx
from app.config import settings

router = APIRouter()

TODAY     = datetime.now().strftime("%Y%m%d")
WEEK_AGO  = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

# ── 각 API의 수집 컬럼·주기·저장 테이블 정적 메타 ──────────────────────────
CATALOG = {
    "nifs_femo": {
        "frequency": "주 1회",
        "db_table": "ocean_fishery_env_raw",
        "fields": [
            {"key": "TEMP_S",  "label": "표층 수온",   "unit": "℃",      "hwangbaek": True},
            {"key": "SAL_S",   "label": "표층 염분",   "unit": "PSU",    "hwangbaek": False},
            {"key": "DO_S",    "label": "용존산소",    "unit": "mg/L",   "hwangbaek": False},
            {"key": "DIN_S",   "label": "DIN",        "unit": "μmol/L", "hwangbaek": True},
            {"key": "DIP_S",   "label": "DIP",        "unit": "μmol/L", "hwangbaek": True},
            {"key": "CHL_S",   "label": "클로로필a",   "unit": "μg/L",   "hwangbaek": False},
            {"key": "FISHERY", "label": "어장명",      "unit": "",       "hwangbaek": False},
            {"key": "LAT/LON", "label": "좌표",        "unit": "deg",    "hwangbaek": False},
        ],
    },
    "nifs_risa": {
        "frequency": "30분",
        "db_table": "realtime_fishery_observation",
        "fields": [
            {"key": "wtr_tmp",   "label": "수온",       "unit": "℃",  "hwangbaek": True},
            {"key": "obs_dat",   "label": "관측일",     "unit": "",   "hwangbaek": False},
            {"key": "obs_tim",   "label": "관측시각",   "unit": "",   "hwangbaek": False},
            {"key": "sta_cde",   "label": "정점코드",   "unit": "",   "hwangbaek": False},
            {"key": "sta_nam_kor","label": "정점명",    "unit": "",   "hwangbaek": False},
        ],
    },
    "nifs_soo": {
        "frequency": "분기",
        "db_table": "nifs_section_ocean_observation",
        "fields": [
            {"key": "wtr_tmp",   "label": "수온",    "unit": "℃",      "hwangbaek": False},
            {"key": "sal",       "label": "염분",    "unit": "PSU",    "hwangbaek": False},
            {"key": "dox",       "label": "DO",      "unit": "mg/L",   "hwangbaek": False},
            {"key": "nut_no3_n", "label": "질산염",  "unit": "μmol/L", "hwangbaek": True},
            {"key": "nut_po4_p", "label": "인산염(DIP)", "unit": "μmol/L","hwangbaek": True},
            {"key": "obs_dtm",   "label": "관측일시","unit": "",       "hwangbaek": False},
        ],
    },
    "nifs_sois": {
        "frequency": "수시",
        "db_table": "satellite_ocean_image_meta",
        "fields": [
            {"key": "seq",         "label": "영상 ID",   "unit": "",  "hwangbaek": False},
            {"key": "survey_date", "label": "촬영일",    "unit": "",  "hwangbaek": False},
            {"key": "data_type",   "label": "데이터 종류","unit": "", "hwangbaek": False},
            {"key": "url",         "label": "다운로드 URL","unit": "","hwangbaek": False},
        ],
    },
    "nifs_red": {
        "frequency": "수시",
        "db_table": "redtide_event_raw",
        "fields": [
            {"key": "조사일시", "label": "조사일시",   "unit": "",  "hwangbaek": False},
            {"key": "진행상황", "label": "진행상황",   "unit": "",  "hwangbaek": False},
            {"key": "특보상황", "label": "특보상황",   "unit": "",  "hwangbaek": False},
            {"key": "조사해역", "label": "조사해역",   "unit": "",  "hwangbaek": False},
            {"key": "수온",     "label": "수온",       "unit": "℃","hwangbaek": False},
        ],
    },
    "koem_obs": {
        "frequency": "월",
        "db_table": "koem_ocean_env_observation",
        "fields": [
            {"key": "표층 수온",  "label": "표층 수온",  "unit": "℃",     "hwangbaek": True},
            {"key": "DO",        "label": "DO",         "unit": "mg/L",  "hwangbaek": False},
            {"key": "DIN",       "label": "DIN",        "unit": "μmol/L","hwangbaek": True},
            {"key": "DIP",       "label": "DIP",        "unit": "μmol/L","hwangbaek": True},
            {"key": "WQI점수",   "label": "WQI 점수",  "unit": "",       "hwangbaek": False},
            {"key": "WQI등급",   "label": "WQI 등급",  "unit": "",       "hwangbaek": False},
            {"key": "클로로필A", "label": "클로로필a",  "unit": "μg/L",  "hwangbaek": False},
            {"key": "pH",        "label": "pH",         "unit": "",       "hwangbaek": False},
            {"key": "염분",      "label": "염분",       "unit": "PSU",   "hwangbaek": False},
        ],
    },
    "koem_stn": {
        "frequency": "정적",
        "db_table": "ocean_station_master",
        "fields": [
            {"key": "stnpntCode",     "label": "정점코드","unit": "","hwangbaek": False},
            {"key": "stnpntKoreanNm", "label": "정점명",  "unit": "","hwangbaek": False},
            {"key": "lat",            "label": "위도",    "unit": "","hwangbaek": False},
            {"key": "lon",            "label": "경도",    "unit": "","hwangbaek": False},
            {"key": "oceanNm",        "label": "해역명",  "unit": "","hwangbaek": False},
        ],
    },
    "mof_temp15": {
        "frequency": "15분",
        "db_table": "grid_water_temperature_15m",
        "fields": [
            {"key": "analsYmd", "label": "분석일시", "unit": "",  "hwangbaek": False},
            {"key": "gridCd",   "label": "격자코드", "unit": "",  "hwangbaek": False},
            {"key": "wtem",     "label": "수온",     "unit": "℃","hwangbaek": True},
        ],
    },
    "mof_salt15": {
        "frequency": "15분",
        "db_table": "grid_salinity_15m",
        "fields": [
            {"key": "analsYmd", "label": "분석일시", "unit": "",    "hwangbaek": False},
            {"key": "gridCd",   "label": "격자코드", "unit": "",    "hwangbaek": False},
            {"key": "slnty",    "label": "염분",     "unit": "PSU","hwangbaek": True},
        ],
    },
    "mof_tempd1": {
        "frequency": "1일",
        "db_table": "grid_water_temperature_forecast_d1",
        "fields": [
            {"key": "gridCd",    "label": "격자코드",  "unit": "",  "hwangbaek": False},
            {"key": "prdnYmd",   "label": "예측일",    "unit": "",  "hwangbaek": False},
            {"key": "prdnWtem",  "label": "예측 수온", "unit": "℃","hwangbaek": False},
        ],
    },
    "mof_farm": {
        "frequency": "정적",
        "db_table": "aquaculture_farm_master",
        "fields": [
            {"key": "어업면허명", "label": "면허 종류",   "unit": "","hwangbaek": False},
            {"key": "양식유형명", "label": "양식 유형",   "unit": "","hwangbaek": False},
            {"key": "어장면적",   "label": "어장 면적",   "unit": "㎡","hwangbaek": False},
            {"key": "위도/경도",  "label": "위치 좌표",   "unit": "","hwangbaek": False},
        ],
    },
    "kma_asos_hr": {
        "frequency": "1시간",
        "db_table": "asos_hourly_weather",
        "fields": [
            {"key": "tm", "label": "관측시각",  "unit": "",    "hwangbaek": False},
            {"key": "rn", "label": "강수량",    "unit": "mm",  "hwangbaek": True},
            {"key": "ta", "label": "기온",      "unit": "℃",  "hwangbaek": False},
            {"key": "hm", "label": "습도",      "unit": "%",   "hwangbaek": False},
            {"key": "ws", "label": "풍속",      "unit": "m/s", "hwangbaek": False},
        ],
    },
    "kma_asos_day": {
        "frequency": "1일",
        "db_table": "asos_daily_weather",
        "fields": [
            {"key": "tm",     "label": "날짜",          "unit": "",   "hwangbaek": False},
            {"key": "sumRn",  "label": "일 강수량",     "unit": "mm", "hwangbaek": True},
            {"key": "avgTa",  "label": "평균 기온",     "unit": "℃", "hwangbaek": False},
            {"key": "avgRhm", "label": "평균 상대습도", "unit": "%",  "hwangbaek": False},
        ],
    },
    "kma_fcst": {
        "frequency": "1시간",
        "db_table": "weather_forecast_grid",
        "fields": [
            {"key": "RN1", "label": "1시간 강수량", "unit": "mm",  "hwangbaek": True},
            {"key": "T1H", "label": "기온",         "unit": "℃",  "hwangbaek": False},
            {"key": "WSD", "label": "풍속",         "unit": "m/s", "hwangbaek": False},
            {"key": "nx/ny","label": "격자 좌표",   "unit": "",    "hwangbaek": False},
        ],
    },
    "krc_dam": {
        "frequency": "1시간",
        "db_table": "dam_sluice_operation_hourly",
        "fields": [
            {"key": "obsrdt",     "label": "관측일시",   "unit": "",      "hwangbaek": False},
            {"key": "inflowqy",   "label": "유입량",     "unit": "m³/s", "hwangbaek": True},
            {"key": "totdcwtrqy", "label": "방류량",     "unit": "m³/s", "hwangbaek": True},
            {"key": "lowlevel",   "label": "저수위",     "unit": "m",    "hwangbaek": False},
            {"key": "rsvwtrt",    "label": "저수율",     "unit": "%",    "hwangbaek": False},
        ],
    },
    "khoa_tide": {
        "frequency": "보류",
        "db_table": "khoa_tide_station_observation",
        "fields": [
            {"key": "obsTime",         "label": "관측시각", "unit": "",    "hwangbaek": False},
            {"key": "tideLevel",       "label": "조위",     "unit": "cm",  "hwangbaek": False},
            {"key": "waterTemp",       "label": "수온",     "unit": "℃",  "hwangbaek": False},
            {"key": "salinity",        "label": "염분",     "unit": "PSU","hwangbaek": False},
            {"key": "currentSpeed",    "label": "유속",     "unit": "m/s","hwangbaek": False},
        ],
    },
}


async def _check_nifs(api_id: str, key: str, extra: dict | None = None) -> dict:
    params = {"id": api_id, "key": key}
    if extra:
        params.update(extra)
    url = "https://www.nifs.go.kr/OpenAPI_json"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, params=params)
        if r.status_code != 200:
            return {"ok": False, "status_code": r.status_code, "message": f"HTTP {r.status_code}"}
        data = r.json()
        header = data.get("header") or data.get("Header") or {}
        code   = header.get("resultCode", "")
        msg    = header.get("resultMsg", "")
        body   = data.get("body") or data.get("Body") or {}
        items  = body.get("item") or data.get("Item") or []
        ok = code in ("00", "0") or msg.lower() in ("success", "normal service")
        return {
            "ok": ok,
            "status_code": r.status_code,
            "message": msg,
            "item_count": len(items) if isinstance(items, list) else (1 if items else 0),
        }
    except Exception as e:
        return {"ok": False, "status_code": None, "message": str(e)}


async def _check_data_go_kr(url: str, service_key: str, extra: dict | None = None) -> dict:
    from urllib.parse import urlencode, quote
    params = {"pageNo": "1", "numOfRows": "1", "resultType": "json"}
    if extra:
        params.update(extra)
    qs       = urlencode(params) + "&ServiceKey=" + quote(service_key, safe="")
    full_url = f"{url}?{qs}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(full_url)
        if r.status_code != 200:
            return {"ok": False, "status_code": r.status_code, "message": f"HTTP {r.status_code}"}
        try:
            data = r.json()
            header = (
                data.get("response", {}).get("header")
                or data.get("Header")
                or next((v.get("header") for v in data.values() if isinstance(v, dict) and "header" in v), None)
                or {}
            )
            code = header.get("resultCode") or header.get("code") or ""
            msg  = header.get("resultMsg")  or header.get("message") or ""
            ok   = str(code) in ("00", "0", "200")
            item_count = 0
            for v in data.values():
                if isinstance(v, dict):
                    items = v.get("item") or v.get("items") or []
                    if isinstance(items, list):
                        item_count = len(items)
                        break
                    elif isinstance(items, dict):
                        item_count = 1
                        break
            return {"ok": ok, "status_code": r.status_code, "message": msg, "item_count": item_count}
        except Exception:
            text = r.text[:200]
            ok   = any(c in text for c in ("<resultCode>00", "<code>00", '"code":"00"'))
            return {"ok": ok, "status_code": r.status_code, "message": text[:120]}
    except Exception as e:
        return {"ok": False, "status_code": None, "message": str(e)}


async def _fetch_sample_nifs(api_id: str, key: str, extra: dict | None = None) -> dict:
    params = {"id": api_id, "key": key}
    if extra:
        params.update(extra)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get("https://www.nifs.go.kr/OpenAPI_json", params=params)
    data = r.json()
    body  = data.get("body") or data.get("Body") or {}
    items = body.get("item") or data.get("Item") or []
    if isinstance(items, list) and items:
        return {"sample": items[0], "total": len(items)}
    if isinstance(items, dict):
        return {"sample": items, "total": 1}
    return {"sample": None, "total": 0, "raw": data}


async def _fetch_sample_data_go_kr(url: str, service_key: str, extra: dict | None = None) -> dict:
    from urllib.parse import urlencode, quote
    params = {"pageNo": "1", "numOfRows": "3", "resultType": "json"}
    if extra:
        params.update(extra)
    qs       = urlencode(params) + "&ServiceKey=" + quote(service_key, safe="")
    full_url = f"{url}?{qs}"
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(full_url)
    try:
        data = r.json()
        for v in data.values():
            if isinstance(v, dict):
                items = v.get("item") or v.get("items") or []
                if isinstance(items, list) and items:
                    return {"sample": items[0], "total": len(items), "raw_count": 3}
                if isinstance(items, dict):
                    return {"sample": items, "total": 1}
        return {"sample": None, "raw": str(data)[:300]}
    except Exception:
        return {"sample": None, "raw": r.text[:300]}


def _pending(reason: str) -> dict:
    return {"ok": None, "status_code": None, "message": reason, "item_count": 0}


def _with_meta(key: str, base: dict) -> dict:
    meta = CATALOG.get(key, {})
    return {**base, "fields": meta.get("fields", []), "frequency": meta.get("frequency", "—"), "db_table": meta.get("db_table", "—")}


@router.get("/api-status")
async def get_api_status():
    sk = settings.service_key

    coros = {
        "nifs_femo":   _check_nifs("femoSeaList",  settings.nifs_api_key_femosealist, {"sdate": WEEK_AGO, "edate": TODAY}),
        "nifs_risa":   _check_nifs("risaList",      settings.nifs_api_key_risalist),
        "nifs_soo":    _check_nifs("sooList",       settings.nifs_api_key_soolist,    {"sdate": WEEK_AGO, "edate": TODAY}),
        "nifs_sois":   _check_nifs("soisSurvey",    settings.nifs_api_key_sois,       {"sdate": WEEK_AGO, "edate": TODAY}),
        "nifs_red":    _check_nifs("redtideList",   settings.nifs_api_key_redtidelist,{"sdate": WEEK_AGO, "edate": TODAY}),
        "koem_stn":    _check_data_go_kr(
                           "http://apis.data.go.kr/B553931/service/OceansNemoInfoService1/getOceansNemoInfo1", sk),
        "mof_temp15":  _check_data_go_kr(
                           "http://apis.data.go.kr/1192000/apVhdService_Tgcw15/getOpnTgcw15", sk,
                           {"numOfRows": "1", "pageNo": "1", "analsYmd": YESTERDAY}),
        "mof_salt15":  _check_data_go_kr(
                           "http://apis.data.go.kr/1192000/apVhdService_Tgcsy15/getOpnTgcsy15", sk,
                           {"numOfRows": "1", "pageNo": "1", "analsYmd": YESTERDAY[:6]}),
        "mof_tempd1":  _check_data_go_kr(
                           "http://apis.data.go.kr/1192000/apVhdService_Tgpw15d1/getOpnTgpw15d1", sk,
                           {"numOfRows": "1", "pageNo": "1", "gridCd": "GR2_G1E23"}),
        "kma_asos_hr": _check_data_go_kr(
                           "http://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList", sk,
                           {"dataType": "JSON", "dataCd": "ASOS", "dateCd": "HR",
                            "startDt": YESTERDAY, "startHh": "00", "endDt": YESTERDAY, "endHh": "01",
                            "stnIds": "165"}),
        "kma_asos_day":_check_data_go_kr(
                           "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList", sk,
                           {"dataType": "JSON", "dataCd": "ASOS", "dateCd": "DAY",
                            "startDt": WEEK_AGO, "endDt": YESTERDAY, "stnIds": "165"}),
        "kma_fcst":    _check_data_go_kr(
                           "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst", sk,
                           {"dataType": "JSON", "base_date": TODAY, "base_time": "0600",
                            "nx": "58", "ny": "74"}),
        "krc_dam":     _check_data_go_kr(
                           "http://apis.data.go.kr/B500001/dam/sluicePresentCondition/hourlist", sk,
                           {"_type": "json", "damcode": "1001001",
                            "stdt": YESTERDAY[:4]+"-"+YESTERDAY[4:6]+"-"+YESTERDAY[6:],
                            "eddt": YESTERDAY[:4]+"-"+YESTERDAY[4:6]+"-"+YESTERDAY[6:]}),
    }

    results = dict(zip(coros.keys(), await asyncio.gather(*coros.values(), return_exceptions=True)))

    def _r(key: str) -> dict:
        v = results.get(key, {})
        if isinstance(v, Exception):
            return {"ok": False, "status_code": None, "message": str(v), "item_count": 0}
        return v

    rows = [
        # ── 국립수산과학원 ──
        {"key": "nifs_femo",   "name": "어장환경관측자료",       "provider": "국립수산과학원", "env_var": "NIFS_API_KEY_femoSeaList",  "priority": "최우선", "desc": "DIN·DIP·수온·염분·DO — 황백화 핵심 데이터",         **_r("nifs_femo")},
        {"key": "nifs_risa",   "name": "실시간어장정보",         "provider": "국립수산과학원", "env_var": "NIFS_API_KEY_risaList",     "priority": "최우선", "desc": "30분 단위 실시간 수온 모니터링",                      **_r("nifs_risa")},
        {"key": "nifs_soo",    "name": "정선해양관측정보",       "provider": "국립수산과학원", "env_var": "NIFS_API_KEY_sooList",      "priority": "높음",   "desc": "수온·염분·DO·영양염 장기 기준선",                     **_r("nifs_soo")},
        {"key": "nifs_sois",   "name": "위성해양영상정보",       "provider": "국립수산과학원", "env_var": "NIFS_API_KEY_sois",         "priority": "중간",   "desc": "클로로필·해색 이상 위성 영상 메타",                   **_r("nifs_sois")},
        {"key": "nifs_red",    "name": "적조정보",               "provider": "국립수산과학원", "env_var": "NIFS_API_KEY_redtideList",  "priority": "선택",   "desc": "적조 발생 보조 지표",                                 **_r("nifs_red")},
        # ── 해양환경공단 ──
        {"key": "koem_obs",    "name": "해양환경측정망 관측",    "provider": "해양환경공단",   "env_var": "ServiceKey",               "priority": "최우선", "desc": "수온·DO·DIN·DIP·WQI 실시간 — URL 공식 확인 필요",    **_pending("엔드포인트 URL 미정 (data.go.kr Swagger 확인 필요)")},
        {"key": "koem_stn",    "name": "해양환경측정망 정점조회","provider": "해양환경공단",   "env_var": "ServiceKey",               "priority": "높음",   "desc": "관측소 위치 마스터 (PostGIS 매칭용)",                  **_r("koem_stn")},
        # ── 해양수산부 ──
        {"key": "mof_temp15",  "name": "연속정보 수온 15분",     "provider": "해양수산부",     "env_var": "ServiceKey",               "priority": "높음",   "desc": "격자 기반 15분 수온 — 대시보드 실시간 보완",          **_r("mof_temp15")},
        {"key": "mof_salt15",  "name": "연속정보 염분 15분",     "provider": "해양수산부",     "env_var": "ServiceKey",               "priority": "높음",   "desc": "담수 유입·염분 급변 모니터링",                        **_r("mof_salt15")},
        {"key": "mof_tempd1",  "name": "해수면 수온 D+1 예측",  "provider": "해양수산부",     "env_var": "ServiceKey",               "priority": "중간",   "desc": "다음날 수온 예측 — 사전 위험 알림용",                 **_r("mof_tempd1")},
        {"key": "mof_farm",    "name": "공동활용 어장정보",      "provider": "해양수산부",     "env_var": "ServiceKey",               "priority": "높음",   "desc": "양식장 위치·면적·면허 마스터",                        **_pending("엔드포인트 URL 미정 (CSV 다운로드 또는 OpenAPI 확인 필요)")},
        # ── 기상청 ──
        {"key": "kma_asos_hr", "name": "기상청 ASOS 시간자료",  "provider": "기상청",         "env_var": "ServiceKey",               "priority": "높음",   "desc": "강수량·기온·풍속 시간자료 (목포 165 기준)",           **_r("kma_asos_hr")},
        {"key": "kma_asos_day","name": "기상청 ASOS 일자료",    "provider": "기상청",         "env_var": "ServiceKey",               "priority": "높음",   "desc": "7/14/30일 누적 강수량 Feature 생성용",               **_r("kma_asos_day")},
        {"key": "kma_fcst",    "name": "기상청 단기예보",        "provider": "기상청",         "env_var": "ServiceKey",               "priority": "중간",   "desc": "강수·기온·풍속 예보 — nx=58, ny=74 (전남 해역)",     **_r("kma_fcst")},
        # ── 한국수자원공사 ──
        {"key": "krc_dam",     "name": "수문 운영 정보",         "provider": "한국수자원공사", "env_var": "ServiceKey",               "priority": "높음",   "desc": "방류량·유입량·저수율 — damcode 대상 댐 설정 필요",    **_r("krc_dam")},
        # ── 조위관측소 ──
        {"key": "khoa_tide",   "name": "조위관측소 관측데이터",  "provider": "국립해양조사원", "env_var": "ServiceKey",               "priority": "보류",   "desc": "조위·수온·염분·유속 — 2026년 대체 API 확인 필요",    **_pending("API 폐기/대체 여부 확인 필요")},
    ]

    return [_with_meta(row["key"], row) for row in rows]


@router.get("/api-sample/{api_key}")
async def get_api_sample(api_key: str):
    """각 API의 실제 샘플 데이터 1건 조회"""
    sk = settings.service_key
    try:
        if api_key == "nifs_femo":
            return await _fetch_sample_nifs("femoSeaList", settings.nifs_api_key_femosealist, {"sdate": WEEK_AGO, "edate": TODAY})
        if api_key == "nifs_risa":
            return await _fetch_sample_nifs("risaList", settings.nifs_api_key_risalist)
        if api_key == "nifs_soo":
            return await _fetch_sample_nifs("sooList", settings.nifs_api_key_soolist, {"sdate": WEEK_AGO, "edate": TODAY})
        if api_key == "nifs_sois":
            return await _fetch_sample_nifs("soisSurvey", settings.nifs_api_key_sois, {"sdate": WEEK_AGO, "edate": TODAY})
        if api_key == "nifs_red":
            return await _fetch_sample_nifs("redtideList", settings.nifs_api_key_redtidelist, {"sdate": WEEK_AGO, "edate": TODAY})
        if api_key == "koem_stn":
            return await _fetch_sample_data_go_kr(
                "http://apis.data.go.kr/B553931/service/OceansNemoInfoService1/getOceansNemoInfo1", sk)
        if api_key == "mof_temp15":
            return await _fetch_sample_data_go_kr(
                "http://apis.data.go.kr/1192000/apVhdService_Tgcw15/getOpnTgcw15", sk,
                {"numOfRows": "3", "pageNo": "1", "analsYmd": YESTERDAY})
        if api_key == "mof_salt15":
            return await _fetch_sample_data_go_kr(
                "http://apis.data.go.kr/1192000/apVhdService_Tgcsy15/getOpnTgcsy15", sk,
                {"numOfRows": "3", "pageNo": "1", "analsYmd": YESTERDAY[:6]})
        if api_key == "mof_tempd1":
            return await _fetch_sample_data_go_kr(
                "http://apis.data.go.kr/1192000/apVhdService_Tgpw15d1/getOpnTgpw15d1", sk,
                {"numOfRows": "3", "pageNo": "1", "gridCd": "GR2_G1E23"})
        if api_key == "kma_asos_hr":
            return await _fetch_sample_data_go_kr(
                "http://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList", sk,
                {"dataType": "JSON", "dataCd": "ASOS", "dateCd": "HR",
                 "startDt": YESTERDAY, "startHh": "00", "endDt": YESTERDAY, "endHh": "03", "stnIds": "165"})
        if api_key == "kma_asos_day":
            return await _fetch_sample_data_go_kr(
                "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList", sk,
                {"dataType": "JSON", "dataCd": "ASOS", "dateCd": "DAY",
                 "startDt": WEEK_AGO, "endDt": YESTERDAY, "stnIds": "165"})
        if api_key == "kma_fcst":
            return await _fetch_sample_data_go_kr(
                "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst", sk,
                {"dataType": "JSON", "base_date": TODAY, "base_time": "0600", "nx": "58", "ny": "74"})
        if api_key == "krc_dam":
            return await _fetch_sample_data_go_kr(
                "http://apis.data.go.kr/B500001/dam/sluicePresentCondition/hourlist", sk,
                {"_type": "json", "damcode": "1001001",
                 "stdt": YESTERDAY[:4]+"-"+YESTERDAY[4:6]+"-"+YESTERDAY[6:],
                 "eddt": YESTERDAY[:4]+"-"+YESTERDAY[4:6]+"-"+YESTERDAY[6:]})
        return {"error": f"알 수 없는 api_key: {api_key}"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/collect/nifs")
async def trigger_nifs_collect():
    from data_pipeline.collectors import nifs_collector
    try:
        saved = await nifs_collector.collect_and_save()
        return {"status": "ok", "saved": saved}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/collect/nifs/raw")
async def nifs_raw_response():
    key = settings.nifs_api_key_risalist
    params = {"id": "risaList", "key": key}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get("https://www.nifs.go.kr/OpenAPI_json", params=params)
    return {"status_code": resp.status_code, "body": resp.json()}
