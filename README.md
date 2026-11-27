# 동막 갯벌 탄소 수송

시간 구간마다 단면 수직 유속, 조위별 침수 단면적, 수중 입자성 유기탄소(POC) 농도를 곱해 유입량과 유출량을 구하는 Streamlit 앱입니다. 이 단면 순수송량은 갯벌 탄소 저장량 평가를 보완하는 지표입니다.

## 계산에 필요한 자료

- 시간별 CSV에 같은 단면의 조위, 대표 유속·유향, 대표 POC 농도와 각 시간 구간을 기록합니다.
- 조위–침수 단면적 CSV는 시간별 조위와 같은 수직 기준면을 사용합니다. 단면적은 표 범위 안에서 선형 보간합니다.
- 진북 기준의 갯벌 방향 단면 법선 방위각을 지정합니다. 수직 유속의 양수는 갯벌 방향입니다.
- 결과는 입력 기간의 질량(kg C)과 24시간 기준 수송률(kg C/day)로 제공합니다. 대조기·소조기 비교는 같은 자료 구분 안에서 주기별 24시간 기준 수송률을 평균합니다.

## Streamlit Community Cloud 배포

1. 이 폴더의 내용을 GitHub 저장소의 최상위에 올립니다. `.streamlit/config.toml`, `data/`, `static/` 폴더를 함께 올립니다.
2. [Streamlit Community Cloud](https://share.streamlit.io/)에서 GitHub와 연결한 뒤 **Create app**을 누릅니다.
3. 저장소와 브랜치(예: `main`)를 선택하고 **Main file path**에 `TidalCarbonApp.py`를 입력합니다. Python 3.12 기본 설정으로 배포할 수 있습니다.
4. [앱 공유 설정](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)에서 보기 권한을 확인하고 배포된 `streamlit.app` 주소를 공유합니다.

## 로컬 실행

```powershell
python -m pip install -r requirements.txt
python -m streamlit run TidalCarbonApp.py
```

동막 인근 위성 자료는 배경 농도 참고용입니다. 가상값과 관측값은 입력 CSV에서 출처와 함께 구분합니다. [NOAA CoastWatch ERDDAP](https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMPOC1day_R2022SQ.html)

단면 유속을 이용한 POC 수송의 관측 사례는 [Ganju 외(2019)](https://pubs.usgs.gov/publication/70203493)를, 조위와 지형을 이용한 물 부피 기반 접근법은 [Yuan 외(2022)](https://doi.org/10.3389/fmars.2021.809618)를 참고했습니다.
