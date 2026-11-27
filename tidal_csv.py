"""Read the tidal observation template and compute section POC transport."""

from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
import io
from math import isfinite
import re


NUMERIC_COLUMNS = (
    'DurationMin', 'SectionNormalSpeedMps', 'WettedAreaM2', 'PocMgL', 'SscMgL',
    'SuspendedOcPct', 'NearBedSpeedMps', 'WaterDensityKgM3', 'DragCoefficient',
    'CriticalShearPa', 'SedimentEpsMgG',
)
POSITIVE_COLUMNS = {'DurationMin', 'WaterDensityKgM3', 'DragCoefficient', 'CriticalShearPa'}
MAXIMUM = {'SuspendedOcPct': 100, 'SedimentEpsMgG': 1000}
NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?')
TIMESTAMP = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-][0-9]{2}:[0-5][0-9])')
GROUP_COLUMNS = ('Region', 'Station', 'CycleId', 'DataKind')
MASS_COLUMNS = ('FloodInPocKgC', 'EbbOutPocKgC', 'TotalInPocKgC', 'TotalOutPocKgC', 'NetInPocKgC',
                'EbbOutFloodInRatioPct')
VOLUME_COLUMNS = ('FloodDurationMin', 'EbbDurationMin', 'FloodInWaterM3', 'EbbOutWaterM3')
SHEAR_COLUMNS = ('FloodPeakBedShearPa', 'EbbPeakBedShearPa', 'FloodMaxShearRatio', 'EbbMaxShearRatio')


def parse_row(headers, values, line):
    if len(values) != len(headers):
        raise ValueError(f'Line {line}: unexpected number of columns.')
    row = dict(zip(headers, (value.strip() for value in values)))
    for key in GROUP_COLUMNS[:3]:
        if not row[key]:
            raise ValueError(f'Line {line}: {key} is required to identify this observation.')
    for key, choices in (
        ('DataKind', ('Observed', 'Scenario')), ('Phase', ('Flood', 'Ebb')),
        ('Direction', ('In', 'Out', 'Slack', '')),
    ):
        if row[key] not in choices:
            raise ValueError(f'Line {line}: invalid {key}.')

    for key in NUMERIC_COLUMNS:
        raw = row[key]
        if not raw:
            row[key] = None
            continue
        value = float(raw) if NUMBER.fullmatch(raw) else float('nan')
        if (not isfinite(value) or value < 0 or (key in POSITIVE_COLUMNS and value == 0)
                or value > MAXIMUM.get(key, float('inf'))):
            raise ValueError(f'Line {line}: {key} has an invalid value. Check the unit and allowed range.')
        row[key] = value

    speed, area = row['SectionNormalSpeedMps'], row['WettedAreaM2']
    poc, ssc, oc_pct = row['PocMgL'], row['SscMgL'], row['SuspendedOcPct']
    if row['Direction'] == 'Slack' and speed not in (None, 0):
        raise ValueError(f'Line {line}: Slack requires a section-normal speed of zero.')
    if area == 0 and speed is not None and speed > 0:
        raise ValueError(f'Line {line}: a dry section cannot have a nonzero section-normal speed.')
    if poc is not None and (ssc is not None or oc_pct is not None):
        raise ValueError(f'Line {line}: enter either direct POC or SSC and suspended organic carbon percentage.')

    row.update(Line=line, Start=None, End=None)
    if row['StartTime']:
        try:
            if not TIMESTAMP.fullmatch(row['StartTime']):
                raise ValueError
            start = datetime.fromisoformat(row['StartTime'])
            if abs(start.utcoffset()) > timedelta(hours=14):
                raise ValueError
            start = start.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise ValueError(f'Line {line}: StartTime must use ISO 8601 with a time-zone offset.') from None
        row['Start'] = start
        if row['DurationMin'] is not None:
            try:
                milliseconds = int(row['DurationMin'] * 60_000 + 0.5)
                row['End'] = start + timedelta(milliseconds=milliseconds)
            except (ValueError, OverflowError):
                raise ValueError(f'Line {line}: DurationMin exceeds the supported date range.') from None
            if row['End'] <= start:
                raise ValueError(f'Line {line}: DurationMin is too small to represent.')

    missing = [key for key in ('Direction', 'StartTime') if not row[key]]
    missing.extend(key for key in ('DurationMin', 'SectionNormalSpeedMps', 'WettedAreaM2') if row[key] is None)
    if speed != 0 and poc is None and (ssc is None or oc_pct is None):
        missing.append('PocMgL or (SscMgL and SuspendedOcPct)')
    if row['DataKind'] == 'Observed' and not row['DataSource']:
        missing.append('DataSource')
    row['Missing'] = missing
    return row


def integrate(rows):
    flood_in = ebb_out = total_in = total_out = flood_volume = ebb_volume = 0.0
    minutes = {'Flood': 0.0, 'Ebb': 0.0}
    for row in rows:
        phase, direction = row['Phase'], row['Direction']
        minutes[phase] += row['DurationMin']
        speed = row['SectionNormalSpeedMps']
        if speed == 0:
            continue
        volume = speed * row['WettedAreaM2'] * (row['DurationMin'] * 60)
        concentration = row['PocMgL']
        if concentration is None:
            concentration = row['SscMgL'] * (row['SuspendedOcPct'] / 100)
        mass = volume * (concentration / 1000)
        if direction == 'In':
            total_in += mass
            if phase == 'Flood':
                flood_in += mass
                flood_volume += volume
        else:
            total_out += mass
            if phase == 'Ebb':
                ebb_out += mass
                ebb_volume += volume

    ratio = ebb_out / flood_in * 100 if flood_in else None
    values = (flood_in, ebb_out, total_in, total_out, total_in - total_out, ratio,
              minutes['Flood'], minutes['Ebb'], flood_volume, ebb_volume)
    if any(not isfinite(value) for value in values if value is not None):
        raise ValueError(f'Line {rows[0]["Line"]}: POC calculation exceeded the supported numeric range.')
    return dict(zip(MASS_COLUMNS + VOLUME_COLUMNS, values))


def protect_cell(value):
    return "'" + value if re.match(r'^\s*[=+@-]', value) else value


def summarize_group(keys, rows):
    flood_count = sum(row['Phase'] == 'Flood' for row in rows)
    ebb_count = len(rows) - flood_count
    notes = [f'Line {row["Line"]}: {", ".join(row["Missing"])}' for row in rows if row['Missing']]
    timed = sorted((row for row in rows if row['End'] is not None), key=lambda row: row['Start'])
    has_gap = False
    for previous, current in zip(timed, timed[1:]):
        if current['Start'] < previous['End']:
            raise ValueError(f'Lines {previous["Line"]} and {current["Line"]}: intervals overlap in the same section and tide cycle.')
        has_gap |= current['Start'] > previous['End']
    if not flood_count:
        notes.append('No Flood rows')
    if not ebb_count:
        notes.append('No Ebb rows')
    if has_gap:
        notes.append('Gap between recorded intervals')

    data_sources = sorted({row['DataSource'] for row in rows if row['DataSource']}, key=str.casefold)
    result = dict(zip(GROUP_COLUMNS, map(protect_cell, keys)))
    result.update(FloodRows=flood_count, EbbRows=ebb_count,
                  InputStatus='ReviewInput' if notes else 'ReadyForModel', InputNotes=' | '.join(notes),
                  DataSources=protect_cell(' | '.join(data_sources)),
                  ModelStatus='SkippedInputReview' if notes else 'Calculated')
    result.update(dict.fromkeys(MASS_COLUMNS + SHEAR_COLUMNS + VOLUME_COLUMNS))
    if not notes:
        result.update(integrate(rows))
    return {key: '' if value is None else str(value) for key, value in result.items()}


def calculate_observation_csv(payload: bytes, expected_headers: list[str]) -> list[dict[str, str]]:
    groups = defaultdict(list)
    try:
        reader = csv.reader(io.StringIO(payload.decode('utf-8-sig'), newline=''), strict=True)
        headers = next(reader, [])
        if sorted(headers) != sorted(expected_headers):
            raise ValueError('Input CSV headers must match the generated observation template.')
        line = reader.line_num + 1
        for values in reader:
            if values and any(value.strip() for value in values):
                row = parse_row(headers, values, line)
                groups[tuple(row[key] for key in GROUP_COLUMNS)].append(row)
            line = reader.line_num + 1
    except (UnicodeError, csv.Error) as error:
        raise ValueError('관측 CSV의 UTF-8 인코딩과 열 구분을 확인하세요.') from error
    if not groups:
        raise ValueError('계산할 관측 구간을 한 행 이상 입력하세요.')
    return [summarize_group(keys, rows) for keys, rows in sorted(groups.items())]
