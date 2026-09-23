# D:\tmpData 에 내려받은 토지특성정보 zip 파일을 전부 찾아 일괄 압축 해제한다.
# (vworld_land_char_downloader.py 로 받은 zip은 안에 csv/shp가 그대로 들어있다)
import argparse
import glob
import os
import shutil
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

SOURCE_DIR = r"D:\tmpData"
# 압축 해제 결과물의 기본 위치. zip 원본(SOURCE_DIR)과 섞이지 않도록 하위 폴더에 따로 모은다.
EXTRACT_DIR = os.path.join(SOURCE_DIR, "files")
# 압축 해제 시 한 번에 메모리에 올릴 크기. 토지특성정보 zip은 500MB~1GB대라 통째로 읽으면 느리다.
COPY_CHUNK_SIZE = 8 * 1024 * 1024
# 동시에 압축 해제할 zip 개수. 압축 해제(zlib)는 파이썬 GIL을 풀어주므로 스레드로도 병렬 이득이 있다.
MAX_WORKERS = min(4, os.cpu_count() or 1)


"""zip 내부 항목 이름이 cp437로 잘못 디코딩되어 깨진 경우 원래 한글 이름으로 복원을 시도한다.

    (파이썬 zipfile은 UTF-8 플래그가 없는 zip 항목명을 cp437로 디코딩하는데,
     압축 프로그램이 실제로는 utf-8/cp949로 인코딩했다면 이름이 깨져 보인다)
"""
def _fix_member_name(name: str) -> str:
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name
    for encoding in ("utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return name


"""zip_path 파일을 out_dir에 압축 해제한다. out_dir이 없으면 만든다. 이미 풀려있는 파일은 건너뛴다.

    안에 파일이 딱 1개뿐이면(브이월드 zip은 보통 csv/shp 1개만 들어있음) 결과 파일명을
    원래 압축 내부 이름 대신 zip 파일명과 동일하게(확장자만 원본 것 유지) 바꿔서 저장한다.
    파일이 여러 개면 이름이 겹칠 수 있어 원래 이름을 그대로 쓴다.
"""
def extract_zip(zip_path: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    zip_stem = os.path.splitext(os.path.basename(zip_path))[0]

    with zipfile.ZipFile(zip_path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        rename_to_zip_name = len(members) == 1

        for info in archive.infolist():
            fixed_name = _fix_member_name(info.filename)
            if info.is_dir():
                os.makedirs(os.path.join(out_dir, fixed_name), exist_ok=True)
                continue

            if rename_to_zip_name:
                ext = os.path.splitext(fixed_name)[1]
                fixed_name = f"{zip_stem}{ext}"

            target_path = os.path.join(out_dir, fixed_name)
            if os.path.exists(target_path):
                print(f"  건너뜀(이미 있음): {fixed_name}")
                continue

            os.makedirs(os.path.dirname(target_path) or out_dir, exist_ok=True)
            with archive.open(info) as source, open(target_path, "wb") as dest:
                shutil.copyfileobj(source, dest, length=COPY_CHUNK_SIZE)
            print(f"  압축 해제: {fixed_name}")


"""directory 안에서 확장자가 .zip인 파일 경로를 전부 찾는다(하위 폴더는 뒤지지 않는다)."""
def find_zip_files(directory: str):
    return sorted(glob.glob(os.path.join(directory, "*.zip")))


def parse_args():
    parser = argparse.ArgumentParser(description=f"{SOURCE_DIR} 안의 zip 파일을 전부 압축 해제한다.")
    parser.add_argument("--dir", default=SOURCE_DIR, help=f"zip 파일을 찾을 폴더 (기본 {SOURCE_DIR})")
    parser.add_argument("--out", default=EXTRACT_DIR, help=f"압축 해제 위치 (기본 {EXTRACT_DIR})")
    return parser.parse_args()


def main():
    args = parse_args()
    zip_paths = find_zip_files(args.dir)
    if not zip_paths:
        print(f"{args.dir} 에 zip 파일이 없습니다.")
        return

    out_dir = args.out
    print(f"zip 파일 {len(zip_paths)}개 발견 -> {out_dir} 에 압축 해제 (동시 {MAX_WORKERS}개)")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(extract_zip, zip_path, out_dir): zip_path for zip_path in zip_paths}
        for future in as_completed(futures):
            zip_path = futures[future]
            future.result()
            print(f"완료: {os.path.basename(zip_path)}")
    print("전체 완료")


if __name__ == "__main__":
    main()
