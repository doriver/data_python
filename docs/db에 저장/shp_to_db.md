# shp/AL_D152_11_20260520.shp 를 읽어서 MySQL에 저장

mysql과 연동하는 코드 필요

* MySQL 테이블 생성 필요
    * 로컬 3307번 포트 , db는 data01
    * 테이블명 official_land_price_seoul
    * 필드 : 고유번호(pnu) , 법정동명, 지번 , 대장구분명 , 좌표 , 공시지가 , 면적 , 지목 , 용도지역명
        * 좌표는 POINT SRID 4326 NOT NULL 로, SPATIAL INDEX 걸어주기

* shp파일의 데이터들
    * 항목 A0 , A2 , A5 , A4 , A9 , A14 , A13 , A16 가 순서대로    
      고유번호(pnu) , 법정동명, 지번 , 대장구분명 , 공시지가 , 면적 , 지목 , 용도지역명   
      에 매핑된다.
    * 코드에서 (위도,경도) 값이 좌표에 매핑되고   
      ST_SRID(POINT(경도, 위도), 4326) 이렇게 insert된다

