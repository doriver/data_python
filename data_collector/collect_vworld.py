"""
vworld 토지특성정보 전국 자동 다운로드 스크립트 (시도 단위)

사용법:
    1. pip install -r requirements.txt && playwright install chromium
    2. .env.example 을 .env 로 복사하고 VWORLD_ID / VWORLD_PW 입력
    3. 아래 TODO 로 표시된 셀렉터들을 실제 페이지 구조에 맞게 채워넣기
       (F12 개발자도구로 로그인폼 / 시도 드롭다운 / 다운로드 버튼 확인)
    4. python collect_vworld.py --yymm 2605   (기준일이 2026-05인 경우)

동작:
    로그인 -> 시도 17개를 순회하며 드롭다운 선택 후 다운로드 버튼 클릭
    -> 다운로드된 zip 을 "{시도}_{yymm}_토지특성.zip" 로 리네임해 data_lake 로 이동
    -> 압축 해제 후 내부 파일/폴더도 동일 규칙으로 리네임
"""

import argparse
import os
import shutil
import zipfile
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

VWORLD_ID = os.environ["VWORLD_ID"]
VWORLD_PW = os.environ["VWORLD_PW"]

DOWNLOAD_DIR = Path(r"C:\Users\user\Downloads")
DATA_LAKE_DIR = Path(r"D:\data\data_lake")

LOGIN_URL = "https://www.vworld.kr/woc/user/login.do"  # TODO: 실제 로그인 페이지 URL 확인
TARGET_URL = (
    "https://www.vworld.kr/dtmk/dtmk_ntads_s002.do"
    "?datIde=&dsId=4&usrIde=tkdduq241&pageSize=10&pageUnit=10"
    "&dataSetSeq=4&svcCde=NA&pageIndex=1&datPageIndex=1&datPageSize=10"
    "&startDate=2025-08-29&endDate=2026-08-29"
    "&sidoCd=&sigunguCd=&dsNm=&formatSelect=CSV"
)

# 행정표준코드 시도 2자리. 강원/전북 특별자치도 개편 이후 코드가 그대로인지
# 실제 드롭다운 값과 대조해서 확인 필요 (TODO: 검증)
SIDO_LIST = [
    ("서울", "11"),
    ("부산", "26"),
    ("대구", "27"),
    ("인천", "28"),
    ("광주", "29"),
    ("대전", "30"),
    ("울산", "31"),
    ("세종", "36"),
    ("경기", "41"),
    ("강원", "42"),
    ("충북", "43"),
    ("충남", "44"),
    ("전북", "45"),
    ("전남", "46"),
    ("경북", "47"),
    ("경남", "48"),
    ("제주", "50"),
]


def login(page):
    page.goto(LOGIN_URL)
    # TODO: 실제 input 셀렉터로 교체
    page.fill("#id", VWORLD_ID)
    page.fill("#pwd", VWORLD_PW)
    page.click("#loginBtn")  # TODO: 실제 로그인 버튼 셀렉터로 교체
    page.wait_for_load_state("networkidle")


def download_sido(page, sido_name: str, sido_code: str) -> Path:
    page.goto(TARGET_URL)
    page.wait_for_load_state("networkidle")

    # TODO: 시도 드롭다운 셀렉터/조작 방식으로 교체 (select 태그면 select_option 사용)
    page.select_option("#sidoCd", sido_code)
    page.wait_for_timeout(500)

    with page.expect_download() as download_info:
        page.click(".btn-download-blue")  # TODO: 파란 다운로드 버튼 셀렉터로 교체
    download = download_info.value

    raw_path = DOWNLOAD_DIR / download.suggested_filename
    download.save_as(raw_path)
    return raw_path


def process_download(raw_path: Path, sido_name: str, yymm: str):
    base_name = f"{sido_name}_{yymm}_토지특성"
    ext = raw_path.suffix  # 보통 .zip
    renamed_path = raw_path.with_name(f"{base_name}{ext}")
    raw_path.rename(renamed_path)

    dest_zip = DATA_LAKE_DIR / renamed_path.name
    shutil.move(str(renamed_path), str(dest_zip))

    extract_dir = DATA_LAKE_DIR / base_name
    with zipfile.ZipFile(dest_zip) as zf:
        zf.extractall(extract_dir)

    # 압축 해제 후 생긴 파일이 단일 파일이면 base_name 규칙으로 리네임
    extracted = list(extract_dir.iterdir())
    if len(extracted) == 1 and extracted[0].is_file():
        single_file = extracted[0]
        single_file.rename(extract_dir / f"{base_name}{single_file.suffix}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yymm", required=True, help="기준일 (예: 2605)")
    parser.add_argument(
        "--sido", default=None, help="특정 시도만 실행 (미지정시 전체 17개)"
    )
    args = parser.parse_args()

    targets = SIDO_LIST
    if args.sido:
        targets = [t for t in SIDO_LIST if t[0] == args.sido]
        if not targets:
            raise SystemExit(f"알 수 없는 시도: {args.sido}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        login(page)

        for sido_name, sido_code in targets:
            print(f"[다운로드 시작] {sido_name}")
            try:
                raw_path = download_sido(page, sido_name, sido_code)
                process_download(raw_path, sido_name, args.yymm)
                print(f"[완료] {sido_name}")
            except Exception as e:
                print(f"[실패] {sido_name}: {e}")

        browser.close()


if __name__ == "__main__":
    main()
