# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module is used to download the historical annual electricity
    consumption of the three main grids of the Philippines (Luzon,
    Visayas, and Mindanao) from the Department of Energy (DOE) of the
    Philippines. The data is published in a PDF file, which is parsed
    to extract the "Electricity Consumption" row (electricity sales,
    own-use, and system loss) of each grid. The unit is MWh.

    Note that, according to the DOE, off-grid consumption is not
    included starting 2021.

    Source: https://doe.gov.ph/articles/group/energy-statistics?category=Electricity&display_type=Card
"""

import io
import logging

import pandas
import pypdf
import requests

# Define the URL of the PDF file with the electricity consumption per
# grid.
URL = "https://prod-cms.doe.gov.ph/documents/d/guest/06_electricity-consumption-pdf"

# Define the codes of the grids as named in the PDF file.
CODES_OF_GRIDS = {
    "Luzon": "PHL_LU",
    "Visayas": "PHL_VI",
    "Mindanao": "PHL_MI",
    "Philippines": "PHL",
}


def get_codes() -> list[str]:
    """
    Get the codes of the entities with data from the DOE.

    Returns
    -------
    list[str]
        The codes of the grids and the country.
    """
    return list(CODES_OF_GRIDS.values())


def download_electricity_consumption() -> pandas.DataFrame:
    """
    Download the annual electricity consumption per grid from the DOE.

    Returns
    -------
    electricity_consumption : pandas.DataFrame
        The annual electricity consumption in MWh, with the codes of
        the grids as index and the years as columns.

    Raises
    ------
    ValueError
        If the electricity consumption of a grid cannot be found in the
        PDF file.
    """
    logging.info(
        "Downloading electricity consumption per grid data from the DOE "
        "of the Philippines."
    )

    # Download the PDF file.
    response = requests.get(
        URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60
    )
    response.raise_for_status()

    # Extract the text of the PDF file.
    reader = pypdf.PdfReader(io.BytesIO(response.content))
    lines = "\n".join(page.extract_text() for page in reader.pages)
    lines = lines.splitlines()

    # Each grid has a header line with its name followed by the years,
    # and an "Electricity Consumption" line with the values of each
    # year. Parse the lines to extract the electricity consumption of
    # each grid.
    electricity_consumption = {}
    grid = None
    years: list[int] = []
    for line in lines:
        words = line.split()

        if not words:
            continue

        if words[0] in CODES_OF_GRIDS:
            # Header line of a grid: get the name of the grid and the
            # years. Duplicates are removed because the header ends
            # with the share of the last year (e.g., "% Share - 2024").
            grid = words[0]
            years = list(
                dict.fromkeys(
                    int(word) for word in words[1:] if word.isdigit()
                )
            )

        elif line.strip().startswith("Electricity Consumption") and grid:
            # Electricity consumption line: get the value of each year.
            values = [
                float(word.replace(",", ""))
                for word in words[2:]
                if word.replace(",", "").replace(".", "").isdigit()
            ]
            electricity_consumption[CODES_OF_GRIDS[grid]] = pandas.Series(
                values[: len(years)], index=years
            )
            grid = None

    missing_codes = set(get_codes()) - set(electricity_consumption)
    if missing_codes:
        raise ValueError(
            "The electricity consumption of the following entities could "
            f"not be found in the DOE PDF file: {', '.join(missing_codes)}."
        )

    # Build a DataFrame with the codes as index and the years as
    # columns.
    electricity_consumption = pandas.DataFrame(electricity_consumption).T
    electricity_consumption.index.name = "Code"
    electricity_consumption.columns.name = "Year"

    logging.info(
        "Electricity consumption per grid data from the DOE has been "
        "downloaded successfully."
    )

    return electricity_consumption
