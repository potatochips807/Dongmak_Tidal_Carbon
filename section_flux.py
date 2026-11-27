"""Integrate signed POC transport over a stage-dependent section."""

from bisect import bisect_right
from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from math import cos, fsum, isfinite, radians

from carbon_budget import BUDGET_COLUMNS, budget_interval, summarize_budget
from tidal_csv import protect_cell


INTERVAL_COLUMNS = ('CycleId', 'DataKind', 'TideRegime', 'StartTime', 'DurationMin',
                    'StageM', 'SpeedMps', 'FlowBearingDeg', 'PocMgL', 'DataSource')
FLOW_COLUMNS = ('CycleId', 'DataKind', 'TideRegime', 'StartTime', 'DurationMin',
                'FlowM3S', 'PocMgL', 'DataSource')
VELOCITY_COLUMNS = (*FLOW_COLUMNS[:5], 'SectionNormalSpeedMps', 'WettedAreaM2', *FLOW_COLUMNS[6:])
AREA_COLUMNS = ('StageM', 'WettedAreaM2')
TIDE_REGIMES = {'Spring': '대조기', 'Neap': '소조기', 'Other': '기타'}
DATA_KINDS = {'Scenario': '가상 입력', 'Observed': '관측 입력'}


def read_csv(payload, columns, optional_columns=()):
    try:
        reader = csv.reader(StringIO(payload.decode('utf-8-sig'), newline=''), strict=True)
        headers = next(reader, [])
        header_set = set(headers)
        if (len(headers) != len(header_set) or
                not set(columns) <= header_set <= set((*columns, *optional_columns))):
            raise ValueError(f'CSV 열 이름을 확인하세요. 필수 열은 {", ".join(columns)}입니다.')
        records = []
        line = reader.line_num + 1
        for fields in reader:
            if any(field.strip() for field in fields):
                if len(fields) != len(headers):
                    raise ValueError(f'{line}행의 열 개수를 확인하세요.')
                records.append((line, dict(zip(headers, (field.strip() for field in fields)))))
            line = reader.line_num + 1
    except (UnicodeError, csv.Error) as error:
        raise ValueError('CSV는 쉼표로 구분한 UTF-8 파일이어야 합니다.') from error
    if not records:
        raise ValueError('CSV에 자료를 한 행 이상 입력하세요.')
    return records


def number(row, column, line, *, minimum=None):
    try:
        value = float(row[column])
    except ValueError:
        raise ValueError(f'{line}행의 {column} 값을 숫자로 입력하세요.') from None
    if not isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError(f'{line}행의 {column} 값이 유효 범위를 벗어났습니다.')
    return value


def optional_number(row, column, line, *, minimum=None):
    return number(row, column, line, minimum=minimum) if row.get(column) else None


def read_area_curve(payload):
    points = sorted((number(row, 'StageM', line), number(row, 'WettedAreaM2', line, minimum=0))
                    for line, row in read_csv(payload, AREA_COLUMNS))
    if len(points) < 2:
        raise ValueError('조위–침수 단면적 표에 두 점 이상이 필요합니다.')
    for (level, area), (next_level, next_area) in zip(points, points[1:]):
        if level == next_level or area > next_area:
            raise ValueError('조위는 중복될 수 없고 침수 단면적은 조위가 높아질 때 줄어들 수 없습니다.')
    return tuple(zip(*points))


def wetted_area(stage, levels, areas):
    if not levels[0] <= stage <= levels[-1]:
        raise ValueError(f'조위 {stage:g} m가 단면적 자료 범위({levels[0]:g}~{levels[-1]:g} m)를 벗어났습니다.')
    upper = bisect_right(levels, stage)
    if upper == len(levels):
        return areas[-1]
    lower = upper - 1
    fraction = (stage - levels[lower]) / (levels[upper] - levels[lower])
    return areas[lower] + fraction * (areas[upper] - areas[lower])


def integrate_section(
    interval_csv, area_csv=None, landward_bearing=None, area_source='', area_kind='Scenario', *, from_velocity=False,
):
    """Integrate measured or estimated section discharge. Positive flow points landward."""
    use_area = area_csv is not None
    if use_area:
        if landward_bearing is None or not 0 <= landward_bearing < 360:
            raise ValueError('유입 법선 방위각은 0° 이상 360° 미만이어야 합니다.')
        if not area_source.strip():
            raise ValueError('조위–단면적 자료의 출처를 입력하세요.')
        if area_kind not in DATA_KINDS:
            raise ValueError('조위–단면적 자료의 구분을 확인하세요.')
        levels, areas = read_area_curve(area_csv)
    geometry_source = {
        'LandwardBearingDeg': landward_bearing if use_area else None,
        'AreaKind': area_kind if use_area else None,
        'AreaSource': protect_cell(area_source.strip()) if use_area else None,
    }
    required_columns = INTERVAL_COLUMNS if use_area else VELOCITY_COLUMNS if from_velocity else FLOW_COLUMNS
    optional_columns = BUDGET_COLUMNS if use_area else (*BUDGET_COLUMNS, 'StageM', 'SpeedMps', 'FlowBearingDeg')
    cycles = defaultdict(list)
    for line, row in read_csv(interval_csv, required_columns, optional_columns):
        cycle_id, data_kind, regime = row['CycleId'], row['DataKind'], row['TideRegime']
        if not cycle_id or data_kind not in DATA_KINDS or regime not in TIDE_REGIMES:
            raise ValueError(f'{line}행의 CycleId, DataKind, TideRegime을 확인하세요.')
        if not row['DataSource']:
            raise ValueError(f'{line}행의 DataSource에 관측 출처 또는 가정 내용을 입력하세요.')
        duration = number(row, 'DurationMin', line, minimum=0)
        try:
            timestamp = datetime.fromisoformat(row['StartTime'])
            if timestamp.utcoffset() is None or 'T' not in row['StartTime']:
                raise ValueError
            start = timestamp.astimezone(timezone.utc)
            end = start + timedelta(minutes=duration)
        except (OverflowError, ValueError):
            raise ValueError(f'{line}행에 시간대가 있는 ISO 8601 시각과 유효한 지속 시간을 입력하세요.') from None
        if end <= start:
            raise ValueError(f'{line}행의 지속 시간은 0보다 커야 합니다.')
        geometry = {}
        if use_area:
            bearing = number(row, 'FlowBearingDeg', line, minimum=0)
            if bearing >= 360:
                raise ValueError(f'{line}행의 유향은 360° 미만이어야 합니다.')
            stage = number(row, 'StageM', line)
            area = wetted_area(stage, levels, areas)
            speed = number(row, 'SpeedMps', line, minimum=0)
            projection = cos(radians(bearing - landward_bearing))
            normal_speed = speed * projection if abs(projection) > 1e-14 else 0.0
            flow = normal_speed * area
            geometry = {'StageM': stage, 'SpeedMps': speed, 'FlowBearingDeg': bearing,
                        'NormalSpeedMps': normal_speed, 'WettedAreaM2': area}
        elif from_velocity:
            normal_speed = number(row, 'SectionNormalSpeedMps', line)
            area = number(row, 'WettedAreaM2', line, minimum=0)
            flow = normal_speed * area
            geometry = {'NormalSpeedMps': normal_speed, 'WettedAreaM2': area}
        else:
            flow = number(row, 'FlowM3S', line)
        poc = number(row, 'PocMgL', line, minimum=0)
        rate = flow * (poc / 1000)
        if not all(isfinite(value) for value in (flow, rate)):
            raise ValueError(f'{line}행의 값이 계산 범위를 벗어났습니다. 단위를 확인하세요.')
        phase = row.get('Phase') or None
        if phase not in (None, 'Flood', 'Ebb', 'Slack'):
            raise ValueError(f'{line}행의 Phase는 Flood, Ebb 또는 Slack으로 입력하세요.')
        doc = optional_number(row, 'DocMgL', line, minimum=0)
        dic = optional_number(row, 'DicMgL', line, minimum=0)
        air_flux = optional_number(row, 'AirCo2FluxUmolM2S', line)
        air_area = optional_number(row, 'AirExchangeAreaM2', line, minimum=0)
        budget = budget_interval(phase, flow, (end - start).total_seconds(), (poc, doc, dic), air_flux, air_area)
        cycles[cycle_id].append((start, end, line, {
            'CycleId': cycle_id, 'DataKind': data_kind, 'TideRegime': regime,
            'StartTime': timestamp.isoformat(), 'DurationMin': duration, 'FlowM3S': flow,
            **geometry, **geometry_source,
            'PocMgL': poc, 'DocMgL': doc, 'DicMgL': dic, 'PocFluxKgCS': rate,
            'AirCo2FluxUmolM2S': air_flux, 'AirExchangeAreaM2': air_area, **budget,
            'DataSource': protect_cell(row['DataSource']),
        }))

    summaries, details = [], []
    for cycle_id, entries in cycles.items():
        entries.sort(key=lambda entry: entry[0])
        rows = [entry[3] for entry in entries]
        if len({(row['DataKind'], row['TideRegime']) for row in rows}) != 1:
            raise ValueError(f'{cycle_id}에 자료 구분 또는 대조·소조 구분이 섞여 있습니다.')
        for left, right in zip(entries, entries[1:]):
            if left[1] != right[0]:
                raise ValueError(f'{cycle_id}의 {left[2]}–{right[2]}행 사이에 공백 또는 시간 중복이 있습니다.')
        seconds = fsum((end - start).total_seconds() for start, end, _, _ in entries)
        budget = summarize_budget(rows)
        inflow, outflow = budget['InPocKgC'], budget['OutPocKgC']
        net = inflow - outflow
        daily_in, daily_out, daily_net = (mass / seconds * 86400 for mass in (inflow, outflow, net))
        if not all(isfinite(value) for value in (daily_in, daily_out, daily_net)):
            raise ValueError(f'{cycle_id}의 일 환산값이 계산 범위를 벗어났습니다.')
        summaries.append({
            **{key: rows[0][key] for key in ('CycleId', 'DataKind', 'TideRegime', 'LandwardBearingDeg', 'AreaKind', 'AreaSource')},
            **budget,
            'DurationHours': seconds / 3600,
            'NetPocKgC': net, 'NetExportPocKgC': -net or 0.0,
            'InPocKgCDay': daily_in, 'OutPocKgCDay': daily_out, 'NetPocKgCDay': daily_net,
            'NetExportPocKgCDay': -daily_net or 0.0,
            'DataSource': ' | '.join(dict.fromkeys(row['DataSource'] for row in rows)),
        })
        details.extend(rows)
    return summaries, details
