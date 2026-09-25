# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module is used to read the census population of the three main
    grids of the Philippines (Luzon, Visayas, and Mindanao) from the
    Philippine Statistics Authority (PSA). The population of each
    administrative region, as reported in the censuses of 2000, 2010,
    2015, 2020, and 2024, is transcribed into a manually downloaded
    Excel file and aggregated by island group. Each census is treated as
    the value of its year, regardless of its reference date.

    Source: https://psa.gov.ph/statistics/population-and-housing
"""

import os

import pandas

# Define the path of the Excel file with the regional census
# population.
FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "manual_downloads",
    "Philippines_Population_Luzon_Visayas_Mindanao_2000-2024.xlsx",
)

# Define the sheet with the regional census population.
SHEET_NAME = "Regional_Census"

# Define the codes of the grids as named in the island group column.
CODES_OF_ISLAND_GROUPS = {
    "Luzon": "PHL_LU",
    "Visayas": "PHL_VI",
    "Mindanao": "PHL_MI",
}


def get_codes() -> list[str]:
    """
    Get the codes of the subdivisions with census data from the PSA.

    Returns
    -------
    list[str]
        The codes of the grids.
    """
    return list(CODES_OF_ISLAND_GROUPS.values())


def read_population_shares() -> pandas.DataFrame:
    """
    Read the share of each grid in the census population of the country.

    Returns
    -------
    pandas.DataFrame
        The share of each grid in the census population of the
        Philippines, with the codes of the grids as index and the census
        years as columns.
    """
    # Read the regional census population. The table header is on the
    # fourth row of the sheet.
    census_population = pandas.read_excel(
        FILE_PATH, sheet_name=SHEET_NAME, header=3
    )

    # Keep only the rows of the regions, which have an island group.
    # This drops the sum of regions and the notes below the table.
    census_population = census_population.dropna(subset=["Island group"])

    # Get the census year columns, whose names start with the year
    # (e.g., "2000\n(1 May 2000)"), and rename them to the year.
    year_columns = {
        column: int(str(column).split()[0])
        for column in census_population.columns
        if str(column).split()[0].isdigit()
    }

    # Sum the population of the regions by island group. Regions that
    # did not exist in a census (e.g., the Negros Island Region before
    # 2024) have no value and are counted in their former regions.
    population_of_grids = (
        census_population.groupby("Island group")[list(year_columns)]
        .sum()
        .rename(columns=year_columns, index=CODES_OF_ISLAND_GROUPS)
    )

    # Calculate the share of each grid in the national population.
    population_shares = population_of_grids / population_of_grids.sum()
    population_shares.index.name = "Code"
    population_shares.columns.name = "Year"

    return population_shares
