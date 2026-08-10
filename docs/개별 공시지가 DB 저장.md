# 개별 공시지가를 DB에 저장

* official_land_price_to_db.py 를 참고해서 파이썬 코드 작성
* 공시지가 데이터 : data\AL_D150_41_20260526.shp
* A0 ~ A15 과 좌표(경도,위도) 저장

A0	고유번호
A1	법정동코드
A2	법정동명
A3	대장구분코드
A4	대장구분명
A5	지번
A6	지번지목부호
A7	기준연도
A8	기준월
A9	개별공시지가(원/㎡)
    
A10	표준지여부
A11	지목코드
A12	지목
A13	토지면적(㎡)
A14	데이터기준일자
A15	시군구코드


* A13 값이 없는 경우에 shpHandling.py 에있는 row['area_sqm'] 처럼 geometry에서 area뽑아서 저장


