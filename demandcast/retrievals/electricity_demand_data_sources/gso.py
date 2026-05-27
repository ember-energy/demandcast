import logging 
import pandas as pd 

#Fetch the data from the manual download from GSO 

folder_path = 'D:/Modelling/demandcast/demandcast/data/electricity_demand/2026-05-25/MYS_gso'

file_path_parquet = 'D:/Modelling/demandcast/demandcast/data/electricity_demand/2026-05-25/MYS_gso_raw.parquet'
file_path_csv = 'D:/Modelling/demandcast/demandcast/data/electricity_demand/2026-05-25/MYS_gso_raw.csv'

df = pd.read_parquet(file_path_parquet)
print(f'Original 10-minute row count: {len(df)}')

df_hourly = df.resample('1h', label = 'right', closed = 'right').mean()

print(f'New compress hourly row count: {len(df_hourly)}')

if "Load (MW)" in df_hourly.columns:
    df_hourly['Load (MW)'] = df_hourly['Load (MW)'].interpolate(method='linear')

missing_count = df_hourly['Load (MW)'].isna().sum()
print(f"Found {missing_count} lingering NaN values in Load (MW).")
df_hourly = df_hourly.dropna(subset=['Load (MW)'])

df_hourly.to_parquet(folder_path + '.parquet')
df_hourly.to_csv(folder_path + '.csv')

print(df_hourly.info)