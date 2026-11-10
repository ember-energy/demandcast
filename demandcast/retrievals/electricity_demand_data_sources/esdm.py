# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Indonesia (IDN) electricity demand profile
Script owner : Giang Vu

Description:

    This module builds a synthetic electricity demand time series for
    Indonesia and its grid nodes (subdivisions). There is no public
    high-resolution demand data for Indonesia, so the demand shape of
    Peninsular Malaysia is used as a proxy:

    1. The latest Peninsular Malaysia demand retrieved from GSO
       (MYS_PEN_gso.parquet or .csv in the most recent dated folder of
       the electricity demand folder) is read. It has a 10-minute
       resolution.
    2. For each local year, the 10-minute demand shape is computed as
       the share of each 10-minute load energy in the total annual load
       energy. Missing 10-minute steps are linearly interpolated first,
       so that gaps do not bias the shares.
    3. The shape is moved from Malaysian local (wall-clock) time to the
       local time of the Indonesian node, so that, for example, the
       Malaysian evening peak lands on the Indonesian evening.
    4. The shape of each year is scaled by the annual PLN electricity
       sales of the node in the same year (GWh, sheet "Node_totals" of
       the ESDM/Pusdatin file in socio_economic_data_sources/
       manual_downloads/esdm_pusdastin).
    5. The 10-minute demand is resampled to hourly means.

    Only the years with both GSO data and PLN sales are returned. The
    country total (IDN) is the sum of the nodes.

    Sources:
    - https://www.gso.org.my/SystemData/SystemDemand.aspx
    - ESDM Handbook of Energy & Economic Statistics of Indonesia 2025 (HEESI 2025)
    - PLN Statistics / ESDM Pusdatin, electricity sales by customer
      group and region, 2017-2024
    - 2025 Electricity Sales was calculated from the average share of node's sales * PLN Electricity Sales from HEESI 2025).
"""

import functools
import logging
import os
import re

import pandas
import utils.config
import utils.entities

# Define the file and sheet with the annual PLN electricity sales.
SALES_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "socio_economic_data_sources",
    "manual_downloads",
    "esdm_pusdastin",
    "PLN_electricity_sales_by_customer_group_and_region_2017-2024.xlsx",
)
SALES_SHEET_NAME = "Node_totals"

# Define the GSO file used as the proxy demand shape, and its time zone.
PROXY_IDENTIFIER = "MYS_PEN_gso"
PROXY_TIME_ZONE = "Asia/Kuala_Lumpur"

# Define the resolution of the proxy demand shape.
PROXY_FREQUENCY = "10min"

# Map the grid nodes of the sales file to the codes of the subdivisions.
CODES_OF_NODES = {
    "ID-JAW": "IDN_JAW",
    "ID-BTM": "IDN_BTM",
    "ID-SUM": "IDN_SUM",
    "ID-KAL": "IDN_KAL",
    "ID-SUL": "IDN_SUL",
    "ID-NUS": "IDN_NUS",
    "ID-MAL": "IDN_MAL",
    "ID-PAP": "IDN_PAP",
}


def redistribute() -> bool:
    """
    Return a boolean indicating if the data can be redistributed.

    Returns
    -------
    bool
        True if the data can be redistributed, False otherwise.
    """
    logging.debug(
        "Synthetic profile built from GSO (Malaysia) demand and PLN "
        "sales statistics; redistribution terms unclear."
    )
    return False


def get_available_requests(code: str = "IDN") -> None:
    """
    Get the available requests.

    Parameters
    ----------
    code : str
        The code of the country or subdivision.

    Returns
    -------
    None
        Returning None indicates to the pipeline that the data can be
        retrieved all at once.
    """
    return None


def _get_latest_proxy_file_path() -> str:
    """
    Get the path of the latest GSO file in the electricity demand folder.

    The electricity demand folder contains one folder per retrieval
    date (YYYY-MM-DD). The most recent folder with a MYS_PEN_gso file
    is used, preferring the Parquet file over the CSV file.

    Returns
    -------
    str
        The path of the latest MYS_PEN_gso file.

    Raises
    ------
    FileNotFoundError
        If no MYS_PEN_gso file is found.
    """
    electricity_demand_folder = utils.config.read_folders_structure()[
        "electricity_demand_folder"
    ]

    # Loop over the dated folders, from the most recent to the oldest.
    dated_folders = sorted(
        (
            folder
            for folder in os.listdir(electricity_demand_folder)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder)
            and os.path.isdir(os.path.join(electricity_demand_folder, folder))
        ),
        reverse=True,
    )
    for folder in dated_folders:
        for extension in (".parquet", ".csv"):
            file_path = os.path.join(
                electricity_demand_folder, folder, PROXY_IDENTIFIER + extension
            )
            if os.path.exists(file_path):
                return file_path

    raise FileNotFoundError(
        f"No {PROXY_IDENTIFIER} file found in {electricity_demand_folder}. "
        "Retrieve the GSO data for MYS_PEN first."
    )


@functools.lru_cache(maxsize=1)
def read_proxy_demand() -> pandas.Series:
    """
    Read the latest Peninsular Malaysia demand from GSO.

    Returns
    -------
    pandas.Series
        The 10-minute demand in MW, indexed by the local (wall-clock)
        time of Peninsular Malaysia, without time zone information.
    """
    file_path = _get_latest_proxy_file_path()
    logging.info(f"Reading the demand shape from {file_path}.")

    if file_path.endswith(".parquet"):
        demand = pandas.read_parquet(file_path)["Load (MW)"]
    else:
        demand = pandas.read_csv(
            file_path, index_col="Time (UTC)", parse_dates=True
        )["Load (MW)"]

    # Convert the time from UTC to Malaysian local time.
    demand.index = (
        pandas.DatetimeIndex(demand.index)
        .tz_localize("UTC")
        .tz_convert(PROXY_TIME_ZONE)
        .tz_localize(None)
    )
    return demand.astype(float).sort_index()


@functools.lru_cache(maxsize=1)
def get_demand_shapes() -> pandas.Series:
    """
    Get the 10-minute demand shape of each local year.

    The shape is the share of each 10-minute load energy in the total
    annual load energy, so that the shares of each year sum to 1. Only
    the years fully covered by the GSO data are kept. Missing
    10-minute steps inside a year are linearly interpolated.

    Returns
    -------
    pandas.Series
        The share of each 10-minute step in its local year, indexed by
        the local (wall-clock) time, without time zone information.
    """
    demand = read_proxy_demand()

    shapes = []
    for year in sorted(demand.index.year.unique()):
        # Define the complete 10-minute time steps of the year.
        full_index = pandas.date_range(
            start=f"{year}-01-01",
            end=f"{year + 1}-01-01",
            freq=PROXY_FREQUENCY,
            inclusive="left",
        )

        # Skip the years that are not fully covered by the data.
        if demand.index[0] > full_index[0] or demand.index[-1] < full_index[-1]:
            logging.info(
                f"Skipping {year}: the GSO data does not cover the full year."
            )
            continue

        # Fill the missing 10-minute steps of the year.
        demand_of_year = demand[demand.index.year == year].reindex(full_index)
        missing_steps = int(demand_of_year.isna().sum())
        if missing_steps:
            logging.info(
                f"Interpolating {missing_steps} missing 10-minute steps of "
                f"the GSO data in {year}."
            )
            demand_of_year = demand_of_year.interpolate(
                method="time", limit_direction="both"
            )

        # Each step lasts 10 minutes, so the share of energy equals the
        # share of power.
        shapes.append(demand_of_year / demand_of_year.sum())

    if not shapes:
        raise ValueError("The GSO data does not cover any full year.")

    return pandas.concat(shapes)


@functools.lru_cache(maxsize=1)
def read_annual_sales() -> pandas.DataFrame:
    """
    Read the annual PLN electricity sales of each grid node.

    Returns
    -------
    pandas.DataFrame
        The annual electricity sales in GWh, with the years as index
        and the codes of the subdivisions as columns.
    """
    sales = pandas.read_excel(SALES_FILE_PATH, sheet_name=SALES_SHEET_NAME, header=3)
    node_column = sales.columns[0]

    # Keep the node rows of the main table, which ends at the
    # "Sum of nodes" row (the rows below detail the mixed Riau values).
    end_of_table = sales.index[sales[node_column] == "Sum of nodes"][0]
    sum_of_nodes = sales.loc[end_of_table]
    sales = sales.loc[: end_of_table - 1]
    sales = sales[sales[node_column].isin(CODES_OF_NODES)]

    # Keep the year columns (e.g., 2017 or "2025 (calculated)").
    year_columns = {
        column: int(str(column)[:4])
        for column in sales.columns
        if re.match(r"^\d{4}", str(column))
    }
    sum_of_nodes = sum_of_nodes[list(year_columns)].astype(float)
    sales = (
        sales.set_index(node_column)[list(year_columns)]
        .astype(float)
        .rename(index=CODES_OF_NODES, columns=year_columns)
        .T
    )
    sales.index.name = "year"
    sales.columns.name = None

    # Check that all the nodes are present and add up to the total.
    missing_nodes = set(CODES_OF_NODES.values()) - set(sales.columns)
    if missing_nodes:
        raise ValueError(f"Nodes missing in the sales file: {missing_nodes}.")
    difference = (sales.sum(axis=1) - sum_of_nodes.to_numpy()).abs()
    if (difference > 1).any():
        logging.warning(
            "The node sales do not add up to the 'Sum of nodes' row:\n"
            f"{difference[difference > 1]}"
        )

    return sales


def _scale_demand_shape(annual_sales: pandas.Series, time_zone: str) -> pandas.Series:
    """
    Scale the demand shape with the annual sales and resample to hourly.

    Parameters
    ----------
    annual_sales : pandas.Series
        The annual electricity sales in GWh, indexed by year.
    time_zone : str
        The time zone of the country or subdivision.

    Returns
    -------
    pandas.Series
        The hourly demand in MW, with a timezone-aware index.
    """
    shapes = get_demand_shapes()

    # Keep the years with both a demand shape and annual sales.
    shape_years = shapes.index.year
    annual_sales = annual_sales.dropna()
    years = sorted(set(shape_years) & set(annual_sales.index))
    skipped_years = sorted(set(annual_sales.index) - set(years))
    if skipped_years:
        logging.warning(f"No full year of GSO data for the years {skipped_years}.")
    if not years:
        return pandas.Series(dtype=float)
    shapes = shapes[shape_years.isin(years)]

    # Energy of each 10-minute step (MWh) = share x annual sales (GWh)
    # x 1000, and power (MW) = energy / (10 / 60 h).
    steps_per_hour = pandas.Timedelta("1h") / pandas.Timedelta(PROXY_FREQUENCY)
    demand = (
        shapes
        * annual_sales.reindex(shapes.index.year).to_numpy()
        * 1000
        * steps_per_hour
    )

    # Use the Malaysian wall-clock time as the local time of the
    # Indonesian node. Ambiguous and non-existent times only occur in
    # time zones with daylight saving time, which is not the case in
    # Indonesia.
    demand.index = demand.index.tz_localize(
        time_zone, ambiguous="NaT", nonexistent="NaT"
    )
    demand = demand[demand.index.notna()]

    # Resample the 10-minute demand to hourly means (MW), which equal
    # the hourly energy in MWh.
    return demand.resample("1h").mean()


def download_and_extract_data(code: str = "IDN") -> pandas.Series:
    """
    Build the hourly electricity demand of a country or subdivision.

    Parameters
    ----------
    code : str
        The code of the country (IDN) or of a subdivision of
        CODES_OF_NODES (e.g., IDN_JAW).

    Returns
    -------
    electricity_demand_time_series : pandas.Series
        The hourly electricity demand time series in MW, with a
        timezone-aware index.

    Raises
    ------
    ValueError
        If the code is not IDN or a code of CODES_OF_NODES.
    """
    if code != "IDN" and code not in CODES_OF_NODES.values():
        raise ValueError(f"Code {code} is not available in ESDM.")

    sales = read_annual_sales()
    time_zone = utils.entities.get_time_zone(code)
    logging.info(f"Building the hourly demand of {code} in {time_zone}.")

    if code == "IDN":
        # The nodes share the same shape and time zone, so the country
        # demand is the shape scaled by the sum of the node sales.
        annual_sales = sales.sum(axis=1, min_count=len(sales.columns))
    else:
        annual_sales = sales[code]

    return _scale_demand_shape(annual_sales, time_zone)


if __name__ == "__main__":
    for code in ["IDN", *CODES_OF_NODES.values()]:
        print(code)
        print(download_and_extract_data(code))
