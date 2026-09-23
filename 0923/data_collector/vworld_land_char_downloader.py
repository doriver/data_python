# 브이월드(vworld.kr) "토지특성정보" 데이터셋(dsId=4)의 CSV/SHP 파일을 특정 연도 기준 전국 일괄 다운로드한다.
#
# [다운로드 URL 규칙 정리]
#   https://www.vworld.kr/dtmk/downloadResourceFile.do?ds_id={ds_id}&fileNo={fileNo}
#     - ds_id  : 데이터셋+포맷 고정 ID. 토지특성정보 CSV = 20171128DS00179, 토지특성공간정보 SHP = 20171128DS00178
#     - fileNo : 목록 화면의 dsFileSq. DB 전역 시퀀스라서 지역/연도로부터 계산해 낼 수 있는 규칙이 없다.
#                따라서 목록 조회 화면(dtmk_ntads_s002.do)을 긁어서 (지역, 기준일) -> fileNo 를 얻어야 한다.
#   목록 화면의 다운로드 버튼은 listFnc.download('{ds_id}', '{fileNo}', '{용량KB}') 형태로 렌더링된다.
#   용량이 500MB(512000KB)를 넘으면 사이트는 downloadDtnaResourceFile.do?ds_file_sq={ds_id}{fileNo} 를 사용한다.
#
# [주의] 다운로드는 로그인 세션이 있어야 한다. 비로그인 상태로 호출하면 Content-Length: 0 인 빈 응답이 온다.
#        아이디/비번으로 직접 로그인하는 대신, collect_vworld_csv.py 와 같은 방식으로
#        브라우저에서 로그인 후 복사한 쿠키(.env의 VWORLD_COOKIE)를 그대로 사용한다.
#        (PJSESSIONID 등 세션 쿠키라 시간이 지나면 만료되므로, 요청이 실패하면 다시 로그인 후 쿠키를 갱신해야 한다)
#
# [연도별 제공 단위가 다름]
#   - 2017년 등 과거 스냅샷: 시·군·구 단위로 250여 개 파일
#   - 최근 스냅샷: 시·도 단위로 17개 파일
#   한 스냅샷 안에서도 기준일이 며칠씩 갈리므로(예: 2024-07-30 / 2024-08-02),
#   전국 시도의 절반 이상이 한꺼번에 올라온 날짜를 '본 배포일'로 보고, 나머지 소수 정정 파일은
#   가장 가까운 본 배포일에 붙여서 하나의 스냅샷으로 묶는다.
#
# 사용 예:
#   python vworld_land_char_downloader.py --year 2026 --list-only
#   python vworld_land_char_downloader.py --year 2026
#   python vworld_land_char_downloader.py --year 2024 --snapshot first
#   python vworld_land_char_downloader.py --year 2026 --format SHP --out data/basis/shp
import argparse
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime

import requests
from dotenv import load_dotenv

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BASE = "https://www.vworld.kr"
LIST_URL = f"{BASE}/dtmk/dtmk_ntads_s002.do"
DOWNLOAD_URL = f"{BASE}/dtmk/downloadResourceFile.do"
BULK_DOWNLOAD_URL = f"{BASE}/dtmk/downloadDtnaResourceFile.do"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

VWORLD_COOKIE = os.environ.get("VWORLD_COOKIE", "")

DATASET_ID = "4"  # 토지특성정보 데이터셋
# 사이트가 단일 다운로드 대신 대용량 다운로드로 넘기는 임계치(KB)
LARGE_FILE_KB = 512_000
OUTPUT_DIR = r"D:\tmpData"
REQUEST_DELAY_SEC = 0.5

# 사이트의 sidoCd 필터는 전남/광주를 12번 하나로 묶어놔서 --sido 만으로는 둘을 구분할 수 없다.
# --region 옵션에 약칭을 입력하면 실제 목록에 찍히는 정식 명칭으로 바꿔 클라이언트에서 한 번 더 거른다.
SIDO_ALIASES = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}

# 목록 화면 <li> 한 건을 통째로 잡는다.
ROW_RE = re.compile(r'<li><!--v-for="n in 10"-->(.*?)</li>', re.S)
FIELD_RES = {
    "file_no": re.compile(r'name="dsFileSq" value="(\d+)"'),
    "ds_id": re.compile(r'name="dsFileId" value="([^"]+)"'),
    "file_format": re.compile(r'<div class="format"><span class="\w+">(\w+)</span>'),
    "title": re.compile(r'<div class="tit min">([^<]*)</div>'),
    "gbn": re.compile(r"구분<em>([^<]*)</em>"),
    "base_date": re.compile(r'기준일<em class="xxs">([^<]*)</em>'),
    "update_date": re.compile(r'갱신일<em class="xxs">([^<]*)</em>'),
}
# 다운로드 버튼: listFnc.download('{ds_id}', '{fileNo}', '{용량KB}')
# 화면의 "용량" 표기는 KB/MB가 섞여 나오므로, 사이트가 대용량 판정에 쓰는 이 세 번째 인자(KB)를 그대로 쓴다.
DOWNLOAD_BTN_RE = re.compile(r"listFnc\.download\('([^']+)',\s*'(\d+)',\s*'(\d+)'\)")
PATH_RE = re.compile(r'<div class="path bg min">(.*?)</div>', re.S)
TAG_RE = re.compile(r"<[^>]+>")
TOTAL_RE = re.compile(r"총<b>(\d+)</b>건")
DISPOSITION_RE = re.compile(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", re.I)


"""HTML 조각에서 태그를 걷어내고 공백을 정리한다."""
def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", fragment)).strip()


"""목록 화면 HTML을 파싱해 파일 레코드 리스트로 만든다."""
def parse_rows(html: str):
    rows = []
    for match in ROW_RE.finditer(html):
        block = match.group(1)
        row = {}
        for key, pattern in FIELD_RES.items():
            found = pattern.search(block)
            row[key] = found.group(1).strip() if found else ""
        path_found = PATH_RE.search(block)
        region = _text(path_found.group(1)) if path_found else ""
        row["region"] = region
        row["sido"] = region.split(" ")[0] if region else ""
        row["sigungu"] = region.split(" ", 1)[1] if " " in region else ""
        button = DOWNLOAD_BTN_RE.search(block)
        if button:
            row["ds_id"] = button.group(1)
            row["file_no"] = button.group(2)
            row["size_kb"] = int(button.group(3))
        else:
            row["size_kb"] = 0
        rows.append(row)
    return rows


"""검색 조건으로 목록 화면을 끝까지 페이징하며 전체 파일 레코드를 수집한다.

    start_date/end_date 는 '기준일' 범위 필터라서, 특정 연도를 뽑을 때 이 값을 그 해의 1/1~12/31로 준다.
"""
def fetch_file_list(session, start_date: str, end_date: str, file_format: str, sido_cd: str = "", page_size: int = 100):
    collected = []
    page_index = 1
    while True:
        params = {
            "dsId": DATASET_ID,
            "dataSetSeq": DATASET_ID,
            "svcCde": "NA",
            "datIde": "",
            "datPageIndex": page_index,
            "datPageSize": page_size,
            "pageIndex": page_index,
            "pageSize": page_size,
            "pageUnit": page_size,
            "startDate": start_date,
            "endDate": end_date,
            "sidoCd": sido_cd,
            "sigunguCd": "",
            "fileGbnCd": "AL",  # 전체데이터(변동데이터 CH 제외)
            "dsNm": "",
            "formatSelect": file_format,
        }
        response = session.get(LIST_URL, params=params, timeout=60)
        response.raise_for_status()
        html = response.text

        if page_index == 1:
            total_found = TOTAL_RE.search(html)
            total = int(total_found.group(1)) if total_found else 0
            print(f"조회 결과: 총 {total}건 (기준일 {start_date} ~ {end_date}, 포맷 {file_format})")
            if total == 0:
                return []

        rows = parse_rows(html)
        if not rows:
            break
        collected.extend(rows)
        if len(collected) >= total:
            break
        page_index += 1
        time.sleep(REQUEST_DELAY_SEC)
    return collected


"""기준일 근처 레코드끼리 하나의 스냅샷(회차)으로 묶는다.

    같은 회차라도 정정 파일 때문에 기준일이 몇 주씩 벌어질 수 있어서, 단순히 '직전 기준일과의
    차이'만 보고 사슬처럼 이어붙이면(예전 방식) 간격이 우연히 다 SNAPSHOT_GAP_DAYS 이내로 이어져
    서로 다른 두 회차(예: 전국 17개 시도가 각각 완전히 새로 올라온 두 번의 배포)가 하나로 합쳐지는
    문제가 있었다. 그래서 "그 날짜에 몇 개 시도 파일이 한꺼번에 올라왔는지"를 봐서, 전국 시도의
    절반 이상이 한꺼번에 올라온 날짜만 회차의 '본 배포일(anchor)'로 인정한다. 1~2건짜리 정정 파일은
    가장 가까운 본 배포일에 붙인다.
    반환값은 오래된 회차부터의 리스트이며, 각 원소는 (대표기준일, 레코드리스트) 튜플이다.
"""
def group_snapshots(rows):
    dated = [r for r in rows if r["base_date"]]
    if not dated:
        return []
    for row in dated:
        row["_date"] = datetime.strptime(row["base_date"], "%Y-%m-%d").date()

    by_date = {}
    for row in dated:
        by_date.setdefault(row["_date"], []).append(row)

    sido_count = len({r["sido"] for r in dated if r["sido"]}) or 1
    anchor_min_files = max(sido_count // 2, 1)
    anchor_dates = sorted(d for d, group in by_date.items() if len(group) >= anchor_min_files)
    if not anchor_dates:
        anchor_dates = [max(by_date, key=lambda d: len(by_date[d]))]

    buckets = {d: [] for d in anchor_dates}
    for d, group in by_date.items():
        nearest = min(anchor_dates, key=lambda a: abs((a - d).days))
        buckets[nearest].extend(group)

    snapshots = []
    for anchor in anchor_dates:
        group = sorted(buckets[anchor], key=lambda r: r["_date"])
        snapshots.append((group[-1]["base_date"], group))
    return snapshots


"""'k1=v1; k2=v2' 형태의 쿠키 문자열을 dict로 쪼갠다."""
def _parse_cookie_string(cookie_str: str) -> dict:
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


"""Content-Disposition 헤더에서 파일명을 뽑아낸다. 없으면 None."""
def _filename_from_headers(headers):
    disposition = headers.get("Content-Disposition", "")
    found = DISPOSITION_RE.search(disposition)
    if not found:
        return None
    raw = found.group(1)
    # 서버가 EUC-KR/UTF-8 바이트를 latin-1로 흘려보내는 경우가 있어 순서대로 복원 시도
    for encoding in ("utf-8", "cp949"):
        try:
            decoded = raw.encode("latin-1").decode(encoding)
            if decoded:
                return unicodedata.normalize("NFC", decoded)
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return unicodedata.normalize("NFC", raw)


"""파일명으로 쓸 수 없는 문자를 걷어낸다."""
def _safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "unnamed"


"""저장 파일명을 "{지역}_토지특성정보_{기준일}{확장자}" 형식으로 만든다.

    확장자는 서버가 내려준 실제 파일명(Content-Disposition)에서 그대로 따오고,
    알 수 없으면 .zip으로 둔다(브이월드는 CSV/SHP를 zip으로 압축해 내려줌).
"""
def _build_filename(row, server_filename: str | None) -> str:
    ext = os.path.splitext(server_filename)[1] if server_filename else ""
    ext = ext or ".zip"
    region = row["region"].replace(" ", "_") or row["file_no"]
    return _safe_name(f"{region}_토지특성정보_{row['base_date']}{ext}")


"""레코드 1건을 내려받아 out_dir에 저장한다. 이미 있으면 건너뛴다."""
def download_row(session, row, out_dir: str):
    if row["size_kb"] > LARGE_FILE_KB:
        url = BULK_DOWNLOAD_URL
        params = {"ds_file_sq": f"{row['ds_id']}{row['file_no']}"}
    else:
        url = DOWNLOAD_URL
        params = {"ds_id": row["ds_id"], "fileNo": row["file_no"]}

    with session.get(url, params=params, stream=True, timeout=600,
                     headers={"Referer": f"{LIST_URL}?dsId={DATASET_ID}&svcCde=NA"}) as response:
        response.raise_for_status()
        length = int(response.headers.get("Content-Length") or 0)
        content_type = response.headers.get("Content-Type", "")
        if length == 0 or "text/html" in content_type:
            raise RuntimeError(
                f"빈 응답(로그인 세션 만료 또는 권한 없음) - fileNo={row['file_no']} content-type={content_type}"
            )

        filename = _build_filename(row, _filename_from_headers(response.headers))
        path = os.path.join(out_dir, filename)
        if os.path.exists(path) and os.path.getsize(path) == length:
            print(f"  건너뜀(이미 있음): {filename}")
            return path

        written = 0
        with open(path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)
                written += len(chunk)
        print(f"  저장: {filename} ({written / 1048576:.1f} MB)")
        return path


"""수집한 레코드를 한 줄씩 보기 좋게 출력한다."""
def print_rows(rows):
    for row in rows:
        print(
            f"  {row['base_date']}  {row['file_format']:<3}  ds_id={row['ds_id']}  fileNo={row['file_no']:>5}"
            f"  {row['size_kb']:>9,}KB  {row['region']}"
        )


def parse_args():
    parser = argparse.ArgumentParser(description="브이월드 토지특성정보 전국 일괄 다운로드")
    parser.add_argument("--year", type=int, help="기준일 연도 (예: 2026). --start/--end 를 주면 무시된다.")
    parser.add_argument("--start", help="기준 시작일 YYYY-MM-DD")
    parser.add_argument("--end", help="기준 종료일 YYYY-MM-DD")
    parser.add_argument("--format", dest="file_format", default="CSV", choices=["CSV", "SHP"], help="파일 포맷")
    parser.add_argument(
        "--snapshot",
        default="first",
        help="내려받을 회차: latest | first(기본) | all | YYYY-MM-DD(해당 회차의 대표 기준일)",
    )
    parser.add_argument("--sido", default="", help="시도 코드로 제한 (예: 11=서울). 비우면 전국")
    parser.add_argument(
        "--region",
        default="",
        help="지역명으로 제한 (예: 전남 또는 전라남도). sidoCd가 광주/전남처럼 여러 시도를 묶어서 --sido 만으로 못 거를 때 사용",
    )
    parser.add_argument("--out", default=OUTPUT_DIR, help=f"저장 폴더 (기본 {OUTPUT_DIR})")
    parser.add_argument("--list-only", action="store_true", help="다운로드 없이 목록만 출력")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.start and args.end:
        start_date, end_date = args.start, args.end
    elif args.year:
        start_date, end_date = f"{args.year}-01-01", f"{args.year}-12-31"
    else:
        today = date.today()
        start_date, end_date = f"{today.year}-01-01", f"{today.year}-12-31"

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    # 로그인 쿠키는 목록 조회보다 먼저 주입해야 한다. 목록 조회를 먼저 하면 서버가 익명 세션 쿠키를
    # Set-Cookie로 내려보내고, 그 뒤에 로그인 쿠키를 넣어도 쿠키 저장소에 동일 이름(PJSESSIONID 등)의
    # 쿠키가 도메인 속성만 다른 채로 공존하게 되어, 다운로드 요청 시 서버가 먼저 만들어진 익명 세션 쪽을
    # 채택해버린다(= 로그인 쿠키가 무시되어 빈 응답이 옴).
    if VWORLD_COOKIE:
        session.cookies.update(_parse_cookie_string(VWORLD_COOKIE))

    rows = fetch_file_list(session, start_date, end_date, args.file_format, args.sido)
    if not rows:
        print("해당 조건의 파일이 없습니다. 기준일 범위를 넓혀 보세요.")
        return

    # 회차(anchor) 판단은 전국 시도 수를 기준으로 하므로, --region 필터보다 먼저 전체 rows로 묶는다.
    snapshots = group_snapshots(rows)

    if args.region:
        resolved_region = SIDO_ALIASES.get(args.region, args.region)
        snapshots = [(base_date, [r for r in group if r["sido"] == resolved_region]) for base_date, group in snapshots]
        snapshots = [(base_date, group) for base_date, group in snapshots if group]
        total = sum(len(group) for _, group in snapshots)
        print(f"지역 필터 적용: {resolved_region} ({total}건)")
        if not snapshots:
            print("해당 지역의 파일이 없습니다. --region 값을 확인해 보세요.")
            return

    print(f"회차 {len(snapshots)}개 감지:")
    for base_date, group in snapshots:
        sido_count = len({r["sido"] for r in group})
        print(f"  - {base_date} : {len(group)}개 파일 / 시도 {sido_count}곳")

    if args.snapshot == "all":
        targets = [row for _, group in snapshots for row in group]
    elif args.snapshot == "first":
        targets = snapshots[0][1]
    elif args.snapshot == "latest":
        targets = snapshots[-1][1]
    else:
        matched = [group for base_date, group in snapshots if base_date == args.snapshot]
        if not matched:
            matched = [group for _, group in snapshots if any(r["base_date"] == args.snapshot for r in group)]
        if not matched:
            print(f"기준일 {args.snapshot} 에 해당하는 회차가 없습니다.")
            return
        targets = matched[0]

    targets.sort(key=lambda r: (r["sido"], r["sigungu"]))
    print(f"\n대상 {len(targets)}건")
    print_rows(targets)

    if args.list_only:
        return

    if not VWORLD_COOKIE:
        print("\n.env 의 VWORLD_COOKIE 가 비어있습니다. 브라우저 개발자도구(F12) > Network 탭에서")
        print("로그인 후 요청의 Cookie 헤더 전체 값을 복사해 넣어주세요. 쿠키 없이는 빈 파일만 내려옵니다.")
        return

    os.makedirs(args.out, exist_ok=True)

    failed = []
    print(f"\n다운로드 시작 -> {args.out}")
    for index, row in enumerate(targets, start=1):
        print(f"[{index}/{len(targets)}] {row['region']} (fileNo={row['file_no']})")
        try:
            download_row(session, row, args.out)
        except Exception as error:  # 한 건 실패해도 나머지는 계속 받는다.
            print(f"  실패: {error}")
            failed.append(row)
        time.sleep(REQUEST_DELAY_SEC)

    print(f"\n완료: 성공 {len(targets) - len(failed)}건 / 실패 {len(failed)}건")
    for row in failed:
        print(f"  실패 - {row['region']} ds_id={row['ds_id']} fileNo={row['file_no']}")


if __name__ == "__main__":
    main()
