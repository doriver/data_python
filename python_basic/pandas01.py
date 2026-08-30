# pandas의 기본 DataFrame 구조와 주요 확인 메서드를 익히기 위한 예제.
import pandas as pd

data = {
    "이름": ["홍길동", "김철수", "이영희", "박민수"],
    "나이": [25, 32, 28, 41],
    "도시": ["서울", "부산", "서울", "대구"],
}
df = pd.DataFrame(data)

print("=== DataFrame 전체 ===")
print(df)

# print("\n=== 상위 2행 (head) ===")
# print(df.head(2))

# print("\n=== 하위 2행 (tail) ===")
# print(df.tail(2))

# print("\n=== shape (행, 열 개수) ===")
# print(df.shape)

print("\n=== columns (컬럼명) ===")
print(df.columns)

print("\n=== index (행 인덱스) ===")
print(df.index)

# print("\n=== dtypes (컬럼별 데이터 타입) ===")
# print(df.dtypes)

# print("\n=== info() ===")
# df.info()

# print("\n=== describe() (수치형 컬럼 통계 요약) ===")
# print(df.describe())

print("\n=== 특정 컬럼 선택 (df['나이']) ===")
print(df["나이"])

print("\n\n=== Series 기본 ===")
# Series: DataFrame의 한 컬럼처럼, 값들과 그에 대응하는 인덱스로 이루어진 1차원 자료구조.
s = pd.Series([25, 32, 28, 41], index=["홍길동", "김철수", "이영희", "박민수"], name="나이")

print("\n=== Series 전체 ===")
print(s)

print("\n=== values (값 배열) ===")
print(s.values)

print("\n=== index (인덱스) ===")
print(s.index)

print("\n=== 인덱스로 값 조회 (s['김철수']) ===")
print(s["김철수"])

print("\n=== 조건 필터링 (30 이상) ===")
print(s[s >= 30])

print("\n=== 연산 (전체에 +1) ===")
print(s + 1)

print("\n=== DataFrame의 한 컬럼도 Series ===")
col = df["나이"]
print(type(col))
print(col)


print("\n\n=== 불리언 마스크로 행 제외 + reset_index (find_land.py 방식) ===")
# find_land.py 50번째 줄과 같은 패턴: 조건에 맞는 행을 마스크로 걸러낸 뒤 인덱스를 재정렬한다.
# print("\n=== 조건 필터링 (나이 30 이상) ===")
# print(df[df["나이"] >= 30])

target_mask = df["나이"] >= 30  # 제외하고 싶은 행을 골라내는 마스크
print("\n=== target_mask ===")
print(target_mask)

filtered = df[~target_mask]  # ~ 로 반전해서 마스크에 해당하지 않는 행만 남김
print("\n=== ~target_mask 적용 (인덱스가 0,2 처럼 중간이 빠짐) ===")
print(filtered)

filtered = filtered.reset_index(drop=True)  # 인덱스를 0부터 다시 연속되게 재정렬
print("\n=== reset_index(drop=True) 적용 후 ===")
print(filtered)
