# xlsx 데이터에 PNU를 기준으로 SHP에서 얻은 좌표(centroid)를 추가하는 스크립트.
# 지역(서울/경기/... 등)별로 실거래가(매핑) xlsx와 지적도 SHP가 따로 존재할 수 있고,
# 일부 지역(예: 경기)은 SHP가 용량 문제로 여러 파트로 쪼개져 있을 수 있으므로,
# data/raw, data/basis를 훑어 파일명 접두어(지역명)로 짝을 찾아 지역별로 순회 처리한다.
import gc
import glob
import os
import sys

import geopandas as gpd
import pandas as pd

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

RAW_DIR = "data/raw"
BASIS_DIR = "data/basis"
# find_land_nationwide.py 와 동일한 지역 판별 목록.
REGION_NAMES = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충청북", "충청남", "전북", "전라남", "경상북", "경상남", "제주",
]
SHP_ENCODING = "cp949"
SHP_PNU_FIELD = "A1"  # 지적도 SHP 필드명. 서울/경기 SHP 기준으로 확인됨(다른 지역은 다를 수 있음)
HEADER_ROW = 2  # 5  , find_land(_nationwide)가 만든 "_매핑" xlsx의 실제 표 헤더 행(0-index)
OUTPUT_DIR = "data/processed"
DATA_START_ROW = 5  # 0-index. 상단 요약 행 + 빈 줄을 남기고 그 아래부터 표 작성


def _match_region(filename: str):
    """파일명이 REGION_NAMES 중 하나로 시작하면 그 지역명을 반환한다."""
    for region in REGION_NAMES:
        if filename.startswith(region):
            return region
    return None


def discover_region_files():
    """RAW_DIR의 xlsx와 BASIS_DIR의 shp를 파일명 접두어(지역명) 기준으로 짝짓는다.

    같은 지역의 실거래가(매핑) xlsx는 연도별로 여러 개 있을 수 있으므로 개수 제한 없이 모두 모은다.
    같은 지역의 SHP도 용량 문제로 여러 파트로 쪼개져 있을 수 있으므로(예: 경기_26_지적도(2).shp)
    csv와 달리 지역당 1개로 제한하지 않고 모두 모아 이후 합쳐서 사용한다.
    """
    xlsx_by_region = {}
    for path in glob.glob(os.path.join(RAW_DIR, "*.xlsx")):
        region = _match_region(os.path.basename(path))
        if region is None:
            print(f"건너뜀: 지역명을 알 수 없는 실거래가 파일 - {path}")
            continue
        xlsx_by_region.setdefault(region, []).append(path)

    shp_by_region = {}
    for path in glob.glob(os.path.join(BASIS_DIR, "*.shp")):
        region = _match_region(os.path.basename(path))
        if region is None:
            print(f"건너뜀: 지역명을 알 수 없는 지적도 파일 - {path}")
            continue
        shp_by_region.setdefault(region, []).append(path)

    region_files = {}
    for region in xlsx_by_region.keys() | shp_by_region.keys():
        xlsx_paths = xlsx_by_region.get(region)
        shp_paths = shp_by_region.get(region)
        if not xlsx_paths or not shp_paths:
            print(f"건너뜀: '{region}' 지역은 xlsx/shp 짝이 없음 (xlsx={xlsx_paths}, shp={shp_paths})")
            continue
        region_files[region] = (xlsx_paths, shp_paths)
    return region_files


def _load_coord_by_pnu(region: str, shp_paths: list) -> tuple:
    """지역의 SHP 파트들을 모두 읽어 PNU -> (경도, 위도) Series 쌍으로 합친다.

    파트마다 원본(투영) 좌표계에서 representative_point(폴리곤 내부가 보장되는 점)를
    구한 뒤, 그 점만 위경도(EPSG:4326/WGS84) 좌표계로 변환한다.
    centroid(무게중심)는 오목한 필지에서 폴리곤 밖으로 벗어날 수 있어 사용하지 않는다.
    """
    lon_parts = []
    lat_parts = []
    for shp_path in shp_paths:
        # geometry 계산에 필요한 PNU 필드만 읽어 불필요한 속성 컬럼 로딩을 피한다.
        gdf = gpd.read_file(shp_path, encoding=SHP_ENCODING, columns=[SHP_PNU_FIELD])
        print(f"[{region}] {os.path.basename(shp_path)} 레코드 수: {len(gdf)}, 원본 좌표계(CRS): {gdf.crs}")

        point = gdf.geometry.representative_point()
        point_4326 = point.to_crs(epsg=4326)
        lon_parts.append(pd.Series(point_4326.x.values, index=gdf[SHP_PNU_FIELD]))
        lat_parts.append(pd.Series(point_4326.y.values, index=gdf[SHP_PNU_FIELD]))
        del gdf, point, point_4326

    lon_by_pnu = pd.concat(lon_parts)
    lat_by_pnu = pd.concat(lat_parts)
    # 파트 여러 개를 합쳤을 때 PNU가 겹치는 경우, 첫 번째 값만 남긴다.
    dup = lon_by_pnu.index.duplicated()
    if dup.any():
        print(f"[{region}] SHP 파트 간 중복 PNU {dup.sum()}건 발견 - 첫 값 사용")
        lon_by_pnu = lon_by_pnu[~dup]
        lat_by_pnu = lat_by_pnu[~dup]
    print(f"[{region}] 전체 지적도 레코드 수(파트 {len(shp_paths)}개 합산): {len(lon_by_pnu)}")

    return lon_by_pnu, lat_by_pnu


def _add_coordinates_and_write(region: str, xlsx_path: str, lon_by_pnu: pd.Series, lat_by_pnu: pd.Series) -> dict:
    deals = pd.read_excel(xlsx_path, header=HEADER_ROW, dtype={"PNU": str})
    total_count = len(deals)
    pnu_count = deals["PNU"].notna().sum()
    print(f"[{region}] {os.path.basename(xlsx_path)} 전체 행 수: {total_count}, PNU 있는 행 수: {pnu_count}")

    deals["경도x"] = deals["PNU"].map(lon_by_pnu)
    deals["위도y"] = deals["PNU"].map(lat_by_pnu)

    matched_count = deals.loc[deals["PNU"].notna(), "경도x"].notna().sum()
    print(f"[{region}] {os.path.basename(xlsx_path)} 좌표 매칭 성공 건수: {matched_count} / {pnu_count}")

    _xlsx_name, _xlsx_ext = os.path.splitext(os.path.basename(xlsx_path))
    output_path = os.path.join(OUTPUT_DIR, f"{_xlsx_name}_좌표{_xlsx_ext}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        deals.to_excel(writer, sheet_name="실거래가", index=False, startrow=DATA_START_ROW)
        sheet = writer.sheets["실거래가"]
        sheet["A1"] = f"전체 건수: {total_count}"
        sheet["A2"] = f"PNU 있는 행 수: {pnu_count}"
        sheet["A3"] = f"좌표 매칭 성공 건수: {matched_count}"
        success_rate = matched_count / pnu_count if pnu_count else 0
        sheet["F3"] = f"좌표 매칭 성공률: {success_rate:.1%}"

    print(f"[{region}] 완료: {output_path}")

    return {
        "region": region,
        "file": os.path.basename(xlsx_path),
        "xlsx": xlsx_path,
        "total": total_count,
        "pnu": pnu_count,
        "matched": matched_count,
        "success_rate": success_rate,
        "output": output_path,
    }


def process_region_group(region: str, xlsx_paths: list, shp_paths: list) -> list:
    """같은 지역의 xlsx 여러 개가 좌표 매핑을 공유하므로, SHP는 지역당 한 번만 읽는다."""
    lon_by_pnu, lat_by_pnu = _load_coord_by_pnu(region, shp_paths)

    summaries = []
    for xlsx_path in xlsx_paths:
        try:
            summaries.append(_add_coordinates_and_write(region, xlsx_path, lon_by_pnu, lat_by_pnu))
        except Exception as e:
            print(f"[{region}] {xlsx_path} 좌표 추가 실패로 건너뜀: {e}")

    # 이 지역의 좌표 매핑(lon_by_pnu/lat_by_pnu)은 다음 지역 처리 전에 해제한다.
    del lon_by_pnu, lat_by_pnu
    gc.collect()
    return summaries


def main():
    region_files = discover_region_files()
    if not region_files:
        print("처리할 지역 파일 쌍을 찾지 못했습니다.")
        return

    summaries = []
    for region, (xlsx_paths, shp_paths) in region_files.items():
        try:
            summaries.extend(process_region_group(region, xlsx_paths, shp_paths))
        except Exception as e:
            print(f"[{region}] 처리 중 오류로 건너뜀: {e}")

    print("\n=== 전국 좌표 추가 처리 요약 ===")
    for s in summaries:
        print(f"[{s['region']}] {os.path.basename(s['xlsx'])} 매칭 {s['matched']} / {s['pnu']} -> {s['output']}")
    region_count = len(set(s["region"] for s in summaries))
    print(f"전체 처리 파일 수: {len(summaries)} (지역 수: {region_count}), 총 좌표 매칭 성공: {sum(s['matched'] for s in summaries)}")

    # 원본 파일명별 핵심 통계(PNU 있는 행 수, 좌표 매칭 성공 건수, 좌표 매칭 성공률)를
    # 개별 좌표 xlsx를 일일이 열어보지 않고 한눈에 비교할 수 있도록 별도 요약 xlsx로 모아둔다.
    summary_rows = [
        {
            "원본파일명": s["file"],
            "PNU 있는 행 수": s["pnu"],
            "좌표 매칭 성공 건수": s["matched"],
            "좌표 매칭 성공률": f"{s['success_rate']:.1%}",
        }
        for s in summaries
    ]
    if summary_rows:
        avg_success_rate = sum(s["success_rate"] for s in summaries) / len(summaries)
        summary_rows.append({
            "원본파일명": "평균",
            "PNU 있는 행 수": "",
            "좌표 매칭 성공 건수": "",
            "좌표 매칭 성공률": f"{avg_success_rate:.1%}",
        })

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        summary_path = os.path.join(OUTPUT_DIR, "통계_요약_좌표추가.xlsx")
        pd.DataFrame(summary_rows).to_excel(summary_path, sheet_name="통계", index=False)
        print(f"통계 요약 저장: {summary_path}")


if __name__ == "__main__":
    main()
