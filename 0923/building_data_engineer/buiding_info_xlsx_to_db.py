# 건물정보(대장pk 1건당 1행) 마스터 xlsx를 읽어 MySQL에 적재하는 스크립트
#
# 프로젝트 루트의 .env 파일에서 접속 정보를 읽습니다 (.env.example 참고).
#   MYSQL_USER, MYSQL_PASSWORD  (필수)
#   MYSQL_HOST (기본값 127.0.0.1), MYSQL_PORT (기본값 3307), MYSQL_DATABASE (기본값 data02)
#
# data/processed 안의 "*건물정보.xlsx" (find_general_building.py의 일반건물_건물정보.xlsx,
# find_house_buillding.py의 단독다가구_건물정보.xlsx) 전체를 훑어 적재한다. 두 파일 모두
# 1행에 통계 요약, 2행은 빈 줄, 3행부터 표가 시작하는 동일한 레이아웃이라 header=2로 읽는다.
#
# building_pk(대장pk)를 고유하게 저장한다. 같은 건물이 일반건물/단독다가구 두 파일에
# 걸쳐 중복 등장하는 경우가 있어(예: 총 11건), 전체 파일을 통틀어 처음 등장한 행만
# 저장하고 이후 중복은 건너뛴다.
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
XLSX_GLOB = "*건물정보.xlsx"
HEADER_ROW = 2  # 실제 표 헤더가 있는 엑셀 행(0-index)
TABLE_NAME = "building_info"
INSERT_BATCH_SIZE = 200

DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ["MYSQL_USER"]
DB_PASSWORD = os.environ["MYSQL_PASSWORD"]
DB_NAME = os.environ.get("MYSQL_DATABASE", "data02")

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id BIGINT NOT NULL AUTO_INCREMENT,
    building_pk VARCHAR(30) NOT NULL,
    address VARCHAR(255) NOT NULL,
    building_name VARCHAR(100) NULL,
    dong_name VARCHAR(50) NULL,
    ledger_site_area DECIMAL(12,2) NULL,
    building_area DECIMAL(12,2) NULL,
    ledger_total_floor_area DECIMAL(12,2) NULL,
    building_coverage_ratio DECIMAL(8,2) NULL,
    floor_area_ratio DECIMAL(8,2) NULL,
    floor_area_ratio_calc_area DECIMAL(12,2) NULL,
    main_structure VARCHAR(50) NULL,
    main_use VARCHAR(50) NULL,
    main_roof VARCHAR(50) NULL,
    above_ground_floors SMALLINT NULL,
    underground_floors SMALLINT NULL,
    approval_date CHAR(8) NULL,
    PRIMARY KEY (id),
    UNIQUE INDEX idx_building_pk (building_pk)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

INSERT_SQL = f"""
INSERT INTO {TABLE_NAME}
    (building_pk, address, building_name, dong_name,
     ledger_site_area, building_area, ledger_total_floor_area,
     building_coverage_ratio, floor_area_ratio, floor_area_ratio_calc_area,
     main_structure, main_use, main_roof,
     above_ground_floors, underground_floors, approval_date)
VALUES
    (%s, %s, %s, %s,
     %s, %s, %s,
     %s, %s, %s,
     %s, %s, %s,
     %s, %s, %s)
"""


def none_if_dash(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value.strip() == "-":
        return None
    return value


xlsx_paths = sorted(glob.glob(os.path.join(XLSX_DIR, XLSX_GLOB)))
if not xlsx_paths:
    print(f"처리할 xlsx 파일이 없습니다: {os.path.join(XLSX_DIR, XLSX_GLOB)}")
    sys.exit(0)

building_rows = []
pk_seen = set()
total_count = 0
total_skipped = 0

for xlsx_path in xlsx_paths:
    df = pd.read_excel(xlsx_path, header=HEADER_ROW, dtype={"대장pk": str})
    df = df.rename(
        columns={
            "대장상 대지면적(㎡)": "대장상대지면적",
            "건축면적(㎡)": "건축면적",
            "대장상 연면적(㎡)": "대장상연면적",
            "건폐율(%)": "건폐율",
            "용적률(%)": "용적률",
            "용적률산정연면적(㎡)": "용적률산정연면적",
        }
    )

    total_count += len(df)
    file_skipped = 0
    for row in df.itertuples(index=False):
        building_pk = row.대장pk
        if building_pk in pk_seen:
            file_skipped += 1
            continue
        pk_seen.add(building_pk)

        above_ground_floors = none_if_dash(row.지상층수)
        underground_floors = none_if_dash(row.지하층수)
        building_rows.append(
            (
                building_pk,
                row.지번주소,
                none_if_dash(row.건물명),
                none_if_dash(row.동명),
                none_if_dash(row.대장상대지면적),
                none_if_dash(row.건축면적),
                none_if_dash(row.대장상연면적),
                none_if_dash(row.건폐율),
                none_if_dash(row.용적률),
                none_if_dash(row.용적률산정연면적),
                none_if_dash(row.주구조),
                none_if_dash(row.주용도),
                none_if_dash(row.주지붕),
                int(above_ground_floors) if above_ground_floors is not None else None,
                int(underground_floors) if underground_floors is not None else None,
                none_if_dash(row.사용승인일),
            )
        )

    total_skipped += file_skipped
    print(
        f"[{os.path.basename(xlsx_path)}] 전체 행 수: {len(df)}, 중복(다른 파일과 building_pk 겹침) 스킵: {file_skipped}"
    )

print(
    f"\n=== 전체 {len(xlsx_paths)}개 파일 취합 ===\n"
    f"총 행 수: {total_count}, 고유 building_pk 수: {len(building_rows)}, 총 스킵(중복): {total_skipped}"
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
        conn.commit()

        inserted = 0
        for i in range(0, len(building_rows), INSERT_BATCH_SIZE):
            batch = building_rows[i : i + INSERT_BATCH_SIZE]
            cursor.executemany(INSERT_SQL, batch)
            conn.commit()
            inserted += len(batch)
            print(f"건물정보 삽입 진행: {inserted}/{len(building_rows)}")

    print(f"완료: 건물정보 {inserted}건 삽입 (스킵 {total_skipped}건)")
finally:
    conn.close()
