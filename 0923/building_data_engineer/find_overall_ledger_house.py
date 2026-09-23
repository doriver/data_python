# 단독/다가구 실거래가(마스킹된 번지)에, 건축물대장 총괄표제부 데이터를 대조해 확정번지를 채워 넣는 스크립트.
# find_house_buillding.py와 달리 원본 총괄표제부 CSV(대장구분 미필터링, 대지_위치가 단일 문자열)를 그대로 사용한다.
import glob
import os
import re
import sys

import pandas as pd

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

INPUT_DIR = "data/raw"  # 이 디렉터리의 모든 xlsx를 전국 대상으로 한번에 처리한다.
BASIS_CSV = "data/basis/건축물대장_총괄표제부.csv"
BASIS_CSV_ENCODING = "utf-8-sig"
OUTPUT_DIR = "data/processed"

HEADER_ROW = 12  # 실거래가 엑셀의 실제 표 헤더 행(0-index)
OUTPUT_SHEET_NAME = "실거래가"
DATA_START_ROW = 2  # 0-index. 1행에 통계 요약, 2행은 빈 줄, 3행부터 표 작성
EMPTY_VALUE = "-"  # 실제 거래를 나타내는 값(해제된 경우는 날짜가 들어감)
CSV_CHUNK_SIZE = 200_000  # 대용량 총괄표제부 CSV를 청크 단위로 읽는다.

# 실거래 주택유형 -> 건축물대장 주용도 중 허용되는 값들.
HOUSE_TYPE_TO_JUYONGDO = {
    "단독": {"단독주택"},
    "다가구": {"단독주택", "다가구주택"},
}

# "서울특별시 성북구 돈암동 552-3번지" / "...산11-1번지" 형태에서 번지 부분을 떼어내기 위한 패턴.
_DAEJI_WICHI_RE = re.compile(r"^(?P<dong>.+?)\s+산?\d+(?:-\d+)?번지$")


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


"""건축물대장의 '대지_위치' 문자열에서 번지 부분을 떼어내, 시군구 문자열을 반환한다.

    패턴이 맞지 않으면(예: 번지로 끝나지 않는 이상값) None을 반환한다.
"""
def parse_daeji_wichi(raw):
    if not isinstance(raw, str):
        return None
    match = _DAEJI_WICHI_RE.match(raw.strip())
    if not match:
        return None
    return normalize_sigungu(match.group("dong"))


"""실거래가 xlsx를 읽어 해제(취소) 거래를 제외한 뒤, 매칭에 쓸 파생 컬럼(시군구, 번지 접두어/자리수)을 추가해 반환한다."""
def _load_deals(xlsx_path: str):
    deals = pd.read_excel(xlsx_path, header=HEADER_ROW)

    # 해제(취소) 신고가 등록되면, 취소되기 전 원본 행(해제사유발생일 "-")이 지워지지 않고, 취소 행(해제사유발생일에 날짜)과 별개로 하나 더 남아 중복되는 경우가 있다.
    # 이런 원본 중복 행은 잘못된 데이터이므로 집계 전에 제거한다.
    dup_key_cols = ["시군구", "번지", "주택유형", "도로조건", "연면적(㎡)", "대지면적(㎡)", "거래금액(만원)", "거래유형"]
    has_cancel_date = deals["해제사유발생일"].notna() & (deals["해제사유발생일"] != EMPTY_VALUE)
    group_ids = deals.groupby(dup_key_cols, dropna=False).ngroup()
    cancelled_group_ids = set(group_ids[has_cancel_date])
    duplicate_original_mask = (~has_cancel_date) & group_ids.isin(cancelled_group_ids)
    if duplicate_original_mask.any():
        print(f"{os.path.basename(xlsx_path)} 해제 중복 원본 행 제거: {duplicate_original_mask.sum()}건")
    deals = deals[~duplicate_original_mask].reset_index(drop=True)
    # 거래 취소된경우 제외
    cancelled_mask = deals["해제사유발생일"].notna() & (deals["해제사유발생일"] != EMPTY_VALUE)
    deals = deals[~cancelled_mask].reset_index(drop=True)
    total_count = len(deals)

    # 시군구 컬럼을 매칭키로 쓴다. 연속 공백을 1개로 줄여 총괄표제부 쪽 키 표기와 맞춘다.
    deals["_시군구"] = deals["시군구"].map(normalize_sigungu)

    parsed = deals["번지"].map(parse_beonji)
    deals["_번지_접두어"] = [p[0] for p in parsed]
    deals["_번지_자리수"] = [p[1] for p in parsed]

    return deals, total_count


"""총괄표제부 CSV를 청크 단위로 읽어, '일반' 대장구분만 남기고 시군구("시도 구 법정동") 별로 묶은 후보 딕셔너리를 만든다.

    전국 xlsx를 모두 처리하므로 동 단위 필터링 없이 전체를 대상으로 한다.
"""
def _load_basis_candidates(basis_csv_path: str) -> dict:
    if not os.path.exists(basis_csv_path):
        raise FileNotFoundError(f"{basis_csv_path} 가 없습니다.")

    print(f"{os.path.basename(basis_csv_path)} 로딩 중...")
    chunks = []
    reader = pd.read_csv(basis_csv_path, encoding=BASIS_CSV_ENCODING, dtype=str, chunksize=CSV_CHUNK_SIZE)
    for chunk in reader:
        chunk = chunk[
            (chunk["대장_구분_코드_명"] == "일반") & (chunk["신_구_대장_구분_코드_명"] == "신대장")
        ]
        if chunk.empty:
            continue

        parsed_dong = chunk["대지_위치"].map(parse_daeji_wichi)
        chunk = chunk[parsed_dong.notna()].copy()
        chunk["_시군구"] = parsed_dong[parsed_dong.notna()]

        chunk["_번_정수"] = pd.to_numeric(chunk["번"], errors="coerce")
        chunk["_지_정수"] = pd.to_numeric(chunk["지"], errors="coerce").fillna(0)
        chunk = chunk[chunk["_번_정수"].notna()].copy()
        chunk["_번_정수"] = chunk["_번_정수"].astype("int64")
        chunk["_지_정수"] = chunk["_지_정수"].astype("int64")
        chunk["_번_문자열"] = chunk["_번_정수"].astype(str)
        chunk["_번_자리수"] = chunk["_번_문자열"].str.len()
        chunk["_사용승인연도"] = pd.to_numeric(chunk["사용승인_일"].astype(str).str[:4], errors="coerce")
        chunk["연면적(㎡)"] = pd.to_numeric(chunk["연면적(㎡)"], errors="coerce")
        chunk["대지_면적(㎡)"] = pd.to_numeric(chunk["대지_면적(㎡)"], errors="coerce")

        chunks.append(chunk)

    if not chunks:
        return {}

    basis = pd.concat(chunks, ignore_index=True)
    return {key: df for key, df in basis.groupby("_시군구")}


"""실거래 한 건(딕셔너리 형태의 행)에 대해 고유 매핑키 -> 서브 매핑키 순으로 후보를 좁혀 확정번지를 찾는다.

    확정되면 "번-지"(지가 0이면 "번") 형식 문자열을, 실패하면 None을 반환한다.
"""
def _match_deal(deal: dict, candidates_by_dong: dict):
    candidates = candidates_by_dong.get(deal["_시군구"])
    if candidates is None:
        return None

    # 고유 매핑키: 번지(자리수+접두어, 지는 제외) + 연면적이 모두 정확히 일치해야 한다.
    mask = (
        (candidates["_번_자리수"] == deal["_번지_자리수"])
        & candidates["_번_문자열"].str.startswith(deal["_번지_접두어"])
        & (candidates["연면적(㎡)"] == deal["연면적(㎡)"])
    )
    hits = candidates[mask]

    # 서브 매핑키: 건축년도 -> 주택유형(주용도) -> 대지면적 순으로, 후보가 2개 이상일 때만 한 단계씩 더 좁힌다.
    if len(hits) >= 2:
        hits = hits[hits["_사용승인연도"] == deal["건축년도"]]
        if len(hits) >= 2:
            allowed_juyongdo = HOUSE_TYPE_TO_JUYONGDO.get(deal["주택유형"], set())
            hits = hits[hits["주_용도_코드_명"].isin(allowed_juyongdo)]
            if len(hits) >= 2:
                hits = hits[hits["대지_면적(㎡)"] == deal["대지면적(㎡)"]]

    if len(hits) != 1:
        return None

    matched = hits.iloc[0]
    return str(matched["_번_정수"]) if matched["_지_정수"] == 0 else f"{matched['_번_정수']}-{matched['_지_정수']}"


"""전체 실거래 행에 매칭을 수행해 확정번지/총괄표제 존재여부 컬럼을 추가하고, 통계를 계산해 결과 xlsx로 저장한다."""
def _match_and_write(xlsx_path: str, deals, total_count: int, candidates_by_dong: dict):
    matched = [_match_deal(deal, candidates_by_dong) for deal in deals.to_dict("records")]
    deals["시군구"] = deals["_시군구"]
    deals = deals.drop(columns=["_시군구", "_번지_접두어", "_번지_자리수"])
    deals["확정번지"] = matched
    deals["총괄표제 존재여부"] = deals["확정번지"].notna().map({True: "O", False: ""})

    success_count = deals["확정번지"].notna().sum()
    success_rate = success_count / total_count if total_count else 0
    print(f"{os.path.basename(xlsx_path)} 전체 건수: {total_count}")
    print(f"{os.path.basename(xlsx_path)} 매칭 성공 건수: {success_count}")
    print(f"{os.path.basename(xlsx_path)} 매칭 성공률: {success_rate:.1%}")

    _xlsx_name, _xlsx_ext = os.path.splitext(os.path.basename(xlsx_path))
    output_path = os.path.join(OUTPUT_DIR, f"{_xlsx_name}_총괄매핑{_xlsx_ext}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        deals.to_excel(writer, sheet_name=OUTPUT_SHEET_NAME, index=False, startrow=DATA_START_ROW)
        sheet = writer.sheets[OUTPUT_SHEET_NAME]
        sheet["A1"] = "total_info"
        sheet["B1"] = f"전체 건수: {total_count}"
        sheet["G1"] = f"매칭 성공 건수: {success_count}"
        sheet["L1"] = f"매칭 성공률: {success_rate:.1%}"

    print(f"완료: {output_path}")


def main():
    xlsx_paths = sorted(glob.glob(os.path.join(INPUT_DIR, "*.xlsx")))
    if not xlsx_paths:
        raise FileNotFoundError(f"{INPUT_DIR} 에 xlsx 파일이 없습니다.")

    candidates_by_dong = _load_basis_candidates(BASIS_CSV)

    print("매칭 중...")
    for xlsx_path in xlsx_paths:
        print(f"{os.path.basename(xlsx_path)} 로딩 중...")
        deals, total_count = _load_deals(xlsx_path)
        _match_and_write(xlsx_path, deals, total_count, candidates_by_dong)


if __name__ == "__main__":
    main()
