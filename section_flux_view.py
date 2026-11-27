"""Observation CSV uploads for the single-page Streamlit app."""

import csv
from io import StringIO
from pathlib import Path

import streamlit as st

from carbon_budget import BUDGET_COLUMNS
from section_flux import AREA_COLUMNS, DATA_KINDS, INTERVAL_COLUMNS, integrate_section
from tidal_csv import calculate_observation_csv


RESULT_KEY = 'inline_carbon_result'
LEGACY_SCHEMA = Path(__file__).with_name('observations.template.csv')


def csv_bytes(columns, rows=()):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().encode('utf-8-sig')


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
    columns = st.columns(2)
    uploaded = columns[0].file_uploader('관측 CSV 업로드', type='csv', max_upload_size=5, on_change=clear_result)
    payload = uploaded.getvalue() if uploaded is not None else None
    legacy = payload is not None and {'Region', 'Direction', 'SectionNormalSpeedMps'} <= csv_headers(payload)
    area = None if legacy else columns[1].file_uploader(
        '조위–침수 단면적 CSV', type='csv', max_upload_size=1, on_change=clear_result,
    )
    with st.container(horizontal=True):
        st.download_button('관측 CSV 양식', csv_bytes((*INTERVAL_COLUMNS, *BUDGET_COLUMNS)),
                           'section-intervals-template.csv', 'text/csv', on_click='ignore')
        st.download_button('조위–단면적 CSV 양식', csv_bytes(AREA_COLUMNS),
                           'section-area-template.csv', 'text/csv', on_click='ignore')

    if payload is None:
        return None
    if legacy:
        return legacy_results(payload) if st.button('탄소 유입·유출량 계산', type='primary') else None

    with st.form('section-config'):
        angle_col, kind_col, source_col = st.columns(3)
        azimuth = angle_col.number_input('갯벌 방향 법선 방위각 (°)', 0.0, 359.99, 0.0,
                                         help='진북부터 시계 방향으로 적습니다.')
        area_kind = kind_col.selectbox('단면적 자료 구분', tuple(DATA_KINDS), format_func=DATA_KINDS.__getitem__)
        area_source = source_col.text_input('단면적 출처와 조위 기준면')
        submitted = st.form_submit_button('탄소 유입·유출량 계산', type='primary', disabled=area is None)
    if submitted:
        summary, _ = integrate_section(payload, area.getvalue(), azimuth, area_source, area_kind)
        return summary
    return None
