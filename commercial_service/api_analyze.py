import json

# 디스코 토지 실거래 데이터 봐본거

# json파일에 있는 데이터는 
# https://www.disco.re/home/hello/? ~ ( query string parameters ㅈㄴ 많음 ) ~  로 payload 해서 얻은 데이터

with open("disco.json", "r", encoding="utf-8") as f: # json파일을 읽기모드(r)로 열음, 열은거를 f라는 변수로 사용, with(작업 끝나면 파일 닫음)
    data = json.load(f) # JSON 파일의 내용을 Python 객체(리스트/딕셔너리 등) 로 변환

print(len(data))
print(type(data)) # list
print(data[0])
print(type(data[0])) # dict
print("=======  ======  ")
print("pnu: " + str(data[0]['pnu']))
print("가격: " + str(data[0]['p']))
print("거래일: " + str(data[0]['y']))
print("좌표lat: " + str(data[0]['lat']))
print("좌표lng: " + str(data[0]['lng']))
# print(": " + data[0][''])
