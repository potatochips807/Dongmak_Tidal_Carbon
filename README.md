# 동막 갯벌 탄소 수송

밀물 POC 유입량과 썰물 POC 유출량을 비교하고, 동막 인근 NOAA 위성 POC 농도를 확인하는 Streamlit 앱입니다.

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

동막 인근 자료 출처는 [NOAA CoastWatch ERDDAP](https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMPOC1day_R2022SQ.html)입니다. 예시 입력은 가상값이며 위성 농도는 단면 수송량 계산에 자동 입력되지 않습니다.
