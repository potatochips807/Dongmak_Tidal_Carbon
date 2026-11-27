import csv
from datetime import datetime, timedelta, timezone
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

from section_flux_view import (
    DEMO_MODE, SERIES_MODE, carbon_reactions, section_input, section_map,
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
    st.info('동막 단면의 밀물 유입량·썰물 유출량은 산정 대기 중입니다. 같은 단면·시각의 유량과 수중 POC 농도가 필요합니다.')

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
        row.update(dict.fromkeys((*daily_fields.values(), 'DailyBasis')))
        if row['ModelStatus'] == 'Calculated':
            duration = float(row['FloodDurationMin']) + float(row['EbbDurationMin'])
            factor, row['DailyBasis'] = daily_scaling(duration)
            for period_key, daily_key in daily_fields.items():
                row[daily_key] = float(row[period_key]) * factor
    return pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig'), rows


def direct_input() -> bytes | None:
    st.caption('입력 자료 · 앱 기본값 또는 사용자 입력을 사용한 가상 시나리오')
    defaults = st.session_state.get('submitted_direct_inputs', [(0.20, 5.0, 2.0, 360), (0.20, 5.0, 3.0, 360)])
    with st.form('direct-input'):
        phases = []
        for column, label, (default_speed, default_area, default_poc, default_minutes) in zip(
            st.columns(2), ('밀물', '썰물'), defaults,
        ):
            with column:
                st.markdown(f'**{label}**')
                speed = st.number_input('단면 수직 유속 (m/s)', 0.0, value=default_speed, step=0.01, key=f'{label}-speed')
                area = st.number_input('잠긴 단면적 (m²)', 0.0, value=default_area, step=0.1, key=f'{label}-area')
                poc = st.number_input('POC 농도 (mg C/L)', 0.0, value=default_poc, step=0.1, key=f'{label}-poc')
                minutes = st.number_input('지속 시간 (분)', 1, value=default_minutes, step=1, key=f'{label}-time')
                phases.append((speed, area, poc, minutes))
        submitted = st.form_submit_button('탄소 수송량 계산', type='primary')

    if not submitted:
        return None

    st.session_state['submitted_direct_inputs'] = phases
    columns = next(csv.reader(io.StringIO(SCHEMA.read_text(encoding='utf-8-sig'))))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    start = datetime(2000, 1, 1, 6, tzinfo=timezone(timedelta(hours=9)))
    for (phase, direction), (speed, area, poc, minutes) in zip((('Flood', 'In'), ('Ebb', 'Out')), phases):
        writer.writerow(dict(
            Region='동막 갯벌', Station='직접 입력 시나리오', CycleId='DIRECT',
            DataKind='Scenario', Phase=phase, Direction='Slack' if speed == 0 else direction,
            StartTime=start.isoformat(), DurationMin=minutes,
            SectionNormalSpeedMps=speed, WettedAreaM2=area, PocMgL=poc, DataSource='가상 직접 입력',
        ))
        start += timedelta(minutes=minutes)
    return buffer.getvalue().encode('utf-8-sig')


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
        net = row['NetInPocKgCDay']
        ratio = row['EbbOutFloodInRatioPct']
        show_daily_basis(float(row['FloodDurationMin']) + float(row['EbbDurationMin']), row['DailyBasis'])
        displayed_net = round(net, 2)
        direction = '순유입' if displayed_net > 0 else '순유출' if displayed_net < 0 else '표시 정밀도에서 균형'
        st.metric('순수송량 (전체 유입 − 전체 유출)',
                  f'{displayed_net or 0:+,.2f} kg C/day', border=True)
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
                      'TotalOutPocKgCDay', 'NetInPocKgCDay', 'DailyBasis', 'ModelStatus', 'InputNotes')
            st.dataframe(pd.DataFrame(rows)[list(fields)].rename(columns={
                'TotalInPocKgCDay': '총유입 (kg C/day)', 'TotalOutPocKgCDay': '총유출 (kg C/day)',
                'NetInPocKgCDay': '순수송량 (kg C/day)',
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
    section_map()
    render_nearby_poc()
    st.stop()

if page == RESULT_PAGE:
    section_result = st.session_state.get('section_result')
    result = st.session_state.get('poc_result')
    if section_result is not None:
        section_results(section_result)
    elif result is None:
        st.title('단면 POC 수송량')
        st.info('입력값 메뉴에서 먼저 탄소 수송량을 계산하세요.')
    else:
        result_csv, result_rows = result
        render_result(result_rows, result_csv)
    section_references()
    carbon_reactions()
    st.stop()

with st.container(horizontal=True, vertical_alignment='center', gap='small', key='workshop-banner'):
    st.image(ROOT / 'kiost-logo.png', width=112, alt='한국해양과학기술원 KIOST 로고')
    st.markdown('한국해양과학기술원(KIOST)  \n**제13차 차세대 해양과학자 워크숍**')
st.title('밀물에 들어온 탄소, 썰물에 얼마나 빠져나갈까?')
st.caption('조석 비대칭성에 따른 비식생 갯벌의 탄소 수송 및 블루카본 저장 안정성 평가')
st.write('조석 기반 단면 POC 순유출량을 산정해 갯벌 탄소 저장량 평가를 보완합니다.')
st.header('입력값')
mode = st.segmented_control('입력 방식', (DEMO_MODE, SERIES_MODE, DIRECT_MODE, CSV_MODE), default=DEMO_MODE,
                            required=True, label_visibility='collapsed', key='tidal_section_input_mode', persist_state='session')

if mode in (DEMO_MODE, SERIES_MODE):
    try:
        section_result = section_input(mode)
    except ValueError as error:
        st.error(str(error))
    else:
        if section_result is not None:
            st.session_state.pop('poc_result', None)
            st.session_state['section_result'] = section_result
            st.session_state['tidal_page'] = RESULT_PAGE
            st.rerun()
    section_references()
    st.stop()

st.caption('단면에 수직인 유속과 침수 단면적을 직접 입력하는 간단 계산입니다. 유향과 조위를 반영하려면 시간별 CSV를 선택하세요.')
if mode == DIRECT_MODE:
    payload = direct_input()
else:
    uploaded = st.file_uploader('관측 CSV 선택', type='csv', max_upload_size=10)
    st.caption('입력 자료 · 사용자 제공 CSV. 관측 기관·보고서 등 원자료 출처는 `DataSource` 열에 입력합니다.')
    data = uploaded.getvalue() if uploaded is not None else None
    compute = st.button('탄소 수송량 계산', type='primary', disabled=not data)
    payload = data if compute else None
    st.download_button('관측 CSV 양식', SCHEMA.read_bytes(), 'observations.template.csv',
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
        st.session_state['poc_result'] = (result_csv, result_rows)
        st.session_state['tidal_page'] = RESULT_PAGE
        st.rerun()

with st.expander('입력 자료 참고문헌'):
    st.markdown(
        '**단면 유량 측정** · Turnipseed와 Sauer(2010), *Discharge Measurements at Gaging Stations*. '
        '[USGS 보고서](https://pubs.usgs.gov/publication/tm3A8)'
    )
