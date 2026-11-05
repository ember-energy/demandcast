# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module provides functions to retrieve the electricity demand
    data from the website of the Grid System Operator (GSO) of
    Peninsular Malaysia. The data has a 10-minute resolution and is
    available from Sep 01, 2016 up to the current date.

    The "Plot" button on the System Demand page calls the ASP.NET web
    method "GetChartDataSource", which accepts any date range as a JSON
    body. This module calls that web method directly, one month per
    request, so no browser automation is needed.

    Source: https://www.gso.org.my/SystemData/SystemDemand.aspx
"""  # noqa: W505

import io
import logging
import time

import pandas
import requests
import utils.entities

# Earliest timestamp with data on the GSO website.
FIRST_AVAILABLE_DATE = pandas.Timestamp("2016-09-01")

# Codes for which the GSO data is valid (Peninsular Malaysia grid).
SUPPORTED_CODES = ["MYS", "MYS_PEN"]

PAGE_URL = "https://www.gso.org.my/SystemData/SystemDemand.aspx"


def redistribute() -> bool:
    """
    Return a boolean indicating if the data can be redistributed.

    Returns
    -------
    bool
        True if the data can be redistributed, False otherwise.
    """
    logging.debug("Publicly available data; redistribution terms unclear.")
    logging.debug("Source: https://www.gso.org.my/SystemData/SystemDemand.aspx")
    return True


def _check_code(code: str) -> None:
    """
    Check that the GSO data is valid for the given code.

    Parameters
    ----------
    code : str
        The code of the country or subdivision.
    """
    if code not in SUPPORTED_CODES:
        raise ValueError(
            f"GSO only publishes Peninsular Malaysia demand; code {code} is "
            f"not supported. Supported codes: {SUPPORTED_CODES}."
        )


def get_available_requests(code: str = "MYS") -> list[tuple[int, int]]:
    """
    Get the available requests.

    Each request is one calendar month between the configured start
    date (but not before Sep 2016) and the configured end date.

    Parameters
    ----------
    code : str
        The code of the country or subdivision.

    Returns
    -------
    requests : list[tuple[int, int]]
        List of tuples in the format (year, month).
    """
    _check_code(code)

    start_date, end_date = (
        utils.entities.read_date_ranges_of_electricity_demand_in_data_source(
            "gso"
        )[code]
    )
    start_date = max(pandas.Timestamp(start_date), FIRST_AVAILABLE_DATE)
    end_date = pandas.Timestamp(end_date)

    return [
        (date.year, date.month)
        for date in pandas.date_range(
            start=start_date.replace(day=1), end=end_date, freq="MS"
        )
    ]


def get_url() -> str:
    """
    Get the URL of the GSO web method that returns the demand data.

    Returns
    -------
    str
        The URL of the web method.
    """
    return f"{PAGE_URL}/GetChartDataSource"


def download_and_extract_data_for_request(
    year: int,
    month: int,
    code: str = "MYS",
    retries: int = 5,
    retry_delay: int = 5,
) -> pandas.Series:
    """
    Download and extract the electricity demand data for one month.

    Parameters
    ----------
    year : int
        The year of the data.
    month : int
        The month of the data.
    code : str
        The code of the country or subdivision.
    retries : int, optional
        The number of retries in case of request errors.
    retry_delay : int, optional
        The delay between retries in seconds.

    Returns
    -------
    electricity_demand_time_series : pandas.Series
        The electricity demand time series in MW.
    """
    _check_code(code)
    assert (year, month) in get_available_requests(code), (
        f"The {year}-{month:02d} request is not available."
    )

    logging.info(f"Retrieving electricity demand data for {year}-{month:02d}.")

    # The web method expects dates in dd/mm/yyyy format, both inclusive.
    first_day = pandas.Timestamp(year=year, month=month, day=1)
    last_day = first_day + pandas.offsets.MonthEnd(0)
    payload = {
        "Fromdate": first_day.strftime("%d/%m/%Y"),
        "Todate": last_day.strftime("%d/%m/%Y"),
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json; charset=utf-8",
        "Referer": PAGE_URL,
    }

    for attempt in range(retries):
        try:
            response = requests.post(
                get_url(), json=payload, headers=headers, timeout=60
            )
            response.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            logging.error(
                f"Request error: {e}. Retrying ({attempt + 1}/{retries})..."
            )
            time.sleep(retry_delay)
    else:
        raise Exception(
            f"Failed to fetch GSO data for {year}-{month:02d} after "
            f"{retries} retries."
        )

    # ASP.NET web methods wrap the result in {"d": "<JSON string>"}.
    records = pandas.read_json(
        io.StringIO(response.json()["d"]), orient="records"
    )

    if records.empty:
        logging.warning(f"No GSO data for {year}-{month:02d}.")
        return pandas.Series(dtype=float)

    # Timestamps are in Malaysia local time (UTC+8, no DST).
    index = pandas.to_datetime(records["DT"]).dt.tz_localize(
        "Asia/Kuala_Lumpur"
    )
    electricity_demand_time_series = pandas.Series(
        records["MW"].astype(float).values, index=index
    )

    return electricity_demand_time_series
