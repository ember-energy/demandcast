"""
Thailand (THA) electricity demand profile 
Script owner : Giang Vu

Description:

    This module provides functions to retrieve the electricity demand
    data for Thailand from the Electricity Generating Authority of Thailand (EGAT).
    The data is available from Jul 1, 2024 to the current date. The data is
    retrieved all at once.

    The demand of the subdivisions is derived from the national demand:
    each hour of a subdivision = national demand at that hour x the
    average share of the subdivision in the total demand at the same
    date (month and day) and hour in 2023 and 2024. The shares are
    computed from the regional demand of EGAT (system_2023.csv and
    system_2024.csv in socio_economic_data_sources/manual_downloads).
    The metropolitan and central demand are combined into THA_CEN.

    Source: https://www.sothailand.com/sysgen/api/hist/actual
"""

import concurrent.futures
import datetime
import functools
import logging
import os
import threading

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import utils.config
import utils.entities

url = 'https://www.sothailand.com/sysgen/api/hist/actual?timestamp='

# Define the number of parallel requests, the timeout of each request
# (connect, read) in seconds, and the retries of the failed requests
# (the waits between retries are BACKOFF_FACTOR x 2^n seconds). Reduce
# MAX_WORKERS if the requests still time out.
MAX_WORKERS = 4
TIMEOUT = (10, 60)
MAX_RETRIES = 5
BACKOFF_FACTOR = 2

# Store a session per thread, as requests.Session is not thread-safe.
_thread_data = threading.local()

# Define the files with the regional demand of EGAT, by year.
REGIONAL_DEMAND_FILE_PATHS = {
    year: os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "socio_economic_data_sources",
        "manual_downloads",
        f"system_{year}.csv",
    )
    for year in (2023, 2024)
}

# Define the column of the regional demand of each subdivision.
CODES_OF_REGIONS = {
    "THA_NOR": "north_demand",
    "THA_NEA": "northeast_demand",
    "THA_SOU": "south_demand",
    "THA_CEN": "metropolitan_central_demand",
}


#The start date and end date of the API request
#Time in LOCAL

def get_available_requests(code: str = "THA") -> None:
    """
    Get the available requests for the electricity demand data
    from EGAT.

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

# def get_available_requests() -> list[str]:
#     """
#     Get the available requests for the electricity demand data 
#     from EGAT.

#     Returns
#     -------
#     list[int]
#         The list of available requests.
#     """     

#     # Read the start and end date of the available data.
#     start_date, end_date = (
#         utils.entities.read_date_ranges_of_electricity_demand_in_data_source(
#             "egat"
#         )['THA']
#     )
#     total_days = (end_date - start_date).days+1
#     date_range = [start_date + datetime.timedelta(days=i) for i in range(total_days)]
#     return [d.strftime('%d-%m-%Y') for d in date_range]

def get_url(date: str) -> str:
    """
    Get the URL of the electricity demand data from EGAT.
    Parameters
    ----------
    date : str
        The date of the electricity demand data.

    Returns
    -------
    url : str
        The URL of the electricity demand data.
    """
    return url + date

def _get_session() -> requests.Session:
    """
    Get the HTTP session of the current thread.

    Each thread has its own session, which retries the failed requests
    with an exponential backoff, so that the EGAT server is not
    overloaded.

    Returns
    -------
    requests.Session
        The session of the current thread.
    """
    if not hasattr(_thread_data, "session"):
        session = requests.Session()
        retries = Retry(
            total=MAX_RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        _thread_data.session = session
    return _thread_data.session


def retrieve_response_from_url(date: str) -> dict:
    url = get_url(date)

    print(url)

    params = {
        "timestamp" : date
    }

    try:
        response = _get_session().get(url, params=params, timeout=TIMEOUT)
        response.raise_for_status()

        data = response.json()

        return data 
    
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None

def transform_response(response : dict) -> pd.DataFrame:
    date_str = response.get('day')
    data_list = response.get('list')

    df = pd.DataFrame(data_list,columns = ['second_from_midnight','Load (MW)'])

    base_date = pd.to_datetime(date_str,format='%d-%m-%Y')

    df['Time (LOCAL)'] = base_date + pd.to_timedelta(df['second_from_midnight'],unit='s')

    df['Time (LOCAL)'] = df['Time (LOCAL)'].dt.tz_localize('Asia/Bangkok')
    
    df_clean = df[['Time (LOCAL)','Load (MW)']]

    df_clean = df_clean.set_index('Time (LOCAL)')

    df_hourly = df_clean.resample('1h').mean()

    df_hourly = df_hourly.reset_index()

    return df_hourly


def process_single_date(date_to_query: str) -> pd.DataFrame | None:
    """Helper function to fetch and transform a single date for concurrent execution."""
    print(f"Processing: {date_to_query}")
    response = retrieve_response_from_url(date_to_query)
    
    if response is not None:
        daily_df = transform_response(response)
        if not daily_df.empty:
            return daily_df
        else:
            print(f'Empty response for {date_to_query}')
            return None
    else:
        print(f'Fail to retrieve for {date_to_query}')
        return None
    
def get_regional_shares() -> pd.DataFrame:
    """
    Get the average hourly share of each subdivision in the total demand.

    The regional demand of 2023 and 2024 is averaged by local hour, the
    metropolitan and central demand are summed into
    metropolitan_central_demand, and the share of each subdivision in
    the total demand is averaged over the two years at the same month,
    day, and hour.

    Returns
    -------
    pd.DataFrame
        The share of each subdivision (columns: the codes of
        CODES_OF_REGIONS), indexed by month, day, and hour.
    """
    regional_demand = []
    for year, file_path in REGIONAL_DEMAND_FILE_PATHS.items():
        demand = pd.read_csv(file_path, encoding="utf-8-sig")

        # Average the demand by hour (e.g., 00:05 is in the hour 00:00),
        # and keep only the hours of the year of the file.
        demand["datetime"] = pd.to_datetime(
            demand["datetime"], format="%d/%m/%Y %H:%M"
        ).dt.floor("h")
        demand = demand[demand["datetime"].dt.year == year]
        demand = demand.groupby("datetime")[
            [
                "north_demand",
                "northeast_demand",
                "south_demand",
                "metropolitan_demand",
                "central_demand",
            ]
        ].mean()
        regional_demand.append(demand)
    regional_demand = pd.concat(regional_demand)

    # Combine the metropolitan and central demand.
    regional_demand["metropolitan_central_demand"] = (
        regional_demand["metropolitan_demand"] + regional_demand["central_demand"]
    )
    regional_demand = regional_demand[list(CODES_OF_REGIONS.values())]

    # Get the share of each subdivision in the total demand.
    shares = regional_demand.div(regional_demand.sum(axis=1), axis=0)
    shares.columns = list(CODES_OF_REGIONS)

    # Average the shares of 2023 and 2024 at the same month, day, and
    # hour. 29 February is only in 2024.
    index = shares.index
    return shares.groupby(
        [index.month.rename("month"), index.day.rename("day"), index.hour.rename("hour")]
    ).mean()


def _get_cache_file_path() -> str:
    """
    Get the path of the file with the downloaded national demand.

    Returns
    -------
    str
        The path of the Parquet file in the electricity demand folder.
    """
    return os.path.join(
        utils.config.read_folders_structure()["electricity_demand_folder"],
        "egat_downloads",
        "THA_egat_hourly.parquet",
    )


def _read_cached_data() -> pd.DataFrame:
    """
    Read the national demand downloaded in the previous runs.

    Returns
    -------
    pd.DataFrame
        The hourly demand with the columns Time (LOCAL) and Load (MW),
        or an empty DataFrame if there is no downloaded data.
    """
    file_path = _get_cache_file_path()
    if not os.path.exists(file_path):
        return pd.DataFrame(
            {
                "Time (LOCAL)": pd.Series(dtype="datetime64[ns, Asia/Bangkok]"),
                "Load (MW)": pd.Series(dtype=float),
            }
        )

    cached_data = pd.read_parquet(file_path)
    cached_data["Time (LOCAL)"] = cached_data["Time (LOCAL)"].dt.tz_convert(
        "Asia/Bangkok"
    )
    return cached_data


def _save_cached_data(data: pd.DataFrame) -> None:
    """
    Save the downloaded national demand, without duplicated hours.

    Parameters
    ----------
    data : pd.DataFrame
        The hourly demand with the columns Time (LOCAL) and Load (MW).
    """
    file_path = _get_cache_file_path()
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    data = (
        data.drop_duplicates("Time (LOCAL)", keep="last")
        .sort_values("Time (LOCAL)")
        .reset_index(drop=True)
    )
    data.to_parquet(file_path, index=False)


def _get_missing_dates(
    cached_data: pd.DataFrame, start_date: datetime.date, end_date: datetime.date
) -> list[datetime.date]:
    """
    Get the dates without complete data in the downloaded data.

    A date is complete if it has a value for each of its 24 hours.

    Parameters
    ----------
    cached_data : pd.DataFrame
        The output of _read_cached_data.
    start_date : datetime.date
        The first date of the available data.
    end_date : datetime.date
        The last date of the available data.

    Returns
    -------
    list[datetime.date]
        The dates to download.
    """
    hours_per_date = (
        cached_data.dropna(subset=["Load (MW)"])["Time (LOCAL)"]
        .dt.date.value_counts()
    )
    complete_dates = set(hours_per_date[hours_per_date >= 24].index)

    total_days = (end_date - start_date).days + 1
    return [
        date
        for date in (start_date + datetime.timedelta(days=i) for i in range(total_days))
        if date not in complete_dates
    ]


@functools.lru_cache(maxsize=1)
def _download_and_extract_national_data() -> pd.Series:
    """
    Download and extract the national electricity demand data.

    Only the dates without complete data in the previous runs are
    downloaded, month by month and with MAX_WORKERS parallel requests.
    The downloaded data is saved after each month, so that a failed run
    can be continued. The result is cached so that the data is
    downloaded only once for all the subdivisions.

    Returns
    -------
    electricity_demand_time_series : pd.Series
        The electricity demand time series in MW, with a timezone-aware index.
    """

    logging.info("Initializing EGAT pipeline...")

    #Read the start and end date of available data
    start_date, end_date =(
        utils.entities.read_date_ranges_of_electricity_demand_in_data_source(
            "egat"
        )['THA']
    )

    # Get the dates that are not downloaded yet.
    cached_data = _read_cached_data()
    missing_dates = _get_missing_dates(cached_data, start_date, end_date)

    # Group the missing dates by month.
    missing_months: dict[str, list[str]] = {}
    for date in missing_dates:
        missing_months.setdefault(date.strftime("%Y-%m"), []).append(
            date.strftime("%d-%m-%Y")
        )

    if missing_months:
        logging.info(
            f"Downloading {len(missing_dates)} missing dates of EGAT in the months "
            f"{', '.join(missing_months)}."
        )
    else:
        logging.info("All the EGAT data is already downloaded.")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for month, target_dates in missing_months.items():
            print(f"Processing {len(target_dates)} dates of {month}.")

            # Filter out None values (failures) from the results.
            daily_dataframes = [
                daily_df
                for daily_df in executor.map(process_single_date, target_dates)
                if daily_df is not None
            ]
            if len(daily_dataframes) < len(target_dates):
                logging.warning(
                    f"{len(target_dates) - len(daily_dataframes)} dates of {month} "
                    "failed. They will be downloaded again in the next run."
                )

            # Save the downloaded data of the month.
            if daily_dataframes:
                cached_data = pd.concat(
                    [df for df in (cached_data, *daily_dataframes) if not df.empty],
                    ignore_index=True,
                )
                _save_cached_data(cached_data)

    # Keep the data of the available dates.
    cached_data = cached_data[
        (cached_data["Time (LOCAL)"].dt.date >= start_date)
        & (cached_data["Time (LOCAL)"].dt.date <= end_date)
    ]
    if cached_data.empty:
        print("\nPipeline finished, but no data was successfully retrieved.")
        return pd.Series(dtype='float64')

    cached_data = (
        cached_data.drop_duplicates("Time (LOCAL)", keep="last")
        .sort_values("Time (LOCAL)")
        .set_index("Time (LOCAL)")
    )

    # Create a timezone-aware Pandas series
    master_series = pd.Series(
        cached_data["Load (MW)"].to_numpy(dtype=float), index=cached_data.index
    )

    print("Pipeline complete!")
    return master_series


@functools.lru_cache(maxsize=None)
def get_annual_energy_shares(year: int) -> pd.Series:
    """
    Get the share of each subdivision in the annual demand of a year.

    The hourly national demand of EGAT in the year (from the downloaded
    data, without new downloads) is split into the subdivisions with
    the hourly shares of get_regional_shares, as in
    download_and_extract_data, and summed over the year.

    Parameters
    ----------
    year : int
        The local year of interest. All its hours must be downloaded.

    Returns
    -------
    pd.Series
        The share of each subdivision in the annual demand, with the
        codes of CODES_OF_REGIONS as index. The shares add up to 1.

    Raises
    ------
    ValueError
        If the national demand of the year is not complete.
    """
    national_demand = (
        _read_cached_data()
        .dropna(subset=["Load (MW)"])
        .drop_duplicates("Time (LOCAL)", keep="last")
        .set_index("Time (LOCAL)")["Load (MW)"]
    )
    national_demand = national_demand[national_demand.index.year == year]

    hours_in_year = 8784 if pd.Timestamp(year=year, month=1, day=1).is_leap_year else 8760
    if len(national_demand) != hours_in_year:
        raise ValueError(
            f"The EGAT demand of {year} has {len(national_demand)} of "
            f"{hours_in_year} hours in {_get_cache_file_path()}. Retrieve "
            "the EGAT data of the whole year first."
        )

    shares = get_regional_shares()
    local_time = national_demand.index
    hourly_shares = shares.reindex(
        pd.MultiIndex.from_arrays(
            [local_time.month, local_time.day, local_time.hour],
            names=["month", "day", "hour"],
        )
    )
    regional_demand = hourly_shares.mul(national_demand.to_numpy(), axis=0).sum()
    return regional_demand / regional_demand.sum()


def download_and_extract_data(code: str = "THA") -> pd.Series:
    """
    Download and extract the electricity demand data of a code.

    Parameters
    ----------
    code : str
        The code of the country (THA) or of a subdivision of
        CODES_OF_REGIONS (e.g., THA_NOR).

    Returns
    -------
    electricity_demand_time_series : pd.Series
        The electricity demand time series in MW, with a timezone-aware index.

    Raises
    ------
    ValueError
        If the code is not THA or a code of CODES_OF_REGIONS.
    """
    if code != "THA" and code not in CODES_OF_REGIONS:
        raise ValueError(f"Code {code} is not available in EGAT.")

    # Copy the cached national data so that it is not modified.
    national_demand = _download_and_extract_national_data().copy()
    if code == "THA" or national_demand.empty:
        return national_demand

    # Get the share of the subdivision at the month, day, and local hour
    # of each hour of the national demand.
    shares = get_regional_shares()[code]
    local_time = national_demand.index.tz_convert("Asia/Bangkok")
    hourly_shares = shares.reindex(
        pd.MultiIndex.from_arrays(
            [local_time.month, local_time.day, local_time.hour],
            names=["month", "day", "hour"],
        )
    ).to_numpy()

    return national_demand * hourly_shares


if __name__ == "__main__":
    final_electricity_data = download_and_extract_data()
    print(final_electricity_data)
