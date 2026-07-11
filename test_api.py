import asyncio, httpx, sys, json
from datetime import datetime, timedelta
from urllib.parse import quote
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")
from app.config import settings

key = settings.service_key
nifs_soo_key = settings.nifs_api_key_soolist

async def test_nifs_soolist():
    print("[NIFS sooList - 정선해양관측]")
    print(f"  key: {nifs_soo_key[:20]}...")
    # NIFS OpenAPI 방식
    params = {"id": "sooList", "key": nifs_soo_key}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
        r = await c.get("https://www.nifs.go.kr/OpenAPI_json", params=params)
        print(f"  STATUS: {r.status_code}")
        try:
            data = r.json()
            body = data.get("body") or data.get("Body") or data
            items = body.get("item") or data.get("Item") or []
            if isinstance(items, dict): items = [items]
            print(f"  ITEMS: {len(items)}")
            if items:
                print(f"  KEYS: {list(items[0].keys())}")
                print(f"  SAMPLE: {str(items[0])[:500]}")
            else:
                print(f"  FULL RESP KEYS: {list(data.keys())}")
                print(f"  BODY: {str(body)[:300]}")
        except:
            print(f"  RAW: {r.text[:400]}")

async def test_nifs_soolist_with_date():
    print("[NIFS sooList - 날짜 파라미터 시도]")
    end = datetime.now()
    start = end - timedelta(days=365)
    for params in [
        {"id": "sooList", "key": nifs_soo_key, "sdate": start.strftime("%Y%m%d"), "edate": end.strftime("%Y%m%d")},
        {"id": "sooList", "key": nifs_soo_key, "year": str(end.year)},
        {"id": "sooList", "key": nifs_soo_key, "sdate": "20250101", "edate": "20251231"},
    ]:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
            r = await c.get("https://www.nifs.go.kr/OpenAPI_json", params=params)
            data = r.json() if r.status_code == 200 else {}
            body = data.get("body") or data.get("Body") or data
            items = body.get("item") or data.get("Item") or []
            if isinstance(items, dict): items = [items]
            param_str = str({k: v for k, v in params.items() if k != 'key'})
            print(f"  {param_str}: {len(items)}건")
            if items:
                print(f"  KEYS: {list(items[0].keys())}")
                print(f"  SAMPLE: {str(items[0])[:400]}")
                break

async def test_koem_obs():
    print("[KOEM 해양환경측정망 - 실측값]")
    # data.go.kr/data/15059973 → 실제 API 엔드포인트 탐색
    endpoints = [
        f"http://apis.data.go.kr/B553931/service/OceansNemoInfoService1/getOceansNemoObsInfo1?pageNo=1&numOfRows=5&ServiceKey={quote(key, safe='')}",
        f"http://apis.data.go.kr/B553931/service/OceansNemoObsService1/getOceansNemoObs1?pageNo=1&numOfRows=5&ServiceKey={quote(key, safe='')}",
        f"http://apis.data.go.kr/1192000/OceansNemoObsService/getOceansNemoObs?pageNo=1&numOfRows=5&ServiceKey={quote(key, safe='')}",
    ]
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
        for url in endpoints:
            r = await c.get(url)
            short = url.split('/')[-1].split('?')[0]
            print(f"  {short}: HTTP {r.status_code} | {r.text[:150]}")

async def main():
    await test_nifs_soolist()
    print()
    await test_nifs_soolist_with_date()
    print()
    await test_koem_obs()

asyncio.run(main())