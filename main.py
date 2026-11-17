"""
IA626 Big Data - ADSB API assignment
Author: sibandb

A Flask API over the ADSB data in `class_datapoints`.

Endpoints (all GET, all require ?key=123):
    /getData               ?start=&end=        datapoints between two dates (max 500)
    /countInPolygon        ?polygon=x y,x y,.. number of datapoints inside a polygon
    /getAvgSpeedByFlight   [?start=&end=]      average ground speed per flight (max 500)

Every response has the top-level keys: code (1 = success, 0 = failed), msg, req, sqltime.
Every request (successful or not) is written to the log table `sibandb_logs`.
API keys are stored in `sibandb_auth`. Run setup_tables.py once to create both tables.
"""
import json
import time
import datetime
import decimal

import pymysql
import yaml
from flask import Flask, request, Response

app = Flask(__name__)

with open("config.yml", "r") as file:
    db_config = yaml.safe_load(file)["mysql"]

USERNAME = "sibandb"
AUTH_TABLE = f"{USERNAME}_auth"
LOG_TABLE = f"{USERNAME}_logs"
MAX_ROWS = 500
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")


# --------------------------------------------------------------------------- helpers
def get_conn():
    return pymysql.connect(**db_config, cursorclass=pymysql.cursors.DictCursor)


def to_json_value(v):
    """Convert MySQL types that json.dumps cannot handle."""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray)):
        return None  # raw geometry blobs; the WKT version is returned instead
    return v


def clean_row(row):
    return {k: to_json_value(v) for k, v in row.items() if not isinstance(v, (bytes, bytearray))}


def parse_date(value):
    """Return a normalised 'YYYY-MM-DD HH:MM:SS' string, or None if invalid."""
    if value is None:
        return None
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(value, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return None


def parse_polygon(value):
    """Turn 'x y,x y,...' into WKT. Returns (wkt, error_message)."""
    if not value:
        return None, "polygon must be provided as a list of 'x y' points separated by commas"
    points = []
    for pair in value.split(","):
        parts = pair.split()
        if len(parts) != 2:
            return None, f"invalid point '{pair.strip()}' - each point must be 'x y'"
        try:
            x, y = float(parts[0]), float(parts[1])
        except ValueError:
            return None, f"invalid point '{pair.strip()}' - coordinates must be numeric"
        points.append((x, y))
    if points[0] != points[-1]:
        points.append(points[0])  # close the ring automatically
    if len(points) < 4:
        return None, "polygon needs at least 3 distinct points"
    ring = ",".join(f"{x} {y}" for x, y in points)
    return f"POLYGON(({ring}))", None


def auth(token):
    if token is None:
        return False
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT `id` FROM `{AUTH_TABLE}` WHERE `token` = %s AND `active` = 1;", (token,))
            return len(cur.fetchall()) == 1
    finally:
        conn.close()


def log(token, endpoint, params, http_status, code, msg, sqltime):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO `{LOG_TABLE}` (`endpoint`,`token`,`params`,`http_status`,`code`,`msg`,`sqltime`,`ip`,`dt`) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (endpoint, token, json.dumps(params), http_status, code, str(msg)[:255], sqltime,
                 request.remote_addr, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
        conn.commit()
        conn.close()
    except Exception as e:  # logging must never break the API
        print("log error:", e)


def respond(res, http_status=200):
    """Log the request and return the JSON response."""
    res.setdefault("sqltime", 0)
    log(request.args.get("key"), res["req"], request.args.to_dict(), http_status,
        res["code"], res["msg"], res["sqltime"])
    return Response(json.dumps(res, indent=4), status=http_status, mimetype="application/json")


def fail(res, msg, http_status=400):
    res["code"] = 0
    res["msg"] = msg
    return respond(res, http_status)


def run_query(sql, params):
    """Run a query and return (rows, seconds_taken)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            t0 = time.time()
            cur.execute(sql, params)
            rows = cur.fetchall()
            return rows, round(time.time() - t0, 6)
    finally:
        conn.close()


def new_res(req):
    return {"code": 0, "msg": "", "req": req, "sqltime": 0}


@app.errorhandler(Exception)
def handle_error(e):
    """Return any unexpected error as JSON instead of an HTML error page."""
    res = {"code": 0, "msg": f"server error: {e}", "req": request.path.strip("/"), "sqltime": 0}
    return Response(json.dumps(res, indent=4), status=500, mimetype="application/json")


# --------------------------------------------------------------------------- endpoints
@app.route("/", methods=["GET"])
def root():
    res = new_res("/")
    return fail(res, "No endpoint specified. Use /getData, /countInPolygon or /getAvgSpeedByFlight", 404)


@app.route("/getData", methods=["GET"])
def get_data():
    res = new_res("getData")
    if not auth(request.args.get("key")):
        return fail(res, "auth error: invalid or missing key", 401)

    start = parse_date(request.args.get("start"))
    end = parse_date(request.args.get("end"))
    if start is None or end is None:
        return fail(res, "start and end are required, format YYYY-MM-DD HH:MM:SS")
    if start > end:
        return fail(res, "start must be before end")

    sql = ("SELECT *, ST_AsText(`geo_point`) AS `geo_point_wkt` FROM `class_datapoints` "
           "WHERE `date_time` BETWEEN %s AND %s ORDER BY `date_time` LIMIT %s;")
    try:
        rows, res["sqltime"] = run_query(sql, (start, end, MAX_ROWS))
    except Exception as e:
        return fail(res, f"database error: {e}", 500)

    res["code"] = 1
    res["msg"] = "ok"
    res["start"] = start
    res["end"] = end
    res["num_results"] = len(rows)
    res["results"] = [clean_row(r) for r in rows]
    return respond(res)


@app.route("/countInPolygon", methods=["GET"])
def count_in_polygon():
    res = new_res("countInPolygon")
    if not auth(request.args.get("key")):
        return fail(res, "auth error: invalid or missing key", 401)

    wkt, err = parse_polygon(request.args.get("polygon"))
    if err:
        return fail(res, err)

    sql = ("SELECT COUNT(*) AS `cnt` FROM `class_datapoints` "
           "WHERE ST_Within(`geo_point`, ST_GeomFromText(%s, 0));")
    try:
        rows, res["sqltime"] = run_query(sql, (wkt,))
    except Exception as e:
        return fail(res, f"database error: {e}", 500)

    res["code"] = 1
    res["msg"] = "ok"
    res["polygon"] = wkt
    res["count"] = int(rows[0]["cnt"])
    return respond(res)


@app.route("/getAvgSpeedByFlight", methods=["GET"])
def get_avg_speed_by_flight():
    res = new_res("getAvgSpeedByFlight")
    if not auth(request.args.get("key")):
        return fail(res, "auth error: invalid or missing key", 401)

    raw_start, raw_end = request.args.get("start"), request.args.get("end")
    start, end = parse_date(raw_start), parse_date(raw_end)
    if raw_start is not None and start is None:
        return fail(res, "start must be in format YYYY-MM-DD HH:MM:SS")
    if raw_end is not None and end is None:
        return fail(res, "end must be in format YYYY-MM-DD HH:MM:SS")
    if start and end and start > end:
        return fail(res, "start must be before end")

    where, params = [], []
    if start:
        where.append("`date_time` >= %s")
        params.append(start)
    if end:
        where.append("`date_time` <= %s")
        params.append(end)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = (f"SELECT `flight_num`, AVG(`gs`) AS `avg_speed`, COUNT(*) AS `num_points` "
           f"FROM `class_datapoints` {where_sql} "
           f"GROUP BY `flight_num` ORDER BY `flight_num` LIMIT %s;")
    params.append(MAX_ROWS)
    try:
        rows, res["sqltime"] = run_query(sql, tuple(params))
    except Exception as e:
        return fail(res, f"database error: {e}", 500)

    res["code"] = 1
    res["msg"] = "ok"
    res["start"] = start
    res["end"] = end
    res["num_results"] = len(rows)
    res["results"] = [
        {"flight_num": r["flight_num"],
         "avg_speed": round(float(r["avg_speed"]), 2) if r["avg_speed"] is not None else None,
         "num_points": int(r["num_points"])}
        for r in rows
    ]
    return respond(res)


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
