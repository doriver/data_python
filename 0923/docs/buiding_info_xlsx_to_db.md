# 건물정보 db에 저장

data\processed 에있는 엑셀파일들의 데이터를 db에 저장

## 테이블과 필드

엑셀파일의 필드들을 db 테이블의 필드로 사용, 1개의 테이블(building_info)에 저장

* building_info
    * 필드들 : id, building_pk(대장pk), 나머지 엑셀 필드들
    * id가 pk, building_pk 에 index와 unique

## 데이터 저장할때

building_pk 를 고유하게 저장
