"""Observation CSV uploads for the single-page Streamlit app."""

import csv
from io import StringIO
from pathlib import Path

import streamlit as st

from section_flux import integrate_section
from tidal_csv import calculate_observation_csv


RESULT_KEY = 'inline_carbon_result'
LEGACY_SCHEMA = Path(__file__).with_name('observations.template.csv')


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
