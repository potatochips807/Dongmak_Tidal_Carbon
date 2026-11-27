# 동막 갯벌 탄소 수송

갯벌의 수중 탄소 유입량과 입자성·용존성·대기 CO₂ 유출량을 비교하는 Streamlit 앱입니다. 수중 유입은 POC + DOC + DIC를 합산합니다. 유출은 수중 POC, 수중 DOC + DIC, 대기 CO₂ 방출로 나누어 각각 계산한 다음 합산합니다. 이 결과는 갯벌 블루카본 저장량 평가를 보완합니다.

## 계산에 필요한 자료

- 관측 CSV의 필수 열은 `CycleId,DataKind,TideRegime,StartTime,DurationMin,FlowM3S,PocMgL,DataSource`입니다. `StartTime`에는 UTC 오프셋이 있는 ISO 8601 시각을 사용합니다.
- `FlowM3S`는 단면 유량(m³/s)입니다. 갯벌 방향은 양수, 바다 방향은 음수입니다. `Phase` 열에는 Flood·Ebb·Slack으로 조석 단계를 기록할 수 있습니다.
- `PocMgL`, `DocMgL`, `DicMgL` 단위는 mg C/L입니다. `AirCo2FluxUmolM2S`는 µmol CO₂/m²/s, `AirExchangeAreaM2`는 m²입니다. 대기 방출은 양수, 흡수는 음수로 기록합니다.
- 한 화면에서 관측 CSV를 올리고 막대그래프의 유입·유출량(kg C)을 확인합니다. 세 유출 경로의 값을 모두 산정한 경우 가장 큰 경로를 표시합니다.

## Streamlit Community Cloud 배포

1. 이 폴더의 내용을 GitHub 저장소의 최상위에 올립니다. `.streamlit/config.toml`, `static/` 폴더를 함께 올립니다.
2. [Streamlit Community Cloud](https://share.streamlit.io/)에서 GitHub와 연결한 뒤 **Create app**을 누릅니다.
3. 저장소와 브랜치(예: `main`)를 선택하고 **Main file path**에 `TidalCarbonApp.py`를 입력합니다. Python 3.12 기본 설정으로 배포할 수 있습니다.
4. [앱 공유 설정](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)에서 보기 권한을 확인하고 배포된 `streamlit.app` 주소를 공유합니다.

## 로컬 실행

```powershell
python -m pip install -r requirements.txt
python -m streamlit run TidalCarbonApp.py
```

단면 유속과 조위별 침수 단면적으로 유량을 구한 뒤 탄소 수송량을 산정한 사례를 참고했습니다. [Bogard 외(2020)](https://doi.org/10.1029/2019GB006430) · [Ganju 외(2019)](https://doi.org/10.1029/2018JG004920)

양쯔강 하구에서 조위와 지형에 따른 침수 부피 변화로 POC·DOC 수송을 추정한 연구도 참고했습니다. [Yuan 외(2022)](https://doi.org/10.3389/fmars.2021.809618)
