"""Streamlit input and results for three carbon export pathways."""

import altair as alt
import pandas as pd
import streamlit as st

from carbon_budget import budget_interval, summarize_budget
from section_flux import DATA_KINDS
from tidal_csv import protect_cell


PATHWAYS = ('입자성 POC', '용존 DOC + DIC', '대기 CO₂')
FLOW_COLORS = ['#246a9a', '#b55c1d', '#21806d', '#8c5599']


def direct_budget_input():
    st.caption('밀물·썰물의 대표값을 입력합니다. 결측값은 빈칸으로 두고 관측된 0은 0으로 입력하세요.')
    with st.form('direct-carbon-budget'):
        records = []
        for column, (label, phase, sign) in zip(st.columns(2), (('밀물', 'Flood', 1), ('썰물', 'Ebb', -1))):
            with column:
                st.subheader(label)
                minutes = st.number_input('지속 시간 (분)', min_value=1, value=None, step=1, key=f'{phase}-minutes')
                flow = st.number_input('평균 유량의 크기 (m³/s)', min_value=0.0, value=None, key=f'{phase}-flow',
                                       help='유량은 단면 수직 유속(m/s) × 침수 단면적(m²)으로 구할 수 있습니다.')
                concentrations = tuple(st.number_input(f'{kind} (mg C/L)', min_value=0.0, value=None,
                                                       key=f'{phase}-{kind}') for kind in ('POC', 'DOC', 'DIC'))
                air_flux = st.number_input('대기 CO₂ 플럭스 (µmol CO₂/m²/s)', value=None, key=f'{phase}-air-flux',
                                           help='대기로 방출되면 양수, 대기에서 흡수되면 음수입니다.')
                air_area = st.number_input('대기 교환 면적 (m²)', min_value=0.0, value=None, key=f'{phase}-air-area',
                                           help='플럭스가 대표하는 수면 또는 노출 갯벌 면적입니다.')
                records.append((phase, sign, minutes, flow, concentrations, air_flux, air_area))
        kind = st.selectbox('자료 구분', tuple(DATA_KINDS), format_func=DATA_KINDS.__getitem__)
        source = st.text_input('자료 출처 또는 가정', placeholder='관측 기관·기간 또는 가정 근거')
        submitted = st.form_submit_button('탄소 유입·유출량 계산', type='primary')
    if not submitted:
        return None
    if not source.strip():
        raise ValueError('자료 출처 또는 가정 근거를 입력하세요.')
    if any(minutes is None or flow is None for _, _, minutes, flow, *_ in records):
        raise ValueError('밀물과 썰물의 지속 시간과 평균 유량을 입력하세요.')
    details = [
        budget_interval(phase, sign * flow, minutes * 60, concentrations, air_flux, air_area)
        for phase, sign, minutes, flow, concentrations, air_flux, air_area in records
    ]
    return {**summarize_budget(details), 'DataKind': kind, 'DataSource': source.strip(),
            'DurationHours': sum(record[2] for record in records) / 60}


def format_mass(value):
    return '자료 부족' if pd.isna(value) else f'{value:,.6g}'


def render_budget(row):
    st.header('탄소 유입·유출량')
    cards = st.columns(3)
    cards[0].metric('밀물 수중 유입 (kg C)', format_mass(row['FloodInWaterKgC']), border=True)
    cards[1].metric('썰물 수중 유출 (kg C)', format_mass(row['EbbOutWaterKgC']), border=True)
    cards[2].metric('입력 기간 세 경로 총유출 (kg C)', format_mass(row['OutCarbonKgC']), border=True)
    st.caption('밀물·썰물 카드는 해당 조석 단계의 수중 수송량입니다. 대기 CO₂는 입력 기간 전체에 대해 합산합니다.')

    direction_rows = (
        ('수중 POC', 'InPocKgC', 'OutPocKgC'),
        ('수중 DOC', 'InDocKgC', 'OutDocKgC'),
        ('수중 DIC', 'InDicKgC', 'OutDicKgC'),
        ('대기 CO₂ 방출', None, 'OutAirCo2KgC'),
        ('수중 유입 / 세 경로 유출 합계', 'InCarbonKgC', 'OutCarbonKgC'),
    )
    outgoing = [row[key] for key in ('OutPocKgC', 'OutDissolvedKgC', 'OutAirCo2KgC')]
    complete_outgoing = not any(pd.isna(value) for value in outgoing)
    if complete_outgoing and row['OutCarbonKgC'] > 0:
        shares = pd.DataFrame({'경로': PATHWAYS, '탄소량': outgoing})
        shares['비중'] = shares['탄소량'] / row['OutCarbonKgC']
        color = alt.Color('경로:N', scale=alt.Scale(domain=list(PATHWAYS), range=FLOW_COLORS[1:]),
                          legend=alt.Legend(title=None, orient='bottom'))
        chart = alt.Chart(shares).mark_arc(innerRadius=48, outerRadius=92, stroke='white').encode(
            theta=alt.Theta('탄소량:Q', stack=True), color=color,
            tooltip=[alt.Tooltip('경로:N'), alt.Tooltip('탄소량:Q', title='유출량 (kg C)', format=',.4g'),
                     alt.Tooltip('비중:Q', format='.1%')],
        ).properties(height=240, description='수중 POC, DOC와 DIC, 대기 CO₂의 총유출 비중')
        st.subheader('세 경로의 탄소 유출 비중')
        st.altair_chart(chart, width='stretch')
        highest = max(outgoing)
        names = ' · '.join(name for name, value in zip(PATHWAYS, outgoing) if value == highest)
        st.caption(f'가장 큰 유출 경로 · **{names}** ({highest / row["OutCarbonKgC"]:.1%})')
    elif complete_outgoing:
        st.info('입력 기간의 총유출량은 0 kg C입니다.')
    else:
        st.info('세 경로의 유출 자료가 모두 갖춰지면 합계, 원형 그래프와 최대 유출 경로를 표시합니다.')

    if complete_outgoing and not pd.isna(row['InCarbonKgC']):
        labels = ['수중 유입 (POC + DOC + DIC)', *PATHWAYS]
        bars = pd.DataFrame({'구분': ['수중 유입', '세 경로 유출', '세 경로 유출', '세 경로 유출'],
                             '경로': labels, '탄소량': [row['InCarbonKgC'], *outgoing], '순서': range(4)})
        chart = alt.Chart(bars).mark_bar().encode(
            x=alt.X('구분:N', sort=['수중 유입', '세 경로 유출'], title=None),
            y=alt.Y('탄소량:Q', title='입력 기간 탄소량 (kg C)', stack='zero'),
            color=alt.Color('경로:N', scale=alt.Scale(domain=labels, range=FLOW_COLORS),
                            legend=alt.Legend(title=None, orient='bottom')),
            order='순서:Q',
            tooltip=[alt.Tooltip('경로:N'), alt.Tooltip('탄소량:Q', title='탄소량 (kg C)', format=',.4g')],
        ).properties(height=230, description='한 색의 총유입 막대와 세 경로로 쌓은 총유출 막대')
        st.subheader('총유입량과 총유출량 비교')
        st.altair_chart(chart, width='stretch')
        difference = row['NetExportCarbonKgC']
        daily_difference = difference / row['DurationHours'] * 24
        st.caption(f'세 경로 총유출 − 수중 총유입 · **{difference:+,.6g} kg C** · '
                   f'24시간 환산 {daily_difference:+,.6g} kg C/day')
    elif complete_outgoing:
        st.caption('총유입이 산정되면 총유입·총유출 막대그래프와 순유출량을 표시합니다.')

    with st.expander('탄소 형태별 수송 결과'):
        st.dataframe(pd.DataFrame([
            {'형태': label, '수중 유입 (kg C)': format_mass(row[in_key]) if in_key else '—',
             '유출 (kg C)': format_mass(row[out_key])}
            for label, in_key, out_key in direction_rows
        ]), hide_index=True, alt='탄소 형태별 유입량과 유출량')
        if not pd.isna(row['InAirCo2KgC']) and row['InAirCo2KgC'] > 0:
            st.caption(f'별도 관측된 대기 CO₂ 흡수량 · {row["InAirCo2KgC"]:,.4g} kg C')
    st.caption('수중 POC는 단면을 통과한 입자성 탄소입니다. 재부유 기여율은 별도 관측으로 평가합니다.')


def direct_budget_results(row):
    st.title('갯벌 탄소 수송 결과')
    st.caption(f'{DATA_KINDS[row["DataKind"]]} · {row["DurationHours"]:g}시간 · {row["DataSource"]}')
    render_budget(row)
    exported = {**row, 'DataSource': protect_cell(row['DataSource'])}
    st.download_button('경로별 결과 CSV', pd.DataFrame([exported]).to_csv(index=False).encode('utf-8-sig'),
                       'carbon-budget-summary.csv', 'text/csv', on_click='ignore')


def budget_methods():
    with st.expander('세 경로 계산식과 관측 자료'):
        st.latex(r'M_j=\sum_i \frac{C_{j,i}}{1000}Q_i\Delta t_i,\qquad j\in\{\mathrm{POC,DOC,DIC}\}')
        st.latex(r'M_{\mathrm{air}}=\sum_i F_i A_i\Delta t_i (12.011\times10^{-9})')
        st.markdown('수중 탄소는 농도(mg C/L) × 단면 유량(m³/s) × 시간(s)을 kg C로 환산합니다. '
                    'CO₂는 면적당 플럭스(µmol CO₂/m²/s) × 대기 교환 면적(m²) × 시간(s)을 kg C로 환산합니다.')
        st.markdown('유출 비중은 수중 POC, 수중 DOC+DIC, 대기로 방출된 CO₂의 **총유출량**으로 계산합니다. '
                    '수중 유입량은 POC + DOC + DIC입니다. 대기 CO₂ 흡수량은 별도로 표시합니다. '
                    '단면 밖으로 운반된 DIC와 중복 집계되지 않도록 대기 CO₂는 연구구역 안에서 방출된 양을 사용합니다.')
        st.markdown('실측 평가에는 동일 단면·시각의 유량과 수중 POC·DOC·DIC 농도, '
                    '같은 기간·연구구역의 대기 CO₂ 플럭스와 대표 교환 면적이 필요합니다. '
                    '공극수가 공급한 용존탄소는 단면을 지날 때 DOC·DIC 농도에 반영됩니다.')
        st.markdown('조석 수로의 탄소 수송과 대기 CO₂ 교환을 함께 평가한 관측 사례입니다. '
                    '[Bogard 외(2020)](https://doi.org/10.1029/2019GB006430)')
