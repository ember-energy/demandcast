# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module is used to download historical electricity demand per
    capita data from Ember.

    Since July 2026, Ember publishes its yearly data in a new format
    (one row per area, year, and electricity source, with the metrics
    as columns), and the former long-format file with the "Demand per
    capita" variable is no longer updated. The new file only has the
    total electricity demand (TWh), so the demand per capita is
    calculated by dividing it by the population of the World Bank. The
    result is in kWh per person.

    Source: https://ember-energy.org/data/yearly-electricity-data/
"""

import logging

import pandas

import retrievals.socio_economic_data_sources.world_bank as world_bank

# Define the URL of the yearly electricity data of Ember.
URL = (
    "https://files.ember-energy.org/public-downloads/generation/outputs/"
    "release_generation_yearly_global.csv"
)


def download_electricity_demand() -> pandas.DataFrame:
    """
    Download historical electricity demand from Ember.

    Returns
    -------
    electricity_demand : pandas.DataFrame
        The electricity demand in TWh, with the ISO Alpha-3 codes of
        the countries as index and the years as columns.
    """
    logging.info("Downloading electricity demand data from Ember.")

    # Download the yearly electricity dataset from Ember.
    electricity_dataset = pandas.read_csv(URL, low_memory=False)

    # Check that the file has the expected format.
    expected_columns = {"ISO 3 code", "Year", "Electricity source", "Generation (TWh)"}
    missing_columns = expected_columns - set(electricity_dataset.columns)
    if missing_columns:
        raise ValueError(
            f"The Ember file {URL} does not have the columns "
            f"{sorted(missing_columns)}. Its format may have changed."
        )

    # Extract the electricity demand of the countries. The demand is
    # stored in the generation column of the "Demand" source. Regions
    # (e.g., ASEAN) have no ISO Alpha-3 code.
    electricity_demand = electricity_dataset[
        (electricity_dataset["Electricity source"] == "Demand")
        & electricity_dataset["ISO 3 code"].notna()
    ]

    # Pivot the table to have years as columns and country codes as
    # index.
    electricity_demand = electricity_demand.pivot_table(
        index="ISO 3 code", columns="Year", values="Generation (TWh)"
    )

    # Convert to the correct data types.
    electricity_demand.columns = electricity_demand.columns.astype(int)
    electricity_demand.index = electricity_demand.index.astype(str)
    electricity_demand = electricity_demand.astype(float)

    # Rename the index and columns.
    electricity_demand.index.name = "Country Code"
    electricity_demand.columns.name = "Year"

    return electricity_demand.dropna(how="all")


def download_electricity_demand_per_capita() -> pandas.DataFrame:
    """
    Download historical electricity demand per capita from Ember.

    The electricity demand of Ember is divided by the population of the
    World Bank.

    Returns
    -------
    electricity_demand_per_capita : pandas.DataFrame
        The electricity demand per capita in kWh, with the ISO Alpha-3
        codes of the countries as index and the years as columns.
    """
    electricity_demand = download_electricity_demand()
    population = world_bank.download("population")

    # Calculate the demand per capita, converting TWh to kWh. The result
    # is NaN where the population is not available.
    electricity_demand_per_capita = (
        electricity_demand * 1e9 / population
    ).reindex(index=electricity_demand.index, columns=electricity_demand.columns)

    # Rename the index and columns.
    electricity_demand_per_capita.index.name = "Country Code"
    electricity_demand_per_capita.columns.name = "Year"

    # Remove rows with all NaN values.
    electricity_demand_per_capita = electricity_demand_per_capita.dropna(
        how="all"
    )

    logging.info(
        "Electricity demand per capita data from Ember has been downloaded "
        "successfully."
    )

    return electricity_demand_per_capita
