# 토지(매매) 실거래가 매핑 xlsx를 읽어 MySQL에 적재하는 스크립트
#
# 프로젝트 루트의 .env 파일에서 접속 정보를 읽습니다 (.env.example 참고).
#   MYSQL_USER, MYSQL_PASSWORD  (필수)
#   MYSQL_HOST (기본값 127.0.0.1), MYSQL_PORT (기본값 3307), MYSQL_DATABASE (기본값 data01)
#
# PNU가 채워진(매칭 성공) 행만 저장한다. 거래된 토지 테이블은 pnu 1건당 1행이고,
# 거래상세 테이블은 거래 1건당 1행이다 (같은 필지가 여러 번 거래된 경우
# 거래된 토지에는 최초 1건만 insert하고, 거래상세는 traded_land_id를 통해
# 해당 토지 행을 참조하며 거래마다 insert한다).
import math
import os
import sys

import pandas as pd
import pymysql
from dotenv import load_dotenv

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

XLSX_PATH = "data/processed/20250806_20260805_토지(매매)_실거래가_매핑.xlsx"
HEADER_ROW = 5  # 실제 표 헤더가 있는 엑셀 행(0-index)
LAND_TABLE_NAME = "traded_land"
DETAIL_TABLE_NAME = "traded_land_detail"
INSERT_BATCH_SIZE = 200

DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ["MYSQL_USER"]
DB_PASSWORD = os.environ["MYSQL_PASSWORD"]
DB_NAME = os.environ.get("MYSQL_DATABASE", "data01")

CREATE_LAND_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {LAND_TABLE_NAME} (
    id BIGINT NOT NULL AUTO_INCREMENT,
    pnu VARCHAR(20) NOT NULL,
    sigungu VARCHAR(100) NOT NULL,
    beonji VARCHAR(20) NULL,
    land_category VARCHAR(20) NULL,
    use_district VARCHAR(50) NULL,
    road_condition VARCHAR(20) NULL,
    cancellation_date VARCHAR(20) NULL,
    confirmed_beonji VARCHAR(20) NULL,
    PRIMARY KEY (id),
    INDEX idx_pnu (pnu)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_DETAIL_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {DETAIL_TABLE_NAME} (
    id BIGINT NOT NULL AUTO_INCREMENT,
    traded_land_id BIGINT NOT NULL,
    pnu VARCHAR(20) NOT NULL,
    contract_year_month CHAR(6) NOT NULL,
    contract_day TINYINT UNSIGNED NOT NULL,
    contract_area DECIMAL(12,2) NULL,
    transaction_amount BIGINT NULL,
    share_type VARCHAR(20) NULL,
    transaction_type VARCHAR(20) NULL,
    brokerage_location VARCHAR(100) NULL,
    PRIMARY KEY (id),
    INDEX idx_traded_land_id (traded_land_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

INSERT_LAND_SQL = f"""
INSERT INTO {LAND_TABLE_NAME}
    (pnu, sigungu, beonji, land_category, use_district,
     road_condition, cancellation_date, confirmed_beonji)
VALUES
    (%s, %s, %s, %s, %s,
     %s, %s, %s)
"""

INSERT_DETAIL_SQL = f"""
INSERT INTO {DETAIL_TABLE_NAME}
    (traded_land_id, pnu, contract_year_month, contract_day, contract_area,
     transaction_amount, share_type, transaction_type, brokerage_location)
VALUES
    (%s, %s, %s, %s, %s,
     %s, %s, %s, %s)
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


df = pd.read_excel(XLSX_PATH, header=HEADER_ROW, dtype={"PNU": str})
df = df.rename(columns={"거래금액(만원)": "거래금액"})

matched = df[df["PNU"].notna()].copy()
skipped = len(df) - len(matched)
print(f"전체 행 수: {len(df)}, PNU 매칭된 행 수: {len(matched)}, 스킵(PNU 없음): {skipped}")

land_rows = []
detail_rows = []
pnu_seen = set()
for row in matched.itertuples(index=False):
    pnu = row.PNU
    if pnu not in pnu_seen:
        pnu_seen.add(pnu)
        land_rows.append(
            (
                pnu,
                row.시군구,
                none_if_dash(row.번지),
                none_if_dash(row.지목),
                none_if_dash(row.용도지역),
                none_if_dash(row.도로조건),
                none_if_dash(row.해제사유발생일),
                none_if_dash(row.확정번지),
            )
        )
    detail_rows.append(
        (
            pnu,
            f"{row.계약년월}",
            int(row.계약일),
            none_if_dash(row.계약면적),
            parse_amount(none_if_dash(row.거래금액)),
            none_if_dash(row.지분구분),
            none_if_dash(row.거래유형),
            none_if_dash(row.중개사소재지),
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
        cursor.execute(CREATE_LAND_TABLE_SQL)
        cursor.execute(CREATE_DETAIL_TABLE_SQL)
        conn.commit()

        # 거래된 토지: pnu -> traded_land.id
        pnu_to_land_id = {}
        inserted_land = 0
        for i, r in enumerate(land_rows, start=1):
            cursor.execute(INSERT_LAND_SQL, r)
            pnu_to_land_id[r[0]] = cursor.lastrowid
            inserted_land += 1
            if i % INSERT_BATCH_SIZE == 0:
                conn.commit()
                print(f"거래된 토지 삽입 진행: {inserted_land}/{len(land_rows)}")
        conn.commit()
        print(f"거래된 토지 삽입 완료: {inserted_land}/{len(land_rows)}")

        # 거래상세: 위에서 확보한 traded_land_id를 채워 넣는다.
        detail_params = [
            (pnu_to_land_id[d[0]], *d) for d in detail_rows
        ]
        inserted_detail = 0
        for i in range(0, len(detail_params), INSERT_BATCH_SIZE):
            batch = detail_params[i : i + INSERT_BATCH_SIZE]
            cursor.executemany(INSERT_DETAIL_SQL, batch)
            conn.commit()
            inserted_detail += len(batch)
            print(f"거래상세 삽입 진행: {inserted_detail}/{len(detail_params)}")

    print(f"완료: 거래된 토지 {inserted_land}건, 거래상세 {inserted_detail}건 삽입 (스킵 {skipped}건)")
finally:
    conn.close()
