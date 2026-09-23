# 단독/다가구 실거래가(마스킹된 번지)에, 건축물대장 데이터를 대조해 확정번지를 채워 넣는 스크립트.
# data/raw 의 모든 실거래가 xlsx를 전국 대상으로 한번에 처리한다.
# 매칭된 건물의 대장pk는 각 실거래 xlsx에 컬럼 하나로 붙이고, 건물 상세 정보는 대장pk 기준으로
# 중복 없이 모아 data/processed/건물정보.xlsx 마스터 테이블 하나로 별도 저장한다.
import glob
import os
import re
import sys

import pandas as pd

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

INPUT_DIR = "data/raw"  # 이 디렉터리의 모든 xlsx를 전국 대상으로 한번에 처리한다.
# 전국 건축물대장 CSV(대장구분 미필터링, 809만행 규모).
# 청크 단위로 읽으며 '일반' 대장구분 + 필요한 동만 추려낸다.
BASIS_CSV = "data/basis/전국_건축물대장_csv_20260915104746.csv"
BASIS_CSV_ENCODING = "utf-8"
OUTPUT_DIR = "data/processed"

HEADER_ROW = 2  # find_house_multi_buillding.py가 저장한 xlsx의 실제 표 헤더 행(0-index)
OUTPUT_SHEET_NAME = "실거래가"
DATA_START_ROW = 2  # 0-index. 1행에 통계 요약, 2행은 빈 줄, 3행부터 표 작성
EMPTY_VALUE = "-"  # 실제 거래를 나타내는 값(해제된 경우는 날짜가 들어감)
CSV_CHUNK_SIZE = 200_000  # 대용량 전국 건축물대장 CSV를 청크 단위로 읽는다.

# 실거래 주택유형 -> 건축물대장 주용도 중 허용되는 값들.
# 건축물대장에는 '다가구주택' 라벨이 거의 없고(전체 중 2건뿐) 대부분 '단독주택'으로 기록되므로,
# 단독/다가구 모두 '단독주택'을 허용하고, 다가구는 혹시 존재하는 '다가구주택'도 함께 허용한다.
HOUSE_TYPE_TO_JUYONGDO = {
    "단독": {"단독주택"},
    "다가구": {"단독주택", "다가구주택"},
}

# 매칭에 성공한 행에 건축물대장에서 함께 붙여줄 컬럼들(건축물대장 기준 원본 컬럼명). PK는 항상 맨 앞에 둔다.
BASIS_EXTRA_COLUMNS = [
    "PK", "건물명", "동명", "대지면적(㎡)", "건축면적(㎡)", "연면적(㎡)", "건폐율(%)", "용적률(%)",
    "용적률산정연면적(㎡)", "주구조", "주용도", "주지붕", "지상층수", "지하층수", "사용승인일",
]
# PK는 결과에서 '대장pk'로, 대지면적(㎡)/연면적(㎡)은 실거래가에도 같은 이름의 컬럼(신고된 값)이 이미
# 있으므로 덮어쓰지 않고 건축물대장 값임을 구분할 수 있도록 별도 컬럼명으로 붙인다.
BASIS_EXTRA_COLUMN_RENAME = {
    "PK": "대장pk",
    "대지면적(㎡)": "대장상 대지면적(㎡)",
    "연면적(㎡)": "대장상 연면적(㎡)",
}
# 위 rename이 적용된 최종 컬럼명들(대장pk 포함 14개). deals에는 이제 이 중 '대장pk' 하나만 직접 붙고,
# 나머지 13개 상세 컬럼은 건물정보.xlsx 마스터 테이블(대장pk 기준, 중복 제거)의 컬럼 순서로 쓰인다.
OUTPUT_EXTRA_COLUMNS = [BASIS_EXTRA_COLUMN_RENAME.get(col, col) for col in BASIS_EXTRA_COLUMNS]
# 숫자로 변환해두는 게 자연스러운 붙임 컬럼들. (건물명/동명/주구조/주용도/주지붕/사용승인일은 문자열 그대로 둔다.)
BASIS_NUMERIC_EXTRA_COLUMNS = [
    "대지면적(㎡)", "건축면적(㎡)", "연면적(㎡)", "건폐율(%)", "용적률(%)", "용적률산정연면적(㎡)",
    "지상층수", "지하층수",
]
# 매칭(대장구분/시도/시군구/법정동/번/지/사용승인일)에 필요한 컬럼 + 붙임 컬럼만 읽어 CSV 파싱 비용을 줄인다.
# 대지구분은 '총괄표제 존재여부'가 O인 지번주소의 표제부 상세 조회에서 산 지번을 구분하는 데 쓴다.
BASIS_USECOLS = sorted(set(
    ["대장구분", "시도", "시군구", "법정동", "번", "지", "대지구분", "사용승인일", "연면적(㎡)", "대지면적(㎡)", "주용도"]
    + BASIS_EXTRA_COLUMNS
))


"""마스킹된 번지 문자열을 (자리수 접두어, 자리수)로 분리한다.

    '1**' -> ('1', 3), '*' -> ('', 1)
"""
def parse_beonji(raw: str):
    body = raw[1:] if raw.startswith("산") else raw
    prefix = body.split("*", 1)[0]
    return prefix, len(body)


"""시군구 문자열의 연속 공백을 1개로 줄인다. 두 데이터 출처의 공백 표기가 달라도 같은 키로 매칭되게 한다."""
def normalize_sigungu(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip())


"""실거래가 xlsx를 읽어 해제(취소) 거래를 제외한 뒤, 매칭에 쓸 파생 컬럼(시군구, 번지 접두어/자리수)을 추가해 반환한다."""
def _load_deals(xlsx_path: str):
    deals = pd.read_excel(xlsx_path, header=HEADER_ROW)
    # 확정번지가 전부 비어있으면(NaN) float64로 읽혀, 이후 문자열 대입 시 타입 충돌이 나므로 object로 맞춰둔다.
    deals["확정번지"] = deals["확정번지"].astype(object)

    cancelled_mask = deals["해제사유발생일"].notna() & (deals["해제사유발생일"] != EMPTY_VALUE)
    deals = deals[~cancelled_mask].reset_index(drop=True)
    total_count = len(deals)

    # 시군구 컬럼을 매칭키로 쓴다. 연속 공백을 1개로 줄여 건축물대장 쪽 키 표기와 맞춘다.
    deals["_시군구"] = deals["시군구"].map(normalize_sigungu)

    parsed = deals["번지"].map(parse_beonji)
    deals["_번지_접두어"] = [p[0] for p in parsed]
    deals["_번지_자리수"] = [p[1] for p in parsed]

    return deals, total_count


"""전국 건축물대장 CSV를 청크 단위로 읽어, '일반' 대장구분만 남기고 시군구(시도+시군구+법정동 결합 문자열) 별로 묶은 후보 딕셔너리를 만든다.

    전국 xlsx를 모두 처리하므로 동 단위 필터링 없이 전체를 대상으로 한다.
"""
def _load_basis_candidates(basis_csv_path: str) -> dict:
    if not os.path.exists(basis_csv_path):
        raise FileNotFoundError(f"{basis_csv_path} 가 없습니다.")

    print(f"{os.path.basename(basis_csv_path)} 로딩 중...")
    chunks = []
    reader = pd.read_csv(
        basis_csv_path, encoding=BASIS_CSV_ENCODING, dtype=str, usecols=BASIS_USECOLS, chunksize=CSV_CHUNK_SIZE
    )
    for chunk in reader:
        chunk = chunk[chunk["대장구분"] == "일반"]
        if chunk.empty:
            continue

        chunk = chunk.copy()
        # 시도/시군구/법정동 중 비어있는 값은 빈 문자열로 취급해 그대로 결합한다.
        dong_parts = chunk["시도"].fillna("") + " " + chunk["시군구"].fillna("") + " " + chunk["법정동"].fillna("")
        chunk["_시군구"] = dong_parts.map(normalize_sigungu)
        chunk["_번_정수"] = pd.to_numeric(chunk["번"], errors="coerce")
        chunk["_지_정수"] = pd.to_numeric(chunk["지"], errors="coerce").fillna(0)
        chunk = chunk[chunk["_번_정수"].notna()].copy()
        chunk["_번_정수"] = chunk["_번_정수"].astype("int64")
        chunk["_지_정수"] = chunk["_지_정수"].astype("int64")
        chunk["_번_문자열"] = chunk["_번_정수"].astype(str)
        chunk["_번_자리수"] = chunk["_번_문자열"].str.len()
        chunk["_사용승인연도"] = pd.to_numeric(chunk["사용승인일"].astype(str).str[:4], errors="coerce")
        for col in BASIS_NUMERIC_EXTRA_COLUMNS:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

        chunks.append(chunk)

    if not chunks:
        return {}

    basis = pd.concat(chunks, ignore_index=True)
    return {key: df for key, df in basis.groupby("_시군구")}


"""실거래 한 건(딕셔너리 형태의 행)에 대해 고유 매핑키 -> 서브 매핑키 순으로 후보를 좁혀 확정번지를 찾는다.

    확정되면 {"확정번지": ..., "지번주소": ..., OUTPUT_EXTRA_COLUMNS...(대장pk 포함)} 딕셔너리를,
    실패하면 None을 반환한다. 지번주소는 산 여부를 원본 '번지'(마스킹된 값, 예: "산1**")로 판단해
    시군구+확정번지로 조합한 것으로, 건물정보.xlsx에 저장할 때 쓰인다.
"""
def _match_deal(deal: dict, candidates_by_dong: dict):
    candidates = candidates_by_dong.get(deal["_시군구"])
    if candidates is None:
        return None

    # 고유 매핑키: 번지(자리수+접두어, 지는 제외) + 연면적 + 건축년도가 모두 정확히 일치해야 한다.
    mask = (
        (candidates["_번_자리수"] == deal["_번지_자리수"])
        & candidates["_번_문자열"].str.startswith(deal["_번지_접두어"])
        & (candidates["연면적(㎡)"] == deal["연면적(㎡)"])
        & (candidates["_사용승인연도"] == deal["건축년도"])
    )
    hits = candidates[mask]

    # 서브 매핑키: 주택유형(주용도) -> 대지면적 순으로, 후보가 2개 이상일 때만 한 단계씩 더 좁힌다.
    if len(hits) >= 2:
        allowed_juyongdo = HOUSE_TYPE_TO_JUYONGDO.get(deal["주택유형"], set())
        hits = hits[hits["주용도"].isin(allowed_juyongdo)]
        if len(hits) >= 2:
            hits = hits[hits["대지면적(㎡)"] == deal["대지면적(㎡)"]]

    if len(hits) != 1:
        return None

    matched = hits.iloc[0]
    beonji = str(matched["_번_정수"]) if matched["_지_정수"] == 0 else f"{matched['_번_정수']}-{matched['_지_정수']}"
    산여부 = str(deal["번지"]).startswith("산")
    지번주소 = deal["시군구"] + (" 산 " if 산여부 else " ") + beonji
    extra = {BASIS_EXTRA_COLUMN_RENAME.get(col, col): matched[col] for col in BASIS_EXTRA_COLUMNS}
    return {"확정번지": beonji, "지번주소": 지번주소, **extra}


"""전체 실거래 행 중 '총괄표제 존재여부'가 비어있는(확정번지가 아직 없는) 행은 _match_deal로 확정번지와
대장pk를 채우고, '총괄표제 존재여부'가 'O'인 행(확정번지가 이미 채워져 있던 행)은 지번주소를 만들어
표제부에서 대장pk만 채운다(둘 다 실패한 행은 대장pk가 비어있는 채로 남는다).

    두 경로에서 매칭된 건물의 상세 정보(OUTPUT_EXTRA_COLUMNS)는 이 xlsx에는 더 이상 붙이지 않고,
    buildings_by_pk(대장pk -> 상세 컬럼 딕셔너리, main()에서 전체 실행 동안 누적)에 모아
    나중에 건물정보.xlsx 하나로 저장한다. address_pk_cache는 총괄표제 O-case 지번주소 ->
    대장pk 문자열 캐시로, main()에서 파일 간에 재사용되어 같은 건물을 여러 번 표제부 조회하지 않게 한다.
    통계를 계산해 결과 xlsx로 저장한다."""
def _match_and_write(
    xlsx_path: str, deals, total_count: int, candidates_by_dong: dict, address_pk_cache: dict, buildings_by_pk: dict
):
    needs_match_mask = deals["확정번지"].isna()
    needs_match_index = deals.index[needs_match_mask]
    match_results = [_match_deal(deal, candidates_by_dong) for deal in deals.loc[needs_match_mask].to_dict("records")]

    found_index = [idx for idx, result in zip(needs_match_index, match_results) if result is not None]
    found_results = [result for result in match_results if result is not None]

    if "대장pk" not in deals.columns:
        deals["대장pk"] = pd.NA
    if found_index:
        deals.loc[found_index, "확정번지"] = [result["확정번지"] for result in found_results]
        deals.loc[found_index, "대장pk"] = [result["대장pk"] for result in found_results]

    # 마스킹 번지 경로(_match_deal)에서 매칭된 건물 상세를 대장pk 기준으로 누적(건물정보.xlsx용).
    for result in found_results:
        buildings_by_pk[result["대장pk"]] = {
            "지번주소": result["지번주소"],
            **{col: result[col] for col in OUTPUT_EXTRA_COLUMNS},
        }

    o_case_pk_count = _fill_o_case_pk(deals, candidates_by_dong, address_pk_cache, buildings_by_pk)

    deals = deals.drop(columns=["_시군구", "_번지_접두어", "_번지_자리수"])

    new_success_count = len(found_index)
    success_count = deals["확정번지"].notna().sum()
    success_rate = success_count / total_count if total_count else 0
    pk_filled_count = deals["대장pk"].notna().sum()
    print(f"{os.path.basename(xlsx_path)} 전체 건수: {total_count}")
    print(f"{os.path.basename(xlsx_path)} 신규 매칭 성공 건수(총괄표제 미존재 대상): {new_success_count} / {needs_match_mask.sum()}")
    print(f"{os.path.basename(xlsx_path)} 매칭 성공 건수(확정번지): {success_count}")
    print(f"{os.path.basename(xlsx_path)} 매칭 성공률: {success_rate:.1%}")
    print(f"{os.path.basename(xlsx_path)} 대장pk 채워진 건수: {pk_filled_count} (신규 매칭 {new_success_count} + 총괄표제 O-case {o_case_pk_count})")

    _xlsx_name, _xlsx_ext = os.path.splitext(os.path.basename(xlsx_path))
    output_path = os.path.join(OUTPUT_DIR, f"{_xlsx_name}_매핑{_xlsx_ext}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        deals.to_excel(writer, sheet_name=OUTPUT_SHEET_NAME, index=False, startrow=DATA_START_ROW)
        sheet = writer.sheets[OUTPUT_SHEET_NAME]
        sheet["A1"] = "total_info"
        sheet["B1"] = f"전체 건수: {total_count}"
        sheet["G1"] = f"매칭 성공 건수(확정번지): {success_count}"
        sheet["L1"] = f"매칭 성공률: {success_rate:.1%}"
        sheet["Q1"] = f"대장pk 채워진 건수: {pk_filled_count}"

    print(f"완료: {output_path}")


"""'총괄표제 존재여부'가 'O'인 행(이미 총괄표제부로 확정번지를 찾은 행)에 대해 지번주소를 만들고,
해당 주소로 매칭되는 건축물대장 PK를 deals의 '대장pk' 컬럼에 채운다. 한 지번주소가 여러 PK(여러
건물/동)에 매칭될 수 있으므로, 매칭된 PK들을 콤마로 이어붙인 문자열로 채운다(예: "12345,67890").

    확정번지는 "번-지"(지가 0이면 "번") 형식이라 산 여부가 드러나지 않으므로, 원본 '번지'
    (마스킹된 값, 예: "산1**")로 산 여부를 판단해 지번주소에 반영한다.

    address_pk_cache는 지번주소 -> 대장pk 문자열(매칭 실패 시 None) 캐시로, main()의 파일 루프
    전체에서 재사용된다. 같은 지번주소가 여러 xlsx 파일에 걸쳐 등장해도 표제부 조회는 한 번만
    수행하고, 매칭된 건물 상세는 buildings_by_pk(대장pk -> 상세 컬럼 딕셔너리)에 함께 누적해
    건물정보.xlsx 마스터 테이블 데이터로 쓴다.

    반환값은 이번 파일에서 대장pk가 채워진 O-case 행 수다.
"""
def _fill_o_case_pk(deals, candidates_by_dong: dict, address_pk_cache: dict, buildings_by_pk: dict) -> int:
    o_case_mask = deals["총괄표제 존재여부"] == "O"
    if not o_case_mask.any():
        return 0

    o_case = deals.loc[o_case_mask].copy()
    o_case["_산여부"] = o_case["번지"].astype(str).str.startswith("산")

    beonji_parts = o_case["확정번지"].astype(str).str.split("-", n=1)
    o_case["_확정번"] = beonji_parts.str[0].astype("int64")
    o_case["_확정지"] = beonji_parts.str.get(1).fillna("0").astype("int64")

    o_case["지번주소"] = (
        o_case["시군구"] + " " + o_case["_산여부"].map({True: "산 ", False: ""}) + o_case["확정번지"]
    )

    # 이 파일 안에서 유니크한 지번주소만 골라, 아직 캐시에 없는 것만 표제부 조회한다.
    unique_addresses = o_case.drop_duplicates(subset="지번주소")
    for address in unique_addresses.to_dict("records"):
        addr_key = address["지번주소"]
        if addr_key in address_pk_cache:
            continue
        basis_rows = _match_address_basis_rows(address, candidates_by_dong)
        if basis_rows[0]["대장pk"] is None:
            address_pk_cache[addr_key] = None
            continue
        for basis_row in basis_rows:
            buildings_by_pk[basis_row["대장pk"]] = {"지번주소": addr_key, **basis_row}
        address_pk_cache[addr_key] = ",".join(str(basis_row["대장pk"]) for basis_row in basis_rows)

    pk_series = o_case["지번주소"].map(address_pk_cache)
    deals.loc[o_case_mask, "대장pk"] = pk_series.values
    return int(pk_series.notna().sum())


"""지번주소 하나(딕셔너리 형태의 행)에 대해 매핑되는 표제부 row(들)를 찾는다.

    산 지번이면 대지구분 == '산' 조건을 추가로 건다. 매칭된 row마다 {OUTPUT_EXTRA_COLUMNS...(대장pk 포함)}
    딕셔너리를 만들어 리스트로 반환하고, 하나도 못 찾으면 값이 모두 비어있는 딕셔너리 1개짜리 리스트를 반환한다.
"""
def _match_address_basis_rows(address: dict, candidates_by_dong: dict) -> list:
    candidates = candidates_by_dong.get(address["_시군구"])
    if candidates is not None:
        mask = (candidates["_번_정수"] == address["_확정번"]) & (candidates["_지_정수"] == address["_확정지"])
        if address["_산여부"]:
            mask &= candidates["대지구분"] == "산"
        hits = candidates[mask]
    else:
        hits = None

    if hits is None or hits.empty:
        return [{col: None for col in OUTPUT_EXTRA_COLUMNS}]

    return [
        {BASIS_EXTRA_COLUMN_RENAME.get(col, col): matched[col] for col in BASIS_EXTRA_COLUMNS}
        for matched in hits.to_dict("records")
    ]


"""buildings_by_pk(건축물대장 PK -> 건물 상세 컬럼 딕셔너리)에 누적된, 전체 실행(모든 입력 xlsx)에서
매칭된 건물들을 대장pk 기준으로 중복 없이 하나의 마스터 엑셀로 저장한다.

    마스킹된 번지 매칭 경로(_match_deal)와 총괄표제 O-case 경로(_match_address_basis_rows) 양쪽에서
    나온 건물이 섞여 들어오며, 동일 대장pk는 buildings_by_pk 단계에서 이미 하나로 합쳐져 있다.
    기존 단독다가구_총괄있는_표제부.xlsx(총괄표제 O-case 지번주소 전용, 지번주소 컬럼 포함)를 대체한다.
    두 매칭 경로 모두 지번주소를 계산해 buildings_by_pk에 함께 담아두므로, 대장pk 옆에 지번주소
    컬럼도 포함해 저장한다."""
def _write_building_info(buildings_by_pk: dict):
    result_columns = ["대장pk", "지번주소"] + [col for col in OUTPUT_EXTRA_COLUMNS if col != "대장pk"]
    result = pd.DataFrame(buildings_by_pk.values(), columns=result_columns)

    building_count = len(result)
    print(f"매칭된 고유 건물(대장pk) 수: {building_count}")

    output_path = os.path.join(OUTPUT_DIR, "단독다가구_건물정보.xlsx")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name=OUTPUT_SHEET_NAME, index=False, startrow=DATA_START_ROW)
        sheet = writer.sheets[OUTPUT_SHEET_NAME]
        sheet["A1"] = "total_info"
        sheet["B1"] = f"매칭된 고유 건물(대장pk) 수: {building_count}"

    print(f"완료: {output_path}")


def main():
    xlsx_paths = sorted(glob.glob(os.path.join(INPUT_DIR, "*.xlsx")))
    if not xlsx_paths:
        raise FileNotFoundError(f"{INPUT_DIR} 에 xlsx 파일이 없습니다.")

    candidates_by_dong = _load_basis_candidates(BASIS_CSV)

    print("매칭 중...")
    address_pk_cache = {}  # 지번주소 -> 대장pk 문자열(또는 None) 캐시, 파일 간 재사용
    buildings_by_pk = {}  # 대장pk -> 건물 상세 딕셔너리, 전체 실행 동안 누적 -> 건물정보.xlsx
    for xlsx_path in xlsx_paths:
        print(f"{os.path.basename(xlsx_path)} 로딩 중...")
        deals, total_count = _load_deals(xlsx_path)
        _match_and_write(xlsx_path, deals, total_count, candidates_by_dong, address_pk_cache, buildings_by_pk)

    _write_building_info(buildings_by_pk)


if __name__ == "__main__":
    main()
