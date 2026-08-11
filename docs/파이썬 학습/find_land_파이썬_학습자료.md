# `find_land_pnu.py`로 배우는 파이썬 기본기

다른 언어는 다뤄봤지만 파이썬은 처음인 개발자를 위한 자료입니다. `find_land_pnu.py`에 실제로 쓰인 코드를 예시로, 파이썬 특유의 문법과 관용구(idiom)를 위에서부터 순서대로 설명합니다.

---

## 1. import와 모듈

```python
import os
import sys

import pandas as pd
```

- `import 모듈이름` — 다른 언어의 `include`/`require`/`import`와 비슷합니다. `os`, `sys`는 파이썬 표준 라이브러리(설치 없이 바로 사용 가능).
- `pandas`는 외부 패키지라서 `venv\Scripts\pip.exe install pandas`로 설치되어 있어야 합니다.
- `import pandas as pd` — `as`로 별칭(alias)을 붙입니다. 이후 코드에서는 `pandas.read_excel(...)` 대신 `pd.read_excel(...)`로 짧게 씁니다. 관례상 pandas는 항상 `pd`로 줄여 씁니다.
- 사용할 때는 `pd.함수이름(...)`, `os.함수이름(...)`처럼 **모듈이름.함수이름** 형태로 접근합니다. (Java의 `static` 메서드 호출과 비슷한 느낌)

## 2. 콘솔 인코딩 설정

```python
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
```

- 파이썬은 문(statement) 블록을 **중괄호 `{}`가 아니라 콜론(`:`) + 들여쓰기**로 구분합니다. `if` 다음 줄부터 들여쓰기 된 부분이 `if`에 속한 코드입니다. (들여쓰기 칸수가 문법의 일부이므로, 같은 블록 안에서는 반드시 동일하게 맞춰야 합니다 — 보통 스페이스 4칸)
- `sys.stdout`은 콘솔 출력 객체. Windows 콘솔의 기본 인코딩이 UTF-8이 아닐 때가 있어서, 한글이 깨지지 않도록 강제로 UTF-8로 바꿔주는 코드입니다.
- `!=` : 다르다(같지 않다). 파이썬은 `!=`를 씁니다(`<>`는 옛날 문법, 지금은 안 씀).

## 3. 상수(constant) 정의

```python
XLSX_PATH = "data/raw/20250806_20260805_토지(매매)_실거래가.xlsx"
CSV_ENCODING = "cp949"
CSV_CHUNK_SIZE = 200_000
HEADER_ROW = 12
AREA_TOLERANCE = 0.01
EMPTY_VALUE = "-"
```

- 파이썬에는 `const`, `final` 같은 진짜 "상수" 키워드가 없습니다. 대신 **관례적으로 변수명을 대문자_스네이크케이스로 쓰면 "이건 상수처럼 취급해달라"**는 의미입니다. (강제되지는 않고, 사람이 지키는 약속)
- `200_000` — 숫자 안의 `_`는 자릿수 구분용 밑줄입니다. `200000`과 완전히 같은 값이며, 읽기 편하라고 넣는 것(자바의 언더스코어 리터럴과 동일).
- 문자열은 `"..."`, `'...'` 둘 다 됩니다(차이 없음). 이 파일은 큰따옴표를 주로 씁니다.
- 변수에 타입을 미리 선언하지 않습니다(`str x = ...` 같은 게 없음). `=` 오른쪽 값을 보고 타입이 자동으로 정해집니다(동적 타이핑).

## 4. 함수 정의와 타입 힌트

```python
def parse_beonji(raw: str):
    """마스킹된 번지 문자열을 (자리수 접두어, 자리수) 로 분리한다.

    '산4*' -> ('4', 2), '산*' -> ('', 1), '1***' -> ('1', 4)
    """
    body = raw[1:] if raw.startswith("산") else raw
    prefix = body.split("*", 1)[0]
    return prefix, len(body)
```

- `def 함수이름(매개변수):` 로 함수를 정의합니다.
- `raw: str` — **타입 힌트**입니다. "raw는 문자열이어야 한다"는 사람(과 IDE)을 위한 표시일 뿐, 실제로 강제되지 않습니다(다른 타입을 넣어도 에러가 안 남). 반환 타입도 `-> tuple[str, int]`처럼 쓸 수 있지만 여기선 생략됨.
- 함수 정의 바로 아래 `"""..."""` 문자열은 **docstring**(함수 설명서). 여러 줄 문자열은 큰따옴표 3개로 감쌉니다.
- `raw[1:]` — **슬라이싱(slicing)**. 문자열/리스트에서 부분을 잘라낼 때 씁니다. `[1:]`은 "인덱스 1번부터 끝까지"라는 뜻(0번째 글자는 버림). 예: `"산4*"[1:]` → `"4*"`.
- `A if 조건 else B` — **삼항 표현식**(다른 언어의 `조건 ? A : B`와 동일한 의미, 순서만 다름). `raw[1:] if raw.startswith("산") else raw`는 "raw가 '산'으로 시작하면 raw[1:]을, 아니면 raw 그대로를 body에 대입"이라는 뜻.
- `.startswith("산")` — 문자열이 특정 접두어로 시작하는지 확인하는 메서드. `True`/`False`를 반환.
- `.split("*", 1)` — `"*"` 기준으로 문자열을 나눔. 두 번째 인자 `1`은 "최대 1번만 나눠라"(즉 리스트 길이가 최대 2개). `[0]`으로 나눠진 리스트의 첫 번째 요소를 꺼냅니다.
- `return prefix, len(body)` — 콤마로 여러 값을 한 번에 반환하면 자동으로 **튜플(tuple)** `(prefix, len(body))`이 됩니다. 파이썬에서 함수가 "값 여러 개를 반환"하는 표준적인 방법입니다.
- `len(body)` — 문자열 길이. `body.length()`가 아니라 `len(body)`처럼 **내장 함수에 인자로 넘기는 형태**입니다(파이썬 관용구).

호출하는 쪽에서는 이렇게 두 값을 한 번에 받습니다:

```python
prefix, digit_count = parse_beonji(row.번지)
```

이걸 **튜플 언패킹(unpacking)**이라고 합니다. 반환된 튜플 `(prefix, digit_count)`를 왼쪽의 두 변수에 순서대로 나눠 담는 문법입니다.

## 5. `main()` 함수와 실행 진입점

```python
def main():
    ...

if __name__ == "__main__":
    main()
```

- 파이썬은 파일 전체가 위에서 아래로 순서대로 실행됩니다. `def main(): ...`는 함수를 "정의"만 할 뿐 아직 실행하지 않습니다.
- `__name__`은 파이썬이 자동으로 채워주는 특수 변수. 이 파일을 **직접 실행**했을 때만 `"__main__"`이 됩니다(다른 파일에서 `import find_land_pnu`로 불러오면 `"__main__"`이 아님).
- 즉 이 블록은 "이 파일이 스크립트로 직접 실행됐을 때만 `main()`을 호출해라"라는, 파이썬의 매우 흔한 관용구입니다. (C의 `int main()` 같은 고정 진입점이 파이썬엔 없어서, 이렇게 직접 만들어 씁니다)

## 6. 데이터 읽기 — pandas DataFrame

```python
deals = pd.read_excel(XLSX_PATH, header=HEADER_ROW)
```

- `pd.read_excel(...)`은 엑셀 파일을 읽어 **DataFrame**(엑셀 시트를 흉내 낸 표 형태의 자료구조, 행/열이 있음)으로 돌려줍니다.
- `header=HEADER_ROW`처럼 `이름=값` 형태로 넘기는 인자를 **키워드 인자(keyword argument)**라고 합니다. 순서 상관없이 이름으로 지정할 수 있어서 인자가 많은 함수에서 가독성이 좋습니다.
- `len(deals)` — DataFrame의 행(row) 개수.
- `deals["시군구"]` — 대괄호 안에 컬럼명을 문자열로 넣으면 그 컬럼(열) 전체를 꺼냅니다. (딕셔너리에서 키로 값을 꺼내는 것과 비슷한 문법)

### CSV를 나눠서 읽기 (메모리 절약)

```python
for chunk in pd.read_csv(
    CSV_PATH, encoding=CSV_ENCODING, dtype=str, usecols=CSV_USECOLS, chunksize=CSV_CHUNK_SIZE
):
    sub = chunk[chunk["법정동명"].isin(needed_dongs)]
    if len(sub):
        candidate_chunks.append(sub)
candidates = pd.concat(candidate_chunks, ignore_index=True)
```

- CSV 파일이 996MB로 커서, 한 번에 다 메모리에 올리지 않고 `chunksize`개 행씩 나눠 읽습니다. `pd.read_csv(..., chunksize=N)`은 DataFrame 하나가 아니라 **DataFrame을 하나씩 꺼내주는 반복 가능한 객체(iterator)**를 반환합니다.
- `for chunk in (반복 가능한 것):` — 파이썬의 표준 반복문. 다른 언어의 `for-each`와 같습니다. `chunk`에 매 반복마다 다음 덩어리(DataFrame)가 들어옵니다.
- `dtype=str` — 모든 컬럼을 문자열로 강제 지정. (PNU 같은 20자리 숫자를 숫자 타입으로 읽으면 정밀도가 깨지기 때문에 명시적으로 문자열 유지)
- `chunk["법정동명"].isin(needed_dongs)` — 해당 컬럼 값이 `needed_dongs`(set) 안에 있는지 행마다 검사해서 `True`/`False`로 이루어진 컬럼(Series)을 만듭니다.
- `chunk[불리언_컬럼]` — DataFrame에 `True`/`False` 컬럼을 인덱스로 넣으면 `True`인 행만 남깁니다. 이게 pandas의 **불리언 마스크(boolean mask) 필터링**이며, 이 파일 전체에서 반복적으로 쓰이는 핵심 패턴입니다. (SQL의 `WHERE`절과 같은 역할)
- `if len(sub):` — 파이썬에서는 `0`, `""`, `[]`, 빈 DataFrame처럼 "비어있는" 값은 `if` 조건에서 자동으로 거짓(falsy)으로 취급됩니다. `len(sub) > 0`과 같은 뜻이지만 파이썬 스타일로 더 짧게 씁니다.
- `candidate_chunks.append(sub)` — 리스트에 항목을 하나 추가. (파이썬 리스트는 자바의 `ArrayList`, JS의 배열과 비슷하며 크기가 고정되어 있지 않음)
- `pd.concat(리스트, ignore_index=True)` — 여러 DataFrame(조각들)을 하나로 이어 붙임. `ignore_index=True`는 이어붙인 후 행 번호(인덱스)를 0부터 새로 매기라는 뜻.

## 7. 딕셔너리(dict)와 딕셔너리 컴프리헨션

```python
candidates_by_dong = {dong: df for dong, df in candidates.groupby("법정동명")}
```

- `{키: 값, ...}` 형태가 파이썬의 **딕셔너리**입니다(다른 언어의 `Map`/`HashMap`/객체와 비슷). 여기서는 "법정동명 → 그 동에 속한 후보 DataFrame" 매핑을 만듭니다.
- `candidates.groupby("법정동명")`은 (동이름, 그 동에 속한 행들의 DataFrame) 짝을 순서대로 만들어주는 반복 가능한 객체입니다.
- `{dong: df for dong, df in ...}` — **딕셔너리 컴프리헨션**. `for dong, df in (반복가능한 것)` 부분이 일반 for문과 같고, 그 결과를 `{키: 값 for ...}` 틀에 넣으면 한 줄로 딕셔너리를 만들 수 있습니다. 아래 코드와 완전히 동일한 의미입니다:

```python
candidates_by_dong = {}
for dong, df in candidates.groupby("법정동명"):
    candidates_by_dong[dong] = df
```

- `dict.get(키)` — 나중에 `candidates_by_dong.get(row.시군구)`처럼 씁니다. 대괄호(`dict[키]`)로 접근하면 키가 없을 때 에러가 나지만, `.get(키)`는 키가 없으면 에러 대신 `None`을 돌려줍니다(안전하게 조회할 때 사용).

## 8. 행 단위로 반복하기 — `itertuples`

```python
for row in deals.itertuples(index=False):
    ...
    prefix, digit_count = parse_beonji(row.번지)
```

- `deals.itertuples(index=False)`는 DataFrame의 각 행을 "이름 있는 튜플(namedtuple)"로 하나씩 돌려주는 반복자입니다. `index=False`는 원래 자동으로 붙는 행 번호(0, 1, 2...) 필드는 빼고 달라는 뜻.
- `row.번지`, `row.지목`처럼 **컬럼명을 속성(attribute)처럼 점(`.`)으로 접근**할 수 있어서 `row["번지"]`보다 짧고 읽기 편합니다. (컬럼 하나하나 값을 꺼내 써야 할 때 `itertuples`가 pandas에서 흔히 쓰는 방식이며, `.iterrows()`보다 빠릅니다)

## 9. 불리언 마스크를 여러 조건으로 조합하기

```python
mask = (
    (dong_candidates["지목명"] == row.지목)
    & (dong_candidates["용도지역명1"] == row.용도지역)
    & (dong_candidates["본번"].str.len() == digit_count)
    & (dong_candidates["본번"].str.startswith(prefix))
)
```

- `dong_candidates["지목명"] == row.지목` — 컬럼 전체와 어떤 값 하나를 비교하면, 행마다 같은지 비교한 `True`/`False` 컬럼이 만들어집니다(SQL의 `WHERE 컬럼 = 값`과 같음).
- **주의**: pandas에서 여러 조건을 합칠 때는 파이썬의 일반 `and`가 아니라 **`&`(비트 AND)**를 씁니다. (`or` 대신 `|`, `not` 대신 `~`) 그리고 각 조건은 반드시 괄호로 감싸야 합니다 — 연산자 우선순위 때문에 괄호가 없으면 엉뚱하게 해석됩니다. `or`/`and`는 "값 하나"에 대해서만 쓸 수 있는데, 컬럼 전체(여러 값)에 대해 각 행마다 판단해야 하므로 `&`/`|`를 씁니다.
- `.str.len()`, `.str.startswith(prefix)` — 컬럼(Series)에 `.str`을 붙이면, 그 컬럼의 모든 값에 대해 문자열 메서드를 한 번에 적용해줍니다(반복문 없이). 파이썬 문자열의 `len(x)`, `x.startswith(...)`와 같은 기능을 컬럼 전체에 벡터화(vectorize)해서 적용하는 것.
- 괄호로 여러 줄을 감싸면(`mask = (\n ... \n)`) 줄바꿈이 자유로워집니다. 파이썬은 보통 한 문장이 한 줄이어야 하는데, `()`, `[]`, `{}` 안에서는 줄바꿈해도 하나의 문장으로 취급됩니다.

```python
if pd.isna(row.지분구분):
    mask &= (dong_candidates["토지면적"] > row.계약면적 - AREA_TOLERANCE) & (
        dong_candidates["토지면적"] < row.계약면적 + AREA_TOLERANCE
    )
else:
    mask &= dong_candidates["토지면적"] > row.계약면적
```

- `pd.isna(값)` — 값이 결측치(NaN, 즉 비어있음)인지 확인. 엑셀의 빈 셀은 `None`이 아니라 보통 `NaN`(float 특수값)으로 읽히기 때문에 `== None`이 아니라 `pd.isna(...)`로 확인해야 합니다.
- `mask &= 다른조건` — `mask = mask & 다른조건`의 축약형. 다른 언어의 `x += 1`(x = x + 1)과 같은 방식의 복합 대입 연산자입니다.
- `if / else` — 조건 분기. 지분구분 유무에 따라 면적 조건을 다르게 적용.

```python
hits = dong_candidates[mask]
if len(hits) == 1:
    ...
```

- `dong_candidates[mask]` — 위에서 만든 `True`/`False` 마스크로 실제 필터링을 실행해서, 조건을 만족하는 행만 남긴 새 DataFrame을 얻습니다.
- `len(hits) == 1` — 후보가 정확히 1개일 때만 매칭 성공으로 인정(스펙에서 요구한 "유일한 후보"조건).

## 10. f-string (문자열 포매팅)

```python
print(f"실거래가 전체 건수: {total_count}")
beonji = f"산 {beonji}"
```

- `f"..."` 형태를 **f-string**이라고 합니다. 문자열 안에 `{변수}`를 쓰면 그 변수의 값이 자동으로 문자열에 끼워집니다. (JS의 템플릿 리터럴 `` `${x}` ``, Kotlin의 `"$x"`와 동일한 개념)
- 문자열 앞의 `f`를 빼먹으면 `{total_count}`가 그냥 글자 그대로 출력되니 주의.

## 11. `None`과 빈 값 표현

```python
matched_pnu = []
matched_beonji = []
...
if len(hits) == 1:
    matched_pnu.append(hits["고유번호"].iloc[0])
    ...
else:
    matched_pnu.append(None)
    matched_beonji.append(None)
```

- `None`은 파이썬에서 "값 없음"을 나타내는 특수 값입니다(자바/JS의 `null`, C#의 `null`과 동일한 역할).
- `hits["고유번호"]`는 필터링된 결과의 "고유번호" 컬럼(여러 행일 수도 있는 Series)이고, `.iloc[0]`은 그중 **0번째(첫 번째) 값 하나**를 꺼냅니다(`len(hits) == 1`이라 사실상 1개뿐이지만, 문법적으로 "위치 기반 인덱싱"이 필요해서 `.iloc[0]`을 씁니다).
- 반복이 끝난 뒤 `matched_pnu`, `matched_beonji`는 각각 "실거래 행 개수"만큼의 리스트가 됩니다(매칭 성공한 행은 값, 실패한 행은 `None`).

```python
deals["PNU"] = matched_pnu
deals["확정번지"] = matched_beonji
```

- DataFrame에 **없는 컬럼 이름으로 대입**하면 새 컬럼이 자동으로 추가됩니다. 리스트 길이가 행 개수와 같으면 순서대로 각 행에 값이 채워집니다.

```python
success_count = deals["PNU"].notna().sum()
```

- `.notna()` — 컬럼의 각 값이 결측치가 아니면 `True`. `.sum()`을 `True`/`False` 컬럼에 쓰면 `True`(=1)의 개수를 세어줍니다. 이는 "값이 채워진(=매칭 성공한) 행 개수"를 세는 파이썬/pandas식 관용구입니다.

## 12. 파일/디렉터리 다루기 — `os` 모듈

```python
os.makedirs(OUTPUT_DIR, exist_ok=True)
```

- 디렉터리를 생성합니다. `exist_ok=True`가 없으면 이미 폴더가 존재할 때 에러가 납니다. 있으면 "이미 있어도 에러내지 말고 넘어가라"는 뜻.

```python
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "20250806_20260805_토지(매매)_실거래가_매핑.xlsx")
```

- `os.path.join(a, b)` — 경로를 OS에 맞는 구분자(윈도우는 `\`, 리눅스/맥은 `/`)로 이어 붙여줍니다. 문자열을 직접 `+`로 이어붙이지 않는 이유는, 이렇게 해야 어느 OS에서 실행하든 안전하기 때문입니다.

## 13. `with` 문 — 컨텍스트 매니저

```python
with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
    deals.to_excel(writer, sheet_name="실거래가", index=False, startrow=DATA_START_ROW)
    sheet = writer.sheets["실거래가"]
    sheet["A1"] = f"전체 건수: {total_count}"
    ...
```

- `with 무언가() as 이름:` 은 "이 블록에 들어갈 때 자동으로 열고, 블록이 끝나면(에러가 나든 안 나든) 자동으로 닫아준다"는 뜻입니다. 자바의 `try-with-resources`, C#의 `using`과 같은 역할.
- 여기서는 엑셀 파일 쓰기를 위한 `ExcelWriter`를 열고, 블록이 끝나면 자동으로 파일에 저장하고 닫습니다. 직접 `writer.close()`를 호출할 필요가 없어서 실수로 안 닫는 버그를 방지합니다.
- `writer.sheets["실거래가"]`로 실제 엑셀 시트 객체를 얻은 뒤, `sheet["A1"] = "..."`처럼 **엑셀 셀 주소를 딕셔너리 키처럼 사용**해서 값을 직접 넣을 수 있습니다(openpyxl 라이브러리 문법).

---

## 요약 치트시트

| 문법 | 의미 | 비유 |
|---|---|---|
| `def f(x: str):` | 함수 정의, `x`는 문자열이라는 힌트 | 함수 선언 + 타입 어노테이션(강제 아님) |
| `a if cond else b` | 삼항 표현식 | `cond ? a : b` |
| `raw[1:]` | 슬라이싱(1번 인덱스부터 끝까지) | `substring(1)` |
| `return a, b` | 튜플로 여러 값 반환 | 다중 리턴값 |
| `a, b = func()` | 튜플 언패킹 | 구조 분해 할당 |
| `{k: v for k, v in ...}` | 딕셔너리 컴프리헨션 | for문으로 dict 채우기의 축약형 |
| `for x in iterable:` | 반복문 | for-each |
| `f"{x}"` | f-string | 템플릿 리터럴 `` `${x}` `` |
| `df[condition]` | 불리언 마스크 필터링 | SQL `WHERE` |
| `&`, `\|`, `~` | pandas에서의 and/or/not | 컬럼 단위 논리연산 (일반 `and`/`or` 대신) |
| `pd.isna(x)` | 값이 비어있는지(NaN) 확인 | `x == null` |
| `df["col"] = list` | 없는 컬럼명에 대입 → 새 컬럼 생성 | — |
| `os.makedirs(p, exist_ok=True)` | 폴더 생성(있어도 에러 안 남) | `mkdir -p` |
| `with X() as y:` | 컨텍스트 매니저(자동 정리) | `try-with-resources` / `using` |
| `if __name__ == "__main__":` | 직접 실행될 때만 동작하는 진입점 | `public static void main` 관용구 |

## 더 살펴보면 좋은 것

- pandas 공식 문서의 "10 minutes to pandas" — DataFrame/Series 기본기.
- 파이썬 공식 튜토리얼의 "5. Data Structures" — 리스트/튜플/딕셔너리/컴프리헨션 정리.
- 이 파일에서 쓰인 `.str.xxx()`, `.isin()`, `.groupby()`, `.itertuples()` 등은 모두 pandas API 문서에서 검색하면 예제와 함께 자세히 나옵니다.
