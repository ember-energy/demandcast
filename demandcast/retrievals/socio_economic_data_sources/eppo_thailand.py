# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module reads the projected annual electricity demand (GWh) of
    Thailand and of its four model regions (THA_CEN, THA_NOR, THA_NEA,
    THA_SOU) for 2024 to 2037, from the sheet "Regional_Energy" of a
    manually prepared Excel file based on the draft Power Development
    Plan 2024 (PDP2024) of the Energy Policy and Planning Office (EPPO),
    Ministry of Energy, Thailand (BASE case).

    The national value is the generation requirement of the 3-utility
    system (EGAT, MEA, PEA), printed in the PDP for 2024, 2030 and 2037
    and measured from the PDP charts for the other years. The regional
    values of the file are a derived estimate (not published by EPPO):
    the national value is allocated to the regions by their share of the
    regional peak demand. See the sheet "README" of the file for the
    method and caveats.

    The regional values are calibrated to the regional energy shares of
    EGAT in SHARE_YEAR (2025): the projection of each region is
    multiplied by its EGAT share divided by its EPPO share in
    SHARE_YEAR, and the regions are then rescaled to add up to the
    national value of each year. So the regional shares are the EGAT
    shares in SHARE_YEAR and follow the trend of the EPPO shares after.
    The national projection is not changed.

    The EGAT shares of SHARE_YEAR are also used in
    retrievals.annual_electricity_demand_per_capita to split the
    historical national demand of Ember into the regions (the same
    shares for all historical years).

    Source: https://www.eppo.go.th (draft PDP2024, June 2024)
"""

import functools
import logging
import os

import pandas

from retrievals.electricity_demand_data_sources import egat

# Define the year of the EGAT regional energy shares used to calibrate
# the regional projection and to split the historical demand. It is
# the only complete year of the EGAT data (available from July 2024).
SHARE_YEAR = 2025

# Define the path of the Excel file with the projected demand.
FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "manual_downloads",
    "eppo",
    "Thailand_PDP2024_regional_annual_electricity_demand_2037_v2.xlsx",
)

# Define the sheet with the projected demand of the regions.
SHEET_NAME = "Regional_Energy"

# Define the code of Thailand and the codes of the regions, with the
# columns of the sheet.
CODE = "THA"
COLUMNS_OF_CODES = {
    "THA": "National generation (GWh)",
    "THA_CEN": "THA-CEN (GWh)",
    "THA_NOR": "THA-NOR (GWh)",
    "THA_NEA": "THA-NEA (GWh)",
    "THA_SOU": "THA-SOU (GWh)",
}


def get_codes() -> list[str]:
    """
    Get the codes of Thailand and its regions with projected demand.

    Returns
    -------
    list[str]
        The code of Thailand and the codes of its regions.
    """
    return list(COLUMNS_OF_CODES)


@functools.lru_cache(maxsize=1)
def read_projected_demand() -> pandas.DataFrame:
    """
    Get the projected annual electricity demand of Thailand and its
    regions, with the regions calibrated to the EGAT shares.

    The projection of each region in the EPPO file is multiplied by its
    EGAT share divided by its EPPO share in SHARE_YEAR, and the regions
    are rescaled to add up to the national value of each year. The
    national value is not changed.

    Returns
    -------
    pandas.DataFrame
        The projected annual electricity demand in GWh, with the codes
        as index and the years (C.E.) as columns.
    """
    demand = read_eppo_file()
    regions = [code for code in get_codes() if code != CODE]

    eppo_shares = demand.loc[regions, SHARE_YEAR] / demand.loc[CODE, SHARE_YEAR]
    egat_shares = egat.get_annual_energy_shares(SHARE_YEAR).reindex(regions)
    logging.info(
        f"Calibrating the EPPO regional demand to the EGAT shares of "
        f"{SHARE_YEAR}: {egat_shares.round(4).to_dict()} (EPPO: "
        f"{eppo_shares.round(4).to_dict()})."
    )

    regional_demand = demand.loc[regions].mul(egat_shares / eppo_shares, axis=0)
    regional_demand = regional_demand * (
        demand.loc[CODE] / regional_demand.sum()
    )

    calibrated = pandas.concat([demand.loc[[CODE]], regional_demand])
    calibrated.index.name = "Code"
    calibrated.columns.name = "Year"
    return calibrated


@functools.lru_cache(maxsize=1)
def read_eppo_file() -> pandas.DataFrame:
    """
    Read the projected annual electricity demand of Thailand and its
    regions, as in the EPPO file.

    Returns
    -------
    pandas.DataFrame
        The projected annual electricity demand in GWh, with the codes
        as index and the years (C.E.) as columns.

    Raises
    ------
    ValueError
        If a column is missing or if the regions do not add up to the
        national value.
    """
    logging.info("Reading the projected demand of Thailand from the EPPO.")

    # The table header is on the fourth row of the sheet.
    sheet = pandas.read_excel(FILE_PATH, sheet_name=SHEET_NAME, header=3)

    missing = set(COLUMNS_OF_CODES.values()) - set(sheet.columns)
    if missing:
        raise ValueError(
            f"The columns {sorted(missing)} were not found in the sheet "
            f"{SHEET_NAME} of {FILE_PATH}."
        )

    # Keep the rows with a year (the notes below the table are dropped).
    years = pandas.to_numeric(sheet["Year (C.E.)"], errors="coerce")
    sheet = sheet[years.notna()].copy()
    sheet.index = years[years.notna()].astype(int)

    demand = (
        sheet[list(COLUMNS_OF_CODES.values())]
        .astype(float)
        .rename(columns={v: k for k, v in COLUMNS_OF_CODES.items()})
        .T
    )

    # Check that the regions add up to the national value.
    regions = [code for code in get_codes() if code != CODE]
    difference = (demand.loc[regions].sum() - demand.loc[CODE]).abs().max()
    if difference > 1:
        raise ValueError(
            "The regions do not add up to the demand of Thailand in "
            f"{FILE_PATH} (difference: {difference:.0f} GWh)."
        )

    demand.index.name = "Code"
    demand.columns.name = "Year"
    return demand


def get_energy_share(code: str, years: list[int]) -> pandas.Series:
    """
    Get the share of a region in the historical demand of Thailand.

    The share of the region in the EGAT demand of SHARE_YEAR is used
    for all years.

    Parameters
    ----------
    code : str
        The code of the region.
    years : list[int]
        The years of interest.

    Returns
    -------
    pandas.Series
        The share of the region in the national demand, with the years
        as index.
    """
    share = egat.get_annual_energy_shares(SHARE_YEAR)[code]
    return pandas.Series(share, index=years, dtype=float)
