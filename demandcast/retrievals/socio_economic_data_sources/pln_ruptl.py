# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module reads the projected electricity sales of PLN by grid node
    from the RUPTL 2025-2034 (Rencana Usaha Penyediaan Tenaga Listrik).
    The values come from the "Sales (GWh)" table of the sheet
    "By_grid_node" of a manually compiled Excel file (manual_downloads/
    pln/RUPTL_2025-2034_Provincial_Demand_1_2.xlsx), where the provincial
    sales of the "Proyeksi Kebutuhan Tenaga Listrik" tables of Lampiran
    A, B and C are summed into the eight grid nodes of Indonesia defined
    in shapes/esdm.py (sheet "Grid_node_mapping" of the same file).

    In retrievals.annual_electricity_demand_per_capita, the sales of the
    nodes are used as the demand of Indonesia (sum of the nodes) and of
    the nodes from 2026 to 2034. The historical demand comes from the PLN
    energy consumption of the nodes (electricity_demand_data_sources/
    esdm.py), which also covers PLN assets only. The RUPTL sales of 2025
    (323.0 TWh) are about 3% higher than the PLN energy consumption of
    2025 (313.6 TWh), so the national demand rises by 8.4% from 2025 to
    2026 (5.2% within the RUPTL). This step is kept as it is.

    The RUPTL row of Kepulauan Riau (IDN_BTM) does not seem to include
    the Batam system (PLN Batam) before 2031: its sales are 1.1 TWh in
    2025 (0.3% of the national sales), compared with 4.2 TWh (1.3%) in
    the PLN energy consumption of the node in 2025, and they jump to
    5.8 TWh (1.3%) in 2031. Until HOLD_HISTORICAL_BTM_SHARE_UNTIL, the
    share of IDN_BTM is therefore set to its average share in the PLN
    sales, and the shares of the other nodes are rescaled so that the
    shares sum to 1 (the national total is unchanged). Set
    HOLD_HISTORICAL_BTM_SHARE_UNTIL to None to use the RUPTL sales of the
    nodes as they are.

    Source: PT PLN (Persero), RUPTL 2025-2034.
"""

import functools
import logging
import os

import pandas

import retrievals.electricity_demand_data_sources.esdm as esdm

# Define the Excel file, the sheet and the title of the table of the
# projected sales of the grid nodes.
FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "manual_downloads",
    "pln",
    "RUPTL_2025-2034_Provincial_Demand_1_2.xlsx",
)
SHEET_NAME = "By_grid_node"
TABLE_TITLE = "Sales (GWh)"
TOTAL_ROW_NAME = "Indonesia (sum of nodes)"

# Define the first and last years of the RUPTL projection used for the
# future demand.
FIRST_YEAR_OF_PROJECTION = 2026
LAST_YEAR_OF_PROJECTION = 2034

# Define the last year in which the share of IDN_BTM is held at its
# average share in the historical PLN sales (None to use the RUPTL
# sales of the nodes as they are).
HOLD_HISTORICAL_BTM_SHARE_UNTIL = 2030
BTM_CODE = "IDN_BTM"

# Define the code of Indonesia.
CODE = "IDN"


def get_codes() -> list[str]:
    """
    Get the codes of the grid nodes with RUPTL data.

    Returns
    -------
    list[str]
        The codes of the grid nodes.
    """
    return list(esdm.CODES_OF_NODES.values())


@functools.lru_cache(maxsize=1)
def read_node_sales() -> pandas.DataFrame:
    """
    Read the projected electricity sales of the grid nodes.

    Returns
    -------
    pandas.DataFrame
        The projected sales in GWh, with the codes of the grid nodes as
        index and the years (2025-2034) as columns.

    Raises
    ------
    ValueError
        If the table, a grid node or a value is missing, or if the nodes
        do not add up to the total row of the table.
    """
    logging.info("Reading the projected electricity sales of the RUPTL.")

    sheet = pandas.read_excel(FILE_PATH, sheet_name=SHEET_NAME, header=None)
    first_column = sheet[0].astype(str).str.strip()

    # Find the table: its title, then the header row with the years.
    title_rows = sheet.index[first_column == TABLE_TITLE]
    if len(title_rows) != 1:
        raise ValueError(
            f"The table {TABLE_TITLE!r} was not found in the sheet "
            f"{SHEET_NAME} of {FILE_PATH}."
        )
    header_row = title_rows[0] + 1
    header = sheet.loc[header_row]
    year_columns = {
        column: int(float(value))
        for column, value in header.items()
        if str(value)[:4].isdigit()
    }

    # Read the rows of the table until the total row.
    node_codes = get_codes()
    rows = {}
    total = None
    for row in range(header_row + 1, len(sheet)):
        name = first_column[row]
        if name in node_codes:
            rows[name] = sheet.loc[row, list(year_columns)]
        elif str(sheet.loc[row, 1]).strip() == TOTAL_ROW_NAME:
            total = (
                sheet.loc[row, list(year_columns)]
                .rename(year_columns)
                .astype(float)
            )
            break

    missing = set(node_codes) - set(rows)
    if missing or total is None:
        raise ValueError(
            f"The grid nodes {sorted(missing)} or the total row were not "
            f"found in the table {TABLE_TITLE!r} of {FILE_PATH}."
        )

    sales = (
        pandas.DataFrame(rows)
        .T.rename(columns=year_columns)
        .astype(float)
        .loc[node_codes]
    )
    if sales.isna().any().any():
        raise ValueError(f"Missing sales values in {FILE_PATH}.")

    # Check that the nodes add up to the total row of the table.
    difference = (sales.sum() - total).abs().max()
    if difference > 1:
        raise ValueError(
            "The grid nodes do not add up to the total sales in "
            f"{FILE_PATH} (difference: {difference:.0f} GWh)."
        )

    sales.index.name = "Code"
    sales.columns.name = "Year"
    return sales


def read_national_sales() -> pandas.Series:
    """
    Read the projected electricity sales of Indonesia.

    Returns
    -------
    pandas.Series
        The projected sales in GWh (sum of the grid nodes), with the
        years (2025-2034) as index.
    """
    return read_node_sales().sum().rename(CODE)


def get_node_shares(years: list[int]) -> pandas.DataFrame:
    """
    Get the share of each grid node in the projected sales of Indonesia.

    The share of a year in the RUPTL (2025-2034) is the sales of the node
    divided by the sales of all nodes. The years before the first year
    of the RUPTL use the share of the first year, and the years after the
    last year use the share of the last year (2034). Until
    HOLD_HISTORICAL_BTM_SHARE_UNTIL, the share of IDN_BTM is its average
    share in the historical PLN sales, and the shares of the other nodes
    are rescaled so that the shares sum to 1.

    Parameters
    ----------
    years : list[int]
        The years of interest.

    Returns
    -------
    pandas.DataFrame
        The shares, with the codes of the grid nodes as index and the
        years as columns. The shares of each year sum to 1.
    """
    nodes = read_node_sales()
    shares = nodes / nodes.sum()

    if HOLD_HISTORICAL_BTM_SHARE_UNTIL is not None:
        btm_share = esdm.get_average_energy_shares()[BTM_CODE]
        held_years = [
            year
            for year in shares.columns
            if year <= HOLD_HISTORICAL_BTM_SHARE_UNTIL
        ]
        others = [code for code in shares.index if code != BTM_CODE]
        shares.loc[others, held_years] = (
            shares.loc[others, held_years]
            / shares.loc[others, held_years].sum()
            * (1 - btm_share)
        )
        shares.loc[BTM_CODE, held_years] = btm_share

    first_year, last_year = shares.columns.min(), shares.columns.max()
    used_years = [min(max(year, first_year), last_year) for year in years]
    return shares[used_years].set_axis(years, axis=1)
