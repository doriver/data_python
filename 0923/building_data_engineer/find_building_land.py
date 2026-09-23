# 건물 실거래가 데이터(확정번지가 채워진 매핑 결과)에, 토지특성정보 데이터를 대조해
# 해당 건물이 위치한 토지의 PNU(고유번호)/토지면적/공시지가를 채워 넣는 스크립트.
# 지역(서울/경기/... 등)별로 건물 실거래가 xlsx와 토지특성정보 csv가 따로 존재하므로,
# data/raw, data/basis를 훑어 파일명 접두어(지역명 별칭)로 짝을 찾아 지역별로 순회 처리한다.
import gc
import glob
import os
import sys

import pandas as pd

from find_overall_ledger_building import normalize_sigungu

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

RAW_DIR = "data/raw"
BASIS_DIR = "data/basis"
BASIS_CSV_ENCODING = "cp949"
BASIS_USECOLS = ["고유번호", "법정동명", "지번", "대장구분명", "토지면적", "공시지가"]
CSV_CHUNK_SIZE = 200_000
OUTPUT_DIR = "data/processed"

HEADER_ROW = 2  # find_house_buillding.py/find_general_building.py가 저장한 xlsx의 실제 표 헤더 행(0-index)
OUTPUT_SHEET_NAME = "실거래가"
DATA_START_ROW = 2  # 0-index. 1행에 통계 요약, 2행은 빈 줄, 3행부터 표 작성

# 지역별로 실거래가 xlsx(공식 지역명 예: "서울특별시_...")와 토지특성정보 csv(약칭 예: "서울_26_...")의
# 파일명 접두어 표기가 다를 수 있어, 지역마다 매칭 가능한 접두어(별칭)를 여러 개 등록해둔다.
# 예: xlsx는 "충청북도_...", csv는 "충북_26_..." 이므로 "충북" 키에 "충북"/"충청북" 두 별칭을 모두 둔다.
# 약칭과 공식 축약형이 이미 같은 지역(서울/부산/... 등)은 별칭이 하나만 있어도 된다.
REGION_ALIASES = {
    "서울": ["서울"], "부산": ["부산"], "대구": ["대구"], "인천": ["인천"],
    "광주": ["광주"], "대전": ["대전"], "울산": ["울산"], "세종": ["세종"],
    "경기": ["경기"], "강원": ["강원"],
    "충북": ["충북", "충청북"], "충남": ["충남", "충청남"],
    "전북": ["전북", "전라북"], "전남": ["전남", "전라남"],
    "경북": ["경북", "경상북"], "경남": ["경남", "경상남"],
    "제주": ["제주"],
}


"""파일명이 REGION_ALIASES에 등록된 별칭 중 하나로 시작하면 해당 지역 키를 반환한다.

    같은 지역이라도 xlsx(공식 지역명)와 csv(약칭)의 접두어 표기가 다를 수 있어,
    지역 키 하나에 별칭 여러 개를 등록해두고 그중 하나라도 매칭되면 그 지역으로 판별한다.
"""
def _match_region(filename: str):
    for region, aliases in REGION_ALIASES.items():
        if any(filename.startswith(alias) for alias in aliases):
            return region
    return None


"""RAW_DIR의 xlsx와 BASIS_DIR의 csv를 파일명 접두어(지역 별칭) 기준으로 짝짓는다.

    같은 지역의 건물 실거래가(확정번지 매핑 결과) xlsx는 여러 개 있을 수 있으므로 개수 제한 없이
    모두 모으고, 해당 지역의 토지특성정보 csv 1개를 공통으로 매칭해 각 xlsx마다 개별 처리·출력한다.
    xlsx만 있고 csv가 없는 지역(예: 아직 basis csv가 없는 광주/전남)은 건너뛴다.
"""
def discover_region_files():
    xlsx_by_region = {}
    for path in glob.glob(os.path.join(RAW_DIR, "*.xlsx")):
        region = _match_region(os.path.basename(path))
        if region is None:
            print(f"건너뜀: 지역명을 알 수 없는 실거래가 파일 - {path}")
            continue
        xlsx_by_region.setdefault(region, []).append(path)

    csv_by_region = {}
    for path in glob.glob(os.path.join(BASIS_DIR, "*.csv")):
        region = _match_region(os.path.basename(path))
        if region is None:
            print(f"건너뜀: 지역명을 알 수 없는 토지특성정보 파일 - {path}")
            continue
        if region in csv_by_region:
            raise ValueError(f"'{region}' 지역의 토지특성정보 파일이 2개 이상 발견됨: {csv_by_region[region]}, {path}")
        csv_by_region[region] = path

    region_files = {}
    for region in xlsx_by_region.keys() | csv_by_region.keys():
        xlsx_paths = xlsx_by_region.get(region)
        csv_path = csv_by_region.get(region)
        if not xlsx_paths or csv_path is None:
            print(f"건너뜀: '{region}' 지역은 xlsx/csv 짝이 없음 (xlsx={xlsx_paths}, csv={csv_path})")
            continue
        region_files[region] = (xlsx_paths, csv_path)
    return region_files


"""건물 실거래가(확정번지 매핑 결과) xlsx를 읽는다.

    확정번지 컬럼이 없으면(아직 건물-건축물대장 매핑을 거치지 않은 파일) None을 반환해 건너뛴다.
    확정번지가 없는 행(매칭 실패한 건물 거래)은 처리 대상에서 제외하되, 결과물에서 삭제하지는 않는다.
"""
def _load_deals(xlsx_path: str):
    deals = pd.read_excel(xlsx_path, header=HEADER_ROW)
    if "확정번지" not in deals.columns:
        return None, 0

    target_count = int(deals["확정번지"].notna().sum())
    return deals, target_count


"""csv_path를 청크 단위로 한 번만 읽어, needed_dongs에 해당하는 행만 묶어 반환한다.

    법정동명은 normalize_sigungu로 연속 공백을 1개로 줄여둔다. 실거래가 쪽 시군구 표기와 토지특성정보
    쪽 법정동명 표기의 공백이 달라도 같은 키로 매칭되게 하기 위함이다(find_overall_ledger_building.py에서
    시군구/대지_위치 매칭에 쓰는 것과 동일한 정규화). 법정동명이 비어있는(NaN) 행은 normalize_sigungu가
    문자열만 받으므로 정규화 전에 미리 제외한다(어차피 그런 행은 needed_dongs와 매칭될 수 없어, 기존에도
    결과에 포함되지 않던 행이다).
    반환 딕셔너리의 키는 정규화된 법정동명이다. 실거래 행마다 반복되는 동 단위 필터링을 미리 끝내두어,
    매칭 시에는 훨씬 작아진 후보군에서 지번/대장구분명만 비교하면 되도록 한다.
"""
def _load_land_candidates(basis_csv_path: str, needed_dongs: set) -> dict:
    candidate_chunks = []
    for chunk in pd.read_csv(
        basis_csv_path, encoding=BASIS_CSV_ENCODING, usecols=BASIS_USECOLS,
        dtype={"고유번호": str, "지번": str}, chunksize=CSV_CHUNK_SIZE,
    ):
        chunk = chunk[chunk["법정동명"].notna()].copy()
        chunk["법정동명"] = chunk["법정동명"].map(normalize_sigungu)
        sub = chunk[chunk["법정동명"].isin(needed_dongs)]
        if len(sub):
            candidate_chunks.append(sub)

    candidates = pd.concat(candidate_chunks, ignore_index=True) if candidate_chunks else pd.DataFrame(columns=BASIS_USECOLS)
    candidates = candidates.dropna(subset=["지번"]).copy()
    candidates["토지면적"] = candidates["토지면적"].astype(float)
    candidates["공시지가"] = candidates["공시지가"].astype(float)

    return {dong: df for dong, df in candidates.groupby("법정동명")}


"""실거래 한 건(딕셔너리 형태의 행)에 대해 시군구+확정번지로 토지 후보를 찾는다.

    확정번지가 '산'으로 시작하면 '산'을 뗀 나머지를 지번과 비교하고, 대장구분명이 '산'인 후보만 허용한다.
    후보가 정확히 1개일 때만 확정하며, (고유번호, 토지면적, 공시지가)를 반환한다. 실패하면 (None, None, None).
"""
def _match_deal(deal: dict, candidates_by_dong: dict):
    candidates = candidates_by_dong.get(deal["시군구"])
    if candidates is None:
        return None, None, None

    beonji = deal["확정번지"]
    is_san = beonji.startswith("산")
    beonji_key = beonji[1:].lstrip() if is_san else beonji

    mask = candidates["지번"] == beonji_key
    if is_san:
        mask &= candidates["대장구분명"] == "산"
    hits = candidates[mask]

    if len(hits) != 1:
        return None, None, None

    matched = hits.iloc[0]
    return matched["고유번호"], matched["토지면적"], matched["공시지가"]


"""확정번지가 있는 행에 한해 토지 매칭을 수행해 PNU/토지면적/공시지가 컬럼을 추가하고,
통계를 계산해 결과 xlsx로 저장한다. 로그에는 어느 지역 처리 중인지 알 수 있도록 [region]을 붙인다."""
def _match_and_write(region: str, xlsx_path: str, deals, target_count: int, candidates_by_dong: dict):
    matched_pnu, matched_area, matched_price = [], [], []
    for deal in deals.to_dict("records"):
        if pd.isna(deal["확정번지"]):
            matched_pnu.append(None)
            matched_area.append(None)
            matched_price.append(None)
            continue

        pnu, area, price = _match_deal(deal, candidates_by_dong)
        matched_pnu.append(pnu)
        matched_area.append(area)
        matched_price.append(price)

    deals["PNU"] = matched_pnu
    deals["토지면적"] = matched_area
    deals["공시지가"] = matched_price

    success_count = deals["PNU"].notna().sum()
    success_rate = success_count / target_count if target_count else 0
    print(f"[{region}] {os.path.basename(xlsx_path)} 처리대상 개수: {target_count}")
    print(f"[{region}] {os.path.basename(xlsx_path)} 매칭 성공 건수: {success_count}")
    print(f"[{region}] {os.path.basename(xlsx_path)} 매칭 성공률: {success_rate:.1%}")

    _xlsx_name, _xlsx_ext = os.path.splitext(os.path.basename(xlsx_path))
    output_path = os.path.join(OUTPUT_DIR, f"{_xlsx_name}_토지매핑{_xlsx_ext}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        deals.to_excel(writer, sheet_name=OUTPUT_SHEET_NAME, index=False, startrow=DATA_START_ROW)
        sheet = writer.sheets[OUTPUT_SHEET_NAME]
        sheet["A1"] = "total_info"
        sheet["B1"] = f"처리대상 개수: {target_count}"
        sheet["G1"] = f"매칭 성공 건수: {success_count}"
        sheet["L1"] = f"매칭 성공률: {success_rate:.1%}"

    print(f"[{region}] 완료: {output_path}")


"""같은 지역의 xlsx 여러 개가 csv 1개를 공유하므로, csv는 지역당 한 번만 읽고 xlsx만 반복 처리한다.
    xlsx 하나를 처리·저장할 때마다 해당 DataFrame을 즉시 해제해, 다음 xlsx 처리 중에 이전 xlsx의
    데이터가 메모리에 남아있지 않도록 한다. 지역 전체 처리가 끝나면 이 지역의 CSV 후보도 해제한다.
"""
def process_region_group(region: str, xlsx_paths, csv_path: str):
    loaded = []
    needed_dongs = set()
    for xlsx_path in xlsx_paths:
        print(f"[{region}] {os.path.basename(xlsx_path)} 로딩 중...")
        try:
            deals, target_count = _load_deals(xlsx_path)
        except Exception as e:
            print(f"[{region}] {xlsx_path} 로드 실패로 건너뜀: {e}")
            continue
        if deals is None:
            print(f"[{region}] 건너뜀: 확정번지 컬럼이 없는 파일 - {xlsx_path}")
            continue
        needed_dongs |= set(deals.loc[deals["확정번지"].notna(), "시군구"].unique())
        loaded.append((xlsx_path, deals, target_count))

    if not loaded:
        return

    print(f"[{region}] {os.path.basename(csv_path)} 로딩 중...")
    candidates_by_dong = _load_land_candidates(csv_path, needed_dongs)

    print(f"[{region}] 매칭 중...")
    while loaded:
        xlsx_path, deals, target_count = loaded.pop(0)
        try:
            _match_and_write(region, xlsx_path, deals, target_count, candidates_by_dong)
        except Exception as e:
            print(f"[{region}] {xlsx_path} 매칭 처리 실패로 건너뜀: {e}")
        finally:
            del deals
            gc.collect()

    del candidates_by_dong
    gc.collect()


def main():
    region_files = discover_region_files()
    if not region_files:
        print("처리할 지역 파일 쌍을 찾지 못했습니다.")
        return

    for region, (xlsx_paths, csv_path) in region_files.items():
        try:
            process_region_group(region, xlsx_paths, csv_path)
        except Exception as e:
            print(f"[{region}] 처리 중 오류로 건너뜀: {e}")


if __name__ == "__main__":
    main()
