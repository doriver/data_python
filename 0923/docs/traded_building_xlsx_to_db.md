# 일반건물 실거래 데이터 db에 저장

data\processed 에있는 엑셀파일들의 데이터를 db에 저장

* 참고 코드 : building_data_engineer\traded_house_xlsx_to_db.py


## 테이블과 필드들

엑셀파일의 필드들을 db 테이블의 필드로 사용, 3개의 테이블(traded_general_building, traded_general_building_detail, general_building_mapping_building)에 나눠서 저장

* traded_general_building
    * 필드들: id, 시군구, 유형, 지번, 도로명, 용도지역, 건축물주용도, 도로조건, 연면적(㎡), 대지면적(㎡), 건축년도, 확정번지, 총괄표제 존재여부, PNU, 토지면적, 공시지가, 좌표(경도x,위도y)
    * id가 pk, 좌표가 SPATIAL INDEX, pnu에 index

* traded_general_building_detail
    * 필드들 : id, traded_general_building_id, PNU, 계약년월, 계약일, 거래금액(만원), 매수자, 매도자, 거래유형, 중개사소재지
    * id가 pk, traded_general_building_id 에 index
    * traded_general_building과 1:n 관계

* general_building_mapping_building
    * 필드들 : id, traded_general_building_id, building_pk(대장pk)
        * 총괄표제 존재여부가 O 인경우, 대장pk가 콤마로 구분된 여러개 값인경우들이 있음, 이때 각각 개별 row로 저장한다 
    * traded_general_building과 1:n 관계
    * id가 pk, traded_general_building_id 에 index

## 데이터 저장할때

* pnu값이 있는 row들만 db에 저장

* 'pnu, 연면적, 대장pk' 을 고유하게 저장
    * 중복된 경우는 traded_house_detail 에만 저장