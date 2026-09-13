"""
국토교통부 실거래가 공개시스템(rt.molit.go.kr) 연간 전체 시도 자동 다운로드 스크립트

동작:
    전국 17개 시도를 순회하며 지정한 연도(1/1 ~ 12/31) 실거래가 엑셀을
    시도 단위로 한 번에 다운로드하여 data_lake 에 저장한다.

사용법:
    python collect_rt_molit_yearly.py --year 2025
    python collect_rt_molit_yearly.py --year 2025 --thing A
    python collect_rt_molit_yearly.py --year 2025 --sido 서울특별시   (특정 시도만)

물건종류(--thing): A=아파트, B=연립다세대, C=단독다가구, D=오피스텔, E=상업업무용, F=공장창고등, G=토지, H=분양입주권
거래구분: 매매(1) 고정
"""

import argparse
import time
from pathlib import Path
import requests

BASE_URL = "https://rt.molit.go.kr"
DATA_LAKE_DIR = Path(r"D:\data\data_lake")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": f"{BASE_URL}/pt/xls/xls.do",
}

def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get(f"{BASE_URL}/pt/xls/xls.do")  # JSESSIONID 쿠키 획득
    return session

def get_sido_list(session: requests.Session) -> list[dict]:
    resp = session.get(f"{BASE_URL}/data/sido.do")
    resp.raise_for_status()
    return resp.json()

def find_sido_code(session: requests.Session, sido_name: str) -> str:
    for item in get_sido_list(session):
        if item["ctprvnNm"] == sido_name:
            return item["signguCode"]
    raise SystemExit(f"알 수 없는 시도명: {sido_name}")


THING_NAME = {
    "A": "아파트",
    "B": "연립다세대",
    "C": "단독다가구",
    "D": "오피스텔",
    "E": "상업업무용",
    "F": "공장창고등",
    "G": "토지",
    "H": "분양입주권",
}
DELNG_SECD = "1"  # 매매 고정

SLEEP_SEC = 1.0  # 요청 간 간격 (서버 부하 방지)

def download_excel(
    session: requests.Session,
    *,
    sido_name: str,
    from_dt: str,
    to_dt: str,
    thing_no: str = "A",
    delng_secd: str = "1",
) -> Path:
    sido_code = find_sido_code(session, sido_name)

    form = {
        "srhThingNo": thing_no,
        "srhDelngSecd": delng_secd,
        "srhAddrGbn": "1",
        "srhLfstsSecd": "1",
        "sidoNm": sido_name,
        "sggNm": "",
        "emdNm": "",
        "loadNm": "",
        "areaNm": "",
        "hsmpNm": "",
        "mobileAt": "",
        "srhFromDt": from_dt,
        "srhToDt": to_dt,
        "srhNewRonSecd": "",
        "srhSidoCd": sido_code,
        "srhSggCd": "",
        "srhEmdCd": "",
        "srhRoadNm": "",
        "srhLoadCd": "",
        "srhHsmpCd": "",
        "srhArea": "",
        "srhLrArea": "",
        "srhFromAmount": "",
        "srhToAmount": "",
    }

    resp = session.post(f"{BASE_URL}/pt/xls/ptXlsExcelDown.do", data=form)
    resp.raise_for_status()

    # 응답 헤더의 Content-disposition에서 서버가 정해준 파일명을 추출
    disposition = resp.headers.get("Content-disposition", "")
    if "filename=" in disposition:
        raw_name = disposition.split("filename=")[-1].strip('"')
        # requests는 헤더를 latin-1로 디코딩하므로 원래 UTF-8 바이트로 되돌린다
        filename = raw_name.encode("latin-1").decode("utf-8")
    else:
        filename = f"{sido_name}_{from_dt}_{to_dt}.xlsx"

    DATA_LAKE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_LAKE_DIR / filename
    out_path.write_bytes(resp.content)
    return out_path



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", required=True, type=int, help="연도 (예: 2025)")
    parser.add_argument("--thing", default="A", help="물건종류 (기본값 A=아파트)")
    parser.add_argument("--sido", default=None, help="특정 시도만 실행 (미지정시 전체)")
    args = parser.parse_args()

    from_dt = f"{args.year}-01-01"
    to_dt = f"{args.year}-12-31"

    session = get_session()
    sido_list = get_sido_list(session)

    if args.sido:
        sido_list = [s for s in sido_list if s["ctprvnNm"] == args.sido]
        if not sido_list:
            raise SystemExit(f"알 수 없는 시도명: {args.sido}")

    thing_name = THING_NAME.get(args.thing, args.thing)

    for item in sido_list:
        sido_name = item["ctprvnNm"]
        print(f"[다운로드 시작] {sido_name} ({args.year}년)")
        try:
            out_path = download_excel(
                session,
                sido_name=sido_name,
                from_dt=from_dt,
                to_dt=to_dt,
                thing_no=args.thing,
                delng_secd=DELNG_SECD,
            )
            renamed = DATA_LAKE_DIR / f"{sido_name}_{args.year}_{thing_name}_실거래가.xlsx"
            out_path.rename(renamed)
            print(f"[완료] {renamed}")
        except Exception as e:
            print(f"[실패] {sido_name}: {e}")

        time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    main()
