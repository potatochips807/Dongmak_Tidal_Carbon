from pathlib import Path

import streamlit as st

from carbon_budget_view import render_budget
from section_flux_view import RESULT_KEY, clear_result, direct_input, section_input


st.set_page_config(page_title='동막 갯벌 탄소 수송', layout='wide')

with st.container(horizontal=True, vertical_alignment='center', gap='small'):
    st.image(Path(__file__).with_name('kiost-logo.png'), width=92, alt='한국해양과학기술원 KIOST 로고')
    st.caption('제13차 차세대 해양과학자 워크숍')

st.title('밀물에 들어온 탄소, 썰물에 얼마나 빠져나갈까?')
st.header('입력값')
mode = st.segmented_control(
    '입력 방식', ('관측 CSV 업로드', '관측 입력'), default='관측 CSV 업로드',
    required=True, on_change=clear_result,
)
try:
    calculated = direct_input() if mode == '관측 입력' else section_input()
except ValueError as error:
    st.session_state.pop(RESULT_KEY, None)
    st.error(str(error))
else:
    if calculated is not None:
        st.session_state[RESULT_KEY] = calculated

rows = st.session_state.get(RESULT_KEY)
index = 0
if rows and len(rows) > 1:
    index = st.selectbox('계산 구간', range(len(rows)), format_func=lambda i: rows[i]['CycleId'])

st.header('결과값')
if rows:
    row = rows[index]
    if row.get('InputError'):
        st.warning(row['InputError'])
    else:
        render_budget(row)
else:
    render_budget()
