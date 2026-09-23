# 단독다가구 실거래가 매핑 xlsx를 읽어 MySQL에 적재하는 스크립트
#
# 프로젝트 루트의 .env 파일에서 접속 정보를 읽습니다 (.env.example 참고).
#   MYSQL_USER, MYSQL_PASSWORD  (필수)
#   MYSQL_HOST (기본값 127.0.0.1), MYSQL_PORT (기본값 3307), MYSQL_DATABASE (기본값 data02)
#
# data/processed 안의 "*_좌표.xlsx"(add_coordinate_nationwide.py 결과물과 동일한
# 형식의 단독다가구용 결과물) 전체를 훑어 적재한다.
#
# PNU가 채워진(매칭 성공) 행만 저장한다. (pnu, 연면적, 대장pk) 조합이
# 처음 등장할 때만 traded_house/house_mapping_building에 insert하고, 같은 조합이
# 다시 나오면 traded_house_detail에만 insert한다 (거래 1건당 1행). 건축년도는 결측치가 있어 dedup 키에서 제외했다(같은 건물이 건축년도 결측 여부만으로 쪼개지는 것을 방지).
#
# 총괄표제 존재여부가 O인 경우 대장pk가 콤마로 구분된 여러 값일 수 있으며, 이때
# house_mapping_building에는 값마다 개별 행으로 저장한다. 대장pk가 없는 행은
# house_mapping_building에 매핑 행을 만들지 않는다.
import glob
import math
import os
import sys

import pandas as pd
import pymysql
from dotenv import load_dotenv

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

XLSX_DIR = "data/processed"
XLSX_GLOB = "*_좌표.xlsx"
HEADER_ROW = 5  # 실제 표 헤더가 있는 엑셀 행(0-index)
HOUSE_TABLE_NAME = "traded_house"
DETAIL_TABLE_NAME = "traded_house_detail"
MAPPING_TABLE_NAME = "house_mapping_building"
INSERT_BATCH_SIZE = 200

DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ["MYSQL_USER"]
DB_PASSWORD = os.environ["MYSQL_PASSWORD"]
DB_NAME = os.environ.get("MYSQL_DATABASE", "data02")

CREATE_HOUSE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {HOUSE_TABLE_NAME} (
    id BIGINT NOT NULL AUTO_INCREMENT,
    pnu VARCHAR(20) NOT NULL,
    sigungu VARCHAR(100) NOT NULL,
    beonji VARCHAR(20) NULL,
    house_type VARCHAR(20) NULL,
    road_condition VARCHAR(20) NULL,
    total_floor_area DECIMAL(12,2) NULL,
    site_area DECIMAL(12,2) NULL,
    built_year SMALLINT NULL,
    road_name VARCHAR(100) NULL,
    confirmed_beonji VARCHAR(20) NULL,
    has_overall_title BOOLEAN NOT NULL,
    land_area DECIMAL(12,2) NULL,
    official_land_price BIGINT NULL,
    coordinates POINT NOT NULL SRID 4326,
    PRIMARY KEY (id),
    INDEX idx_pnu (pnu),
    SPATIAL INDEX idx_coordinates (coordinates)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_DETAIL_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {DETAIL_TABLE_NAME} (
    id BIGINT NOT NULL AUTO_INCREMENT,
    traded_house_id BIGINT NOT NULL,
    pnu VARCHAR(20) NOT NULL,
    contract_year_month CHAR(6) NOT NULL,
    contract_day TINYINT UNSIGNED NOT NULL,
    transaction_amount BIGINT NULL,
    buyer VARCHAR(100) NULL,
    seller VARCHAR(100) NULL,
    transaction_type VARCHAR(20) NULL,
    brokerage_location VARCHAR(100) NULL,
    PRIMARY KEY (id),
    INDEX idx_traded_house_id (traded_house_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_MAPPING_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {MAPPING_TABLE_NAME} (
    id BIGINT NOT NULL AUTO_INCREMENT,
    traded_house_id BIGINT NOT NULL,
    building_pk VARCHAR(30) NULL,
    PRIMARY KEY (id),
    INDEX idx_traded_house_id (traded_house_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

INSERT_HOUSE_SQL = f"""
INSERT INTO {HOUSE_TABLE_NAME}
    (pnu, sigungu, beonji, house_type, road_condition,
     total_floor_area, site_area, built_year, road_name, confirmed_beonji,
     has_overall_title, land_area, official_land_price, coordinates)
VALUES
    (%s, %s, %s, %s, %s,
     %s, %s, %s, %s, %s,
     %s, %s, %s, ST_SRID(POINT(%s, %s), 4326))
"""

INSERT_DETAIL_SQL = f"""
INSERT INTO {DETAIL_TABLE_NAME}
    (traded_house_id, pnu, contract_year_month, contract_day,
     transaction_amount, buyer, seller, transaction_type, brokerage_location)
VALUES
    (%s, %s, %s, %s,
     %s, %s, %s, %s, %s)
"""

INSERT_MAPPING_SQL = f"""
INSERT INTO {MAPPING_TABLE_NAME}
    (traded_house_id, building_pk)
VALUES
    (%s, %s)
"""


def none_if_dash(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value.strip() == "-":
        return None
    return value


def parse_amount(value):
    if value is None:
        return None
    return int(str(value).replace(",", ""))


def zero_if_missing(value):
    # 좌표 매칭 실패(SHP에서 PNU를 못 찾은 경우) 시 (0, 0)으로 대체 저장한다.
    if value is None:
        return 0
    if isinstance(value, float) and math.isnan(value):
        return 0
    return value


# 대장pk를 콤마로 분리해 개별 값 리스트로 반환한다. 값이 없으면 빈 리스트를 반환한다.
def split_building_pks(value):
    cleaned = none_if_dash(value)
    if cleaned is None:
        return []
    return [pk.strip() for pk in str(cleaned).split(",") if pk.strip()]


xlsx_paths = sorted(glob.glob(os.path.join(XLSX_DIR, XLSX_GLOB)))
if not xlsx_paths:
    print(f"처리할 xlsx 파일이 없습니다: {os.path.join(XLSX_DIR, XLSX_GLOB)}")
    sys.exit(0)

house_rows = []
detail_rows = []
mapping_by_key = {}
key_seen = set()
total_count = 0
total_skipped = 0
total_no_coord = 0

for xlsx_path in xlsx_paths:
    df = pd.read_excel(xlsx_path, header=HEADER_ROW, dtype={"PNU": str, "대장pk": str})
    df = df.rename(
        columns={
            "거래금액(만원)": "거래금액",
            "연면적(㎡)": "연면적",
            "대지면적(㎡)": "대지면적",
            "총괄표제 존재여부": "총괄표제존재여부",
        }
    )

    matched = df[df["PNU"].notna()].copy()
    skipped = len(df) - len(matched)
    no_coord = matched["경도x"].isna().sum()
    total_count += len(df)
    total_skipped += skipped
    total_no_coord += no_coord
    print(
        f"[{os.path.basename(xlsx_path)}] 전체 행 수: {len(df)}, PNU 매칭된 행 수: {len(matched)}, "
        f"스킵(PNU 없음): {skipped}, 좌표 없음(0,0으로 저장): {no_coord}"
    )

    for row in matched.itertuples(index=False):
        pnu = row.PNU
        floor_area = none_if_dash(row.연면적)
        building_pk_raw = none_if_dash(row.대장pk)
        key = (pnu, floor_area, building_pk_raw)

        if key not in key_seen:
            key_seen.add(key)
            built_year = none_if_dash(row.건축년도)
            house_rows.append(
                (
                    key,
                    pnu,
                    row.시군구,
                    none_if_dash(row.번지),
                    none_if_dash(row.주택유형),
                    none_if_dash(row.도로조건),
                    floor_area,
                    none_if_dash(row.대지면적),
                    int(built_year) if built_year is not None else None,
                    none_if_dash(row.도로명),
                    none_if_dash(row.확정번지),
                    row.총괄표제존재여부 == "O",
                    none_if_dash(row.토지면적),
                    none_if_dash(row.공시지가),
                    zero_if_missing(row.경도x),
                    zero_if_missing(row.위도y),
                )
            )
            mapping_by_key[key] = split_building_pks(building_pk_raw)

        detail_rows.append(
            (
                key,
                pnu,
                f"{row.계약년월}",
                int(row.계약일),
                parse_amount(none_if_dash(row.거래금액)),
                none_if_dash(row.매수자),
                none_if_dash(row.매도자),
                none_if_dash(row.거래유형),
                none_if_dash(row.중개사소재지),
            )
        )

print(
    f"\n=== 전체 {len(xlsx_paths)}개 파일 취합 ===\n"
    f"총 행 수: {total_count}, 고유 (pnu,연면적,대장pk) 수(거래된 주택) 수: {len(house_rows)}, "
    f"거래상세 행 수: {len(detail_rows)}, 총 스킵(PNU 없음): {total_skipped}, 총 좌표 없음: {total_no_coord}"
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
        cursor.execute(CREATE_HOUSE_TABLE_SQL)
        cursor.execute(CREATE_DETAIL_TABLE_SQL)
        cursor.execute(CREATE_MAPPING_TABLE_SQL)
        conn.commit()

        # 거래된 주택: (pnu,연면적,대장pk) -> traded_house.id
        key_to_house_id = {}
        inserted_house = 0
        for i, r in enumerate(house_rows, start=1):
            key, r = r[0], r[1:]
            cursor.execute(INSERT_HOUSE_SQL, r)
            key_to_house_id[key] = cursor.lastrowid
            inserted_house += 1
            if i % INSERT_BATCH_SIZE == 0:
                conn.commit()
                print(f"거래된 주택 삽입 진행: {inserted_house}/{len(house_rows)}")
        conn.commit()
        print(f"거래된 주택 삽입 완료: {inserted_house}/{len(house_rows)}")

        # 건물 매핑: 대장pk가 콤마로 구분된 경우 값마다 개별 행으로 저장한다.
        mapping_params = [
            (key_to_house_id[key], pk)
            for key, pks in mapping_by_key.items()
            for pk in pks
        ]
        inserted_mapping = 0
        for i in range(0, len(mapping_params), INSERT_BATCH_SIZE):
            batch = mapping_params[i : i + INSERT_BATCH_SIZE]
            cursor.executemany(INSERT_MAPPING_SQL, batch)
            conn.commit()
            inserted_mapping += len(batch)
            print(f"건물 매핑 삽입 진행: {inserted_mapping}/{len(mapping_params)}")

        # 거래상세: 위에서 확보한 traded_house_id를 채워 넣는다.
        detail_params = [
            (key_to_house_id[d[0]], *d[1:]) for d in detail_rows
        ]
        inserted_detail = 0
        for i in range(0, len(detail_params), INSERT_BATCH_SIZE):
            batch = detail_params[i : i + INSERT_BATCH_SIZE]
            cursor.executemany(INSERT_DETAIL_SQL, batch)
            conn.commit()
            inserted_detail += len(batch)
            print(f"거래상세 삽입 진행: {inserted_detail}/{len(detail_params)}")

    print(
        f"완료: 거래된 주택 {inserted_house}건, 건물 매핑 {inserted_mapping}건, "
        f"거래상세 {inserted_detail}건 삽입 (스킵 {total_skipped}건)"
    )
finally:
    conn.close()
