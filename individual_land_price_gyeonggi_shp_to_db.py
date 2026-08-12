# geopandas로 SHP(경기도 개별공시지가/지목) 데이터를 읽어 MySQL에 적재하는 스크립트
#
# 프로젝트 루트의 .env 파일에서 접속 정보를 읽습니다 (.env.example 참고).
#   MYSQL_USER, MYSQL_PASSWORD  (필수)
#   MYSQL_HOST (기본값 127.0.0.1), MYSQL_PORT (기본값 3307), MYSQL_DATABASE (기본값 data01)
#
# A13(토지면적)이 없는 행은 geometry에서 계산한 면적(area_sqm)으로 대체한다.
# 면적은 반드시 원본 투영좌표계(EPSG:5186, 미터 단위)에서 계산해야 하므로
# to_crs(epsg=4326) 변환 전에 미리 계산해 둔다 (shpHandling.py 참고).
import math
import os
import pickle
import sys

import geopandas as gpd
import pymysql
from dotenv import load_dotenv

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

SHP_PATH = "data/AL_D150_41_20260526(2).shp"
TABLE_NAME = "individual_land_price_gyeonggi"
INSERT_BATCH_SIZE = 2000
# 삽입에 실패한 행을 모아두는 파일. --retry-failed 로 실행하면 이 파일에 있는 행만 재시도한다.
FAILED_ROWS_PATH = f"data/processed/{TABLE_NAME}_failed_rows.pkl"

DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ["MYSQL_USER"]
DB_PASSWORD = os.environ["MYSQL_PASSWORD"]
DB_NAME = os.environ.get("MYSQL_DATABASE", "data01")

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id BIGINT NOT NULL AUTO_INCREMENT,
    pnu VARCHAR(20) NOT NULL,
    bjdong_code CHAR(10) NOT NULL,
    bjdong_name VARCHAR(100) NULL,
    ledger_division_code CHAR(1) NOT NULL,
    ledger_division_name VARCHAR(20) NULL,
    jibun VARCHAR(20) NULL,
    jibun_category_mark VARCHAR(20) NOT NULL,
    base_year CHAR(4) NULL,
    base_month CHAR(2) NULL,
    official_land_price BIGINT NULL,
    is_standard_lot TINYINT(1) NULL,
    land_category_code CHAR(2) NULL,
    land_category VARCHAR(20) NULL,
    area DECIMAL(12,2) NOT NULL,
    data_base_date DATE NOT NULL,
    sigungu_code CHAR(5) NOT NULL,
    coordinates POINT NOT NULL SRID 4326,
    PRIMARY KEY (id),
    SPATIAL INDEX idx_coordinates (coordinates)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

INSERT_SQL = f"""
INSERT INTO {TABLE_NAME}
    (pnu, bjdong_code, bjdong_name, ledger_division_code, ledger_division_name,
     jibun, jibun_category_mark, base_year, base_month, official_land_price,
     is_standard_lot, land_category_code, land_category, area, data_base_date,
     sigungu_code, coordinates)
VALUES
    (%s, %s, %s, %s, %s,
     %s, %s, %s, %s, %s,
     %s, %s, %s, %s, %s,
     %s, ST_SRID(POINT(%s, %s), 4326))
"""


def none_if_nan(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


# --retry-failed 로 실행하면 SHP를 다시 읽지 않고, 이전 실행에서 실패한 행만 불러와 재시도한다.
retry_only = "--retry-failed" in sys.argv

if retry_only:
    if not os.path.exists(FAILED_ROWS_PATH):
        print(f"재시도할 실패 데이터 파일이 없습니다: {FAILED_ROWS_PATH}")
        sys.exit(1)
    with open(FAILED_ROWS_PATH, "rb") as f:
        rows = pickle.load(f)
    print(f"재시도 대상 실패 데이터 건수: {len(rows)}")
else:
    # SHP 파일 읽기
    gdf = gpd.read_file(SHP_PATH, encoding="cp949")
    # 면적(㎡)은 미터 단위 원본 좌표계에서 계산해야 정확함 (위경도 변환 후 계산하면 값이 왜곡됨)
    gdf["area_sqm"] = gdf.geometry.area
    # 위경도(EPSG:4326/WGS84) 좌표계로 변환
    gdf = gdf.to_crs(epsg=4326)

    print(f"좌표계(CRS): {gdf.crs}")
    print(f"전체 레코드 수: {len(gdf)}")

    rows = []
    for _, row in gdf.iterrows():
        centroid = row.geometry.centroid
        area = row["A13"] if not (isinstance(row["A13"], float) and math.isnan(row["A13"])) else row["area_sqm"]
        is_standard_lot = none_if_nan(row["A10"])
        if is_standard_lot is not None:
            is_standard_lot = int(is_standard_lot)
        official_land_price = none_if_nan(row["A9"])
        if official_land_price is not None:
            official_land_price = int(official_land_price)

        rows.append(
            (
                row["A0"],
                row["A1"],
                none_if_nan(row["A2"]),
                row["A3"],
                none_if_nan(row["A4"]),
                none_if_nan(row["A5"]),
                row["A6"],
                none_if_nan(row["A7"]),
                none_if_nan(row["A8"]),
                official_land_price,
                is_standard_lot,
                none_if_nan(row["A11"]),
                none_if_nan(row["A12"]),
                round(area, 2),
                row["A14"].date(),
                row["A15"],
                centroid.x,
                centroid.y,
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
        failed_rows = []
        for i in range(0, len(rows), INSERT_BATCH_SIZE):
            batch = rows[i : i + INSERT_BATCH_SIZE]
            try:
                cursor.executemany(INSERT_SQL, batch)
                conn.commit()
                inserted += len(batch)
            except pymysql.MySQLError as e:
                # 배치 전체가 실패하면 롤백 후 행 단위로 재시도해서, 문제 없는 행은 살리고
                # 진짜 문제가 있는 행만 failed_rows 에 모아 추후 재시도할 수 있게 한다.
                conn.rollback()
                print(f"배치 삽입 실패, 행 단위로 재시도: {e}")
                for r in batch:
                    try:
                        cursor.execute(INSERT_SQL, r)
                        conn.commit()
                        inserted += 1
                    except pymysql.MySQLError as row_e:
                        conn.rollback()
                        print(f"행 삽입 실패: {row_e}")
                        failed_rows.append(r)
            print(f"삽입 진행: {inserted}/{len(rows)} (실패 {len(failed_rows)}건)")

    if failed_rows:
        os.makedirs(os.path.dirname(FAILED_ROWS_PATH), exist_ok=True)
        with open(FAILED_ROWS_PATH, "wb") as f:
            pickle.dump(failed_rows, f)
        print(f"실패 {len(failed_rows)}건을 {FAILED_ROWS_PATH} 에 저장했습니다. --retry-failed 로 재시도하세요.")
    elif os.path.exists(FAILED_ROWS_PATH):
        os.remove(FAILED_ROWS_PATH)

    print(f"완료: {inserted}건 삽입")
finally:
    conn.close()
