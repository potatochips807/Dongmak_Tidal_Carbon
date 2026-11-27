"""Observation CSV uploads for the single-page Streamlit app."""

import csv
from io import StringIO
from pathlib import Path

import streamlit as st

from carbon_budget import budget_interval, summarize_budget
from section_flux import DATA_KINDS, integrate_section
from tidal_csv import calculate_observation_csv


RESULT_KEY = 'inline_carbon_result'
LEGACY_SCHEMA = Path(__file__).with_name('observations.template.csv')
DIRECT_EXAMPLES = {
    'Flood': (360, 1.0, (1.0, 2.0, 24.0), 1.0, 10000.0),
    'Ebb': (360, 1.2, (2.0, 3.0, 26.0), 2.0, 10000.0),
}


def csv_headers(payload):
    try:
        return set(next(csv.reader(StringIO(payload.decode('utf-8-sig'), newline=''), strict=True), ()))
    except (UnicodeError, csv.Error):
        raise ValueError('관측 CSV를 UTF-8 형식으로 저장해 주세요.') from None


def legacy_results(payload):
    with LEGACY_SCHEMA.open(encoding='utf-8-sig', newline='') as template:
        rows = calculate_observation_csv(payload, next(csv.reader(template)))
    results = []
    for row in rows:
        summary = {'CycleId': row['CycleId'], 'DataKind': row['DataKind']}
        if row['ModelStatus'] == 'Calculated':
            summary.update({
                'FloodInPocKgC': float(row['FloodInPocKgC']),
                'EbbOutPocKgC': float(row['EbbOutPocKgC']),
            })
        else:
            summary['InputError'] = row['InputNotes'] or 'POC 수송량을 계산할 자료가 부족합니다.'
        results.append(summary)
    if not results:
        raise ValueError('계산할 관측 구간이 없습니다.')
    return results


def clear_result():
    st.session_state.pop(RESULT_KEY, None)


def section_input():
    uploaded = st.file_uploader(
        '관측 CSV 업로드', type='csv', max_upload_size=5, on_change=clear_result,
        help='FlowM3S는 단면 유량(m³/s)입니다. 갯벌 방향은 양수, 바다 방향은 음수로 적습니다.',
    )
    submitted = st.button('탄소 유입·유출량 계산', type='primary', disabled=uploaded is None)
    if uploaded is None or not submitted:
        return None
    payload = uploaded.getvalue()
    headers = csv_headers(payload)
    if 'FlowM3S' not in headers and {'Region', 'Direction', 'SectionNormalSpeedMps'} <= headers:
        return legacy_results(payload)
    summary, _ = integrate_section(payload)
    return summary


def direct_input():
    data_kind = st.selectbox('자료 구분', tuple(DATA_KINDS), format_func=DATA_KINDS.__getitem__,
                             on_change=clear_result)
    is_scenario = data_kind == 'Scenario'
    if is_scenario:
        st.caption('계산을 확인할 수 있도록 가상 예시값을 채웠습니다. 값을 바꿔 계산할 수 있습니다.')
    suffix = '' if is_scenario else '-observed'
    with st.form('direct-carbon'):
        intervals = []
        for column, (heading, phase, sign) in zip(
            st.columns(2), (('밀물', 'Flood', 1), ('썰물', 'Ebb', -1)),
        ):
            defaults = DIRECT_EXAMPLES[phase] if is_scenario else (None, None, (None, None, None), None, None)
            minutes, flow, carbon, air_flux, area = defaults
            with column:
                st.subheader(heading)
                duration = st.number_input('지속 시간 (분)', min_value=1, value=minutes, key=f'{phase}-minutes{suffix}')
                discharge = st.number_input('평균 유량의 크기 (m³/s)', min_value=0.0, value=flow,
                                            key=f'{phase}-flow{suffix}')
                concentrations = tuple(st.number_input(
                    f'{name} 농도 (mg C/L)', min_value=0.0, value=value, key=f'{phase}-{name}{suffix}',
                ) for name, value in zip(('POC', 'DOC', 'DIC'), carbon))
                flux = st.number_input('대기 CO₂ 플럭스 (µmol CO₂/m²/s)', value=air_flux, key=f'{phase}-flux{suffix}',
                                       help='대기로 방출되는 값은 양수, 대기에서 흡수되는 값은 음수입니다.')
                exchange_area = st.number_input('대기 CO₂ 교환 면적 (m²)', min_value=0.0, value=area,
                                                key=f'{phase}-air-area{suffix}')
                intervals.append((phase, sign, duration, discharge, concentrations, flux, exchange_area))
        submitted = st.form_submit_button('탄소 유입·유출량 계산', type='primary')
    if not submitted:
        return None
    if any(duration is None or discharge is None for _, _, duration, discharge, *_ in intervals):
        raise ValueError('밀물과 썰물의 지속 시간과 평균 유량을 입력해 주세요.')
    budget = summarize_budget([
        budget_interval(phase, sign * discharge, duration * 60, concentrations, flux, exchange_area)
        for phase, sign, duration, discharge, concentrations, flux, exchange_area in intervals
    ])
    return [{**budget, 'CycleId': '직접 입력', 'DataKind': data_kind}]
