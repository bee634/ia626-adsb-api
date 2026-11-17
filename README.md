# IA626 – ADSB Flight Data API (Flask + MySQL)

A Flask web service over the ADSB data stored in the `class_datapoints` table.
Author: **sibandb**

## Files

| File | Purpose |
|---|---|
| `main.py` | The Flask API (all three endpoints, auth, logging) |
| `test_client.py` | Test client – calls every endpoint with good and bad inputs and prints PASS/FAIL |
| `setup_tables.py` | One-time script that creates `sibandb_auth` and `sibandb_logs` and adds key `123` |
| `schemas.json` | Proposed JSON Schema (draft-07) for each endpoint's response |
| `config.example.yml` | Template for the database credentials (copy to `config.yml`) |

## Setup

```bash
pip install flask pymysql pyyaml requests
cp config.example.yml config.yml      # then fill in the password
python setup_tables.py                # creates the auth + log tables, inserts key 123
python main.py                        # API on http://127.0.0.1:5000
python test_client.py                 # in a second terminal
```

## Endpoints

Base URL: `http://127.0.0.1:5000`. All endpoints are `GET` and need `key=123`.

| Endpoint | Parameters | What it returns |
|---|---|---|
| `/getData` | `key`, `start`, `end` (both required) | Datapoints between `start` and `end`, ordered by time, max 500 |
| `/countInPolygon` | `key`, `polygon` = `x y,x y,...` | Number of datapoints inside the polygon (ring auto-closed if needed) |
| `/getAvgSpeedByFlight` | `key`, `start`, `end` (both optional) | Average ground speed (`AVG(gs)`) per flight, max 500 |

Example calls:

```
/getData?key=123&start=2022-11-23 05:28:10&end=2022-11-23 05:28:15
/countInPolygon?key=123&polygon=-74 42,-75 39,-74 41,-74 42
/getAvgSpeedByFlight?key=123&start=2022-11-23 05:00:00&end=2022-11-23 08:00:00
```

Dates are `YYYY-MM-DD HH:MM:SS` (also accepts `YYYY-MM-DD HH:MM` and `YYYY-MM-DD`).

## Response format

Every response contains:

| Key | Meaning |
|---|---|
| `code` | `1` = success, `0` = request failed |
| `msg` | `ok`, or why the request failed |
| `req` | The method requested (`getData`, `countInPolygon`, `getAvgSpeedByFlight`) |
| `sqltime` | Seconds the SQL query took, measured with `time.time()` (0 if no query ran) |

Plus endpoint-specific keys (`results`, `num_results`, `count`, …) – see `schemas.json`.

Example – `/countInPolygon?key=123&polygon=-74 42,-75 39,-74 41,-74 42`

```json
{
    "code": 1,
    "msg": "ok",
    "req": "countInPolygon",
    "sqltime": 0.004999,
    "polygon": "POLYGON((-74.0 42.0,-75.0 39.0,-74.0 41.0,-74.0 42.0))",
    "count": 518
}
```

Example – wrong key

```json
{
    "code": 0,
    "msg": "auth error: invalid or missing key",
    "req": "getData",
    "sqltime": 0
}
```

HTTP status codes are set too: 200 OK, 400 bad parameters, 401 bad key, 500 database error.

## Auth and logging

* **`sibandb_auth`** – `id, token, owner, active, created`. A request is allowed only if its `key`
  matches an active token (key `123` is inserted by `setup_tables.py`).
* **`sibandb_logs`** – `id, endpoint, token, params, http_status, code, msg, sqltime, ip, dt`.
  Every request is logged, including failed and unauthorised ones.

## Notes

* All SQL uses parameterised queries (`%s`), including the polygon WKT, so user input can't inject SQL.
* `geo_point` is a binary geometry column, so `/getData` returns it as WKT text in `geo_point_wkt`.
