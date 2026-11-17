"""
One-time setup: creates the auth and log tables (prefixed with my username)
and inserts the API key 123.  Run:  python setup_tables.py
"""
import pymysql
import yaml

with open("config.yml", "r") as file:
    db_config = yaml.safe_load(file)["mysql"]

USERNAME = "sibandb"

conn = pymysql.connect(**db_config)
cur = conn.cursor()

cur.execute(f"""
CREATE TABLE IF NOT EXISTS `{USERNAME}_auth` (
    `id`      INT AUTO_INCREMENT PRIMARY KEY,
    `token`   VARCHAR(64) NOT NULL UNIQUE,
    `owner`   VARCHAR(64),
    `active`  TINYINT(1) NOT NULL DEFAULT 1,
    `created` DATETIME DEFAULT CURRENT_TIMESTAMP
);""")

cur.execute(f"""
CREATE TABLE IF NOT EXISTS `{USERNAME}_logs` (
    `id`          INT AUTO_INCREMENT PRIMARY KEY,
    `endpoint`    VARCHAR(64),
    `token`       VARCHAR(64),
    `params`      TEXT,
    `http_status` INT,
    `code`        TINYINT,
    `msg`         VARCHAR(255),
    `sqltime`     DOUBLE,
    `ip`          VARCHAR(45),
    `dt`          DATETIME
);""")

cur.execute(f"INSERT IGNORE INTO `{USERNAME}_auth` (`token`,`owner`) VALUES (%s,%s);", ("123", USERNAME))
conn.commit()

cur.execute(f"SELECT * FROM `{USERNAME}_auth`;")
print("auth table:", cur.fetchall())
conn.close()
print("Tables ready.")
