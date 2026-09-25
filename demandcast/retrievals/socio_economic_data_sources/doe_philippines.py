# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module is used to download the historical annual gross power
    generation of the three main grids of the Philippines (Luzon,
    Visayas, and Mindanao) from the Department of Energy (DOE) of the
    Philippines. The data is published in the summary PDF file of the
    power statistics, which is parsed to extract the "Gross Power
    Generation per Grid in GWh" table. The values are converted to MWh.

    Note that, according to the DOE, gross power generation includes
    grid-connected, embedded, and off-grid generators, but off-grid
    generation is excluded starting 2021.

    In the DOE's Power Statistics, the gross power generation is equal to the electricity consumption. So in this script we use the gross generation interchangably with the electricity demand

    Source: https://prod-cms.doe.gov.ph/documents/d/guest/annex-1_summary-electric-consumption-system-demand-gross-generation-installed-and-dependable-capacity-2003-2025-pdf
"""

import io
import logging

import pandas
import pypdf
import requests

# Define the URL of the PDF file with the summary of the power
# statistics, including the gross power generation per grid.
URL = "https://prod-cms.doe.gov.ph/documents/d/guest/annex-1_summary-electric-consumption-system-demand-gross-generation-installed-and-dependable-capacity-2003-2025-pdf"  # noqa: W505

# Define the header of the table with the gross power generation per
# grid.
TABLE_HEADER = "Gross Power Generation per Grid in GWh"

# Define the codes of the grids as named in the PDF file.
CODES_OF_GRIDS = {
    "Luzon": "PHL_LU",
    "Visayas": "PHL_VI",
    "Mindanao": "PHL_MI",
    "Total Gross Generation": "PHL",
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


def download_gross_generation() -> pandas.DataFrame:
    """
    Download the annual gross power generation per grid from the DOE.

    Returns
    -------
    gross_generation : pandas.DataFrame
        The annual gross power generation in MWh, with the codes of the
        grids as index and the years as columns.

    Raises
    ------
    ValueError
        If the table or the gross power generation of a grid cannot be
        found in the PDF file.
    """
    logging.info(
        "Downloading gross power generation per grid data from the DOE "
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
    lines = [line.strip() for line in lines.splitlines()]

    # Find the header line of the table, which ends with the years.
    try:
        header_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(TABLE_HEADER)
        )
    except StopIteration:
        raise ValueError(
            f"The table '{TABLE_HEADER}' could not be found in the DOE PDF "
            "file."
        ) from None
    years = [
        int(word)
        for word in lines[header_index][len(TABLE_HEADER) :].split()
    ]

    # Each line of the table starts with the name of the grid, followed
    # by the value of each year. The table ends with the "Total Gross
    # Generation" line.
    gross_generation = {}
    for line in lines[header_index + 1 :]:
        grid = next(
            (name for name in CODES_OF_GRIDS if line.startswith(name)), None
        )
        if grid is None:
            break

        values = [
            float(word.replace(",", ""))
            for word in line[len(grid) :].split()
        ]
        if len(values) != len(years):
            raise ValueError(
                f"The number of values of {grid} ({len(values)}) does not "
                f"match the number of years ({len(years)}) in the DOE PDF "
                "file."
            )

        # Convert the values from GWh to MWh.
        gross_generation[CODES_OF_GRIDS[grid]] = pandas.Series(
            values, index=years
        ) * 1000

        if CODES_OF_GRIDS[grid] == "PHL":
            break

    missing_codes = set(get_codes()) - set(gross_generation)
    if missing_codes:
        raise ValueError(
            "The gross power generation of the following entities could "
            f"not be found in the DOE PDF file: {', '.join(missing_codes)}."
        )

    # Build a DataFrame with the codes as index and the years as
    # columns.
    gross_generation = pandas.DataFrame(gross_generation).T
    gross_generation.index.name = "Code"
    gross_generation.columns.name = "Year"

    logging.info(
        "Gross power generation per grid data from the DOE has been "
        "downloaded successfully."
    )

    return gross_generation
