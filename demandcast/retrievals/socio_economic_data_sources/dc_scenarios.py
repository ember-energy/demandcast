# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module reads the commissioned IT capacity of the data centres
    of the ASEAN-6 countries (Philippines, Indonesia, Malaysia,
    Singapore, Thailand, and Viet Nam) from the workbook "DC Demand
    Scenarios - ASEAN.xlsx" (manual_downloads/dc_scenarios), by grid
    node, scenario, and year:

    - 2026: "Commissioned IT capacity 2026 (MW)", the existing capacity
      (C&W operating, H1 2026), the same in all scenarios;
    - 2030: the capacity added between 2026 and 2030 in each scenario
      (the "Added" rows of "Commissioned IT capacity 2030 (MW)"), without
      the existing capacity. The total capacity in 2030 is the sum of the
      2026 and 2030 values.

    The scenarios are:

    - Low: C&W full book (operating + under construction + planned);
    - Mid: existing + 50% of the announced pipeline;
    - High: existing + 100% of the announced pipeline;
    - Suitable sites: High capacity, with the added capacity reallocated
      across the nodes by the suitability scores.

    The grid nodes are given with the codes of demandcast (e.g., PHL_LU
    or IDN_JAW), and each country also has its total (e.g., IDN). The
    occupancy, utilisation, and PUE of each country and scenario, used
    in the workbook to convert the IT capacity to the average grid
    draw, are also read.

    Usage (e.g., in iso_data_centre_demand.py):

        from retrievals.socio_economic_data_sources import dc_scenarios

        # Capacity of one code.
        dc_scenarios.get_capacity("High", 2030, "IDN_JAW")

        # Capacity of all the nodes of a country, as {code: MW}.
        CAPACITY_MW = dc_scenarios.get_capacities("High", 2030, "IDN")

        # Occupancy, utilisation, and PUE of a country and scenario.
        dc_scenarios.get_conversion_parameters("High", "IDN")

        # All the values, as {scenario: {year: {code: MW}}}.
        dc_scenarios.read_capacities()
"""

import functools
import os
import re

import pandas

# Define the path of the workbook.
FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "manual_downloads",
    "dc_scenarios",
    "DC Demand Scenarios - ASEAN.xlsx",
)

# Define the scenarios, in the order of the columns of the capacity
# tables (columns B to E of each country sheet).
SCENARIOS = ["Low", "Mid", "High", "Suitable sites"]

# Define other names accepted for the scenarios (lower case).
SCENARIO_ALIASES = {
    "low scenario": "Low",
    "mid scenario": "Mid",
    "high scenario": "High",
    "suitable site": "Suitable sites",
    "high suitable areas": "Suitable sites",
    "high suitable sites": "Suitable sites",
}

# Define the years of the capacity tables.
YEARS = [2026, 2030]

# Define, for each country, the sheet and the codes of the grid nodes
# as named in the capacity tables (e.g., "Jawa-Bali - Existing").
NODES = {
    "PHL": {
        "sheet": "Philippines",
        "codes": {"Luzon": "PHL_LU", "Visayas": "PHL_VI", "Mindanao": "PHL_MI"},
    },
    "IDN": {
        "sheet": "Indonesia",
        "codes": {
            "Jawa-Bali": "IDN_JAW",
            "Batam-Riau Islands": "IDN_BTM",
            "Sumatera": "IDN_SUM",
            "Kalimantan": "IDN_KAL",
            "Sulawesi": "IDN_SUL",
            "Nusa Tenggara": "IDN_NUS",
            "Maluku": "IDN_MAL",
            "Papua": "IDN_PAP",
        },
    },
    "MYS": {
        "sheet": "Malaysia",
        "codes": {"Peninsular": "MYS_PEN", "Sabah": "MYS_SAB", "Sarawak": "MYS_SAR"},
    },
    "SGP": {"sheet": "Singapore", "codes": {"Singapore": "SGP"}},
    "THA": {
        "sheet": "Thailand",
        "codes": {
            "Central": "THA_CEN",
            "North": "THA_NOR",
            "Northeast": "THA_NEA",
            "South": "THA_SOU",
        },
    },
    "VNM": {
        "sheet": "Vietnam",
        "codes": {"North": "VNM_NOR", "Central": "VNM_CEN", "South": "VNM_SOU"},
    },
}

# Define the labels of the rows with the conversion parameters.
CONVERSION_PARAMETERS = ["Occupancy", "Utilisation", "PUE"]


def _normalise_scenario(scenario: str) -> str:
    """
    Get the name of a scenario as in SCENARIOS.

    Parameters
    ----------
    scenario : str
        The scenario, in any case (e.g., "high"), or an alias of
        SCENARIO_ALIASES (e.g., "High suitable areas").

    Returns
    -------
    str
        The scenario as in SCENARIOS.

    Raises
    ------
    ValueError
        If the scenario is not available.
    """
    key = re.sub(r"\s+", " ", scenario.strip().lower())
    for name in SCENARIOS:
        if key == name.lower():
            return name
    if key in SCENARIO_ALIASES:
        return SCENARIO_ALIASES[key]
    raise ValueError(
        f"Scenario '{scenario}' is not available. Available scenarios: "
        f"{SCENARIOS}."
    )


def _read_block(
    sheet: pandas.DataFrame, header: str, suffix: str, country_code: str
) -> pandas.DataFrame:
    """
    Read the node rows of a capacity table of a country sheet.

    Parameters
    ----------
    sheet : pandas.DataFrame
        The country sheet, read without header.
    header : str
        The start of the label of the table (e.g., "Commissioned IT
        capacity 2026"). The table is the last row with this label,
        followed by the node rows.
    suffix : str
        The suffix of the labels of the node rows ("Existing" or
        "Added").
    country_code : str
        The ISO Alpha-3 code of the country.

    Returns
    -------
    pandas.DataFrame
        The capacity (MW) with the codes of the nodes as index and the
        scenarios as columns.
    """
    labels = sheet[0].astype(str).str.strip()
    header_rows = labels.index[labels.str.startswith(header)]
    if header_rows.empty:
        raise ValueError(
            f"The table '{header}' was not found in the sheet "
            f"{NODES[country_code]['sheet']} of {FILE_PATH}."
        )

    # Read the node rows that follow the last row with the label (the
    # first one is the country total at the top of the sheet).
    codes = NODES[country_code]["codes"]
    values = {}
    row = header_rows[-1] + 1
    while row < len(sheet):
        match = re.fullmatch(rf"(.+?)\s*-\s*{suffix}", labels[row])
        if not match:
            break
        node = re.sub(r"\s+", " ", match.group(1))
        if node not in codes:
            raise ValueError(
                f"Unknown node '{node}' in the sheet "
                f"{NODES[country_code]['sheet']}. Add it to NODES."
            )
        values[codes[node]] = (
            pandas.to_numeric(sheet.iloc[row, 1 : 1 + len(SCENARIOS)])
            .fillna(0)
            .to_numpy(dtype=float)
        )
        row += 1

    missing = set(codes.values()) - set(values)
    if missing:
        raise ValueError(
            f"No '{suffix}' row for {sorted(missing)} in the table "
            f"'{header}' of the sheet {NODES[country_code]['sheet']}."
        )
    return pandas.DataFrame.from_dict(values, orient="index", columns=SCENARIOS)


def _get_row_values(sheet: pandas.DataFrame, label: str) -> list[float]:
    """
    Get the values of the scenarios of the first row with a label.

    Parameters
    ----------
    sheet : pandas.DataFrame
        The country sheet, read without header.
    label : str
        The start of the label of the row.

    Returns
    -------
    list[float]
        The values in the order of SCENARIOS.
    """
    labels = sheet[0].astype(str).str.strip()
    rows = labels.index[labels.str.startswith(label)]
    if rows.empty:
        raise ValueError(f"The row '{label}' was not found.")
    return (
        pandas.to_numeric(sheet.iloc[rows[0], 1 : 1 + len(SCENARIOS)])
        .astype(float)
        .tolist()
    )


@functools.lru_cache(maxsize=1)
def _read_workbook() -> tuple[dict, dict]:
    """
    Read the capacities and the conversion parameters of the workbook.

    Returns
    -------
    tuple[dict, dict]
        The capacities, as {scenario: {year: {code: MW}}}, and the
        conversion parameters, as {scenario: {country code: {parameter:
        value}}}.
    """
    capacities = {
        scenario: {year: {} for year in YEARS} for scenario in SCENARIOS
    }
    parameters = {scenario: {} for scenario in SCENARIOS}

    for country_code, country in NODES.items():
        sheet = pandas.read_excel(FILE_PATH, sheet_name=country["sheet"], header=None)

        existing = _read_block(
            sheet, "Commissioned IT capacity 2026", "Existing", country_code
        )
        added = _read_block(
            sheet, "Commissioned IT capacity 2030", "Added", country_code
        )
        # The value of 2030 is only the capacity added by 2030, not the
        # existing capacity plus the added capacity.
        by_year = {2026: existing, 2030: added}

        # Check the node values against the country totals of the sheet,
        # where the total of 2030 is the existing plus the added
        # capacity.
        checks = {
            2026: (
                existing.sum(),
                _get_row_values(sheet, "Commissioned IT capacity 2026"),
            ),
            2030: (
                existing.sum() + added.sum(),
                _get_row_values(sheet, "Commissioned IT capacity 2030"),
            ),
        }
        for year, (node_sum, total) in checks.items():
            difference = (node_sum - total).abs().max()
            if difference > 0.01:
                raise ValueError(
                    f"The nodes of {country_code} do not add up to the "
                    f"commissioned IT capacity {year} of the sheet "
                    f"(difference: {difference:.3f} MW)."
                )

        for scenario in SCENARIOS:
            for year, table in by_year.items():
                capacities[scenario][year].update(table[scenario].to_dict())
                capacities[scenario][year][country_code] = float(
                    table[scenario].sum()
                )
            parameters[scenario][country_code] = {
                parameter: _get_row_values(sheet, parameter)[
                    SCENARIOS.index(scenario)
                ]
                for parameter in CONVERSION_PARAMETERS
            }

    return capacities, parameters


def read_capacities() -> dict[str, dict[int, dict[str, float]]]:
    """
    Read the commissioned IT capacity of all scenarios, years, and codes.

    Returns
    -------
    dict[str, dict[int, dict[str, float]]]
        The commissioned IT capacity in MW, as {scenario: {year: {code:
        MW}}}, where the codes are the grid nodes (e.g., IDN_JAW) and
        the countries (e.g., IDN, the sum of their nodes). The values of
        2030 are only the capacity added by 2030.
    """
    capacities, __ = _read_workbook()
    return {
        scenario: {year: dict(values) for year, values in years.items()}
        for scenario, years in capacities.items()
    }


def get_capacity(scenario: str, year: int, code: str) -> float:
    """
    Get the commissioned IT capacity of a code.

    Parameters
    ----------
    scenario : str
        The scenario: Low, Mid, High, or Suitable sites.
    year : int
        The year: 2026 (existing) or 2030 (added by 2030).
    code : str
        The code of the grid node (e.g., IDN_JAW) or of the country
        (e.g., IDN).

    Returns
    -------
    float
        The commissioned IT capacity in MW.
    """
    capacities = _get_capacities_of_year(scenario, year)
    if code not in capacities:
        raise ValueError(
            f"Code '{code}' is not available. Available codes: "
            f"{sorted(capacities)}."
        )
    return capacities[code]


def get_capacities(scenario: str, year: int, country_code: str) -> dict[str, float]:
    """
    Get the commissioned IT capacity of the grid nodes of a country.

    Parameters
    ----------
    scenario : str
        The scenario: Low, Mid, High, or Suitable sites.
    year : int
        The year: 2026 (existing) or 2030 (added by 2030).
    country_code : str
        The ISO Alpha-3 code of the country (e.g., IDN).

    Returns
    -------
    dict[str, float]
        The commissioned IT capacity in MW, as {code: MW}, of each grid
        node of the country (e.g., {"IDN_JAW": ..., "IDN_BTM": ...}).
        For Singapore, the only node is SGP.
    """
    if country_code not in NODES:
        raise ValueError(
            f"Country '{country_code}' is not available. Available "
            f"countries: {list(NODES)}."
        )
    capacities = _get_capacities_of_year(scenario, year)
    return {code: capacities[code] for code in NODES[country_code]["codes"].values()}


def get_conversion_parameters(scenario: str, country_code: str) -> dict[str, float]:
    """
    Get the occupancy, utilisation, and PUE of a country and scenario.

    The average grid draw of the workbook is the commissioned IT
    capacity x occupancy x utilisation x PUE.

    Parameters
    ----------
    scenario : str
        The scenario: Low, Mid, High, or Suitable sites.
    country_code : str
        The ISO Alpha-3 code of the country (e.g., IDN).

    Returns
    -------
    dict[str, float]
        The values of "Occupancy", "Utilisation", and "PUE".
    """
    __, parameters = _read_workbook()
    scenario = _normalise_scenario(scenario)
    if country_code not in parameters[scenario]:
        raise ValueError(
            f"Country '{country_code}' is not available. Available "
            f"countries: {list(NODES)}."
        )
    return dict(parameters[scenario][country_code])


def _get_capacities_of_year(scenario: str, year: int) -> dict[str, float]:
    """
    Get the capacities of all codes for a scenario and a year.

    Parameters
    ----------
    scenario : str
        The scenario.
    year : int
        The year.

    Returns
    -------
    dict[str, float]
        The commissioned IT capacity in MW, as {code: MW}.
    """
    capacities, __ = _read_workbook()
    scenario = _normalise_scenario(scenario)
    if year not in YEARS:
        raise ValueError(
            f"Year {year} is not available. Available years: {YEARS} "
            "(2026 is the existing capacity and 2030 the capacity added "
            "by 2030, as in the workbook)."
        )
    return capacities[scenario][year]


if __name__ == "__main__":
    # Print all the capacities as a table.
    table = pandas.DataFrame(
        {
            (scenario, year): values
            for scenario, years in read_capacities().items()
            for year, values in years.items()
        }
    )
    with pandas.option_context("display.width", 200, "display.max_columns", 20):
        print(table.round(1))
