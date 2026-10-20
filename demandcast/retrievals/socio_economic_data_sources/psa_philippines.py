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

    This module also reads the national population projections of the
    PSA (2020 Census-Based Population Projections, Scenarios 1 to 3),
    which replace the IIASA projections for the Philippines. The
    projections are only national, so the subnational projections are
    obtained by applying the census shares of the grids. Each
    projection is treated as the value of its year (e.g., 1 July 2030 is
    2030).

    Source: https://psa.gov.ph/statistics/population-and-housing
"""

import logging
import os

import numpy
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

# Define the path of the Excel file with the national population
# projections.
PROJECTION_FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "manual_downloads",
    "Philippines_Population_Projection_2055.xlsx",
)

# Define the sheets with the projected population by five-year intervals
# and by single-year intervals (Tables 1-3 and 9-11, in thousands of
# people), and the scenarios in the order in which their tables appear.
FIVE_YEAR_PROJECTION_SHEET_NAME = "T1-T3"
SINGLE_YEAR_PROJECTION_SHEET_NAME = "T9-T11"
PROJECTION_SCENARIOS = ["PSA1", "PSA2", "PSA3"]

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


def get_projection_scenarios() -> list[str]:
    """
    Get the scenarios of the national population projections of the PSA.

    Returns
    -------
    list[str]
        The scenarios, where PSA1, PSA2, and PSA3 are the high,
        medium, and low assumption Scenarios 1, 2, and 3 of the PSA.
    """
    return list(PROJECTION_SCENARIOS)


def _read_all_ages_projections(sheet_name: str) -> pandas.DataFrame:
    """
    Read the projected population of all ages from a sheet of the PSA.

    Parameters
    ----------
    sheet_name : str
        The name of the sheet with one table per scenario.

    Returns
    -------
    pandas.DataFrame
        The projected population of all ages in number of people, with
        the scenarios as index and the years as columns.
    """
    sheet = pandas.read_excel(
        PROJECTION_FILE_PATH, sheet_name=sheet_name, header=None
    )

    # The header row has the reference dates (e.g., "01 July 2030") of
    # the columns.
    header = sheet[sheet[0].astype(str).str.strip() == "Age Group"].iloc[0]
    year_columns = {
        column: int(str(value).split()[-1])
        for column, value in header.items()
        if column != 0 and str(value).split()[-1].isdigit()
    }

    # Get the rows of all ages. Each scenario has three rows, in the
    # order of both sexes, male, and female. Keep the rows of both
    # sexes, which are the first of each scenario. The values are in
    # thousands of people.
    all_ages = sheet[sheet[0].astype(str).str.strip() == "All Ages"]
    if len(all_ages) != 3 * len(PROJECTION_SCENARIOS):
        raise ValueError(
            f"Expected {3 * len(PROJECTION_SCENARIOS)} rows of all ages in "
            f"the sheet {sheet_name} of the PSA projections, but found "
            f"{len(all_ages)}."
        )
    all_ages = all_ages.iloc[::3]

    projections = all_ages[list(year_columns)].astype(float) * 1000
    projections.index = PROJECTION_SCENARIOS
    projections.columns = list(year_columns.values())

    return projections


def read_national_population_projection(scenario: str) -> pandas.Series:
    """
    Read the projected population of the Philippines from the PSA.

    The single-year projections are used where available (up to 2030).
    For later years, only five-year projections are available, so the
    years in between are geometrically interpolated.

    Parameters
    ----------
    scenario : str
        The scenario of the projection (PSA1, PSA2, or PSA3).

    Returns
    -------
    pandas.Series
        The projected population of the Philippines in number of
        people, with the years as index.

    Raises
    ------
    ValueError
        If the scenario is not available.
    """
    if scenario.upper() not in PROJECTION_SCENARIOS:
        raise ValueError(
            f"scenario must be one of the following: {PROJECTION_SCENARIOS}."
        )
    scenario = scenario.upper()

    logging.info(
        f"Loading future population data from the PSA for {scenario}."
    )

    five_year = _read_all_ages_projections(FIVE_YEAR_PROJECTION_SHEET_NAME)
    single_year = _read_all_ages_projections(SINGLE_YEAR_PROJECTION_SHEET_NAME)

    # Interpolate geometrically between the five-year projections after
    # the last year of the single-year projections.
    last_single_year = single_year.columns.max()
    five_year_after = five_year.loc[scenario]
    five_year_after = five_year_after[
        five_year_after.index >= last_single_year
    ]
    interpolated = (
        numpy.exp(
            numpy.interp(
                range(five_year_after.index.min(), five_year_after.index.max() + 1),
                five_year_after.index,
                numpy.log(five_year_after.to_numpy()),
            )
        )
    )
    interpolated = pandas.Series(
        interpolated,
        index=range(
            five_year_after.index.min(), five_year_after.index.max() + 1
        ),
    )

    # Combine the single-year and the interpolated projections.
    projection = pandas.concat(
        [
            single_year.loc[scenario].loc[
                single_year.columns < last_single_year
            ],
            interpolated,
        ]
    )
    projection.index.name = "Year"

    return projection
