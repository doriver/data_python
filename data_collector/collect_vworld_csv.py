"""
vworld 자료실(dtmk) 파일 다운로드 스크립트

동작:
    브라우저에서 로그인 후 복사한 쿠키(.env의 VWORLD_COOKIE)를 사용해
    downloadResourceFile.do 엔드포인트에서 파일을 받아 data_lake 에 저장한다.

사용법:
    1. .env.example 을 .env 로 복사하고 VWORLD_COOKIE 에
       브라우저 개발자도구(F12) > Network 탭에서 복사한 Cookie 헤더 전체 값을 붙여넣기
       (로그인 후 발급되는 PJSESSIONID 등은 세션 쿠키라 시간이 지나면 만료되므로,
        요청이 실패하면 다시 로그인 후 쿠키를 갱신해야 한다)
    2. python collect_vworld_csv.py --ds-id 20171128DS00179 --file-no 2174

참고:
    요청 URL 예시:
    https://www.vworld.kr/dtmk/downloadResourceFile.do?ds_id={ds_id}&fileNo={file_no}
"""

import argparse
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

if sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BASE_URL = "https://www.vworld.kr"
DATA_LAKE_DIR = Path(r"D:\data\data_lake")

VWORLD_COOKIE = os.environ.get("VWORLD_COOKIE", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": f"{BASE_URL}/dtmk/dtmk_ntads_s002.do",
}


def _parse_cookie_string(cookie_str: str) -> dict:
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def download_file(ds_id: str, file_no: str) -> Path:
    if not VWORLD_COOKIE:
        raise SystemExit(".env 의 VWORLD_COOKIE 가 비어있습니다. 브라우저 쿠키를 복사해 넣어주세요.")

    cookies = _parse_cookie_string(VWORLD_COOKIE)

    resp = requests.get(
        f"{BASE_URL}/dtmk/downloadResourceFile.do",
        params={"ds_id": ds_id, "fileNo": file_no},
        headers=HEADERS,
        cookies=cookies,
    )
    resp.raise_for_status()

    disposition = resp.headers.get("Content-disposition", "")
    if "filename=" in disposition:
        raw_name = disposition.split("filename=")[-1].strip().strip(";").strip('"')
        try:
            filename = raw_name.encode("latin-1").decode("utf-8")
        except UnicodeDecodeError:
            filename = raw_name
    else:
        filename = f"{ds_id}_{file_no}.csv"

    DATA_LAKE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_LAKE_DIR / filename
    out_path.write_bytes(resp.content)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ds-id", required=True, help="데이터셋 ID (예: 20171128DS00179)")
    parser.add_argument("--file-no", required=True, help="파일 번호 (예: 2174)")
    args = parser.parse_args()

    print(f"[다운로드 시작] ds_id={args.ds_id} fileNo={args.file_no}")
    try:
        out_path = download_file(args.ds_id, args.file_no)
        print(f"[완료] {out_path}")
    except Exception as e:
        print(f"[실패] {e}")


if __name__ == "__main__":
    main()
