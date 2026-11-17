"""
Test client for the ADSB API.  Start the API first (python main.py), then run:
    python test_client.py
Each test prints PASS/FAIL plus a short summary of the response.
"""
import json
import requests

BASE = "http://127.0.0.1:5000"
KEY = "123"
REQUIRED_KEYS = {"code", "msg", "req", "sqltime"}

passed = failed = 0


def call(endpoint, params):
    r = requests.get(BASE + endpoint, params=params)
    try:
        return r.status_code, r.json()
    except ValueError:
        print(f"\n!! The API did not return JSON (HTTP {r.status_code}). First part of the reply:")
        print(r.text[:800])
        print("!! Check the terminal window where main.py is running for the full error.\n")
        raise SystemExit(1)


def check(name, endpoint, params, expect_code, extra_check=None):
    global passed, failed
    status, resp = call(endpoint, params)
    ok = REQUIRED_KEYS.issubset(resp) and resp["code"] == expect_code
    if ok and extra_check:
        ok = extra_check(resp)
    if ok:
        passed += 1
    else:
        failed += 1
    summary = {k: resp.get(k) for k in ("code", "msg", "req", "sqltime", "num_results", "count") if k in resp}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  (HTTP {status})  {json.dumps(summary)}")
    return resp


print("=== getData ===")
resp = check("getData valid range", "/getData",
             {"key": KEY, "start": "2022-11-23 05:28:10", "end": "2022-11-23 05:28:15"}, 1,
             lambda r: r["num_results"] == len(r["results"]) <= 500)
if resp.get("results"):
    print("   first row:", json.dumps(resp["results"][0]))
check("getData capped at 500", "/getData",
      {"key": KEY, "start": "2022-11-23 00:00:00", "end": "2022-11-24 00:00:00"}, 1,
      lambda r: r["num_results"] <= 500)
check("getData missing end", "/getData", {"key": KEY, "start": "2022-11-23 05:28:10"}, 0)
check("getData bad date", "/getData", {"key": KEY, "start": "yesterday", "end": "today"}, 0)
check("getData wrong key", "/getData",
      {"key": "999", "start": "2022-11-23 05:28:10", "end": "2022-11-23 05:28:15"}, 0)
check("getData no key", "/getData", {"start": "2022-11-23 05:28:10", "end": "2022-11-23 05:28:15"}, 0)

print("\n=== countInPolygon ===")
check("countInPolygon valid", "/countInPolygon",
      {"key": KEY, "polygon": "-74 42,-75 39,-74 41,-74 42"}, 1,
      lambda r: isinstance(r["count"], int))
check("countInPolygon unclosed ring (auto-closed)", "/countInPolygon",
      {"key": KEY, "polygon": "-74 42,-75 39,-74 41"}, 1)
check("countInPolygon bad polygon", "/countInPolygon", {"key": KEY, "polygon": "abc,def"}, 0)
check("countInPolygon missing polygon", "/countInPolygon", {"key": KEY}, 0)
check("countInPolygon wrong key", "/countInPolygon",
      {"key": "bad", "polygon": "-74 42,-75 39,-74 41,-74 42"}, 0)

print("\n=== getAvgSpeedByFlight ===")
resp = check("getAvgSpeedByFlight with dates", "/getAvgSpeedByFlight",
             {"key": KEY, "start": "2022-11-23 05:00:00", "end": "2022-11-23 08:00:00"}, 1,
             lambda r: r["num_results"] <= 500)
if resp.get("results"):
    print("   first 3:", json.dumps(resp["results"][:3]))
check("getAvgSpeedByFlight no dates (optional)", "/getAvgSpeedByFlight", {"key": KEY}, 1,
      lambda r: r["num_results"] <= 500)
check("getAvgSpeedByFlight start only", "/getAvgSpeedByFlight",
      {"key": KEY, "start": "2022-11-23 05:00:00"}, 1)
check("getAvgSpeedByFlight bad date", "/getAvgSpeedByFlight", {"key": KEY, "start": "nope"}, 0)
check("getAvgSpeedByFlight wrong key", "/getAvgSpeedByFlight", {"key": "abc"}, 0)

print(f"\n{passed} passed, {failed} failed")
