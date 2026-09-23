# 일반건물 표제부 매핑 수정

building_data_engineer\find_general_building.py 를 수정하면 됨

## 아래 조건들을 순서대로 만족시키며 수정

* 데이터 변경됨, 이에 맞게 수정
    * RAW엑셀 파일에 '확정번지', '총괄표제 존재여부' 컬럼이 추가됐어
    * BASIS파일도 변경됨

* 건축물 대장의 '대장구분' 값이 '일반'인 경우만 대상으로

* '총괄표제 존재여부' 의 값이 비어있는경우만 기존 매핑 로직을 적용

* 매칭되서 확정번지가 생기는 row에 표제부의 특정 컬럼들(아래에 설명) 추가
    * building_data_engineer\find_house_buillding.py 에서 BASIS_EXTRA_COLUMNS( 연관된 BASIS_EXTRA_COLUMN_RENAME 등도 참고 ) 

* '총괄표제 존재여부' 값이 O 인 경우를 처리
    * '시구군 + 확정번지' 로 '지번주소' 를 만들고
    * 지번주소에 매핑되는 표제부 row(시도 + 시군구 + 법정동 + 대지구분(산인경우만) + 번 + 지)들을 찾아, 해당 row들의 데이터를 새로운 엑셀파일(총괄표제부 있는경우)에 저장
    * 여기 컬럼들은 '대장pk, 지번주소(시구군+확정번지),  총괄없던거에서 추가했던 컬럼들'

## 참고 파일

building_data_engineer\find_house_buillding.py
