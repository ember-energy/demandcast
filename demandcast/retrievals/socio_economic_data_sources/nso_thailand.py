# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module reads the registered population of Thailand and of its
    four model regions (subdivisions) from the National Statistical
    Office of Thailand (NSO), as published from the Department of
    Provincial Administration (DOPA), Ministry of Interior, for 2012 to
    2025 (B.E. 2555 to 2568). The population (male + female) of the
    NSO regions is aggregated into the model regions in the sheet
    "Regional_totals" of a manually downloaded Excel file (see its sheet
    "Corrections" for a corrected value of the Northern Region in 2021):

    - THA_CEN: Metropolitan and Central (Bangkok Metropolis and the NSO
      Central Region, 26 provinces);
    - THA_NOR: North (Northern Region, 17 provinces);
    - THA_NEA: Northeast (Northeastern Region, 20 provinces);
    - THA_SOU: South (Southern Region, 14 provinces).

    In retrievals.population, the average share of each region in the
    national population over the years of the file is used for the
    earlier years, and the share of the most recent year of the file
    (2025) for the future years.

    Note that the registered population is lower than the population
    estimated by the World Bank (by about 8-10% in 2012-2025), as it does
    not include the residents who are not registered (e.g., migrants).

    Source: https://www.nso.go.th (Statistical Data Warehouse)
"""

import functools
import logging
import os

import pandas

# Define the path of the Excel file with the population of the regions.
FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "manual_downloads",
    "nso",
    "nso-thailand-population-male-female-2012-2025_EN_regions.xlsx",
)

# Define the sheet with the population of the regions.
SHEET_NAME = "Regional_totals"

# Define the code of Thailand and the codes of the regions as in the
# "Region code" column of the sheet.
CODE = "THA"
CODES_OF_REGIONS = {
    "THA-CEN": "THA_CEN",
    "THA-NOR": "THA_NOR",
    "THA-NEA": "THA_NEA",
    "THA-SOU": "THA_SOU",
}


def get_codes() -> list[str]:
    """
    Get the codes of the subdivisions with population data from the NSO.

    Returns
    -------
    list[str]
        The codes of the regions.
    """
    return list(CODES_OF_REGIONS.values())


@functools.lru_cache(maxsize=1)
def read_population() -> pandas.DataFrame:
    """
    Read the registered population of Thailand and its regions.

    Returns
    -------
    pandas.DataFrame
        The registered population in number of people, with the codes
        of the regions and of Thailand (the sum of the regions) as index
        and the years as columns.

    Raises
    ------
    ValueError
        If a region is missing or if the regions do not add up to the
        national total of the file.
    """
    logging.info("Reading the population of Thailand from the NSO.")

    # The table header is on the fourth row of the sheet.
    sheet = pandas.read_excel(FILE_PATH, sheet_name=SHEET_NAME, header=3)
    sheet["Region code"] = sheet["Region code"].astype(str).str.strip()

    # Get the year columns (e.g., 2021 or "2021").
    year_columns = {
        column: int(str(column)[:4])
        for column in sheet.columns
        if str(column)[:4].isdigit()
    }

    # Keep the rows of the regions and of the national total.
    population = (
        sheet[sheet["Region code"].isin(list(CODES_OF_REGIONS) + [CODE])]
        .set_index("Region code")[list(year_columns)]
        .rename(index=CODES_OF_REGIONS, columns=year_columns)
        .astype(float)
    )

    missing = set(get_codes() + [CODE]) - set(population.index)
    if missing:
        raise ValueError(
            f"The rows {sorted(missing)} were not found in the sheet "
            f"{SHEET_NAME} of {FILE_PATH}."
        )

    # Check that the regions add up to the national total.
    difference = (
        population.loc[get_codes()].sum() - population.loc[CODE]
    ).abs().max()
    if difference > 1:
        raise ValueError(
            "The regions do not add up to the population of Thailand in "
            f"{FILE_PATH} (difference: {difference:.0f} people)."
        )

    population.index.name = "Code"
    population.columns.name = "Year"
    return population


def read_average_shares() -> pandas.Series:
    """
    Read the average share of each region in the population of Thailand.

    Returns
    -------
    pandas.Series
        The share of each region in the national population, averaged
        over the years of the file, with the codes of the regions as
        index. The shares sum to 1.
    """
    population = read_population()
    shares = population.loc[get_codes()] / population.loc[CODE]
    average_shares = shares.mean(axis=1)
    return average_shares / average_shares.sum()


def read_latest_shares() -> pandas.Series:
    """
    Read the share of each region in the population of Thailand in the
    most recent year of the file.

    Returns
    -------
    pandas.Series
        The share of each region in the national population in the most
        recent year of the file, with the codes of the regions as index.
        The shares sum to 1.
    """
    population = read_population()
    latest_year = population.columns.max()
    return (
        population.loc[get_codes(), latest_year]
        / population.loc[CODE, latest_year]
    ).rename(latest_year)
