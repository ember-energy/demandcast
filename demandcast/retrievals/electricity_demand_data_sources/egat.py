"""
Thailand (THA) electricity demand profile 
Script owner : Giang Vu

Description:

    This module provides functions to retrieve the electricity demand
    data for Thailand from the Electricity Generating Authority of Thailand (EGAT).
    The data is available from Jul 1, 2024 to the current date. The data is
    retrieved all at once.

    Source: https://www.sothailand.com/sysgen/api/hist/actual 
"""

import logging 
import pandas as pd
import datetime
import utils.entities 
import requests
import time
import concurrent.futures

url = 'https://www.sothailand.com/sysgen/api/hist/actual?timestamp='


#The start date and end date of the API request
#Time in LOCAL

def get_available_requests() -> None:
    """
    Get the available requests for the electricity demand data 
    from EGAT.

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

def retrieve_response_from_url(date: str) -> dict:
    url = get_url(date)

    print(url)

    params = {
        "timestamp" : date
    }

    try:
        response = requests.get(url, params = params, timeout=15)
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
    
def download_and_extract_data() -> pd.Series:
    """
    Download and extract electricity demand data.

    Orchestrates the data extraction and transformation pipeline for all available dates.
    Combines daily data into a single, continuous DataFrame using concurrency.

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

    total_days = (end_date - start_date).days+1
    target_dates = [(start_date + datetime.timedelta(days=i)).strftime('%d-%m-%Y') for i in range(total_days)]
    
    print(f"Found {len(target_dates)} dates to process.")

    daily_dataframes = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        # map() blocks until all dates are processed
        results = executor.map(process_single_date, target_dates)
        
        # Filter out None values (failures) from the results
        for daily_df in results:
            if daily_df is not None:
                daily_dataframes.append(daily_df)

    if daily_dataframes:
        combined_df = pd.concat(daily_dataframes, ignore_index=True)
        combined_df = combined_df.sort_values('Time (LOCAL)').reset_index(drop = True)
        combined_df = combined_df.set_index('Time (LOCAL)')

        # Create a timezone-aware Pandas series
        # Make sure these paths are correct for your machine!
        master_series = pd.Series(combined_df['Load (MW)'].values, index=combined_df.index)
        
        print("Pipeline complete!")
        return master_series
    else:
        print("\nPipeline finished, but no data was successfully retrieved.")
        return pd.Series(dtype='float64')


if __name__ == "__main__":
    final_electricity_data = download_and_extract_data()
    print(final_electricity_data)   
