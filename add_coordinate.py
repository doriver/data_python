# xlsx 데이터에 PNU를 기준으로 SHP에서 얻은 좌표(centroid)를 추가하는 스크립트.
# docs/좌표 추가.md 의 지시를 그대로 구현한다.
import os
import sys

import geopandas as gpd
import pandas as pd

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

XLSX_PATH = "data/raw/서울25년_토지(매매)_실거래가_26매핑.xlsx"
SHP_PATH = "data/basis/AL_D002_11_20260104.shp"
SHP_ENCODING = "cp949"
SHP_PNU_FIELD = "A1"  # 이 SHP는 필드 A1이 PNU
HEADER_ROW = 5  # 실제 표 헤더가 있는 엑셀 행(0-index)
OUTPUT_DIR = "data/processed"
_xlsx_name, _xlsx_ext = os.path.splitext(os.path.basename(XLSX_PATH))
OUTPUT_PATH = os.path.join(OUTPUT_DIR, f"{_xlsx_name}_좌표{_xlsx_ext}")
DATA_START_ROW = 5  # 0-index. 상단 요약 행 + 빈 줄을 남기고 그 아래부터 표 작성


def main():
    deals = pd.read_excel(XLSX_PATH, header=HEADER_ROW, dtype={"PNU": str})
    total_count = len(deals)
    pnu_count = deals["PNU"].notna().sum()
    print(f"전체 행 수: {total_count}, PNU 있는 행 수: {pnu_count}")

    # SHP 파일 읽기. 원본(투영) 좌표계에서 representative_point(폴리곤 내부가 보장되는 점)를
    # 구한 뒤, 그 점만 위경도(EPSG:4326/WGS84) 좌표계로 변환한다.
    # centroid(무게중심)는 오목한 필지에서 폴리곤 밖으로 벗어날 수 있어 사용하지 않는다.
    gdf = gpd.read_file(SHP_PATH, encoding=SHP_ENCODING)
    print(f"SHP 레코드 수: {len(gdf)}, 원본 좌표계(CRS): {gdf.crs}")

    point = gdf.geometry.representative_point()
    point_4326 = point.to_crs(epsg=4326)
    lon_by_pnu = pd.Series(point_4326.x.values, index=gdf[SHP_PNU_FIELD])
    lat_by_pnu = pd.Series(point_4326.y.values, index=gdf[SHP_PNU_FIELD])

    deals["경도x"] = deals["PNU"].map(lon_by_pnu)
    deals["위도y"] = deals["PNU"].map(lat_by_pnu)

    matched_count = deals.loc[deals["PNU"].notna(), "경도x"].notna().sum()
    print(f"좌표 매칭 성공 건수: {matched_count} / {pnu_count}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        deals.to_excel(writer, sheet_name="실거래가", index=False, startrow=DATA_START_ROW)
        sheet = writer.sheets["실거래가"]
        sheet["A1"] = f"전체 건수: {total_count}"
        sheet["A2"] = f"PNU 있는 행 수: {pnu_count}"
        sheet["A3"] = f"좌표 매칭 성공 건수: {matched_count}"

    print(f"완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
