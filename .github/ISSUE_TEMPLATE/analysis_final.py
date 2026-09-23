import pandas as pd
import datetime as dt
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import os


def load_data(type: str, country_code: str) -> pd.DataFrame:
    """Helper to load Parquet or CSV file"""
    #Define the base directory for raw data to compare
    RAW_DATA_DIR = r'D:\Modelling\demandcast\demandcast\data\assembled_raw_for_compare'

    #Define the forecast result directory 
    FORECAST_DIR = r'D:\Modelling\demandcast\demandcast\ml_models\results\backcasts'

    if type == 'raw':
        for filename in os.listdir(RAW_DATA_DIR):
            if filename.endswith(f'{country_code}_raw.csv') or filename.endswith(f'{country_code}_raw.parquet'):
                full_path = os.path.join(RAW_DATA_DIR, filename)
    elif type == "forecast":
        for filename in os.listdir(FORECAST_DIR):
            if filename.endswith(f'{country_code}_raw.csv') or filename.endswith(f'{country_code}_raw.parquet'):
                full_path = os.path.join(FORECAST_DIR, filename)
    else:
        raise ValueError("The 'label' argument must be either 'Load' or 'Fraction'.")
    
    print(f'Loading {type} data from path: {full_path}')

    if full_path.endswith('.parquet'):
        return pd.read_parquet(full_path)
    return pd.read_csv(full_path)
            

def transform_df(df: pd.DataFrame, entity: str, start_date: str, end_date: str, timezone: str) -> pd.DataFrame:
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    
    if 'Entity code' in df.columns:
        df = df[df['Entity code'] == entity]
    else:
        df['Entity code'] = entity
    
    df['Time (UTC)'] = pd.to_datetime(df['Time (UTC)'])
    df['Time (LOCAL)'] = df['Time (UTC)'].dt.tz_localize('UTC').dt.tz_convert(f'Asia/{timezone}').dt.tz_localize(None)


    df = df[df['Time (LOCAL)'].between(start, end)]

    # If the dataframe is the training data
    if "Load (fraction of annual total)" in df.columns:
        df = df[['Time (UTC)', 'Time (LOCAL)', 'Entity code', 'Load (MW)', 'Load (fraction of annual total)']]
    # If the dataframe is the result data
    elif "Normalized forecast load fraction (%)" in df.columns:
        df = df[['Time (UTC)', 'Time (LOCAL)','Entity code', 'Normalized forecast load fraction (%)', 'Forecast Load (MW)']]
    else: 
        print('Dataframe not valid.')
    
    return df

def combine_df(df1: pd.DataFrame, df2: pd.DataFrame, entity: str, start_date: str, end_date: str, timezone: str) -> pd.DataFrame:
    df1 = transform_df(df1, entity, start_date, end_date, timezone)
    df2 = transform_df(df2, entity, start_date, end_date, timezone)

    combined_df = pd.merge(df1, df2, on=['Time (UTC)', 'Time (LOCAL)', 'Entity code'], how='left')
    combined_df = combined_df.dropna()
    combined_df['Load (MW)'] = pd.to_numeric(combined_df['Load (MW)'])
    combined_df['Forecast Load (MW)'] = pd.to_numeric(combined_df['Forecast Load (MW)'])
    combined_df = combined_df.reset_index(drop=True)

    return combined_df

def create_compare_graph(df: pd.DataFrame, label: str):
    if label.lower() == 'load':
        actual_col = 'Load (MW)'
        forecast_col = 'Forecast Load (MW)'
        y_axis_label = 'MW'
        file_prefix = 'Actual_vs_Forecast'
    elif label.lower() == 'fraction':
        actual_col = 'Load (fraction of annual total)'
        forecast_col = 'Normalized forecast load fraction (%)'
        y_axis_label = 'Fraction'
        file_prefix = 'Actual_vs_Forecast_Fraction'
    else:
        raise ValueError("The 'label' argument must be either 'Load' or 'Fraction'.")
    
    df['Year'] = df['Time (LOCAL)'].dt.year
    years = sorted(df['Year'].unique())
    print(years)

    fig, axes = plt.subplots(nrows=len(years), ncols=1, figsize=(15, 6 * len(years)), sharex=False)
    if len(years) == 1:
        axes = [axes]

    entity = df['Entity code'].unique().item()

    for i, year in enumerate(years):
        # Filter data for the specific year
        yearly_data = df[df['Year'] == year]
        
        # Plot Actual Load (Blue)
        axes[i].plot(yearly_data['Time (LOCAL)'], yearly_data[actual_col], 
                    label=f'Actual {label}', color='#1f77b4', alpha=0.8, linewidth=1)
        
        # Plot Forecast Load (Red/Orange)
        axes[i].plot(yearly_data['Time (LOCAL)'], yearly_data[forecast_col], 
                    label=f'Forecast {label}', color='#ff7f0e', alpha=0.7, linewidth=1)
        
        # Error metrics
        if label.lower() == 'fraction':
            y_true = yearly_data['Load (fraction of annual total)']
            y_pred = yearly_data['Normalized forecast load fraction (%)']

            # Calculations
            mae = mean_absolute_error(y_true, y_pred)
            mse = mean_squared_error(y_true, y_pred)
            rmse = np.sqrt(mse) 
            mape = mean_absolute_percentage_error(y_true, y_pred)
            r2 = r2_score(y_true, y_pred)   

            # Format the text
            metrics_text = (f"MAE: {mae:.2e}\n"
                            f"MSE: {mse:.2e}\n"
                            f"RMSE: {rmse:.2e}\n"
                            f"MAPE: {mape * 100:.2f}%\n"
                            f"R²: {r2:.4f}")

            axes[i].text(0.02, 0.95, metrics_text, transform=axes[i].transAxes, 
                        fontsize=10, verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor='gray'))

        # Formatting
        axes[i].set_title(f'{entity} Actual vs Forecast {label} - {year}', fontsize=14, fontweight='bold')
        axes[i].set_ylabel(f'{y_axis_label}', fontsize=12)
        axes[i].legend(loc='upper right')
        axes[i].grid(True, linestyle='--', alpha=0.5)

    # Adjust layout to prevent overlapping text
    plt.tight_layout()
    # Save the high-resolution image to your folder 
    time_current = datetime.now().strftime('%Y%m%d-%H%M%S')
    output_path = rf"D:\Modelling\demandcast\demandcast\analysis\{file_prefix}_{entity}_{time_current}.png"
    plt.savefig(output_path, dpi=300)
    print(f"Graph saved to {output_path}")
    plt.show()

def analyze_forecast_vs_actual(
    type: str,
    entity_code: str,
    timezone_name: str,
    start_date: str = '2025-01-01',
    end_date: str = '2026-01-01',
    plot_label: str = 'load'
):
    """
    Main function to read forecast and actual data, combine them, and plot a comparison graph.
    """
    df_results = load_data(type = 'forecast',country_code = entity_code)
    
    df_train = load_data(type = 'raw',country_code = entity_code)
    
    print("Combining and transforming data...")
    df_combined = combine_df(df_results, df_train, entity_code, start_date, end_date, timezone_name)
    
    if df_combined.empty:
        print("Warning: The combined DataFrame is empty! Please check the date ranges and entity codes.")
        return
        
    print("Generating plot...")
    create_compare_graph(df_combined, label=plot_label)


if __name__ == "__main__":
    # Example usage block
    forecast_file = r'D:\Modelling\demandcast\demandcast\ml_models\results\forecasts\with_xgboost_model_20260603_165542\using_assembled_data_for_forecasting_20260603_165630\all_raw_normalized_20260603_165653.parquet'
    actual_file = r'D:\Modelling\demandcast\demandcast\data\assembled_raw_for_compare\MYS_raw.csv'
    
    analyze_forecast_vs_actual(
        file_path_forecast=forecast_file,
        file_path_actual=actual_file,
        entity_code='MYS',
        timezone_name='Singapore',
        start_date='2025-01-01',
        end_date='2026-01-01',
        plot_label='fraction'
    )