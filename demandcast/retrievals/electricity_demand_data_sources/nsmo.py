import pandas as pd
import json 
import pickle 
import datetime as dt
import os 

viet_to_eng={
    'thoiGian': 'time',
    'congSuatMB':'capacity-north-mw',
    'congSuatMT':'capacity-central-mw',
    'congSuatMN':'capacity-south-mw',
    'congSuatHT':'capacity-load-total-mw'
}



def create_date_range(start_date: str,end_date:str) -> list:
    return pd.date_range(start=start_date, end=end_date, freq='MS').strftime('%Y-%m-%d').tolist()

def process_time_shifts(group:pd.DataFrame) -> pd.DataFrame:
    is_after_cutoff = group.name

    if is_after_cutoff:
        group.index = group.index - pd.Timedelta(minutes = 30)
        return group.resample('h').mean()
    else:
        daily_groups = group.groupby(group.index.date)
        hour_offsets = daily_groups.cumcount()
        group.index = group.index.normalize() + pd.to_timedelta(hour_offsets, unit='h')
        return group

def convert_response_df(start_date: str, end_date:str) -> pd.DataFrame:
    load_data=[]
    cutoff_date = '2020-08-31'
    date_range = pd.date_range(start=start_date, end=end_date, freq='MS').strftime('%Y-%m-%d').tolist()

    for i in date_range:
        file_path = rf"D:\Data\ember-data-processing\tmp_local\storage_assets\sources\nsmo_load_daily_subnational_raw\GetChartPhuTaiVM-{i}.pickle"

        if not os.path.exists(file_path):
            print(f'File missing for date {i}.')
            continue

        try:
            with open(file_path, 'rb') as f:
                data_raw = pickle.load(f)

            for k in data_raw.keys():
                if pd.Timestamp(k) < pd.to_datetime('today'):
                    if not data_raw[pd.Timestamp(k)].json().get('result').get('data').get('phuTais'):
                        print(f'Skipping {k} because the load list is empty')
                        continue    

                    load_profile=data_raw[pd.Timestamp(k)].json().get('result').get('data').get('phuTais')
                    load_data.append(load_profile)
                else: 
                    continue
        except Exception as e:
            print(f'Error with file for date {i}: {e}')


    load_data=[item for sublist in load_data for item in sublist]
    load_data_df=pd.DataFrame(load_data)

    load_data_df.columns=load_data_df.columns.map(viet_to_eng)
    load_data_df['time']=pd.to_datetime(load_data_df['time'].str.replace('T'," "))
    load_data_df = load_data_df.set_index('time')
    cols_to_numeric = ['capacity-north-mw', 'capacity-central-mw', 'capacity-south-mw', 'capacity-load-total-mw']
    load_data_df[cols_to_numeric]=load_data_df[cols_to_numeric].apply(pd.to_numeric, errors='coerce')

    df_final = load_data_df.groupby(load_data_df.index > cutoff_date, group_keys=False).apply(process_time_shifts)

    df_final = df_final.reset_index().rename(columns= {'index':'time'})

    return df_final

def conform_retrieval(df: pd.DataFrame) -> pd.DataFrame:
    df['Time (UTC)'] = df['time'].dt.tz_localize('Asia/Bangkok').dt.tz_convert('UTC').dt.tz_localize(None)
    df['Load (MW)'] = df['capacity-load-total-mw']

    df = df[['Time (UTC)','Load (MW)']]
    df = df.set_index('Time (UTC)')

    df.to_csv(rf'D:\Modelling\demandcast\demandcast\data\processing\VNM_nsmo_full_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.csv')
    df.to_parquet(rf'D:\Modelling\demandcast\demandcast\data\processing\VNM_nsmo_full_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.parquet')

    return df

#Create the df including nan months to assemble the feature data
def fill_missing_intervals(df_conformed: pd.DataFrame) -> pd.DataFrame:
    start_time = df_conformed.index.min()
    end_time = df_conformed.index.max()

    print(f"Analyzing data from {start_time} to {end_time}...")
    
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
    
    df_filled.to_csv(rf'D:\Modelling\demandcast\demandcast\data\processing\VNM_nsmo_filled_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.csv')
    df_filled.to_parquet(rf'D:\Modelling\demandcast\demandcast\data\processing\VNM_nsmo_filled_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.parquet')
    
    return df_filled

#Get the df with only missing intervals
def extract_nan_load_data(df_filled: pd.DataFrame) -> pd.DataFrame:
    nan_load_data = df_filled[df_filled['Load (MW)'].isna()]

    #Export the df to merge with feature dataset later
    nan_load_data.to_csv(rf'D:\Modelling\demandcast\demandcast\data\processing\nan_load_data_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.csv')
    nan_load_data.to_parquet(rf'D:\Modelling\demandcast\demandcast\data\processing\nan_load_data_{dt.datetime.now().strftime("%Y%m%d %H%M%S")}.parquet')

    return nan_load_data

#Merge the feature data of missing months 
#The input file path should be the assembled dataset from df_filled (Obtain the feature dataset by running forecast)
#The input df is the nan_load_df
#The output is the feature data of the missing months only

def manual_assemble_data(file_path: str, nan_load_df: pd.DataFrame) -> pd.DataFrame:
    feature_df = pd.read_parquet(file_path).set_index('Time (UTC)')
    df_missing_features = feature_df.loc[nan_load_df.index]
    df_missing_features = df_missing_features.reset_index()
    df_missing_features.to_parquet(rf'D:\Modelling\demandcast\demandcast\data\processing\assembled_data_for_backcast_vnm_nsmo_{dt.datetime.now().strftime("%Y%m%d")}_{dt.datetime.now().strftime("%H%M%S")}.parquet')
    df_missing_features.to_csv(rf'D:\Modelling\demandcast\demandcast\data\processing\assembled_data_for_backcast_vnm_nsmo_{dt.datetime.now().strftime("%Y%m%d")}_{dt.datetime.now().strftime("%H%M%S")}.csv')
    return df_missing_features

#When having the feature data of the missing months, we run the forecast
#After that, we have to merge it with the original conformed dataset.
#The output dataset is the full continuous historical load profiles 

def merge_backfill_data(file_path: str, df_conformed: pd.DataFrame) -> pd.DataFrame:
    backfill_df = pd.read_parquet(file_path)
    backfill_df = backfill_df[['Time (UTC)','Forecast Load (MW)']]
    backfill_df = backfill_df.set_index('Time (UTC)')
    backfill_df.columns = ['Load (MW)']
    backfill_df.index.name = 'Time (UTC)'

    merged_df = pd.concat(
        [df_conformed, backfill_df])
    merged_df.dropna(inplace=True)
    merged_df.sort_index(inplace=True)
    merged_df.to_csv(rf'D:\Modelling\demandcast\demandcast\data\electricity_demand\2026-06-01\VNM_nsmo.csv')
    merged_df.to_parquet(rf'D:\Modelling\demandcast\demandcast\data\electricity_demand\2026-06-01\VNM_nsmo.parquet')
    return merged_df


if __name__ == "__main__":
    start_date='2019-12-31'
    end_date='2025-12-31'
    df = convert_response_df(start_date = start_date, end_date= end_date)
    df_conformed=conform_retrieval(df)
    df_filled = fill_missing_intervals(df_conformed)
    nan_load_data = extract_nan_load_data(df_filled)
    df_missing_features = manual_assemble_data(r'D:\Modelling\demandcast\demandcast\data\assembled\assembled_data_for_forecasting_20260603_150407.parquet',nan_load_data)    
    print(df_missing_features)
    merged_df = merge_backfill_data(file_path=r'D:\Modelling\demandcast\demandcast\ml_models\results\forecasts\with_xgboost_model_20260603_150331\using_assembled_data_for_backcast_vnm_nsmo_20260603_152047\all_raw_normalized_20260603_152127.parquet',df_conformed=df_conformed)
    print(merged_df[merged_df['Load (MW)'].isnull()])

          

