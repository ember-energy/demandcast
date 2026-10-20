# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module is used to read the projected annual electricity sales of
    the three main grids of the Philippines (Luzon, Visayas, and
    Mindanao) from the Philippine Energy Plan (PEP) of the Department of
    Energy (DOE), for the Reference (REF) and the Clean Energy (CES)
    scenarios. The sales are converted to annual electricity demand by
    multiplying them by the grid-load factor of each grid, which is the
    ratio between the actual annual gross generation of the grid
    reported by the NGCP and the actual electricity sales reported by
    the DOE, averaged over 2023 and 2024.

    The sales are read from a manually downloaded Excel file, in GWh,
    and converted to MWh.
"""

import logging
import os

import pandas

# Define the path of the Excel file with the projected sales.
FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "manual_downloads",
    "Philippines_PEP_annual_electricity_sales_2050.xlsx",
)

# Define the codes of the grids as named in the columns of the file.
CODES_OF_GRIDS = {
    "Luzon": "PHL_LU",
    "Visayas": "PHL_VI",
    "Mindanao": "PHL_MI",
}

# Define the scenarios of the PEP, as the prefix of the columns in the
# file.
SCENARIOS = ["REF", "CES"]

# Define the grid-load factors (annual demand over annual sales),
# calculated from the NGCP's actual yearly generation and the DOE's
# actual electricity sales between 2021 and 2024.
GRID_LOAD_FACTORS = {
    "PHL_LU": 1.14,
    "PHL_VI": 1.23,
    "PHL_MI": 1.19,
}


def get_codes() -> list[str]:
    """
    Get the codes of the grids with projected electricity sales.

    Returns
    -------
    list[str]
        The codes of the grids.
    """
    return list(CODES_OF_GRIDS.values())


def get_scenarios() -> list[str]:
    """
    Get the scenarios of the projected electricity sales of the PEP.

    Returns
    -------
    list[str]
        The scenarios (REF for Reference and CES for Clean Energy).
    """
    return list(SCENARIOS)


def read_annual_electricity_demand(scenario: str) -> pandas.DataFrame:
    """
    Read the projected annual electricity demand of the three grids.

    The demand is calculated as the projected electricity sales
    multiplied by the grid-load factor of each grid.

    Parameters
    ----------
    scenario : str
        The scenario of the PEP (REF or CES).

    Returns
    -------
    pandas.DataFrame
        The projected annual electricity demand in MWh, with the codes
        of the grids as index and the years as columns.

    Raises
    ------
    ValueError
        If the scenario is not available.
    """
    if scenario.upper() not in SCENARIOS:
        raise ValueError(f"scenario must be one of the following: {SCENARIOS}.")
    scenario = scenario.upper()

    logging.info(
        f"Loading future electricity sales from the PEP for {scenario}."
    )

    # Read the sales, with the years as index.
    sales = pandas.read_excel(FILE_PATH, index_col="Year")

    # Get the sales of the grids of the scenario, which are in GWh, and
    # convert them to MWh.
    sales = sales[[f"{scenario} {grid}" for grid in CODES_OF_GRIDS]] * 1000
    sales.columns = list(CODES_OF_GRIDS.values())

    # Convert the sales to demand using the grid-load factors.
    demand = sales * pandas.Series(GRID_LOAD_FACTORS)

    # Return the demand with the codes of the grids as index and the
    # years as columns.
    demand = demand.T
    demand.index.name = "Code"
    demand.columns.name = "Year"

    return demand
