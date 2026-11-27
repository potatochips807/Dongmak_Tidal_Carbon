import csv
import hashlib
import io
import json
from math import isclose
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import altair as alt
import pandas as pd
import streamlit as st

from carbon_budget_view import (
    budget_methods, direct_budget_input, direct_budget_results, preview_budget_results, render_budget,
)
from section_flux import DATA_KINDS
from section_flux_view import (
    carbon_reactions, section_input, select_section_row,
    section_references, section_results,
)
from tidal_csv import calculate_observation_csv

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT / 'observations.template.csv'
NOAA_POC = ROOT / 'data' / 'dongmak-poc-noaa.json'
ENGINE = ROOT / 'TidalCarbonIO.ps1'
INPUT_PAGE = '입력값'
RESULT_PAGE = '결과값'
NEARBY_PAGE = '동막 인근 자료'
DIRECT_MODE = '직접 입력'
CSV_MODE = '관측 CSV 업로드'
DAILY_BASIS = {
    '24h_total': '24시간 합계',
    '24h_equivalent': '24시간 환산값 · 같은 패턴 반복 가정',
    'mean_per_day': '입력 기간의 일평균',
}


def daily_scaling(duration_min: float) -> tuple[float, str]:
    if isclose(duration_min, 1440, rel_tol=0, abs_tol=1e-6):
        return 1.0, '24h_total'
    return 1440 / duration_min, '24h_equivalent' if duration_min < 1440 else 'mean_per_day'


def show_daily_basis(duration_min: float, basis: str) -> None:
    st.caption(f'입력 기간 {duration_min / 60:g}시간 · {DAILY_BASIS[basis]}')


def render_nearby_poc() -> None:
    data = json.loads(NOAA_POC.read_text(encoding='utf-8'))
    start, end = data['period']
    nearest, nearby = data['nearest'], data['nearby']
    observations = pd.DataFrame(data['observations_mg_c_m3'], columns=['date', 'poc_mg_c_m3'])
    observations['date'] = pd.to_datetime(observations['date'])
    observations['poc_mg_c_l'] = observations['poc_mg_c_m3'] / 1000

    st.caption(f'NOAA MODIS Aqua · 4 km 격자 · 일별 표층 POC · 확인 기간 {start} ~ {end}')
    exact_card, nearby_card = st.columns(2)
    exact_card.metric('동막해변 최근접 격자', f'{nearest["valid_days"]}일', border=True)
    nearby_card.metric(f'동막 인근 해역 · 약 {nearby["distance_km"]:.1f} km', f'{len(observations)}일', border=True)
    st.caption('유효한 농도 값이 있는 날짜 수입니다.')

    chart = alt.Chart(observations).mark_point(filled=True, size=35, opacity=0.75).encode(
        x=alt.X('date:T', title='날짜'),
        y=alt.Y('poc_mg_c_l:Q', title='표층 POC 농도 (mg C/L)'),
        color=alt.value('#14877F'),
        tooltip=[alt.Tooltip('date:T', title='날짜', format='%Y-%m-%d'),
                 alt.Tooltip('poc_mg_c_l:Q', title='POC (mg C/L)', format='.4f')],
    ).properties(height=270, description='동막 인근 해역의 유효한 일별 표층 POC 농도')
    st.altair_chart(chart, width='stretch')
    st.caption('그래프 자료 · [NOAA CoastWatch ERDDAP, MODIS Aqua POC 일별 4 km 제품]'
               '(https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMPOC1day_R2022SQ.html)')
    st.info('동막의 세 경로를 산정하려면 같은 단면·시각의 유량과 POC·DOC·DIC 농도, '
            '같은 기간의 대기 CO₂ 플럭스와 교환 면적이 필요합니다. 이 위성 자료는 인근 표층 POC 농도를 보여줍니다.')
    st.caption('유속·유향과 조위 자료는 관측소 위치와 기간을 확인하세요. '
               '[국립해양조사원 해양 관측자료](https://www.data.go.kr/data/15155508/openapi.do)')

    with st.expander('격자 위치·자료 처리·참고문헌'):
        exact_lat, exact_lon = nearest['coordinates']
        near_lat, near_lon = nearby['coordinates']
        st.write(f'동막해변 최근접 격자 · {exact_lat:.5f}°N, {exact_lon:.5f}°E  \n'
                 f'동막 인근 해역 격자 · {near_lat:.5f}°N, {near_lon:.5f}°E')
        st.caption('원자료의 mg C/m³를 1,000으로 나눠 mg C/L로 표시했습니다. 결측일과 유효 범위 밖 값은 그래프에서 제외했습니다.')
        st.markdown(
            '- **위성 POC 산출 방법** · Stramski 외(2008), *Biogeosciences*, 5, 171–201. '
            '[논문](https://bg.copernicus.org/articles/5/171/2008/)\n'
            '- **강화 인근 부유퇴적물 수송** · 우한준 외(2004), 「한국 서해 강화 갯벌의 퇴적물 특성」. '
            '[KIOST 수록 논문](https://sciwatch.kiost.ac.kr/handle/2020.kiost/5289)'
        )


def run_windows_model(payload: bytes) -> list[dict]:
    with TemporaryDirectory(prefix='tidal-carbon-') as folder:
        source = Path(folder) / 'observations.csv'
        output = Path(folder) / 'results.csv'
        source.write_bytes(payload)
        run = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(ENGINE),
             '-InputCsv', str(source), '-OutputCsv', str(output), '-Calculate'],
            capture_output=True, timeout=60, check=False,
        )
        if run.returncode != 0:
            detail = run.stderr.decode('utf-8', errors='replace').strip()
            raise ValueError(detail or 'PowerShell에서 결과 CSV를 생성하지 못했습니다.')
        result = output.read_bytes()
    return list(csv.DictReader(io.StringIO(result.decode('utf-8-sig'))))


def run_model(payload: bytes) -> tuple[bytes, list[dict]]:
    if sys.platform == 'win32' and ENGINE.is_file():
        rows = run_windows_model(payload)
    else:
        with SCHEMA.open(encoding='utf-8-sig', newline='') as template:
            rows = calculate_observation_csv(payload, next(csv.reader(template)))
    daily_fields = {
        'FloodInPocKgC': 'FloodInPocKgCDay', 'EbbOutPocKgC': 'EbbOutPocKgCDay',
        'TotalInPocKgC': 'TotalInPocKgCDay', 'TotalOutPocKgC': 'TotalOutPocKgCDay',
        'NetInPocKgC': 'NetInPocKgCDay',
    }
    for row in rows:
        row.update(dict.fromkeys((*daily_fields.values(), 'DailyBasis', 'NetExportPocKgC', 'NetExportPocKgCDay')))
        if row['ModelStatus'] == 'Calculated':
            duration = float(row['FloodDurationMin']) + float(row['EbbDurationMin'])
            factor, row['DailyBasis'] = daily_scaling(duration)
            for period_key, daily_key in daily_fields.items():
                row[daily_key] = float(row[period_key]) * factor
            row['NetExportPocKgC'] = -float(row['NetInPocKgC']) or 0.0
            row['NetExportPocKgCDay'] = -row['NetInPocKgCDay'] or 0.0
    return pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig'), rows


def render_result(rows: list[dict], payload: bytes) -> None:
    st.title('POC 수송 결과')
    selected = 0
    if len(rows) > 1:
        selected = st.selectbox(
            '관측 단면 · 조석 주기', range(len(rows)),
            format_func=lambda i: ' · '.join(rows[i][key] for key in ('Region', 'Station', 'CycleId', 'DataKind')),
            key=f'cycle-{hashlib.sha256(payload).hexdigest()}',
        )
    row = rows[selected]
    if row['DataKind'] == 'Scenario':
        st.caption('가상 시나리오')
    elif len(rows) == 1:
        st.caption(' · '.join(row[key] for key in ('Region', 'Station', 'CycleId')))
    st.text(f'계산에 사용한 자료 · {row.get("DataSources") or "입력 자료에 출처 미기재"}')

    if row['ModelStatus'] == 'Calculated':
        flood = row['FloodInPocKgCDay']
        ebb = row['EbbOutPocKgCDay']
        net_export = round(row['NetExportPocKgCDay'], 2)
        ratio = row['EbbOutFloodInRatioPct']
        show_daily_basis(float(row['FloodDurationMin']) + float(row['EbbDurationMin']), row['DailyBasis'])
        direction = '순유출' if net_export > 0 else '순유입' if net_export < 0 else '표시 정밀도에서 균형'
        st.metric('POC 순유출량 (전체 유출 − 전체 유입)',
                  f'{net_export or 0:+,.2f} kg C/day', border=True)
        st.caption(direction)
        metrics = st.columns(3)
        metrics[0].metric('밀물 유입량 (kg C/day)', f'{flood:,.2f}', border=True)
        metrics[1].metric('썰물 유출량 (kg C/day)', f'{ebb:,.2f}', border=True)
        metrics[2].metric('유출/유입 비율', f'{float(ratio):,.2f}%' if ratio else '산정 불가', border=True)

        values = pd.DataFrame({'구분': ['밀물 유입', '썰물 유출'], '수송량': [flood, ebb]})
        chart = alt.Chart(values).mark_bar(cornerRadiusEnd=5, size=30).encode(
            y=alt.Y('구분:N', sort=['밀물 유입', '썰물 유출'], title=None),
            x=alt.X('수송량:Q', title='입자성 유기탄소 수송량 (kg C/day)', scale=alt.Scale(zero=True)),
            color=alt.Color('구분:N', scale=alt.Scale(
                domain=['밀물 유입', '썰물 유출'], range=['#007C78', '#AD542F']), legend=None),
            tooltip=[alt.Tooltip('구분:N'), alt.Tooltip('수송량:Q', format=',.2f')],
        ).properties(height=130)
        st.altair_chart(chart, width='stretch')
        if not ratio:
            st.caption('밀물 유입량이 0이면 비율을 계산할 수 없습니다.')
    else:
        st.warning(f"입력을 확인해 주세요. {row['InputNotes']}")

    if len(rows) > 1:
        with st.expander('전체 단면 결과'):
            fields = ('Region', 'Station', 'CycleId', 'DataKind', 'TotalInPocKgCDay',
                      'TotalOutPocKgCDay', 'NetExportPocKgCDay', 'DailyBasis', 'ModelStatus', 'InputNotes')
            st.dataframe(pd.DataFrame(rows)[list(fields)].rename(columns={
                'TotalInPocKgCDay': '총유입 (kg C/day)', 'TotalOutPocKgCDay': '총유출 (kg C/day)',
                'NetExportPocKgCDay': 'POC 순유출량 (kg C/day)',
            }), hide_index=True, width='stretch')
    st.download_button('결과 CSV 다운로드', payload, 'tidal-carbon-results.csv', 'text/csv', on_click='ignore')


st.set_page_config(page_title='동막 갯벌 탄소 수송', layout='wide')
if st.session_state.get('tidal_page') not in (INPUT_PAGE, RESULT_PAGE, NEARBY_PAGE):
    st.session_state['tidal_page'] = INPUT_PAGE
page = st.session_state['tidal_page']
with st.sidebar:
    st.header('분석 메뉴')
    for label, icon in ((INPUT_PAGE, 'edit_note'), (RESULT_PAGE, 'analytics'), (NEARBY_PAGE, 'satellite_alt')):
        st.button(
            label, icon=f':material/{icon}:', width='stretch', key=f'analysis-menu-{icon}',
            type='primary' if page == label else 'secondary',
            on_click=st.session_state.update, kwargs={'tidal_page': label},
        )

if page == NEARBY_PAGE:
    st.title(NEARBY_PAGE)
    direct_result = st.session_state.get('carbon_budget_result')
    section_result = st.session_state.get('section_result')
    if direct_result is not None:
        st.caption(f'입력한 자료 · {DATA_KINDS[direct_result["DataKind"]]} · '
                   f'{direct_result["DataSource"]}')
        render_budget(direct_result)
    elif section_result is not None and 'OutCarbonKgC' in section_result[0][0]:
        row = select_section_row(pd.DataFrame(section_result[0]))
        st.caption(f'업로드한 단면 자료 · {row.CycleId} · {DATA_KINDS[row.DataKind]} · {row.DataSource} '
                   f'· 단면적 {DATA_KINDS[row.AreaKind]}')
        render_budget(row)
    else:
        preview_budget_results()
    st.header('동막 인근 위성 POC 농도')
    render_nearby_poc()
    st.stop()

if page == RESULT_PAGE:
    direct_result = st.session_state.get('carbon_budget_result')
    section_result = st.session_state.get('section_result')
    result = st.session_state.get('poc_result')
    if direct_result is not None:
        direct_budget_results(direct_result)
    elif section_result is not None:
        section_results(section_result)
    elif result is None:
        st.title('결과 그래프 미리보기')
        preview_budget_results()
        st.button('자료 입력으로 이동', on_click=st.session_state.update, kwargs={'tidal_page': INPUT_PAGE})
    else:
        result_csv, result_rows = result
        render_result(result_rows, result_csv)
    st.caption('이 결과는 조석기의 탄소 이동을 보여줍니다. 장기 저장량 변화는 퇴적·매몰과 재퇴적 자료를 함께 평가해야 합니다.')
    budget_methods()
    section_references()
    carbon_reactions()
    st.stop()

with st.container(horizontal=True, vertical_alignment='center', gap='small', key='workshop-banner'):
    st.image(ROOT / 'kiost-logo.png', width=112, alt='한국해양과학기술원 KIOST 로고')
    st.markdown('한국해양과학기술원(KIOST)  \n**제13차 차세대 해양과학자 워크숍**')
st.title('밀물에 들어온 탄소, 썰물에 얼마나 빠져나갈까?')
st.caption('조석 비대칭성에 따른 비식생 갯벌의 탄소 수송 및 블루카본 저장 안정성 평가')
st.markdown('**갯벌 탄소 유입·유출량 산정 프로그램**')
st.caption('수중 POC·DOC·DIC 유입과 입자성·용존성·대기 CO₂ 유출을 비교해 블루카본 저장량 평가를 보완합니다.')
has_result = any(key in st.session_state for key in ('carbon_budget_result', 'section_result', 'poc_result'))
st.button('결과 그래프 보기' if has_result else '결과 그래프 미리보기',
          icon=':material/analytics:', on_click=st.session_state.update, kwargs={'tidal_page': RESULT_PAGE})
st.header('입력값')
mode = st.segmented_control('입력 방식', (CSV_MODE, DIRECT_MODE), default=CSV_MODE,
                            required=True, label_visibility='collapsed', key='tidal_carbon_budget_input_mode',
                            persist_state='session')

if mode == DIRECT_MODE:
    try:
        direct_result = direct_budget_input()
    except ValueError as error:
        st.error(str(error))
    else:
        if direct_result is not None:
            st.session_state.pop('poc_result', None)
            st.session_state.pop('section_result', None)
            st.session_state['carbon_budget_result'] = direct_result
            st.session_state['tidal_page'] = RESULT_PAGE
            st.rerun()
    budget_methods()
    st.stop()

try:
    section_result = section_input()
except ValueError as error:
    st.error(str(error))
else:
    if section_result is not None:
        st.session_state.pop('poc_result', None)
        st.session_state.pop('carbon_budget_result', None)
        st.session_state['section_result'] = section_result
        st.session_state['tidal_page'] = RESULT_PAGE
        st.rerun()

with st.expander('기존 POC 전용 관측 CSV'):
    uploaded = st.file_uploader('기존 관측 CSV 선택', type='csv', max_upload_size=10)
    data = uploaded.getvalue() if uploaded is not None else None
    compute = st.button('POC 전용 계산', disabled=not data)
    payload = data if compute else None
    st.download_button('POC 전용 CSV 양식', SCHEMA.read_bytes(), 'observations.template.csv',
                       'text/csv', on_click='ignore')

if payload is not None:
    try:
        with st.spinner('수송량 계산 중…'):
            result_csv, result_rows = run_model(payload)
        if not result_rows:
            raise ValueError('계산할 관측 구간이 없습니다.')
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        st.error('계산할 수 없습니다. 입력값이나 CSV 양식을 확인해 주세요.')
        with st.expander('오류 상세'):
            st.code(str(error), language=None)
    else:
        st.session_state.pop('section_result', None)
        st.session_state.pop('carbon_budget_result', None)
        st.session_state['poc_result'] = (result_csv, result_rows)
        st.session_state['tidal_page'] = RESULT_PAGE
        st.rerun()

budget_methods()
section_references()
