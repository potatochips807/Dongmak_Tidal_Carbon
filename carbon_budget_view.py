"""Draw one labeled comparison and identify its largest export pathway."""

from itertools import accumulate

import altair as alt
import pandas as pd
import streamlit as st

from carbon_budget import sum_known


PATHWAYS = ('입자성 POC', '용존 DOC + DIC', '대기 CO₂')
COLORS = ['#256d9b', '#b55c1d', '#21806d', '#8c5599']
WATER_TYPES = ('Poc', 'Doc', 'Dic')


def render_budget(row=None):
    waiting_for_data = row is None
    if waiting_for_data:
        row = {}
    has_tide_phases = row.get('FloodInPocKgC') is not None and row.get('EbbOutPocKgC') is not None
    in_prefix, out_prefix = ('FloodIn', 'EbbOut') if has_tide_phases else ('In', 'Out')
    incoming = [row.get(f'{in_prefix}{name}KgC') for name in WATER_TYPES]
    outgoing = [
        row.get(f'{out_prefix}PocKgC'),
        sum_known(row.get(f'{out_prefix}{name}KgC') for name in ('Doc', 'Dic')),
        row.get('OutAirCo2KgC'),
    ]
    categories = ['밀물 수중 유입', '썰물 유출 + 대기'] if has_tide_phases else ['수중 유입', '세 경로 유출']
    title = '탄소 유입량과 유출량'
    inflow_label = '수중 유입'
    segments, totals = [], []
    for category, values, labels in (
        (categories[0], incoming, (inflow_label,) * 3),
        (categories[1], outgoing, PATHWAYS),
    ):
        known = [(value, label) for value, label in zip(values, labels) if value is not None]
        total = sum_known(value for value, _ in known)
        if known and category == categories[0]:
            known = [(total, inflow_label)]
        ends = list(accumulate((value for value, _ in known), initial=0.0))
        for (_, label), start, end in zip(known, ends, ends[1:]):
            segments.append({'구분': category, '경로': label, '시작': start, '끝': end, '탄소량': end - start})
        text = f'{total:,.6g} kg C' if known else '계산 대기' if waiting_for_data else '자료 부족'
        if known and len(values) != sum(value is not None for value in values):
            text = f'확인분 {text}'
        totals.append({'구분': category, '끝': total, '표시값': text})

    scale_end = max(item['끝'] for item in totals) or 1
    axis = alt.Scale(domain=[0, scale_end * 1.75], nice=False)
    y = alt.Y('구분:N', scale=alt.Scale(domain=categories), title=None,
              axis=alt.Axis(labelFontSize=13, labelLimit=134, labelPadding=10, ticks=False, domain=False))
    bars = alt.Chart(pd.DataFrame(segments, columns=('구분', '경로', '시작', '끝', '탄소량'))).mark_bar(size=35).encode(
        y=y, x=alt.X('시작:Q', scale=axis, axis=None), x2='끝:Q',
        color=alt.Color('경로:N', scale=alt.Scale(domain=[inflow_label, *PATHWAYS], range=COLORS),
                        legend=alt.Legend(title=None, orient='bottom', columns=2)),
        tooltip=[alt.Tooltip('경로:N'), alt.Tooltip('탄소량:Q', title='탄소량 (kg C)', format=',.6g')],
    )
    labels = alt.Chart(pd.DataFrame(totals)).mark_text(align='left', dx=8, fontSize=14, fontWeight='bold').encode(
        y=y, x=alt.X('끝:Q', scale=axis, axis=None), text='표시값:N',
    )
    chart = (labels + bars).properties(height=175, title=title).configure_view(strokeWidth=0)
    chart_summary = ' · '.join(f'{item["구분"]} {item["표시값"]}' for item in totals)
    st.altair_chart(chart, width='stretch', height=175, alt=chart_summary)
    if waiting_for_data:
        st.metric('가장 큰 유출 경로', '계산 대기', border=True)
    elif any(value is None for value in outgoing):
        st.metric('가장 큰 유출 경로', '자료 부족', border=True)
    else:
        total_out = sum_known(outgoing)
        if total_out:
            highest = max(outgoing)
            names = ' · '.join(name for name, value in zip(PATHWAYS, outgoing) if value == highest)
            st.metric('가장 큰 유출 경로', names, delta=f'{highest:,.6g} kg C · {highest / total_out:.1%}',
                      delta_color='off', border=True)
        else:
            st.metric('가장 큰 유출 경로', '유출량 0 kg C', border=True)
    if has_tide_phases and outgoing[-1] is not None:
        st.caption('대기 CO₂ 방출량은 입력 기간 전체 기준입니다.')
    if row.get('DataKind') == 'Scenario' or row.get('AreaKind') == 'Scenario':
        st.caption('가상 입력을 사용한 결과입니다.')
