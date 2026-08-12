# python01

한국 토지/부동산 데이터 파이프라인. 프로젝트 개요와 환경 설정은 `CLAUDE.md` 참고.

## individual_land_price_gyeonggi_shp_to_db.py

경기도 개별공시지가 SHP를 읽어 MySQL `individual_land_price_gyeonggi` 테이블에 적재하는 스크립트.

```
venv\Scripts\python.exe individual_land_price_gyeonggi_shp_to_db.py
```

`INSERT_BATCH_SIZE`(기본 2000) 단위로 커밋하며, 배치 실패 시 해당 배치를 행 단위로 재시도해 정상 행은 살리고 실패한 행만 걸러낸다.

### 모두 성공한 경우

콘솔에 `완료: N건 삽입`이 출력된다. 이전 실행에서 남아 있던 실패 데이터 파일(`db_error/individual_land_price_gyeonggi_failed_rows.pkl`)이 있었다면 자동으로 삭제된다.

### 일부 실패한 경우

실패한 행이 있으면 `db_error/individual_land_price_gyeonggi_failed_rows.pkl` 파일에 저장되고, 콘솔에 아래와 같은 안내가 출력된다.

```
실패 N건을 db_error/individual_land_price_gyeonggi_failed_rows.pkl 에 저장했습니다. --retry-failed 로 재시도하세요.
```

성공한 행은 이미 커밋되어 있으므로, 실패한 행만 별도로 다시 시도하면 된다.

### 실패한 행만 재시도하기

`--retry-failed` 플래그로 실행하면 SHP를 다시 읽지 않고, 저장해둔 실패 행만 불러와 다시 삽입을 시도한다.

```
venv\Scripts\python.exe individual_land_price_gyeonggi_shp_to_db.py --retry-failed
```

재시도 후에도 실패하는 행이 있으면 같은 파일에 다시 저장되고, 모두 성공하면 파일이 삭제된다. 실패 원인(제약조건 위반, 값 형식 오류 등)을 코드나 원본 데이터에서 먼저 해결한 뒤 재시도하는 것을 권장한다.
