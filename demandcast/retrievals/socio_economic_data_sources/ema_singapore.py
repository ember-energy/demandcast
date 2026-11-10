# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module reads the projected annual electricity generation of
    Singapore from the Energy Market Authority (EMA), "Electricity
    Demand and Supply Outlook 2025" information paper, Table 1b
    "Projected Total Generation in 10-year EDF (GWh)" on page 5. The
    table gives, for 2025 to 2034, the generation needed to meet the
    Base Electricity Demand Forecast (EDF) and the Upper-bound EDF. The
    generation is the gross generation of the generation companies and
    of the consumers with own or embedded generation, including solar,
    rounded to the nearest 100 GWh. It is based on the information
    available as of October 2025.

    The projected generation of the selected scenario (BASE or UPPER)
    is used as the projected annual electricity demand of Singapore in
    retrievals.annual_electricity_demand_per_capita.

    Source: https://www.ema.gov.sg/resources/industry-reports
"""

import logging
import os
import re

import pandas
from pypdf import PdfReader

# Define the path of the PDF file of the EMA.
FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "manual_downloads",
    "ema",
    "EMA-Regulations-Policies-Info-Paper-On-Electricity-Demand-And-Supply-Outlook-2025.pdf",
)

# Define the page (1-based) and the title of Table 1b.
PAGE_NUMBER = 5
TABLE_TITLE = "Table 1b"

# Define the scenarios, in the order of the columns of Table 1b.
SCENARIOS = {"BASE": "Base EDF", "UPPER": "Upper-bound EDF"}

# Define the code of Singapore.
CODE = "SGP"


def get_scenarios() -> list[str]:
    """
    Get the scenarios of the EMA projection used in the model.

    Returns
    -------
    list[str]
        The scenarios: BASE (generation to meet the Base EDF) and UPPER
        (generation to meet the Upper-bound EDF).
    """
    return list(SCENARIOS)


def read_projected_generation(scenario: str = "BASE") -> pandas.Series:
    """
    Read the projected annual electricity generation of Singapore.

    Parameters
    ----------
    scenario : str
        The scenario of the EMA projection: BASE (Base EDF) or UPPER
        (Upper-bound EDF).

    Returns
    -------
    pandas.Series
        The projected annual electricity generation in GWh, with the
        years as index.

    Raises
    ------
    ValueError
        If the scenario is not available or if Table 1b cannot be read.
    """
    scenario = scenario.upper()
    if scenario not in SCENARIOS:
        raise ValueError(
            f"scenario must be one of the following: {list(SCENARIOS)}."
        )

    logging.info(
        f"Reading the projected generation to meet the "
        f"{SCENARIOS[scenario]} of Singapore from the EMA."
    )

    text = PdfReader(FILE_PATH).pages[PAGE_NUMBER - 1].extract_text()
    if TABLE_TITLE not in text:
        raise ValueError(
            f"{TABLE_TITLE} was not found on page {PAGE_NUMBER} of {FILE_PATH}."
        )

    # Read the rows of the table, e.g., "2026 61,600 65,400", after the
    # title of the table.
    rows = re.findall(
        r"^\s*(20\d{2})\s+([\d,]+)\s+([\d,]+)\s*$",
        text.split(TABLE_TITLE, 1)[1],
        flags=re.MULTILINE,
    )
    if not rows:
        raise ValueError(
            f"No rows of {TABLE_TITLE} were read on page {PAGE_NUMBER} of "
            f"{FILE_PATH}."
        )

    column = list(SCENARIOS).index(scenario) + 1
    generation = pandas.Series(
        {int(row[0]): float(row[column].replace(",", "")) for row in rows},
        name=CODE,
    ).sort_index()
    generation.index.name = "Year"

    # Check that the years are consecutive.
    expected_years = list(
        range(generation.index.min(), generation.index.max() + 1)
    )
    if generation.index.tolist() != expected_years:
        raise ValueError(
            f"The years of {TABLE_TITLE} are not consecutive: "
            f"{generation.index.tolist()}."
        )

    return generation
