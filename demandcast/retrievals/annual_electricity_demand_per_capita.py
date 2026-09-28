# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module includes functions to download and extract historical
    annual electricity demand per capita data from Ember and the World
    Bank, and to calculate future annual electricity demand per capita
    based on growth rates from the IAMC scenarios. The electricity
    demand data is extracted for the countries and subdivisions of
    interest and saved into CSV and Parquet files.

    For subdivisions with regional gross power generation data (the
    grids of the Philippines, from the DOE), the historical annual
    electricity demand per capita is calculated by dividing the
    regional gross power generation by the regional population. For
    the years before the regional data starts, and for other
    subdivisions, the national value is used.
"""

import logging
import os

import pandas
import utils.config
import utils.entities
import utils.scenarios
import utils.time_series
from tqdm import tqdm

import retrievals.population
from retrievals.socio_economic_data_sources import doe_philippines
import retrievals.socio_economic_data_sources.ember as ember
import retrievals.socio_economic_data_sources.iiasa as iiasa
import retrievals.socio_economic_data_sources.world_bank as world_bank


def get_available_scenarios() -> list[str]:
    """
    Get the available future scenarios.

    Returns
    -------
    list[str]
        The available IAMC scenarios.
    """
    return [
        "SSP1-Baseline",
        "SSP1-19",
        "SSP1-26",
        "SSP1-34",
        "SSP1-45",
        "SSP2-Baseline",
        "SSP2-19",
        "SSP2-26",
        "SSP2-34",
        "SSP2-45",
        "SSP2-60",
        "SSP3-Baseline",
        "SSP3-34",
        "SSP3-45",
        "SSP3-60",
        "SSP4-Baseline",
        "SSP4-26",
        "SSP4-34",
        "SSP4-45",
        "SSP4-60",
        "SSP5-Baseline",
        "SSP5-19",
        "SSP5-26",
        "SSP5-34",
        "SSP5-45",
        "SSP5-60",
    ]


def get_historical_data() -> pandas.DataFrame:
    """
    Get historical electricity demand per capita data.

    Returns
    -------
    pandas.DataFrame
        The historical electricity demand per capita data.
    """
    # Download the electricity demand per capita from Ember.
    ember_electricity_demand_per_capita = (
        ember.download_electricity_demand_per_capita()
    )

    # Download the electricity demand per capita from the World Bank.
    world_bank_electricity_demand_per_capita = world_bank.download(
        "electricity_demand_per_capita"
    )

    # Merge the two datasets by averaging them.
    electricity_demand_per_capita = (
        world_bank_electricity_demand_per_capita
        + ember_electricity_demand_per_capita
    ) / 2

    # Where the combined DataFrame is NaN because one of the datasets is
    # missing, use the other dataset.
    return electricity_demand_per_capita.fillna(
        world_bank_electricity_demand_per_capita
    ).fillna(ember_electricity_demand_per_capita)


def get_regional_codes() -> list[str]:
    """
    (MANUAL SOURCE FOR PHL SUBNATIONALS)
    Get the codes of the subdivisions with regional data.

    Returns
    -------
    list[str]
        The codes of the subdivisions for which regional gross power
        generation data is available.
    """
    return [code for code in doe_philippines.get_codes() if "_" in code]


def get_regional_historical_data(
    regional_gross_generation: pandas.DataFrame,
    code: str,
    global_historical_population: pandas.DataFrame | None = None,
) -> pandas.Series:
    """
    Get the historical electricity demand per capita of a subdivision.

    This function divides the regional gross power generation by the
    regional population of the subdivision.

    Parameters
    ----------
    regional_gross_generation : pandas.DataFrame
        The regional gross power generation in MWh, with the codes as
        index and the years as columns.
    code : str
        The code of the subdivision of interest.
    global_historical_population : pandas.DataFrame | None, optional
        The global historical population data from the World Bank.

    Returns
    -------
    pandas.Series
        The historical electricity demand per capita in kWh.
    """
    # Get the gross power generation of the subdivision.
    gross_generation = regional_gross_generation.loc[
        code
    ].dropna()

    # Get the population of the subdivision for the same years.
    population = retrievals.population.get_historical_population(
        code,
        gross_generation.index.tolist(),
        global_historical_population,
    )

    # Calculate the electricity demand per capita, converting MWh to
    # kWh.
    return (gross_generation * 1000 / population).dropna()


def run_data_retrieval(
    code: str | None,
    file: str | None,
    year: int | None,
    start_year: int | None,
    end_year: int | None,
    scenario: str | None,
) -> None:
    """
    Download and extract annual electricity demand per capita.

    This function downloads historical electricity demand per capita
    data from Ember and the World Bank, extracts the electricity data
    for the countries and subdivisions of interest, calculates future
    electricity demand per capita based on growth rates from the IAMC
    scenarios, and saves it into CSV and Parquet files.

    Parameters
    ----------
    code : str | None
        The code of the country or subdivision of interest.
    file : str | None
        The file path containing the codes of the countries or
        subdivisions of interest.
    year : int | None
        The year of the electricity demand per capita data to be
        retrieved.
    start_year : int | None
        The start year of the range of electricity demand per capita
        data to be retrieved.
    end_year : int | None
        The end year of the range of electricity demand per capita
        data to be retrieved.
    scenario : str | None
        The scenario of the electricity demand per capita data to be
        retrieved.
    """
    # Get the directory to store the annual electricity demand per
    # capita data.
    # Files are saved in a subfolder named after the current date.
    result_directory = utils.config.get_dated_folder(
        "annual_electricity_demand_per_capita_folder"
    )

    # Download the historical electricity demand per capita data.
    global_historical_electricity_demand_per_capita = get_historical_data()

    # Read the growth rates of future electricity demand per capita.
    global_future_electricity_demand_per_capita_growth_rates = iiasa.read(
        "annual_electricity_demand_per_capita"
    )

    # Get the list of codes of the countries and subdivisions of
    # interest.
    codes = utils.entities.check_and_get_codes_with(
        "all_data", code=code, file_path=file
    )

    # Get the available scenarios.
    available_scenarios = get_available_scenarios()

    # If any subdivision has regional data, download the regional
    # gross power generation and the population data.
    if set(codes) & set(get_regional_codes()):
        regional_gross_generation = (
            doe_philippines.download_gross_generation()
        )
        global_historical_population = world_bank.download("population")

    # Loop over the countries and subdivisions.
    for code in tqdm(codes, desc="Countries and subdivisions"):
        # Get the ISO Alpha-3 code of the country itself or the country
        # to which the subdivision belongs.
        iso_alpha_3_code = code.split("_")[0]

        # Get the time zone of the country or subdivision.
        time_zone = utils.entities.get_time_zone(code)

        # Extract the electricity data for the country.
        historical_electricity_demand_per_capita = (
            global_historical_electricity_demand_per_capita.loc[
                iso_alpha_3_code
            ]
        ).dropna()

        if code in get_regional_codes():
            # Calculate the electricity demand per capita from the
            # regional gross power generation and population.
            logging.info(
                f"Using regional gross power generation data for {code}."
            )
            regional_electricity_demand_per_capita = (
                get_regional_historical_data(
                    regional_gross_generation,
                    code,
                    global_historical_population,
                )
            )

            # For the years before the regional data starts, fall back
            # to the national electricity demand per capita, scaled by
            # the ratio between the regional and national values in the
            # first year of the regional data to avoid a discontinuity.
            first_regional_year = (
                regional_electricity_demand_per_capita.index.min()
            )
            ratio = (
                regional_electricity_demand_per_capita.loc[first_regional_year]
                / historical_electricity_demand_per_capita.loc[
                    first_regional_year
                ]
            )
            earlier_national_electricity_demand_per_capita = (
                historical_electricity_demand_per_capita.loc[
                    historical_electricity_demand_per_capita.index
                    < first_regional_year
                ]
            )
            historical_electricity_demand_per_capita = pandas.concat(
                [
                    earlier_national_electricity_demand_per_capita * ratio,
                    regional_electricity_demand_per_capita,
                ]
            )

        # Get the years of available historical data.
        available_historical_years = (
            historical_electricity_demand_per_capita.index.tolist()
        )

        # Get the years of available future data.
        available_future_years = list(
            range(max(available_historical_years) + 1, 2101)
        )

        # Get the list of year and scenario combinations.
        year_scenario_list = (
            utils.scenarios.get_year_and_scenario_combinations(
                year,
                start_year,
                end_year,
                available_historical_years,
                available_future_years,
                scenario,
                available_scenarios,
            )
        )

        # Define the file path of the electricity demand per capita
        # data of the country or subdivision.
        file_path_without_ext = os.path.join(result_directory, code)

        # Get the selcted historical years.
        selected_historical_years = list(
            set(
                [
                    year
                    for year, scenario in year_scenario_list
                    if scenario is None
                ]
            )
        )

        # Get the selected future years.
        selected_future_years = list(
            set(
                [
                    year
                    for year, scenario in year_scenario_list
                    if scenario is not None
                ]
            )
        )

        # Get the selected scenarios.
        selected_scenarios = list(
            set(
                [
                    scenario
                    for __, scenario in year_scenario_list
                    if scenario is not None
                ]
            )
        )

        if selected_historical_years:
            if not os.path.exists(
                file_path_without_ext + ".parquet"
            ) or not os.path.exists(file_path_without_ext + ".csv"):
                logging.info(
                    f"Extracting historical annual electricity per capita data "
                    f"for {code}."
                )

                # Extract the respective electricity demand per capita.
                selected_historical_electricity_demand_per_capita = (
                    historical_electricity_demand_per_capita[
                        historical_electricity_demand_per_capita.index.isin(
                            selected_historical_years
                        )
                    ]
                )

                # Convert the historical electricity demand per capita
                # data from yearly to hourly values.
                selected_historical_electricity_demand_per_capita = (
                    utils.time_series.convert_from_yearly_to_hourly(
                        selected_historical_electricity_demand_per_capita,
                        time_zone,
                    )
                )

                # Clean the time series.
                selected_historical_electricity_demand_per_capita = (
                    utils.time_series.clean_data(
                        selected_historical_electricity_demand_per_capita,
                        "Annual electricity demand per capita (kWh)",
                    )
                )

                # Save the electricity demand per capita data to parquet
                # and CSV files.
                selected_historical_electricity_demand_per_capita.to_frame().to_parquet(
                    file_path_without_ext + ".parquet"
                )
                selected_historical_electricity_demand_per_capita.to_csv(
                    file_path_without_ext + ".csv",
                )

                logging.info(
                    f"Historical annual electricity per capita data for {code} "
                    "has been extracted and saved successfully."
                )

            else:
                logging.info(
                    f"Historical annual electricity per capita data of {code} "
                    "already exists. Skipping retrieval."
                )

        if selected_future_years:
            for scenario in selected_scenarios:
                if not os.path.exists(
                    f"{file_path_without_ext}_"
                    f"{scenario.replace('-', '_')}.parquet"
                ) or not os.path.exists(
                    f"{file_path_without_ext}_{scenario.replace('-', '_')}.csv"
                ):
                    logging.info(
                        f"Extracting future annual electricity demand per "
                        f"capita data for {code} and {scenario}."
                    )

                    # Get the last year and value of the historical
                    # electricity demand per capita.
                    last_historical_year = max(available_historical_years)
                    last_historical_value = (
                        historical_electricity_demand_per_capita.loc[
                            last_historical_year
                        ]
                    )

                    # Calculate the future electricity demand per
                    # capita.
                    future_electricity_demand_per_capita = iiasa.extrapolate(
                        global_future_electricity_demand_per_capita_growth_rates,
                        iso_alpha_3_code,
                        scenario,
                        last_historical_value,
                        last_historical_year,
                        available_future_years,
                    )

                    # Extract the electricity demand per capita for
                    # the selected future years.
                    selected_future_electricity_demand_per_capita = (
                        future_electricity_demand_per_capita[
                            future_electricity_demand_per_capita.index.isin(
                                selected_future_years
                            )
                        ]
                    )

                    # Convert the future electricity demand per capita
                    # data from yearly to hourly values.
                    selected_future_electricity_demand_per_capita = (
                        utils.time_series.convert_from_yearly_to_hourly(
                            selected_future_electricity_demand_per_capita,
                            time_zone,
                        )
                    )

                    # Clean the time series.
                    selected_future_electricity_demand_per_capita = (
                        utils.time_series.clean_data(
                            selected_future_electricity_demand_per_capita,
                            "Annual electricity demand per capita (kWh)",
                        )
                    )

                    # Save the electricity demand per capita data to
                    # parquet and CSV files.
                    selected_future_electricity_demand_per_capita.to_frame().to_parquet(
                        f"{file_path_without_ext}_{scenario.replace('-', '_')}.parquet"
                    )
                    selected_future_electricity_demand_per_capita.to_csv(
                        f"{file_path_without_ext}_{scenario.replace('-', '_')}.csv",
                    )

                    logging.info(
                        f"Future annual electricity demand per capita data "
                        f"for {code} and {scenario} has been extracted "
                        "and saved successfully."
                    )

                else:
                    logging.info(
                        f"Future annual electricity demand per capita data "
                        f"for {code} and {scenario} already exists. "
                        "Skipping retrieval."
                    )
