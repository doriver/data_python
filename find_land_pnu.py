# 실거래가(토지 매매) 데이터의 마스킹된 번지를 토지특성정보 SHP와 대조하여
# PNU/전체지번을 찾아 추가하는 스크립트. (docs/find_land.md 참고)
#
# 입력
#   data/raw/xlsx/20250806_20260805_토지(매매)_실거래가.xlsx : 번지가 마스킹된 실거래가
#   data/basis/AL_D194_41450_20260520.shp                   : 토지특성정보(SHP)
#
# 매칭 기준: 시군구(읍면동), 산여부, 지번 앞자리+자릿수, 지목, 용도지역
#           (+ 지분구분이 빈값인 경우에만 계약면적)
#
# 출력
#   data/processed/20250806_20260805_토지(매매)_실거래가_PNU매칭.xlsx
#     - 원본 컬럼 + PNU, 전체지번, 매칭결과 컬럼
#     - "요약" 시트에 전체/성공/실패 건수
import os
import re
import sys

import geopandas as gpd
import pandas as pd

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

XLSX_PATH = "data/raw/xlsx/20250806_20260805_토지(매매)_실거래가.xlsx"
SHP_PATH = "data/basis/AL_D194_41450_20260520.shp"
OUTPUT_DIR = "data/processed"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "20250806_20260805_토지(매매)_실거래가_PNU매칭.xlsx")

# 실거래가 엑셀은 상단 12줄이 안내문구/검색조건이고 13번째 줄(0-based 12)이 헤더다.
XLSX_HEADER_ROW = 12

# 계약면적과 토지특성정보 면적(A12) 비교 시 허용 오차(㎡)
AREA_TOLERANCE = 0.01

# 마스킹된 번지 패턴: (산)? + (앞자리 숫자 1개)? + (마스킹 *)?  예) "산4*", "3**", "2*", "*"
BEONJI_PATTERN = re.compile(r"^(산)?(\d)?(\*+)?$")


def parse_masked_beonji(value: str):
    """마스킹된 번지 문자열에서 산여부, 본번 앞자리, 본번 자릿수를 추출한다."""
    match = BEONJI_PATTERN.match(value)
    if not match:
        raise ValueError(f"인식할 수 없는 번지 형식: {value!r}")
    is_mountain = match.group(1) == "산"
    first_digit = match.group(2)
    masked = match.group(3) or ""
    digit_count = (1 if first_digit else 0) + len(masked)
    return is_mountain, first_digit, digit_count


def load_trade_data() -> pd.DataFrame:
    df = pd.read_excel(XLSX_PATH, header=XLSX_HEADER_ROW)
    parsed = df["번지"].apply(parse_masked_beonji)
    df["_산여부"] = parsed.apply(lambda t: t[0])
    df["_본번앞자리"] = parsed.apply(lambda t: t[1])
    df["_본번자릿수"] = parsed.apply(lambda t: t[2])
    return df


def load_land_characteristics() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(SHP_PATH, encoding="cp949")
    gdf = gdf[["A1", "A3", "A5", "A6", "A11", "A12", "A14"]].copy()
    gdf.rename(
        columns={
            "A1": "pnu",
            "A3": "bjdong_name",
            "A5": "mountain_name",
            "A6": "bonbun_busan",
            "A11": "land_category",
            "A12": "area",
            "A14": "use_district_name",
        },
        inplace=True,
    )
    gdf["mountain"] = gdf["mountain_name"] == "산"
    bonbun = gdf["bonbun_busan"].str.split("-").str[0]
    gdf["bonbun_first_digit"] = bonbun.str[0]
    gdf["bonbun_digit_count"] = bonbun.str.len()
    gdf["full_jibun"] = gdf["mountain_name"].where(gdf["mountain"], "") + gdf["bonbun_busan"]
    return gdf


def build_candidate_index(gdf: gpd.GeoDataFrame) -> dict:
    """(법정동명, 산여부, 지번자릿수, 지번앞자리, 지목, 용도지역) -> 후보 행 목록"""
    index: dict = {}
    for row in gdf.itertuples(index=False):
        key = (
            row.bjdong_name,
            row.mountain,
            row.bonbun_digit_count,
            row.bonbun_first_digit,
            row.land_category,
            row.use_district_name,
        )
        index.setdefault(key, []).append(row)
    return index


def find_match(row, index: dict):
    key = (
        row["시군구"],
        row["_산여부"],
        row["_본번자릿수"],
        row["_본번앞자리"],
        row["지목"],
        row["용도지역"],
    )
    candidates = index.get(key, [])

    # 지분구분이 빈값일 때만 계약면적이 토지 전체 면적을 의미하므로 면적으로 추가 필터링한다.
    if pd.isna(row["지분구분"]):
        candidates = [
            c for c in candidates if abs(c.area - row["계약면적"]) < AREA_TOLERANCE
        ]

    if len(candidates) == 1:
        match = candidates[0]
        return match.pnu, match.full_jibun
    return None, None


def main():
    print("실거래가 데이터 로드 중...")
    trades = load_trade_data()
    print(f"실거래가 전체 건수: {len(trades)}")

    print("토지특성정보(SHP) 로드 중...")
    land = load_land_characteristics()
    print(f"토지특성정보 전체 건수: {len(land)}")

    index = build_candidate_index(land)

    pnu_list = []
    jibun_list = []
    for _, row in trades.iterrows():
        pnu, jibun = find_match(row, index)
        pnu_list.append(pnu)
        jibun_list.append(jibun)

    trades["PNU"] = pnu_list
    trades["전체지번"] = jibun_list
    trades["매칭결과"] = ["성공" if p else "실패" for p in pnu_list]

    trades.drop(columns=["_산여부", "_본번앞자리", "_본번자릿수"], inplace=True)

    total = len(trades)
    failed = int((trades["매칭결과"] == "실패").sum())
    succeeded = total - failed
    print(f"매칭 완료: 전체 {total}건 / 성공 {succeeded}건 / 실패 {failed}건")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary = pd.DataFrame(
        {"항목": ["전체 건수", "성공 건수", "실패 건수"], "값": [total, succeeded, failed]}
    )
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        trades.to_excel(writer, sheet_name="실거래가_PNU매칭", index=False)
        summary.to_excel(writer, sheet_name="요약", index=False)

        # PNU는 19자리 숫자로만 구성돼 있어 재오픈 시 지수표기로 오인되지 않도록 텍스트 서식을 강제한다.
        sheet = writer.sheets["실거래가_PNU매칭"]
        pnu_col_idx = trades.columns.get_loc("PNU") + 1
        for cell in sheet.iter_rows(
            min_row=2, max_row=len(trades) + 1, min_col=pnu_col_idx, max_col=pnu_col_idx
        ):
            cell[0].number_format = "@"

    print(f"저장 완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
