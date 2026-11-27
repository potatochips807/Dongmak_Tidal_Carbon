# 동막 갯벌 탄소 수송

갯벌의 수중 탄소 유입량과 입자성·용존성·대기 CO₂ 유출량을 비교하는 Streamlit 앱입니다. 수중 유입은 POC + DOC + DIC를 합산합니다. 유출은 수중 POC, 수중 DOC + DIC, 대기 CO₂ 방출로 나누어 각각 계산한 다음 합산합니다. 이 결과는 갯벌 블루카본 저장량 평가를 보완합니다.

## 계산에 필요한 자료

- 관측 CSV에 같은 단면의 조위, 대표 유속·유향, POC·DOC·DIC 농도(mg C/L)와 각 시간 구간을 기록합니다. Flood·Ebb·Slack으로 조석 단계를 기록합니다.
- 조위–침수 단면적 CSV는 시간별 조위와 같은 수직 기준면을 사용합니다. 단면적은 표 범위 안에서 선형 보간합니다.
- 진북 기준의 갯벌 방향 단면 법선 방위각을 지정합니다. 수직 유속의 양수는 갯벌 방향입니다.
- 대기 CO₂ 플럭스는 µmol CO₂/m²/s, 대표 교환 면적은 m²로 입력합니다. 방출을 양수, 흡수를 음수로 입력합니다. 대기 흡수량은 별도로 표시합니다.
- 직접 입력에서는 밀물·썰물별 시간을 비롯해 대표 유량, 농도와 대기 교환 자료를 입력합니다. 관측되지 않은 값은 빈칸으로 둡니다.
- 결과는 입력 기간의 kg C와 24시간 환산 kg C/day로 제공합니다. 세 경로를 모두 산정한 경우 원형 그래프를 표시합니다.

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

단면 유속과 조위별 침수 단면적으로 유량을 구한 뒤 탄소 수송량을 산정한 사례를 참고했습니다. [Bogard 외(2020)](https://doi.org/10.1029/2019GB006430) · [Ganju 외(2019)](https://doi.org/10.1029/2018JG004920)

양쯔강 하구에서 조위와 지형에 따른 침수 부피 변화로 POC·DOC 수송을 추정한 연구도 참고했습니다. [Yuan 외(2022)](https://doi.org/10.3389/fmars.2021.809618)
