"""A carbon budget across one water section and the overlying air boundary."""

from math import fsum, isfinite


BUDGET_COLUMNS = ('Phase', 'DocMgL', 'DicMgL', 'AirCo2FluxUmolM2S', 'AirExchangeAreaM2')
WATER_TYPES = ('Poc', 'Doc', 'Dic')
CARBON_KG_PER_UMOL = 12.011e-9


def budget_interval(phase, flow, seconds, concentrations, air_flux=None, air_area=None):
    """Water flow is positive inward. Air flux is positive upward."""
    result = {'Phase': phase, 'WaterFlowM3S': flow}
    for name, concentration in zip(WATER_TYPES, concentrations):
        result[f'Signed{name}KgC'] = (
            0.0 if flow == 0 else None if concentration is None else flow * (concentration / 1000) * seconds
        )
    result['SignedAirCo2KgC'] = (
        None if air_flux is None or air_area is None
        else air_flux * CARBON_KG_PER_UMOL * air_area * seconds
    )
    if any(value is not None and not isfinite(value) for key, value in result.items() if key != 'Phase'):
        raise ValueError('탄소 수송량이 계산 범위를 벗어났습니다. 입력 단위를 확인하세요.')
    return result


def sum_known(values):
    values = tuple(values)
    if any(value is None for value in values):
        return None
    try:
        return fsum(values)
    except OverflowError:
        raise ValueError('탄소 합계가 계산 범위를 벗어났습니다.') from None


def directional_total(rows, field, inward_sign):
    return sum_known(None if row[field] is None else max(inward_sign * row[field], 0.0) for row in rows)


def summarize_budget(rows):
    totals = {}
    for name in WATER_TYPES:
        field = f'Signed{name}KgC'
        totals[f'In{name}KgC'] = directional_total((row for row in rows if row['WaterFlowM3S'] > 0), field, 1)
        totals[f'Out{name}KgC'] = directional_total((row for row in rows if row['WaterFlowM3S'] < 0), field, -1)
    for direction in ('In', 'Out'):
        totals[f'{direction}DissolvedKgC'] = sum_known(totals[f'{direction}{name}KgC'] for name in ('Doc', 'Dic'))
        totals[f'{direction}WaterKgC'] = sum_known(totals[f'{direction}{name}KgC'] for name in WATER_TYPES)
    totals['InAirCo2KgC'] = directional_total(rows, 'SignedAirCo2KgC', -1)
    totals['OutAirCo2KgC'] = directional_total(rows, 'SignedAirCo2KgC', 1)
    totals['InCarbonKgC'] = totals['InWaterKgC']
    totals['OutCarbonKgC'] = sum_known((totals['OutWaterKgC'], totals['OutAirCo2KgC']))
    incoming, outgoing = totals['InCarbonKgC'], totals['OutCarbonKgC']
    totals['NetExportCarbonKgC'] = None if incoming is None or outgoing is None else outgoing - incoming
    for phase, direction, sign in (('Flood', 'In', 1), ('Ebb', 'Out', -1)):
        phase_rows = [row for row in rows if row['Phase'] == phase]
        direction_rows = [row for row in phase_rows if sign * row['WaterFlowM3S'] > 0]
        for name in WATER_TYPES:
            totals[f'{phase}{direction}{name}KgC'] = (
                directional_total(direction_rows, f'Signed{name}KgC', sign)
                if phase_rows and all(row['Phase'] for row in rows) else None
            )
        totals[f'{phase}{direction}WaterKgC'] = sum_known(
            totals[f'{phase}{direction}{name}KgC'] for name in WATER_TYPES
        )
    return totals
