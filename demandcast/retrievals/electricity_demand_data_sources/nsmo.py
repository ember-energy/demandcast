import pandas as pd
import pickle
import datetime as dt
import functools
import os
import unicodedata

import utils.entities

#Folder with the monthly files downloaded from NSMO (one pickle per month, named YYYY-MM-01)
#Each file is a dict {day: {chart_key: json_response}}
NSMO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "socio_economic_data_sources",
    "manual_downloads",
    "nsmo",
)

#Key of the half-hourly load profile in each daily response
LOAD_PROFILE_KEY = 'GetBcsxChartDataPhuTai'

#Map the demandcast codes to the node names in the NSMO data
CODES_OF_NODES = {
    'VNM_NOR': 'Bắc',
    'VNM_SOU': 'Nam',
    'VNM_CEN': 'Trung',
    'VNM': 'Quốc gia',
}

LOCAL_TIME_ZONE = 'Asia/Ho_Chi_Minh'

#Output folder of the electricity demand, in a subfolder named after today's date (as SGP and THA)
ELECTRICITY_DEMAND_DIR = os.path.join(
    r'D:\Modelling\demandcast\demandcast\data\electricity_demand',
    dt.datetime.now().strftime('%Y-%m-%d'),
)


def create_date_range(start_date: str,end_date:str) -> list:
    return pd.date_range(start=start_date, end=end_date, freq='MS').strftime('%Y-%m-%d').tolist()

def _normalize_name(name: str) -> str:
    #Vietnamese names can be stored in composed or decomposed unicode forms
    return unicodedata.normalize('NFC', name).strip()

@functools.lru_cache(maxsize=1)
def convert_response_df(start_date: str, end_date:str) -> pd.DataFrame:
    """
    Extract the half-hourly load profile of the 4 nodes (Bắc, Trung, Nam, Quốc gia)
    from the monthly NSMO files.

    The hour labels are period-ending: '00:30' is the load of 00:00-00:30 and '00:00'
    is the load of 23:30-24:00, i.e. midnight of the next day. On some days the list
    is rotated (e.g. starts at '06:30'), so the timestamps are built from the labels
    rather than from the order of the list.

    Returns a df with the local time (period ending) and one column per demandcast code.
    """
    names_to_codes = {_normalize_name(name): code for code, name in CODES_OF_NODES.items()}
    load_data=[]

    for i in create_date_range(start_date, end_date):
        file_path = os.path.join(NSMO_DIR, i)

        if not os.path.exists(file_path):
            print(f'File missing for month {i}.')
            continue

        try:
            with open(file_path, 'rb') as f:
                data_raw = pickle.load(f)
        except Exception as e:
            print(f'Error with file for month {i}: {e}')
            continue

        for day, responses in data_raw.items():
            day = pd.Timestamp(day).normalize()
            load_profile = responses.get(LOAD_PROFILE_KEY) if isinstance(responses, dict) else None

            if not isinstance(load_profile, dict) or not load_profile.get('result'):
                print(f'Skipping {day.date()} because the load profile is missing')
                continue

            for node in load_profile['result']:
                code = names_to_codes.get(_normalize_name(node.get('name', '')))
                if code is None:
                    print(f"Skipping unknown node {node.get('name')} on {day.date()}")
                    continue

                for point in node.get('data') or []:
                    time = day + pd.Timedelta(f"{point['hour']}:00")
                    if point['hour'] == '00:00':
                        time += pd.Timedelta(days=1)
                    load_data.append({'time': time, 'code': code, 'Load (MW)': point['value']})

    load_data_df = pd.DataFrame(load_data)
    load_data_df['Load (MW)'] = pd.to_numeric(load_data_df['Load (MW)'], errors='coerce')
    load_data_df = load_data_df.drop_duplicates(subset=['time', 'code'], keep='first')

    df_final = load_data_df.pivot(index='time', columns='code', values='Load (MW)').sort_index()
    df_final = df_final[[code for code in CODES_OF_NODES if code in df_final.columns]]
    df_final.columns.name = None

    df_final = df_final.reset_index()

    return df_final

def _to_hourly(df: pd.DataFrame, code: str) -> pd.Series:
    #Shift the period-ending half hours to period-starting and average them into hourly values
    series = df.set_index('time')[code]
    series.index = series.index - pd.Timedelta(minutes = 30)
    series = series.resample('h').mean()
    series.index = series.index.tz_localize(LOCAL_TIME_ZONE)
    return series

def get_available_requests(code: str = 'VNM') -> None:
    """
    Get the available requests for the electricity demand data from NSMO.

    Returning None indicates to the pipeline that the data of each code is
    retrieved all at once from the monthly files.
    """
    return None

def download_and_extract_data(code: str = 'VNM') -> pd.Series:
    """
    Extract the hourly electricity demand of a code from the monthly NSMO files.

    Called by retrieve.py, which cleans the time series and saves it as
    {code}.csv/.parquet in today's electricity demand folder.

    Parameters
    ----------
    code : str
        VNM or a code of CODES_OF_NODES (e.g. VNM_NOR).

    Returns
    -------
    pd.Series
        The electricity demand time series in MW, with a timezone-aware index.
    """
    if code not in CODES_OF_NODES:
        raise ValueError(f'{code} is not one of {list(CODES_OF_NODES)}.')

    #The files of all the codes are read once, so use the date range of the country
    start_date, end_date = (
        utils.entities.read_date_ranges_of_electricity_demand_in_data_source('nsmo')['VNM']
    )
    df = convert_response_df(str(start_date), str(end_date))

    return _to_hourly(df, code)

def conform_retrieval(df: pd.DataFrame, code: str = 'VNM') -> pd.DataFrame:
    series = _to_hourly(df, code)
    series.index = series.index.tz_convert('UTC').tz_localize(None)
    series.index.name = 'Time (UTC)'
    df = series.to_frame('Load (MW)')

    df.to_csv(rf'D:\Modelling\demandcast\demandcast\data\processing\{code}_nsmo_full_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.csv')
    df.to_parquet(rf'D:\Modelling\demandcast\demandcast\data\processing\{code}_nsmo_full_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.parquet')

    return df

#Save the hourly load of a node as {code}.csv/.parquet in today's electricity demand folder
def export_electricity_demand(df: pd.DataFrame, code: str = 'VNM') -> pd.DataFrame:
    df = df.dropna().sort_index()

    os.makedirs(ELECTRICITY_DEMAND_DIR, exist_ok=True)
    df.to_csv(os.path.join(ELECTRICITY_DEMAND_DIR, f'{code}.csv'))
    df.to_parquet(os.path.join(ELECTRICITY_DEMAND_DIR, f'{code}.parquet'))

    return df

#Create the df including nan months to assemble the feature data
def fill_missing_intervals(df_conformed: pd.DataFrame, code: str = 'VNM') -> pd.DataFrame:
    start_time = df_conformed.index.min()
    end_time = df_conformed.index.max()

    print(f"Analyzing data of {code} from {start_time} to {end_time}...")

    #Identify intervals present in the dataset and already have NaN values
    pre_existing_nans = df_conformed[df_conformed['Load (MW)'].isna()].index

    #Identify the perfectly continuous hourly range
    expected_range = pd.date_range(start=start_time, end=end_time, freq='h')

    #Identify intervals that are completely missing from the dataset
    completely_missing_hours = expected_range.difference(df_conformed.index)

    # 6. Find the missing timestamps by finding the difference
    df_filled = df_conformed.reindex(expected_range)
    df_filled.index.name = 'Time (UTC)'

    print(f"\n--- Data Quality Report ---")
    print(f"Original row count:              {len(df_conformed)}")
    print(f"New row count:                   {len(df_filled)}")
    print(f"Pre-existing NaN records:        {len(pre_existing_nans)}")
    print(f"Completely missing hours added:  {len(completely_missing_hours)}")
    print(f"Total NaN intervals in final df: {df_filled['Load (MW)'].isna().sum()}")
    print(f"---------------------------\n")

    df_filled.to_csv(rf'D:\Modelling\demandcast\demandcast\data\processing\{code}_nsmo_filled_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.csv')
    df_filled.to_parquet(rf'D:\Modelling\demandcast\demandcast\data\processing\{code}_nsmo_filled_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.parquet')

    return df_filled

#Get the df with only missing intervals
def extract_nan_load_data(df_filled: pd.DataFrame, code: str = 'VNM') -> pd.DataFrame:
    nan_load_data = df_filled[df_filled['Load (MW)'].isna()]

    #Export the df to merge with feature dataset later
    nan_load_data.to_csv(rf'D:\Modelling\demandcast\demandcast\data\processing\{code}_nan_load_data_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.csv')
    nan_load_data.to_parquet(rf'D:\Modelling\demandcast\demandcast\data\processing\{code}_nan_load_data_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.parquet')

    return nan_load_data

#Merge the feature data of missing months
#The input file path should be the assembled dataset from df_filled (Obtain the feature dataset by running forecast)
#The input df is the nan_load_df
#The output is the feature data of the missing months only

def manual_assemble_data(file_path: str, nan_load_df: pd.DataFrame, code: str = 'VNM') -> pd.DataFrame:
    feature_df = pd.read_parquet(file_path).set_index('Time (UTC)')
    df_missing_features = feature_df.loc[nan_load_df.index]
    df_missing_features = df_missing_features.reset_index()
    df_missing_features.to_parquet(rf'D:\Modelling\demandcast\demandcast\data\processing\assembled_data_for_backcast_{code.lower()}_nsmo_{dt.datetime.now().strftime("%Y%m%d")}_{dt.datetime.now().strftime("%H%M%S")}.parquet')
    df_missing_features.to_csv(rf'D:\Modelling\demandcast\demandcast\data\processing\assembled_data_for_backcast_{code.lower()}_nsmo_{dt.datetime.now().strftime("%Y%m%d")}_{dt.datetime.now().strftime("%H%M%S")}.csv')
    return df_missing_features

#When having the feature data of the missing months, we run the forecast
#After that, we have to merge it with the original conformed dataset.
#The output dataset is the full continuous historical load profiles

def merge_backfill_data(file_path: str, df_conformed: pd.DataFrame, code: str = 'VNM') -> pd.DataFrame:
    backfill_df = pd.read_parquet(file_path)
    backfill_df = backfill_df[['Time (UTC)','Forecast Load (MW)']]
    backfill_df = backfill_df.set_index('Time (UTC)')
    backfill_df.columns = ['Load (MW)']
    backfill_df.index.name = 'Time (UTC)'

    merged_df = pd.concat(
        [df_conformed, backfill_df])
    merged_df = export_electricity_demand(merged_df, code)
    return merged_df


if __name__ == "__main__":
    start_date='2020-09-01'
    end_date='2026-08-31'
    df = convert_response_df(start_date = start_date, end_date= end_date)

    for code in CODES_OF_NODES:
        df_conformed=conform_retrieval(df, code)
        export_electricity_demand(df_conformed, code)

        #The backcast steps need the missing intervals, the assembled feature data and the forecast results of each node
        #df_filled = fill_missing_intervals(df_conformed, code)
        #nan_load_data = extract_nan_load_data(df_filled, code)

    #df_missing_features = manual_assemble_data(r'D:\Modelling\demandcast\demandcast\data\assembled\assembled_data_for_forecasting_20260603_150407.parquet',nan_load_data, code)
    #print(df_missing_features)
    #merged_df = merge_backfill_data(file_path=r'D:\Modelling\demandcast\demandcast\ml_models\results\forecasts\with_xgboost_model_20260603_150331\using_assembled_data_for_backcast_vnm_nsmo_20260603_152047\all_raw_normalized_20260603_152127.parquet',df_conformed=df_conformed, code=code)
    #print(merged_df[merged_df['Load (MW)'].isnull()])
