# 토지 실거래가(마스킹된 번지)에, 토지 특성정보 CSV를 대조해 실제 번지와 PNU를 채워 넣는 스크립트.
# docs/find_land.md 의 매핑 기준을 그대로 구현한다.
import os
import sys

import pandas as pd

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

XLSX_PATH = "data/raw/20250806_20260805_토지(매매)_실거래가.xlsx"
CSV_PATH = "data/basis/AL_D195_41_20260519.csv"
CSV_ENCODING = "cp949"
CSV_CHUNK_SIZE = 200_000
CSV_USECOLS = ["고유번호", "법정동명", "지번", "지목명", "용도지역명1", "토지면적"]
HEADER_ROW = 12  # 실제 표 헤더가 있는 엑셀 행(0-index)
OUTPUT_DIR = "data/processed"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "20250806_20260805_토지(매매)_실거래가_매핑.xlsx")
DATA_START_ROW = 5  # 0-index. 상단 4행(전체/제외/처리대상/성공 건수) + 빈 줄을 남기고 그 아래부터 표 작성
AREA_TOLERANCE = 0.01
EMPTY_VALUE = "-"  # 실제 거래된거를 나타내는 값( 해제된경우는 날짜 들어가있음 )


def parse_beonji(raw: str):
    """마스킹된 번지 문자열을 (자리수 접두어, 자리수) 로 분리한다.

    '산4*' -> ('4', 2), '산*' -> ('', 1), '1***' -> ('1', 4)
    """
    body = raw[1:] if raw.startswith("산") else raw
    prefix = body.split("*", 1)[0]
    return prefix, len(body)


def main():
    deals = pd.read_excel(XLSX_PATH, header=HEADER_ROW)
    total_count = len(deals)
    print(f"실거래가 전체 건수: {total_count}")

    cancelled_mask = deals["해제사유발생일"].notna() & (deals["해제사유발생일"] != EMPTY_VALUE)
    cancelled_count = cancelled_mask.sum()
    print(f"해제사유발생일 있어 제외된 건수: {cancelled_count}")
    deals = deals[~cancelled_mask].reset_index(drop=True)
    actual_target_count = total_count - cancelled_count

    needed_dongs = set(deals["시군구"].unique())

    candidate_chunks = []
    for chunk in pd.read_csv(
        CSV_PATH, encoding=CSV_ENCODING, dtype=str, usecols=CSV_USECOLS, chunksize=CSV_CHUNK_SIZE
    ):
        sub = chunk[chunk["법정동명"].isin(needed_dongs)]
        if len(sub):
            candidate_chunks.append(sub)
    candidates = pd.concat(candidate_chunks, ignore_index=True)
    candidates = candidates.dropna(subset=["지번"]).copy()
    candidates["본번"] = candidates["지번"].str.split("-", n=1).str[0]
    candidates["토지면적"] = candidates["토지면적"].astype(float)
    print(f"토지 특성정보 후보 건수(대상 법정동 내): {len(candidates)}")

    candidates_by_dong = {dong: df for dong, df in candidates.groupby("법정동명")}

    matched_pnu = []
    matched_beonji = []
    for row in deals.itertuples(index=False):
        dong_candidates = candidates_by_dong.get(row.시군구)
        if dong_candidates is None:
            matched_pnu.append(None)
            matched_beonji.append(None)
            continue

        prefix, digit_count = parse_beonji(row.번지)
        mask = (
            (dong_candidates["지목명"] == row.지목)
            & (dong_candidates["용도지역명1"] == row.용도지역)
            & (dong_candidates["본번"].str.len() == digit_count)
            & (dong_candidates["본번"].str.startswith(prefix))
        )
        if pd.isna(row.지분구분):
            mask &= (dong_candidates["토지면적"] > row.계약면적 - AREA_TOLERANCE) & (
                dong_candidates["토지면적"] < row.계약면적 + AREA_TOLERANCE
            )
        else:
            mask &= dong_candidates["토지면적"] > row.계약면적

        hits = dong_candidates[mask]
        if len(hits) == 1:
            matched_pnu.append(hits["고유번호"].iloc[0])
            beonji = hits["지번"].iloc[0]
            if row.번지.startswith("산"):
                beonji = f"산 {beonji}"
            matched_beonji.append(beonji)
        else:
            matched_pnu.append(None)
            matched_beonji.append(None)

    deals["PNU"] = matched_pnu
    deals["확정번지"] = matched_beonji

    success_count = deals["PNU"].notna().sum()
    print(f"매칭 성공 건수: {success_count} / {actual_target_count}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        deals.to_excel(writer, sheet_name="실거래가", index=False, startrow=DATA_START_ROW)
        sheet = writer.sheets["실거래가"]
        sheet["A1"] = f"전체 건수: {total_count}"
        sheet["A2"] = f"해제사유발생일 있어 제외된 건수: {cancelled_count}"
        sheet["A3"] = f"실제 처리 대상: {actual_target_count}"
        sheet["A4"] = f"매칭 성공 건수: {success_count}"

    print(f"완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
