# 건축물대장 xlsx(58만행 규모)를 매칭에 필요한 컬럼만 남겨 '일반' 대장구분만 CSV로 미리 변환해두는 스크립트.
# find_house_buillding.py가 매번 openpyxl로 xlsx 전체를 읽는 대신, 한 번만 변환해두고
# 이후에는 CSV(pandas C 파서)로 훨씬 빠르게 읽을 수 있도록 하기 위함이다.
import os
import sys

import pandas as pd

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

BASIS_XLSX = "data/basis/건축물대장_20260821163300.xlsx"
BASIS_HEADER_ROW = 0
BASIS_USECOLS = [
    "대장구분", "시도", "시군구", "법정동", "번", "지",
    "대지면적(㎡)", "연면적(㎡)", "주용도", "사용승인일", "용도지역코드명정보",
]
CSV_ENCODING = "utf-8"

# 매칭에서 정확히 같은 값인지(==)로 비교하는 컬럼들. CSV 왕복 후에도 값이 달라지지 않았는지 검증한다.
EXACT_MATCH_COLUMNS = ["번", "지", "대지면적(㎡)", "연면적(㎡)"]


"""xlsx 경로로부터 변환될 CSV 경로를 만든다. (예: 건축물대장_..xlsx -> 건축물대장_.._일반.csv)"""
def basis_csv_path(xlsx_path: str) -> str:
    name, _ = os.path.splitext(xlsx_path)
    return f"{name}_일반.csv"


"""건축물대장 xlsx를 읽어 '일반' 대장구분만 남긴다.

    번/지 컬럼은 int64인데, 결측치가 있으면 CSV 왕복 시 float으로 바뀌어 매칭이 깨질 수 있으므로
    결측치가 있으면 여기서 바로 에러를 낸다.
"""
def _load_and_filter(xlsx_path: str) -> pd.DataFrame:
    print(f"{os.path.basename(xlsx_path)} 로딩 중...")
    # calamine(Rust 기반) 엔진이 openpyxl보다 훨씬 빠르다. pip install python-calamine 필요.
    basis = pd.read_excel(xlsx_path, header=BASIS_HEADER_ROW, usecols=BASIS_USECOLS, engine="calamine")
    basis = basis[basis["대장구분"] == "일반"].reset_index(drop=True)

    for col in ("번", "지"):
        null_count = int(basis[col].isna().sum())
        if null_count:
            raise ValueError(
                f"'{col}' 컬럼에 결측치 {null_count}건이 있어 CSV 변환을 중단합니다. "
                "int64 컬럼에 결측치가 있으면 CSV 왕복 시 float으로 바뀌어 매칭이 깨질 수 있습니다."
            )

    return basis


"""CSV로 저장한 뒤 다시 읽어 들여, 매칭에서 완전일치(==)로 비교하는 컬럼들이 원본과
정확히 같은 값을 유지하는지 검증한다. 하나라도 달라졌으면 에러를 내고 CSV를 남기지 않는다."""
def _write_and_verify(basis: pd.DataFrame, csv_path: str) -> None:
    basis.to_csv(csv_path, index=False, encoding=CSV_ENCODING)

    print("CSV 왕복 후 값 일치 여부 검증 중...")
    reloaded = pd.read_csv(csv_path, encoding=CSV_ENCODING, dtype={"번": "int64", "지": "int64"})

    for col in EXACT_MATCH_COLUMNS:
        if not basis[col].equals(reloaded[col]):
            os.remove(csv_path)
            raise ValueError(f"'{col}' 컬럼이 CSV 왕복 후 원본과 달라져 변환을 중단합니다: {csv_path}")


def main():
    basis = _load_and_filter(BASIS_XLSX)
    csv_path = basis_csv_path(BASIS_XLSX)
    _write_and_verify(basis, csv_path)
    print(f"완료: {csv_path} ({len(basis)}행)")


if __name__ == "__main__":
    main()