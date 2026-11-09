# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    1. Default setting (from demandcast)

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

    2. For specific scenarios

    2.1. Philippines

    Historical gross power generation data by subdivisions are taken from the Philippines' Department of Energy (DOE) from 2003 - 2025.
    Historical population by subdivisions are taken from the Philippines Statistics Agency (PSA) from 2000 - 2024. 

    For the future, the Philippines and its grids do not use the growth
    rates of the IAMC scenarios. Instead, the projected annual
    electricity sales of the Philippine Energy Plan (PEP) are converted
    to annual electricity demand with the grid-load factors, and divided
    by the projected population of the PSA. The scenarios are named
    after the PEP scenario (REF or CES) and the PSA population scenario
    (PSA1, PSA2, or PSA3), e.g., PEP-REF-PSA2. Use the same PSA
    scenario for the population when assembling the data, so that the
    annual demand is retrieved.

    2.2. Singapore

    Historical data uses the default setting (average of Ember and the
    World Bank, up to the last historical year).

    For the future, Singapore follows:
    - 2026 - 2034: the projected generation (GWh) of the Energy Market
      Authority (EMA), "Electricity Demand and Supply Outlook 2025",
      page 5, Table 1b, to meet either:
      - the Base Electricity Demand Forecast (Base EDF): EMA-BASE-..., or
      - the Upper-bound EDF: EMA-UPPER-...
      It is divided by the projected IIASA SSP population.
    - 2035 onwards: the value of 2034 is extrapolated with the growth
      rates of the IAMC scenario.
    - Any year between the last historical year and 2026: the last
      historical value is extrapolated with the growth rates of the
      IAMC scenario.
    The scenarios are named after the EMA scenario and the IAMC
    scenario, e.g., EMA-BASE-SSP2-45 or EMA-UPPER-SSP2-45. The SSP of
    the IAMC scenario is also used for the population, so use the same
    SSP for the population when assembling the data
    (scenario_for_population: SSP2).

    2.3. Thailand

    Historical data of Thailand uses the default setting (average of
    Ember and the World Bank, up to the last historical year). For the
    regions (THA_CEN, THA_NOR, THA_NEA, THA_SOU), no regional historical
    demand is available, so the national demand of Ember (TWh) is
    multiplied by the energy share of the region in the EGAT demand of
    2025 (the same share for all historical years, see
    electricity_demand_data_sources/egat.py), and divided by the
    historical population of the region (retrievals.population: World
    Bank total x NSO shares).

    For the future, Thailand and its regions follow:
    - 2026 - 2037: the projected annual electricity demand (GWh) of the
      draft Power Development Plan 2024 (PDP2024) of the Energy Policy
      and Planning Office (EPPO), BASE case, sheet "Regional_Energy".
      The national value is used as is. The regional values (derived
      by EPPO peak shares) are scaled by the EGAT share / EPPO share of
      each region in 2025 and rescaled to add up to the national value,
      see socio_economic_data_sources/eppo_thailand.py. It is divided by
      the projected population of retrievals.population (IIASA SSP,
      scaled to the regions by the NSO shares of the latest year).
    - 2038 onwards: the value of 2037 is extrapolated with the growth
      rates of the IAMC scenario.
    - Any year between the last historical year and 2026: the last
      historical value is extrapolated with the growth rates of the
      IAMC scenario.
    The scenarios are named after the EPPO and the IAMC scenario, e.g.,
    EPPO-SSP2-45. The SSP of the IAMC scenario is also used for the
    population, so use the same SSP for the population when assembling
    the data (scenario_for_population: SSP2).
"""

import functools
import logging
import os

import pandas
import utils.config
import utils.entities
import utils.scenarios
import utils.time_series
from tqdm import tqdm

import retrievals.population
from retrievals.socio_economic_data_sources import (
    doe_philippines,
    ema_singapore,
    eppo_thailand,
    pep_philippines,
    psa_philippines,
)
import retrievals.socio_economic_data_sources.ember as ember
import retrievals.socio_economic_data_sources.iiasa as iiasa
import retrievals.socio_economic_data_sources.world_bank as world_bank

# Define the first year of the EMA projection used for Singapore.
FIRST_YEAR_OF_EMA_PROJECTION = 2026

# Define the first and last years of the EPPO projection used for
# Thailand and its regions.
FIRST_YEAR_OF_EPPO_PROJECTION = 2026
LAST_YEAR_OF_EPPO_PROJECTION = 2037


def get_available_scenarios() -> list[str]:
    """
    Get the available future scenarios.

    Returns
    -------
    list[str]
        The available IAMC scenarios and the country-specific scenarios.
    """
    return (
        get_iamc_scenarios()
        + get_pep_scenarios()
        + get_ema_scenarios()
        + get_eppo_scenarios()
    )


def get_iamc_scenarios() -> list[str]:
    """
    Get the IAMC scenarios.

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


def get_eppo_scenarios() -> list[str]:
    """
    Get the scenarios for Thailand based on the EPPO projection.

    Returns
    -------
    list[str]
        The IAMC scenarios prefixed with EPPO. The IAMC scenario gives
        the growth rates after the EPPO projection, and its SSP the
        population used to convert the demand to demand per capita.
    """
    return [f"EPPO-{scenario}" for scenario in get_iamc_scenarios()]


def uses_eppo_projection(code: str) -> bool:
    """
    Check if the future demand of a code comes from the EPPO.

    Parameters
    ----------
    code : str
        The code of the country or subdivision of interest.

    Returns
    -------
    bool
        True for Thailand and its regions.
    """
    return code in eppo_thailand.get_codes()


def get_future_data_from_eppo(
    code: str,
    scenario: str,
    growth_rates: pandas.DataFrame,
    last_historical_value: float,
    last_historical_year: int,
) -> pandas.Series:
    """
    Get the future electricity demand per capita from the EPPO.

    The projected demand of the EPPO is divided by the projected
    population of retrievals.population from FIRST_YEAR_OF_EPPO_PROJECTION
    to LAST_YEAR_OF_EPPO_PROJECTION. Before, the last historical value is
    extrapolated with the growth rates of the IAMC scenario. After, the
    value of LAST_YEAR_OF_EPPO_PROJECTION is extrapolated with them.

    Parameters
    ----------
    code : str
        The code of Thailand or one of its regions.
    scenario : str
        The scenario, with the format EPPO-{IAMC scenario}.
    growth_rates : pandas.DataFrame
        The IIASA growth rates of electricity demand per capita.
    last_historical_value : float
        The last historical electricity demand per capita in kWh.
    last_historical_year : int
        The last historical year.

    Returns
    -------
    pandas.Series
        The future electricity demand per capita in kWh, with the years
        from the year after the last historical year to 2100 as index.
    """
    iamc_scenario = scenario.split("-", 1)[1]
    population_scenario = iamc_scenario.split("-")[0].upper()
    iso_alpha_3_code = code.split("_")[0]

    # Get the annual electricity demand of the EPPO in GWh.
    demand = eppo_thailand.read_projected_demand().loc[code]
    demand = demand[
        (demand.index >= FIRST_YEAR_OF_EPPO_PROJECTION)
        & (demand.index <= LAST_YEAR_OF_EPPO_PROJECTION)
        & (demand.index > last_historical_year)
    ]

    # Get the projected population, as in retrievals.population.
    population = retrievals.population._extract_future_population(
        code, _read_future_population(), [], [], [], population_scenario
    )

    # Calculate the electricity demand per capita, converting GWh to
    # kWh.
    eppo_demand_per_capita = (demand * 1e6 / population).dropna()

    return _extend_with_iamc_growth_rates(
        eppo_demand_per_capita,
        iso_alpha_3_code,
        iamc_scenario,
        growth_rates,
        last_historical_value,
        last_historical_year,
    )


def _extend_with_iamc_growth_rates(
    projection: pandas.Series,
    iso_alpha_3_code: str,
    iamc_scenario: str,
    growth_rates: pandas.DataFrame,
    last_historical_value: float,
    last_historical_year: int,
) -> pandas.Series:
    """
    Extend a projection of electricity demand per capita to 2100.

    Before the projection, the last historical value is extrapolated
    with the growth rates of the IAMC scenario. After the projection,
    its last value is extrapolated with them.

    Parameters
    ----------
    projection : pandas.Series
        The projected electricity demand per capita in kWh, with the
        years as index.
    iso_alpha_3_code : str
        The ISO Alpha-3 code of the country whose growth rates are used.
    iamc_scenario : str
        The IAMC scenario of the growth rates, e.g., SSP2-45.
    growth_rates : pandas.DataFrame
        The IIASA growth rates of electricity demand per capita.
    last_historical_value : float
        The last historical electricity demand per capita in kWh.
    last_historical_year : int
        The last historical year.

    Returns
    -------
    pandas.Series
        The future electricity demand per capita in kWh, with the years
        from the year after the last historical year to 2100 as index.
    """
    parts = []

    # Extrapolate the last historical value to the years before the
    # projection.
    years_before = list(range(last_historical_year + 1, projection.index.min()))
    if years_before:
        parts.append(
            iiasa.extrapolate(
                growth_rates,
                iso_alpha_3_code,
                iamc_scenario,
                last_historical_value,
                last_historical_year,
                years_before,
            )
        )

    parts.append(projection)

    # Extrapolate the last value of the projection to the years after
    # it.
    last_projected_year = projection.index.max()
    years_after = list(range(last_projected_year + 1, 2101))
    if years_after:
        parts.append(
            iiasa.extrapolate(
                growth_rates,
                iso_alpha_3_code,
                iamc_scenario,
                projection.loc[last_projected_year],
                last_projected_year,
                years_after,
            )
        )

    return pandas.concat(parts).sort_index()


def get_ema_scenarios() -> list[str]:
    """
    Get the scenarios for Singapore based on the EMA projection.

    Returns
    -------
    list[str]
        The combinations of the EMA scenario and the IAMC scenario. The
        IAMC scenario gives the growth rates after the EMA projection,
        and its SSP the population used to convert the demand to demand
        per capita.
    """
    return [
        f"EMA-{ema_scenario}-{iamc_scenario}"
        for ema_scenario in ema_singapore.get_scenarios()
        for iamc_scenario in get_iamc_scenarios()
    ]


def uses_ema_projection(code: str) -> bool:
    """
    Check if the future demand of a code comes from the EMA.

    Parameters
    ----------
    code : str
        The code of the country or subdivision of interest.

    Returns
    -------
    bool
        True for Singapore.
    """
    return code == ema_singapore.CODE


@functools.lru_cache(maxsize=1)
def _read_future_population() -> pandas.DataFrame:
    """
    Read the future population of IIASA once.

    Returns
    -------
    pandas.DataFrame
        The future population data of IIASA.
    """
    return iiasa.read("population")


def get_future_data_from_ema(
    code: str,
    scenario: str,
    growth_rates: pandas.DataFrame,
    last_historical_value: float,
    last_historical_year: int,
) -> pandas.Series:
    """
    Get the future electricity demand per capita from the EMA.

    The projected generation to meet the EDF of the EMA is used as the
    annual electricity demand from FIRST_YEAR_OF_EMA_PROJECTION to the
    last year of the EMA projection, and divided by the projected
    population of IIASA (the same projection as in
    retrievals.population). Before, the last historical value is
    extrapolated with the growth rates of the IAMC scenario. After, the
    value of the last year of the EMA projection is extrapolated with
    them.

    Parameters
    ----------
    code : str
        The code of Singapore.
    scenario : str
        The scenario, with the format EMA-{EMA scenario}-{IAMC
        scenario}, e.g., EMA-BASE-SSP2-45.
    growth_rates : pandas.DataFrame
        The IIASA growth rates of electricity demand per capita.
    last_historical_value : float
        The last historical electricity demand per capita in kWh.
    last_historical_year : int
        The last historical year.

    Returns
    -------
    pandas.Series
        The future electricity demand per capita in kWh, with the years
        from the year after the last historical year to 2100 as index.
    """
    __, ema_scenario, iamc_scenario = scenario.upper().split("-", 2)
    population_scenario = iamc_scenario.split("-")[0]

    # Get the annual electricity demand in GWh.
    demand = ema_singapore.read_projected_generation(ema_scenario)
    demand = demand[
        (demand.index >= FIRST_YEAR_OF_EMA_PROJECTION)
        & (demand.index > last_historical_year)
    ]

    # Get the projected population.
    population = iiasa.extract_and_interpolate(
        _read_future_population(), code, population_scenario
    )

    # Calculate the electricity demand per capita, converting GWh to
    # kWh.
    ema_demand_per_capita = (demand * 1e6 / population).dropna()

    return _extend_with_iamc_growth_rates(
        ema_demand_per_capita,
        code,
        iamc_scenario,
        growth_rates,
        last_historical_value,
        last_historical_year,
    )


def get_pep_scenarios() -> list[str]:
    """
    Get the scenarios for the Philippines based on the PEP.

    Returns
    -------
    list[str]
        The combinations of the PEP scenario and the PSA population
        scenario used to convert the demand to demand per capita.
    """
    return [
        f"PEP-{pep_scenario}-{population_scenario}"
        for pep_scenario in pep_philippines.get_scenarios()
        for population_scenario in psa_philippines.get_projection_scenarios()
    ]


def uses_pep_projection(code: str) -> bool:
    """
    Check if the future demand of a code comes from the PEP.

    Parameters
    ----------
    code : str
        The code of the country or subdivision of interest.

    Returns
    -------
    bool
        True for the Philippines and its grids.
    """
    return code == "PHL" or code in pep_philippines.get_codes()


def get_available_scenarios_for_code(code: str) -> list[str]:
    """
    Get the available future scenarios of a country or subdivision.

    Parameters
    ----------
    code : str
        The code of the country or subdivision of interest.

    Returns
    -------
    list[str]
        The PEP-based scenarios for the Philippines and its grids, the
        EMA-based scenarios for Singapore, and the IAMC scenarios for
        the other countries and subdivisions.
    """
    if uses_pep_projection(code):
        return get_pep_scenarios()

    if uses_ema_projection(code):
        return get_ema_scenarios()

    if uses_eppo_projection(code):
        return get_eppo_scenarios()

    return get_iamc_scenarios()


def get_future_data_from_pep(code: str, scenario: str) -> pandas.Series:
    """
    Get the future electricity demand per capita from the PEP.

    The projected annual electricity sales of the grids are multiplied
    by the grid-load factors to get the annual electricity demand. The
    demand of the Philippines is the sum of the demand of the grids.
    The demand is divided by the projected population of the PSA.

    Parameters
    ----------
    code : str
        The code of the Philippines or one of its grids.
    scenario : str
        The scenario, with the format PEP-{PEP scenario}-{PSA scenario}.

    Returns
    -------
    pandas.Series
        The future electricity demand per capita in kWh, with the years
        as index. It covers the years in which both the PEP and the PSA
        projections are available.
    """
    __, pep_scenario, population_scenario = scenario.split("-")

    # Get the annual electricity demand in MWh.
    demand = pep_philippines.read_annual_electricity_demand(pep_scenario)
    demand = demand.sum() if code == "PHL" else demand.loc[code]

    # Get the projected population.
    population = retrievals.population.get_future_population_from_psa(
        code, population_scenario
    )

    # Calculate the electricity demand per capita, converting MWh to
    # kWh.
    return (demand * 1000 / population).dropna()


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


def get_regional_historical_data_from_eppo(
    code: str,
    national_electricity_demand: pandas.DataFrame,
    global_historical_population: pandas.DataFrame | None = None,
) -> pandas.Series:
    """
    Get the historical electricity demand per capita of a Thai region.

    The national demand of Ember is multiplied by the energy share of
    the region in the EGAT demand of eppo_thailand.SHARE_YEAR and
    divided by the historical population of the region.

    Parameters
    ----------
    code : str
        The code of the region of Thailand.
    national_electricity_demand : pandas.DataFrame
        The national electricity demand of Ember in TWh, with the ISO
        Alpha-3 codes as index and the years as columns.
    global_historical_population : pandas.DataFrame | None, optional
        The global historical population data from the World Bank.

    Returns
    -------
    pandas.Series
        The historical electricity demand per capita in kWh.
    """
    # Get the national demand and split it into the region.
    national_demand = national_electricity_demand.loc[
        code.split("_")[0]
    ].dropna()
    years = national_demand.index.tolist()
    regional_demand = national_demand * eppo_thailand.get_energy_share(
        code, years
    )

    # Get the population of the region for the same years.
    population = retrievals.population.get_historical_population(
        code, years, global_historical_population
    )

    # Calculate the electricity demand per capita, converting TWh to
    # kWh.
    return (regional_demand * 1e9 / population).dropna()


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

    # If any subdivision has regional data, download the regional
    # gross power generation and the population data.
    if set(codes) & set(get_regional_codes()):
        regional_gross_generation = (
            doe_philippines.download_gross_generation()
        )
        global_historical_population = world_bank.download("population")

    # If any region of Thailand is of interest, download the national
    # demand of Ember and the population data.
    if any(uses_eppo_projection(code) and "_" in code for code in codes):
        national_electricity_demand = ember.download_electricity_demand()
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
        elif uses_eppo_projection(code) and "_" in code:
            # Split the national demand of Ember into the region with
            # the energy share of the region in the EGAT demand.
            logging.info(
                f"Using the national demand of Ember and the EGAT energy "
                f"share of {eppo_thailand.SHARE_YEAR} for {code}."
            )
            historical_electricity_demand_per_capita = (
                get_regional_historical_data_from_eppo(
                    code,
                    national_electricity_demand,
                    global_historical_population,
                )
            )

        # Get the years of available historical data.
        available_historical_years = (
            historical_electricity_demand_per_capita.index.tolist()
        )

        # Get the years of available future data.
        available_future_years = list(
            range(max(available_historical_years) + 1, 2101)
        )

        # Get the available scenarios of the country or subdivision. If
        # an unavailable scenario that is requested, no
        # future data is retrieved for it.
        available_scenarios = get_available_scenarios_for_code(code)
        scenario_of_code = (
            scenario
            if scenario is None
            or scenario.upper() in [s.upper() for s in available_scenarios]
            else None
        )
        if scenario_of_code is None:
            logging.warning(
                f"The scenario {scenario} is not available for {code}. "
                f"Available scenarios: {available_scenarios}."
            )

        # Get the list of year and scenario combinations.
        year_scenario_list = (
            utils.scenarios.get_year_and_scenario_combinations(
                year,
                start_year,
                end_year,
                available_historical_years,
                available_future_years,
                scenario_of_code,
                available_scenarios,
            )
        )
        if scenario_of_code is None and scenario is not None:
            year_scenario_list = [
                (year, scenario_of_year)
                for year, scenario_of_year in year_scenario_list
                if scenario_of_year is None
            ]

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
            for future_scenario in selected_scenarios:
                if not os.path.exists(
                    f"{file_path_without_ext}_"
                    f"{future_scenario.replace('-', '_')}.parquet"
                ) or not os.path.exists(
                    f"{file_path_without_ext}_{future_scenario.replace('-', '_')}.csv"
                ):
                    logging.info(
                        f"Extracting future annual electricity demand per "
                        f"capita data for {code} and {future_scenario}."
                    )

                    if uses_pep_projection(code):
                        # Calculate the future electricity demand per
                        # capita from the projected electricity sales
                        # of the PEP and the projected population of
                        # the PSA.
                        future_electricity_demand_per_capita = (
                            get_future_data_from_pep(code, future_scenario)
                        )
                    elif uses_ema_projection(code):
                        # Calculate the future electricity demand per
                        # capita from the projected generation of the
                        # EMA and the projected population of IIASA,
                        # extended with the growth rates of the IAMC
                        # scenario.
                        last_historical_year = max(available_historical_years)
                        future_electricity_demand_per_capita = (
                            get_future_data_from_ema(
                                code,
                                future_scenario,
                                global_future_electricity_demand_per_capita_growth_rates,
                                historical_electricity_demand_per_capita.loc[
                                    last_historical_year
                                ],
                                last_historical_year,
                            )
                        )
                    elif uses_eppo_projection(code):
                        # Calculate the future electricity demand per
                        # capita from the projected demand of the EPPO
                        # and the projected population, extended with
                        # the growth rates of the IAMC scenario.
                        last_historical_year = max(available_historical_years)
                        future_electricity_demand_per_capita = (
                            get_future_data_from_eppo(
                                code,
                                future_scenario,
                                global_future_electricity_demand_per_capita_growth_rates,
                                historical_electricity_demand_per_capita.loc[
                                    last_historical_year
                                ],
                                last_historical_year,
                            )
                        )
                    else:
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
                        future_electricity_demand_per_capita = (
                            iiasa.extrapolate(
                                global_future_electricity_demand_per_capita_growth_rates,
                                iso_alpha_3_code,
                                future_scenario,
                                last_historical_value,
                                last_historical_year,
                                available_future_years,
                            )
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
                        f"{file_path_without_ext}_{future_scenario.replace('-', '_')}.parquet"
                    )
                    selected_future_electricity_demand_per_capita.to_csv(
                        f"{file_path_without_ext}_{future_scenario.replace('-', '_')}.csv",
                    )

                    logging.info(
                        f"Future annual electricity demand per capita data "
                        f"for {code} and {future_scenario} has been extracted "
                        "and saved successfully."
                    )

                else:
                    logging.info(
                        f"Future annual electricity demand per capita data "
                        f"for {code} and {future_scenario} already exists. "
                        "Skipping retrieval."
                    )
