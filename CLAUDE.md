# CLAUDE.md

## 프로젝트 개요

한국 토지/부동산 데이터 파이프라인입니다. 공시지가, 실거래가, 좌표, 기타 다른 정보들을 로컬 MySQL 데이터베이스에 적재하는걸 목표. 소스 데이터, 코드 주석, 문서 모두 한국어로 작성되어 있습니다. 소스데이터 파일 형식으론 shp, xlsx 등을 사용한다.

## 환경 및 명령어

- Python 3.12, 의존성은 로컬 `venv\`에 설치되어 있습니다 (저장소에 `requirements.txt`/`pyproject.toml` 없음 — 설치된 패키지는 `venv\Scripts\pip.exe list`로 확인: geopandas, pymysql, python-dotenv, pandas, shapely, pyproj, pyogrio 등).
- PowerShell에서 venv 활성화: `venv\Scripts\Activate.ps1`
- 스크립트 실행: `venv\Scripts\python.exe <스크립트 파일>`
- 새 의존성 설치: `venv\Scripts\pip.exe install <package>` (업데이트할 매니페스트 파일이 없음)
- 이 저장소에는 테스트, 린터, 빌드 단계가 설정되어 있지 않습니다.

### 데이터베이스 설정

- `.env.example`을 `.env`로 복사하고 `MYSQL_USER`/`MYSQL_PASSWORD`를 설정하세요 (host/port/database는 기본값 `127.0.0.1:3307`/`data01`이며, 로컬 MySQL 인스턴스를 가리킵니다).
- 스크립트는 `python-dotenv`의 `load_dotenv()`로 설정을 불러옵니다. `MYSQL_USER`/`MYSQL_PASSWORD`는 필수 환경변수이며 설정하지 않으면 `KeyError`가 발생합니다.
- `.env`, `shp\`, `xlsx\`, `venv\`는 모두 gitignore 대상입니다 — 원본 지리데이터와 DB 자격증명은 커밋되지 않습니다. 환경마다 이 디렉터리들의 내용이 다를 수 있다는 점에 유의하세요.

## 아키텍처

### 셰이프파일 속성 매핑

이 데이터 소스의 셰이프파일은 설명적인 컬럼명 대신 알아보기 어려운 코드(`A0`, `A2`, `A5` 등)를 사용합니다. 개별공시지가 셰이프파일(`shp/AL_D152_11_20260520.shp`)의 매핑은 `docs/shp_to_db.md`에 문서화되어 있습니다:

| SHP 컬럼 | 의미 | DB 컬럼 |
|---|---|---|
| A0 | 고유번호(PNU) | `pnu` |
| A2 | 법정동명 | `bjdong_name` |
| A5 | 지번 | `jibun` |
| A4 | 대장구분명 | `ledger_division_name` |
| A9 | 공시지가 | `official_land_price` |
| A14 | 면적 | `area` |
| A13 | 지목 | `land_category` |
| A16 | 용도지역명 | `use_district_name` |

다른 셰이프파일(예: `shp/토지특성정보/`)을 다룰 때는 동일한 `A*` 코드가 적용된다고 가정하지 말고, 먼저 데이터나 `.dbf` 스키마를 확인해야 합니다.

### 주요 파일

- `official_land_price_to_db.py` : 개별공시지가 SHP를 읽어 MySQL에 `official_land_price_seoul` 테이블이 없으면 생성하고(`coordinates`에 `SPATIAL INDEX` 포함), row를 배치 삽입합니다 (`INSERT_BATCH_SIZE = 500`).
- `docs/shp_to_db.md` — 위 스크립트의 스펙/노트(스키마 + 컬럼 매핑). 참고 문서라기보다 작업 지시서 형태로 작성되어 있으며, SHP→DB 매핑의 기준(source of truth)으로 취급하면 됩니다.
