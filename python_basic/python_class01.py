# 파이썬 클래스의 기본 개념(정의, 생성자, 속성, 메서드, 상속)을 익히기 위한 예제.


class Land:
    """토지 정보를 나타내는 클래스."""

    # 클래스 변수: 모든 인스턴스가 공유하는 값
    country = "대한민국"

    def __init__(self, pnu, bjdong_name, area, official_land_price):
        # 인스턴스 변수: 인스턴스마다 각자 가지는 값
        self.pnu = pnu
        self.bjdong_name = bjdong_name
        self.area = area
        self.official_land_price = official_land_price

    def total_value(self):
        """공시지가 * 면적으로 토지 전체 가치를 계산하는 메서드."""
        return self.area * self.official_land_price

    def __str__(self):
        # print(instance) 했을 때 보여줄 문자열
        return f"{self.bjdong_name} (PNU={self.pnu}, 면적={self.area}㎡)"


# 상속 예제: Land를 확장한 자식 클래스
class ResidentialLand(Land):
    """주거용 토지. Land를 상속받아 용도지역 정보를 추가한다."""

    def __init__(self, pnu, bjdong_name, area, official_land_price, use_district_name):
        super().__init__(pnu, bjdong_name, area, official_land_price)  # 부모 생성자 호출
        self.use_district_name = use_district_name

    def total_value(self):
        # 부모 메서드를 오버라이드(재정의): 주거용은 10% 가산
        return super().total_value() * 1.1


if __name__ == "__main__":
    print("=== 인스턴스 생성 ===")
    land1 = Land(pnu="1111010100100010000", bjdong_name="종로구 청운동", area=100.0, official_land_price=5_000_000)
    land2 = Land(pnu="1111010100100020000", bjdong_name="종로구 신교동", area=80.0, official_land_price=4_500_000)

    print("\n=== 속성 접근 ===")
    print(land1.pnu)
    print(land1.bjdong_name)
    print(land1.country)  # 클래스 변수는 인스턴스에서도 접근 가능

    print("\n=== 메서드 호출 ===")
    print(f"land1 전체 가치: {land1.total_value():,.0f}원")

    print("\n=== __str__ (print로 객체 표현) ===")
    print(land1)
    print(land2)

    print("\n=== 클래스 확인 (type, isinstance) ===")
    print(type(land1))
    print(isinstance(land1, Land))

    print("\n=== 상속 예제 ===")
    res_land = ResidentialLand(
        pnu="1111010100100030000",
        bjdong_name="종로구 효자동",
        area=120.0,
        official_land_price=6_000_000,
        use_district_name="제2종일반주거지역",
    )
    print(res_land)
    print(f"주거용 가산 적용 가치: {res_land.total_value():,.0f}원")
    print(isinstance(res_land, Land))  # 자식 클래스는 부모 클래스의 인스턴스이기도 함

    print("\n=== 여러 인스턴스를 리스트로 관리 ===")
    lands = [land1, land2, res_land]
    for land in lands:
        print(f"- {land} / 가치: {land.total_value():,.0f}원")
