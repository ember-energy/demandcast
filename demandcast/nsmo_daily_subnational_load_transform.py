import pandas as pd
import json 
import pickle 
import datetime 
import os 

start_date='2017-12-01'
end_date='2026-02-01'
cutoff_date = '2020-08-31'

viet_to_eng={
    'thoiGian': 'time',
    'congSuatMB':'capacity-north-mw',
    'congSuatMT':'capacity-central-mw',
    'congSuatMN':'capacity-south-mw',
    'congSuatHT':'capacity-load-total-mw'
}

target_date_list = pd.date_range(start=start_date, end=end_date, freq='MS').strftime('%Y-%m-%d').tolist()

load_data=[]

for i in target_date_list: 
    print(f'Currently processing date {i}') 
    file_path=rf"C:\ember-data-processing\tmp_local\storage_assets\sources\nsmo_load_daily_subnational_raw\GetChartPhuTaiVM-{i}.pickle"
    
    if not os.path.exists(file_path):
        print(f'File missing for date {i}')
        continue
    
    try:
        with open(rf"C:\ember-data-processing\tmp_local\storage_assets\sources\nsmo_load_daily_subnational_raw\GetChartPhuTaiVM-{i}.pickle",'rb') as f: 
            data_raw=pickle.load(f)
            print(f'Successfully open : {i}')   

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
load_data_df.set_index('time')
load_data_df[['capacity-north-mw','capacity-central-mw','capacity-south-mw','capacity-load-total-mw']]=load_data_df[['capacity-north-mw','capacity-central-mw','capacity-south-mw','capacity-load-total-mw']].apply(pd.to_numeric, errors='coerce')

#Split the load_data_df into two to fix the index error 
df_before = load_data_df.loc[:cutoff_date].set_index('time')
df_after = load_data_df.loc[cutoff_date:].set_index('time')

#For data before 1 Sep 2020, shift the time to 30-minutes earlier, and then convert them into hourly index instead of 30-minute intervals
groups = df_before.groupby(df_before.index.date)
hour_offsets = groups.cumcount()
df_before.index = df_before.index.normalize() + pd.to_timedelta(hour_offsets, unit='h')


#For data after 1 Sep 2020, only shift the time to 30-minutes earlier. Then resample to hourly value by averaging
df_after.index = df_after.index - pd.Timedelta(minutes = 30)
df_after = df_after.resample('h').mean()

df_final = pd.concat([df_before, df_after]).reset_index()
df_final.rename(columns= {'index':'time'},inplace = True)

df_final.to_csv(f'load-curve-in-mw-vietnam-{start_date}-{end_date}.csv')
print(df_final) 
print(df_final.columns)
print(df_final.info())
