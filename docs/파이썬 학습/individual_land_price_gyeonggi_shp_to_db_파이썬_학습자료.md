# `individual_land_price_gyeonggi_shp_to_db.py`로 배우는 파이썬 기본기

[`find_land_pnu.py` 학습자료](find_land_pnu_파이썬_학습자료.md)의 후속편입니다. f-string, `if/else`, `with`문처럼 이미 다룬 문법은 간단히만 짚고, 이 파일에만 새로 나오는 문법·관용구 위주로 설명합니다. (SHP 파일을 읽어 geometry를 좌표로 바꾸고, MySQL에 직접 INSERT하는 스크립트)

---

## 1. `.env` 파일에서 환경변수 읽기 — `python-dotenv`

```python
from dotenv import load_dotenv

load_dotenv()
```

- `from 모듈 import 이름` — 모듈 전체가 아니라 그 안의 특정 함수/클래스만 이름으로 바로 가져옵니다. `import dotenv` 후 `dotenv.load_dotenv()`라고 매번 쓰는 대신, `load_dotenv()`라고 짧게 쓸 수 있게 해줍니다.
- `load_dotenv()`는 프로젝트 루트의 `.env` 파일(`MYSQL_USER=xxx` 같은 줄들)을 읽어서, 파이썬 프로세스의 **환경변수**로 등록해주는 함수입니다. `.env` 파일 자체는 파이썬 문법이 아니라 `키=값` 형태의 텍스트 파일입니다.

```python
DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ["MYSQL_USER"]
```

- `os.environ`은 환경변수 전체를 담은 딕셔너리 같은 객체입니다.
- `os.environ.get("키", "기본값")` — 키가 없어도 에러 없이 기본값을 돌려줍니다(포트/호스트처럼 없어도 되는 값에 사용).
- `os.environ["키"]` — 대괄호로 직접 접근하면, **키가 없을 때 `KeyError`로 즉시 에러**가 납니다. `MYSQL_USER`/`MYSQL_PASSWORD`처럼 반드시 있어야 하는 필수값에 일부러 이 방식을 씁니다(CLAUDE.md에도 명시된 의도적 설계).
- `int(...)` — 문자열을 정수로 변환. 환경변수는 항상 문자열이라서, 포트 번호처럼 숫자로 써야 할 때는 명시적으로 변환해야 합니다.

## 2. 여러 줄 f-string으로 SQL 문자열 만들기

```python
CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id BIGINT NOT NULL AUTO_INCREMENT,
    ...
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""
```

- `f"""..."""` — f-string(이전 자료 참고)과 여러 줄 문자열(`"""..."""`)을 합친 형태. 문자열 안 줄바꿈이 그대로 유지되면서, `{TABLE_NAME}` 자리에 상수 값이 끼워집니다.
- 이 상수는 SQL문 텍스트 자체이고, 실행은 나중에 `cursor.execute(CREATE_TABLE_SQL)`에서 이루어집니다. 즉 여기서는 "SQL 문자열을 미리 조립"만 하는 단계입니다.

```python
INSERT_SQL = f"""
INSERT INTO {TABLE_NAME}
    (pnu, bjdong_code, ...)
VALUES
    (%s, %s, ..., ST_SRID(POINT(%s, %s), 4326))
"""
```

- `%s`는 파이썬 문자열 포매팅 기호가 **아니라**, `pymysql`(DB 드라이버)이 이해하는 **placeholder(자리표시자)**입니다. 실제 값은 나중에 `cursor.execute(INSERT_SQL, 값들)`처럼 별도 인자로 넘겨서, 드라이버가 안전하게 치환합니다.
- 이렇게 값을 `%s`로 분리해서 넘기는 이유는 **SQL 인젝션 방지**입니다. `f"INSERT INTO ... VALUES ({user_input})"`처럼 문자열을 직접 조립하면 위험하지만, `%s` + 별도 인자 방식은 드라이버가 값을 이스케이프 처리해줍니다.

## 3. 함수 안에서 `None`/`NaN` 처리하기

```python
def none_if_nan(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
```

- `isinstance(값, 타입)` — 값이 특정 타입인지 검사합니다(자바의 `instanceof`와 동일). `type(값) == float`와 비슷하지만, 상속 관계까지 고려하는 더 안전한 방식이라 파이썬에서는 `isinstance`를 표준으로 씁니다.
- `math.isnan(값)` — 부동소수점 특수값 `NaN`(Not a Number)인지 확인. `값 == float("nan")`은 항상 `False`가 나오는 파이썬(과 대부분 언어)의 특성 때문에, 반드시 `math.isnan()` 같은 전용 함수로 검사해야 합니다.
- `and` — 일반 값 하나에 대한 논리 AND(컬럼 전체에 쓰는 pandas의 `&`와는 다름, [이전 자료](find_land_pnu_파이썬_학습자료.md) 9번 참고). `isinstance(...)`가 먼저 `True`여야 `math.isnan(...)`을 검사하므로, `value`가 float가 아닐 때 `math.isnan()`이 엉뚱한 타입을 받아 에러나는 것을 방지합니다(단락 평가, short-circuit).
- 함수 안에 `return`이 여러 번 있어도 됩니다. 어느 하나라도 실행되면 그 즉시 함수가 끝나고 값을 돌려줍니다.

## 4. geopandas로 SHP 읽고 좌표계 변환하기

```python
gdf = gpd.read_file(SHP_PATH, encoding="cp949")
gdf["area_sqm"] = gdf.geometry.area
gdf = gpd.to_crs(epsg=4326)
```

- `gpd.read_file(...)`은 SHP(Shapefile)를 읽어 **GeoDataFrame**(pandas의 DataFrame에 `geometry`라는 특수 컬럼이 추가된 것)을 만듭니다.
- `gdf.geometry`는 각 행의 도형(점/폴리곤 등) 객체가 담긴 컬럼. `.area`를 붙이면 각 도형의 면적을 한 번에 계산해서 새 컬럼(`area_sqm`)으로 저장합니다(이전 자료의 `.str.len()`처럼, 컬럼 전체에 벡터화된 연산을 적용하는 패턴).
- `.to_crs(epsg=4326)` — 좌표계(CRS, Coordinate Reference System)를 변환. 원본은 미터 단위 좌표계(EPSG:5186)인데, 위경도(EPSG:4326, GPS가 쓰는 좌표계)로 바꿉니다. **주석에 적혀 있듯, 면적 계산은 변환 전(미터 단위)에 먼저 해야 정확**합니다 — 위경도 좌표계에서 면적을 계산하면 지구가 둥글어서 값이 왜곡되기 때문입니다.

## 5. `for _, row in ...` — 사용하지 않는 변수는 `_`

```python
for _, row in gdf.iterrows():
    centroid = row.geometry.centroid
    ...
```

- `gdf.iterrows()`는 각 행을 `(인덱스, 행데이터)` 튜플로 하나씩 돌려줍니다.
- `for _, row in ...` — 튜플 언패킹(이전 자료 4번)인데, 첫 번째 값(인덱스)은 안 쓸 거라서 관례적으로 변수명을 `_`(밑줄 하나)로 둡니다. "이 값은 필요 없어서 이름도 안 붙인다"는 파이썬의 흔한 관용구입니다.
- `row.geometry.centroid` — 도형의 중심점(centroid) 객체를 구함. 뒤에서 `centroid.x`, `centroid.y`로 경도/위도 값을 꺼내 씁니다.

## 6. 삼항 표현식으로 결측치 대체

```python
area = row["A13"] if not (isinstance(row["A13"], float) and math.isnan(row["A13"])) else row["area_sqm"]
```

- 이전 자료 4번에서 본 `A if 조건 else B`의 실전 예시. 풀어 쓰면:

```python
if isinstance(row["A13"], float) and math.isnan(row["A13"]):
    area = row["area_sqm"]
else:
    area = row["A13"]
```

- `not (...)` — 괄호 안 조건을 뒤집습니다("~이 아니면"). "A13이 NaN이면 area_sqm을, 아니면(=NaN이 아니면) A13 값을 쓴다"는 뜻을 한 줄로 압축한 것입니다.

## 7. 튜플 리스트를 쌓아서 배치(batch)로 만들기

```python
rows = []
for _, row in gdf.iterrows():
    ...
    rows.append(
        (
            row["A0"],
            row["A1"],
            none_if_nan(row["A2"]),
            ...
            centroid.x,
            centroid.y,
        )
    )
```

- 매 반복마다 **튜플 하나**(괄호로 감싼, 콤마로 구분된 값들 — 수정 불가능한 리스트라고 생각하면 됩니다)를 만들어 `rows` 리스트에 쌓습니다.
- 이 튜플의 각 위치가 `INSERT_SQL`의 `%s` 자리와 **순서대로 1:1 대응**합니다. 즉 `rows`는 "DB에 넣을 행 데이터 뭉치 = 튜플의 리스트"입니다.
- 괄호를 여러 줄로 늘여써도(`(\n row["A0"],\n row["A1"],\n ...\n)`) 하나의 튜플 표현식으로 취급됩니다(이전 자료 9번의 "괄호 안에서는 줄바꿈 자유" 규칙과 동일).

## 8. DB 연결 — `pymysql`, `try/finally`

```python
conn = pymysql.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    charset="utf8mb4",
)
try:
    with conn.cursor() as cursor:
        cursor.execute(CREATE_TABLE_SQL)
        ...
    conn.commit()
    print(f"완료: {inserted}건 삽입")
finally:
    conn.close()
```

- `pymysql.connect(...)`로 MySQL 서버에 연결한 커넥션 객체를 얻습니다. 모두 키워드 인자로 넘김(이전 자료 6번).
- `try: ... finally: ...` — `try` 블록 안에서 에러가 나든 안 나든, **`finally` 블록은 반드시 실행**됩니다. 여기서는 "무슨 일이 있어도 `conn.close()`로 연결을 닫아야 한다"는 걸 보장하기 위해 씁니다. (참고로 `with conn:` 형태로도 비슷하게 처리 가능하지만, 이 코드는 명시적으로 `try/finally`를 선택함)
- `with conn.cursor() as cursor:` — 이전 자료 13번에서 본 컨텍스트 매니저. 커서(SQL 실행 단위 객체)를 열고, 블록이 끝나면 자동으로 정리합니다.
- `cursor.execute(SQL문)` — SQL 하나를 실행(여기서는 `CREATE TABLE IF NOT EXISTS`).
- `conn.commit()` — MySQL은 기본적으로 트랜잭션 단위로 동작해서, `commit()`을 호출해야 실제로 DB에 반영됩니다(안 부르면 롤백됨). `with` 블록(커서) 밖, `try` 블록 안에서 마지막에 호출하는 순서에 주의.

## 9. `range()`와 슬라이싱으로 배치 나누기

```python
inserted = 0
for i in range(0, len(rows), INSERT_BATCH_SIZE):
    batch = rows[i : i + INSERT_BATCH_SIZE]
    cursor.executemany(INSERT_SQL, batch)
    inserted += len(batch)
    print(f"삽입 진행: {inserted}/{len(rows)}")
```

- `range(시작, 끝, 증가폭)` — 시작값부터 끝값 **직전까지**, 증가폭만큼 뛰면서 숫자를 만들어주는 반복 가능한 객체. `range(0, len(rows), 500)`은 `0, 500, 1000, 1500, ...`을 순서대로 만듭니다(500개씩 끊어 처리하기 위한 시작 인덱스).
- `rows[i : i + INSERT_BATCH_SIZE]` — 리스트 슬라이싱(이전 자료 4번의 문자열 슬라이싱과 동일한 문법을 리스트에도 그대로 씀). `i`번째부터 `i + 500`번째 **직전까지**를 잘라, 최대 500개짜리 부분 리스트(`batch`)를 만듭니다. 마지막 배치는 `rows`가 모자라도 에러 없이 있는 만큼만 잘립니다.
- `cursor.executemany(SQL문, 튜플들의_리스트)` — 같은 INSERT문을 여러 행에 대해 한 번에 실행(한 건씩 `execute()`를 500번 부르는 것보다 훨씬 빠름). `batch`의 각 튜플이 `%s` 자리들에 순서대로 채워집니다.
- `inserted += len(batch)` — 복합 대입 연산자(이전 자료에서 pandas `&=`로 본 것과 같은 패턴을, 여기서는 일반 정수 `+=`로 사용).
- 진행 상황을 매 배치마다 `print`로 출력해서, 큰 작업의 중간 진행률을 눈으로 볼 수 있게 합니다.

## 10. 리스트/딕셔너리가 아닌 값에 메서드 체이닝

```python
row["A14"].date()
```

- `row["A14"]`가 날짜/시간(datetime) 타입 값일 때, `.date()`를 붙이면 시간 정보를 뺀 "날짜만" 뽑아냅니다. 값 뒤에 점을 찍고 메서드를 연달아 호출하는 것을 **메서드 체이닝**이라 부르며, 파이썬/pandas 코드 전반에서 매우 흔합니다(`gdf.geometry.area`, `row.geometry.centroid` 등도 같은 패턴).

---

## 요약 치트시트 (이 파일에서 새로 나온 것)

| 문법 | 의미 | 비고 |
|---|---|---|
| `from dotenv import load_dotenv` | 모듈에서 특정 이름만 가져오기 | `import X` 후 `X.func()`보다 짧음 |
| `os.environ.get(k, default)` | 환경변수 조회(없으면 기본값) | 필수값은 `os.environ[k]`로 접근해 `KeyError` 유도 |
| `f"""...{X}..."""` | 여러 줄 f-string | SQL 등 긴 텍스트 조립에 사용 |
| `%s` (SQL 안) | DB 드라이버의 값 자리표시자 | SQL 인젝션 방지, `execute(sql, values)`로 채움 |
| `isinstance(x, T)` | 타입 검사 | 자바 `instanceof` |
| `math.isnan(x)` | float NaN 검사 | `x == nan`은 항상 False라서 반드시 이 함수 사용 |
| `gpd.read_file(...)` | SHP → GeoDataFrame | pandas DataFrame + `geometry` 컬럼 |
| `.to_crs(epsg=...)` | 좌표계 변환 | 면적 계산은 변환 **전**에 |
| `for _, row in df.iterrows():` | 인덱스를 안 쓸 때 `_` 관례 | "이 값 안 씀" 표시 |
| `(a, b, c)` | 튜플 리터럴 | 수정 불가능한 값 묶음, INSERT 파라미터로 자주 사용 |
| `try: ... finally: ...` | 에러 여부와 무관하게 정리 코드 실행 보장 | `conn.close()` 등 |
| `range(start, stop, step)` | 등차수열 생성 | 배치 나누기의 시작 인덱스 만들 때 흔히 사용 |
| `lst[i:i+n]` | 리스트 슬라이싱 | 문자열 슬라이싱과 동일 문법 |
| `cursor.executemany(sql, rows)` | 여러 행을 한 번에 INSERT | 한 건씩 `execute()`보다 훨씬 빠름 |
| `x += n` | 복합 대입 연산자 | `x = x + n`의 축약형 |

## 이전 자료와 겹치는 개념 (복습만 필요)

- f-string, `if/else`, 삼항 표현식, `with`문(컨텍스트 매니저), 딕셔너리/컬럼 벡터화 연산(`.geometry.area`도 같은 패턴), 상수 대문자 관례 → [`find_land_pnu.py` 학습자료](find_land_pnu_파이썬_학습자료.md) 참고.

## 더 살펴보면 좋은 것

- geopandas 공식 문서의 "Reading and writing files", "Projections" 챕터.
- `pymysql` 공식 문서의 커서/트랜잭션 사용법.
- 파이썬 공식 튜토리얼의 "4.6. Defining Functions"(가변 인자 등)와 "8. Errors and Exceptions"(`try/except/finally`).
