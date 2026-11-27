"""Streamlit views for section flux inputs, results, and methods."""

import csv
from datetime import datetime, timedelta
from io import StringIO
from math import cos, pi, sin
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from section_flux import AREA_COLUMNS, DATA_KINDS, INTERVAL_COLUMNS, TIDE_REGIMES, integrate_section
from tidal_csv import protect_cell


DEMO_MODE = '대조·소조 예시'
SERIES_MODE = '시간별 CSV'
MAP_FILE = Path(__file__).resolve().parent / 'data' / 'study-area-section.svg'


def csv_bytes(columns, rows):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().encode('utf-8-sig')


def example_files():
    period = 745
    records = []
    for cycle, regime, date, amplitude, peak_speed in (
        ('SPRING-DEMO', 'Spring', '2000-01-01T06:00:00+09:00', 3.5, 0.58),
        ('NEAP-DEMO', 'Neap', '2000-01-08T06:00:00+09:00', 1.8, 0.34),
    ):
        start = datetime.fromisoformat(date)
        for elapsed in range(0, period, 60):
            duration = min(60, period - elapsed)
            angle = 2 * pi * (elapsed + duration / 2) / period
            phase_flow = sin(angle)
            records.append((cycle, 'Scenario', regime, (start + timedelta(minutes=elapsed)).isoformat(),
                            duration, round(-amplitude * cos(angle), 3), round(peak_speed * abs(phase_flow), 3),
                            25 if phase_flow >= 0 else 205, 0.35 if phase_flow >= 0 else 0.53,
                            '발표용 가상 조석 조건'))
    geometry = [(-9, 0), (-3, 9000), (0, 16500), (3, 24200), (5, 30000)]
    return csv_bytes(INTERVAL_COLUMNS, records), csv_bytes(AREA_COLUMNS, geometry)


def section_input(mode):
    example_series, example_area = example_files()
    with st.container(horizontal=True):
        st.download_button('시간별 CSV 예시', example_series, 'section-intervals-example.csv', 'text/csv', on_click='ignore')
        st.download_button('조위–단면적 CSV 예시', example_area, 'section-area-example.csv', 'text/csv', on_click='ignore')
    if mode == DEMO_MODE:
        st.info('발표용 가상 입력입니다. 지도에 표시한 가상 단면의 북쪽을 유입 방향으로 둡니다.')
        with st.expander('시간별 가상 입력과 조위–단면적 표'):
            for payload, label in ((example_series, '가상 시간별 입력'), (example_area, '가상 조위–단면적 표')):
                st.dataframe(pd.DataFrame(list(csv.DictReader(StringIO(payload.decode('utf-8-sig'))))),
                             hide_index=True, alt=label)
        if st.button('단면 POC 수송량 계산', type='primary'):
            return integrate_section(example_series, example_area, 0.0, '발표용 가상 조위–단면적 표')
        return None

    st.caption('한 번에 한 단면을 계산합니다. 조위 시계열과 단면적 표에는 같은 수직 기준면을 사용하세요.')
    source_col, area_col = st.columns(2)
    intervals = source_col.file_uploader('시간별 유속·유향·조위·POC CSV', type='csv', max_upload_size=5)
    area = area_col.file_uploader('조위–침수 단면적 CSV', type='csv', max_upload_size=1)
    with st.form('section-config'):
        azimuth = st.number_input('갯벌 방향 단면 법선 방위각 (°)', 0.0, 359.99, 0.0,
                                  help='진북에서 시계 방향으로 잽니다. 유향은 물이 향하는 쪽입니다.')
        area_kind = st.selectbox('단면적 표의 자료 구분', tuple(DATA_KINDS), format_func=DATA_KINDS.__getitem__)
        area_source = st.text_input('단면적 출처와 조위 기준면', placeholder='예: 단면 측량 보고서, 기본수준면')
        submitted = st.form_submit_button('단면 POC 수송량 계산', type='primary', disabled=not (intervals and area))
    if submitted:
        return integrate_section(intervals.getvalue(), area.getvalue(), azimuth, area_source, area_kind)
    with st.expander('시간별 CSV 작성법'):
        st.write('한 행은 값이 대표하는 시간 구간입니다. StartTime에는 UTC 오프셋을 넣고, DurationMin으로 구간 길이를 지정합니다.')
        st.write('DataKind는 Scenario 또는 Observed, TideRegime은 Spring(대조기), Neap(소조기), Other(기타)입니다. 주기마다 CycleId를 지정하고 DataSource에 출처를 적으세요.')
        st.write('StageM은 조위(m), SpeedMps는 유속 크기(m/s), FlowBearingDeg는 유향(°), PocMgL은 단면을 대표하는 수중 POC 농도(mg C/L)입니다. 연속 구간 사이에 공백이 있으면 계산을 보류합니다.')
    return None


def section_results(result):
    summary, detail = map(pd.DataFrame, result)
    st.title('단면 POC 수송량')
    index = 0
    if len(summary) > 1:
        index = st.selectbox('계산 구간', range(len(summary)), format_func=lambda i: (
            f'{TIDE_REGIMES[summary.iloc[i].TideRegime]} · {summary.iloc[i].CycleId}'))
    row = summary.iloc[index]
    st.caption(f'{DATA_KINDS[row.DataKind]} · {TIDE_REGIMES[row.TideRegime]} · 구간 {row.DurationHours:.2f}시간')
    st.text(f'유속·조위·POC 출처 · {row.DataSource}')
    st.text(f'단면적 출처 · {DATA_KINDS[row.AreaKind]} · {row.AreaSource}')
    if row.DataKind == 'Observed' and row.AreaKind == 'Scenario':
        st.info('관측 시계열에 가상 단면적을 적용한 시나리오입니다.')
    cards = st.columns(3)
    cards[0].metric('갯벌 방향 유입 (kg C)', f'{row.InPocKgC:,.2f}', border=True)
    cards[1].metric('바다 방향 유출 (kg C)', f'{row.OutPocKgC:,.2f}', border=True)
    cards[2].metric('순수송량 (kg C)', f'{row.NetPocKgC:+,.2f}', border=True,
                    help='유입량에서 유출량을 뺍니다. 음수는 바다 방향 순유출입니다.')
    st.caption(f'24시간 기준 순수송률 {row.NetPocKgCDay:+,.2f} kg C/day · 입력 기간의 평균 수송률을 하루 단위로 환산')

    unique_cycles = summary[summary.TideRegime.isin(('Spring', 'Neap'))]
    comparison = unique_cycles.groupby(['DataKind', 'AreaKind', 'TideRegime'], as_index=False).agg(
        count=('CycleId', 'size'), inflow=('InPocKgCDay', 'mean'),
        outflow=('OutPocKgCDay', 'mean'), net=('NetPocKgCDay', 'mean'))
    comparison = comparison[comparison.groupby(['DataKind', 'AreaKind']).TideRegime.transform('size') == 2]
    if not comparison.empty:
        st.subheader('대조기·소조기 비교')
        comparison = comparison.assign(DataKind=comparison.DataKind.map(DATA_KINDS),
                                       AreaKind=comparison.AreaKind.map(DATA_KINDS),
                                       TideRegime=comparison.TideRegime.map(TIDE_REGIMES))
        st.dataframe(comparison.round(2).rename(columns={
            'DataKind': '시계열 자료', 'AreaKind': '단면적 자료', 'TideRegime': '조석 조건',
            'count': '입력 구간 수', 'inflow': '평균 유입 (kg C/day)',
            'outflow': '평균 유출 (kg C/day)', 'net': '평균 순수송 (kg C/day)',
        }), hide_index=True, alt='자료 종류별 대조기와 소조기의 평균 순수송률')
        st.caption('조석 조건은 입력 CSV의 구분을 사용합니다. 비교하려면 각 CycleId에 같은 기준으로 조석 주기를 기록하세요.')
    else:
        st.caption('같은 자료 구분으로 대조기와 소조기를 모두 입력하면 두 조건의 수송량을 비교합니다.')

    with st.expander('구간별 유속·침수 단면적·POC 플럭스'):
        selected = detail[detail.CycleId == row.CycleId]
        chart = alt.Chart(selected).mark_line(point=True).encode(
            x=alt.X('StartTime:T', title='구간 시작 시각'),
            y=alt.Y('PocFluxKgCS:Q', title='부호 있는 POC 플럭스 (kg C/s)'),
            tooltip=['StageM:Q', 'NormalSpeedMps:Q', 'WettedAreaM2:Q', 'PocFluxKgCS:Q'],
        ).properties(height=180, description='선택한 구간의 시간별 단면 POC 플럭스')
        if len(selected) <= 5000:
            st.altair_chart(chart, width='stretch')
        st.dataframe(selected[['StartTime', 'StageM', 'NormalSpeedMps', 'WettedAreaM2', 'PocFluxKgCS', 'SignedPocKgC']],
                     hide_index=True, alt='구간별 조위, 수직 유속, 침수 면적, 플럭스와 POC 질량')
    with st.container(horizontal=True):
        for label, frame, filename in (('주기별 결과 CSV', summary, 'section-flux-summary.csv'),
                                       ('시간별 결과 CSV', detail, 'section-flux-intervals.csv')):
            payload = frame.assign(CycleId=frame.CycleId.map(protect_cell)).to_csv(index=False).encode('utf-8-sig')
            st.download_button(label, payload, filename, 'text/csv', on_click='ignore')


def section_map():
    st.subheader('연구해역과 가상 단면')
    st.image(MAP_FILE, width='stretch',
             alt='강화 남단 연구해역의 가상 단면. 북쪽은 갯벌 방향 유입, 남쪽은 바다 방향 유출.')
    st.caption('제공된 연구해역 지도 위에 가상 단면을 표시했습니다. 단면 중심은 약 37.57°N, 126.40°E입니다. 예시의 갯벌 방향 법선은 진북 0°입니다.')


def section_references():
    with st.expander('단면 플럭스 계산식과 참고문헌'):
        st.latex(r'U_{perp,i} = U_i\cos(\theta_i-\theta_n),\qquad Q_i=A(\eta_i)U_{perp,i}')
        st.latex(r'F_{\mathrm{POC},i}=\frac{Q_i C_i}{1000},\qquad M_i=F_{\mathrm{POC},i}\Delta t_i')
        st.latex(r'M_{\mathrm{net}}=\sum_i\max(M_i,0)-\sum_i\max(-M_i,0)')
        st.write('진북 기준 유향과 갯벌 방향 법선의 차이로 수직 유속을 구합니다. 조위에 따른 침수 단면적은 입력한 표에서 선형 보간합니다.')
        st.write('각 구간을 대표하는 유속·면적·농도의 곱에 지속 시간(초)을 곱하고, 양수와 음수를 따로 적분합니다. 단면 내 수직·수평 분포는 대표값으로 근사합니다.')
        st.caption('Q는 m³/s, C는 mg C/L입니다. 1 mg C/L = 0.001 kg C/m³이므로 1,000으로 나누면 F가 kg C/s, M이 kg C입니다.')
        st.markdown('- **조석 수로의 관측 기반 POC 수송** · Ganju 외(2019). [단면 유속과 부유입자 연구](https://pubs.usgs.gov/publication/70203493)\n'
                    '- **유속–면적법** · Turnipseed & Sauer(2010). [USGS 보고서](https://pubs.usgs.gov/publication/tm3A8)\n'
                    '- **조위·지형 기반 물 부피 변화 방식** · Yuan 외(2022). [비교 연구](https://doi.org/10.3389/fmars.2021.809618)')


def carbon_reactions():
    with st.expander('생지화학 참고 · POC에서 DOC와 DIC로'):
        st.write('입자성 유기물의 미생물 효소 가수분해는 탄소를 용존 유기물로 옮길 수 있습니다. DOC 일부는 미생물 호흡으로 CO₂(aq)를 생성해 해수의 DIC에 기여합니다.')
        st.latex(r'\mathrm{POC}\xrightarrow{\text{hydrolysis}}\mathrm{DOC}'
                 r'\xrightarrow{\text{remineralization}}\mathrm{CO_2(aq)}\subset\mathrm{DIC}')
        st.latex(r'\mathrm{CH_2O}+\mathrm{O_2}\rightarrow\mathrm{CO_2(aq)}+\mathrm{H_2O}')
        st.caption('CH₂O는 유기물의 단순화된 표현입니다. 수송량은 단면을 통과한 POC의 질량이며, 이 반응식은 별도의 과정 설명입니다.')
        st.markdown('- **입자 유기물의 효소 가수분해** · Smith 외(1992). [Nature](https://doi.org/10.1038/359139a0)\n'
                    '- **용존 유기물의 미생물 재광물화** · Hach 외(2020). [해수 배양에서 표지 탄소가 CO₂로 전환된 사례](https://pmc.ncbi.nlm.nih.gov/articles/PMC7400608/)')
