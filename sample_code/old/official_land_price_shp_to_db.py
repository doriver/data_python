# geopandas로 SHP(개별공시지가) 데이터를 읽어 MySQL에 적재하는 스크립트
#
# 프로젝트 루트의 .env 파일에서 접속 정보를 읽습니다 (.env.example 참고).
#   MYSQL_USER, MYSQL_PASSWORD  (필수)
#   MYSQL_HOST (기본값 127.0.0.1), MYSQL_PORT (기본값 3307), MYSQL_DATABASE (기본값 data01)
import os
import sys

import geopandas as gpd
import pymysql
from dotenv import load_dotenv

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

SHP_PATH = "shp/AL_D152_11_20260520.shp"
TABLE_NAME = "official_land_price_seoul"
INSERT_BATCH_SIZE = 500

DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ["MYSQL_USER"]
DB_PASSWORD = os.environ["MYSQL_PASSWORD"]
DB_NAME = os.environ.get("MYSQL_DATABASE", "data01")

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id BIGINT NOT NULL AUTO_INCREMENT,
    pnu VARCHAR(19) NOT NULL,
    bjdong_name VARCHAR(100) NOT NULL,
    jibun VARCHAR(20) NOT NULL,
    ledger_division_name VARCHAR(20) NOT NULL,
    coordinates POINT NOT NULL SRID 4326,
    official_land_price BIGINT NOT NULL,
    area DECIMAL(12,2) NOT NULL,
    land_category VARCHAR(20) NOT NULL,
    use_district_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    SPATIAL INDEX idx_coordinates (coordinates)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

INSERT_SQL = f"""
INSERT INTO {TABLE_NAME}
    (pnu, bjdong_name, jibun, ledger_division_name, coordinates,
     official_land_price, area, land_category, use_district_name)
VALUES
    (%s, %s, %s, %s, ST_SRID(POINT(%s, %s), 4326), %s, %s, %s, %s)
"""

# SHP 파일 읽기
gdf = gpd.read_file(SHP_PATH, encoding="cp949")
# 위경도(EPSG:4326/WGS84) 좌표계로 변환
gdf = gdf.to_crs(epsg=4326)

print(f"좌표계(CRS): {gdf.crs}")
print(f"전체 레코드 수: {len(gdf)}")

rows = []
for _, row in gdf.iterrows():
    centroid = row.geometry.centroid
    rows.append(
        (
            row["A0"],
            row["A2"],
            row["A5"],
            row["A4"],
            centroid.x,
            centroid.y,
            row["A9"],
            row["A14"],
            row["A13"],
            row["A16"],
        )
    )

conn = pymysql.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    charset="utf8mb4",
)
try:
    with conn.cursor() as cursor:
        cursor.execute(CREATE_TABLE_SQL)

        inserted = 0
        for i in range(0, len(rows), INSERT_BATCH_SIZE):
            batch = rows[i : i + INSERT_BATCH_SIZE]
            cursor.executemany(INSERT_SQL, batch)
            inserted += len(batch)
            print(f"삽입 진행: {inserted}/{len(rows)}")

    conn.commit()
    print(f"완료: {inserted}건 삽입")
finally:
    conn.close()