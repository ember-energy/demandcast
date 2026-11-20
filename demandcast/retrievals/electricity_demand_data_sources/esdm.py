# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Indonesia (IDN) electricity demand profile
Script owner : Giang Vu

Description:

    This module builds a synthetic hourly electricity demand time series
    for Indonesia (IDN) and its eight grid nodes (IDN_JAW, IDN_SUM,
    IDN_BTM, IDN_KAL, IDN_SUL, IDN_NUS, IDN_MAL, IDN_PAP) for 2017-2025.
    There is no public multi-year high-resolution demand data for
    Indonesia, so one year of hourly load shapes is fitted to annual
    national and node statistics (files in
    socio_economic_data_sources/manual_downloads/pln). For each year:

    1. Load shapes. The hourly load shape of each node is read from the
       "Load_Shape_pu" tab of Indonesia_Load_Shapes_Peaks_GridNodes.xlsx.
       It was extracted from the 2017 hourly demand profile of
       Indonesia (8,736 hours, 52 weeks from Sunday 1 January to
       Saturday 30 December 2017), in per unit of the node's own annual
       peak, in local time.

    2. Calendar alignment. The 2017 shape is mapped onto the calendar
       of the year (_map_shape_to_year), so that the holidays fall on
       their dates of the year:
       - Holidays. Each public holiday of the year (holidays package,
         as in assemble.py) takes the 2017 day of the same holiday.
         Lebaran (Idul Fitri) moves with the 7 days before and after it
         (collective leave and "mudik"), Christmas with 24 and 26
         December, and New Year with 2 January (HOLIDAY_WINDOWS). For
         example, the Lebaran of 31 March 2025 takes the Lebaran of
         25 June 2017. The days of these windows keep their offset from
         the holiday, not their weekday.
       - Other days take the 2017 day with the same weekday and the
         closest day of the year (the same shift, between -3 and +3
         days, for the whole year). If that day is a 2017 holiday (or in
         its window), or is outside the 364 days of the shape, the day
         with the same weekday in the closest week that is not is used.
         Weekends therefore stay on weekends, and the 2017 holiday load
         does not appear on normal days.
       Holidays of the year that are not in 2017 (e.g., election days,
       and Easter Sunday from 2024) are treated as normal days.

    3. Base profiles. The shape of each node is scaled to the node's
       annual energy consumption ("Grid_Node_Energy_GWh" tab of
       Indonesia_PLN_Peak_Energy_LoadFactor_2017-2025.xlsx):
           base_node(h) = E_node x shape(h) / sum of shape over the year
       The base profile of Indonesia is the sum of the base node
       profiles (load factor of about 78% in every year).

    4. National target. The national peak load P and on-grid
       generation E (NATIONAL_TARGETS) set the target load factor
       LF = E / (P x hours). The base profile of Indonesia is divided by
       its peak (so that its peak hour is 1) and raised to the power k:
           IDN(h) = P x (base_IDN(h) / max base_IDN) ** k
       The peak hour stays at 1 for any k, so the peak is exactly P.
       The other hours, below 1, move: k > 1 lowers them (peakier
       curve, lower load factor) and k < 1 raises them (flatter curve,
       higher load factor), and the lower the hour, the larger the
       change. The load factor decreases monotonically with k, so a
       single k matches LF (found by bisection in _solve_exponent), and
       the annual energy is exactly E. The order of the hours, and so
       the timing of the daily and weekly patterns and of the peak, is
       kept. k is about 1 in 2017-2021 (0.99-1.19), 0.70 in 2022 and
       1.87-2.05 in 2023-2025.

    5. Breakdown into nodes. The national target is split into the
       nodes by iterative proportional fitting (_fit_to_targets) of the
       base node profiles: the hours and the nodes are rescaled in turn
       until (a) the nodes add up to the national target in every hour
       and (b) the annual energy of each node is its share of the node
       energy consumption of the year x E. Each node keeps its own
       daily and weekly pattern; the node peaks are not targeted and
       result from the fitting.

    National targets (NATIONAL_TARGETS):
    - On-grid generation: "Total On Grid" of HEESI 2025 section 6.4.2A
      (PLN production and PLN purchases from captive power and IPP),
      2017-2024. For 2025, which follows a new classification by
      power-plant ownership (section 6.4.2B): PLN sub total + PLN
      electricity purchase from IPP, captive power and PPU.
    - Peak load: HEESI 2025 section 6.4.8 (PLN only), except in 2018,
      2020 and 2022, where the HEESI peak load and load factor do not
      match the on-grid generation. The Statistik PLN peaks are used
      for these years, which, with the published load factors, give
      the on-grid generation.
    With these targets, the load factors equal the published load
    factors over 8,760 hours in 2017-2024 (over the actual number of
    hours, they are about 0.2 percentage points lower in the leap years
    2020 and 2024). In 2025, the load factor is 61.3% against 62.2%
    published, because of the new classification. The 2025 values are
    unaudited.

    Notes and limitations:
    - The profiles are at the level of on-grid generation, so their
      annual energy is about 12-15% higher than the energy consumption
      of Grid_Node_Energy_GWh (it includes losses and own use). The
      same basis is used for all the years.
    - All the years reuse the 2017 shapes, so the peak is always on the
      same weekday and hour (a Monday in late October, 18:00-19:00
      local time, for IDN). Changes in the daily pattern over time
      (e.g., air conditioning, rooftop solar) are not captured.
    - Only the holidays move to their dates of the year. Ramadan (27
      May - 24 June in 2017) keeps its 2017 dates, as its effect on the
      load is small compared with the major holidays.
    - From 2023, the published peak includes the generation
      subsidiaries, so the peak increases by about 40% between 2022 and
      2023 and the curves of 2023-2025 are much peakier (k of about 2).
    - Four nodes (IDN_BTM, IDN_NUS, IDN_MAL, IDN_PAP) share the same
      2017 shape and differ only in scale.
    - All the nodes use the time zone Asia/Jakarta (esdm.yaml), while
      the shapes are in local time, so the nodes in WITA and WIT peak
      at the same instant as Jawa and the node peaks are almost
      coincident.
    - The PLN node peaks (Grid_Node_Peak_MW) are not used: they are
      sums of non-coincident unit peaks.

    Sources:
    - Indonesia Load Profile-AEO workbook (tab TOTAL LOAD; RUPTL-based
      hourly provincial load in 2017)
    - PT PLN (Persero), Statistik PLN 2017-2025, Table 1 (peak load of
      2018, 2020 and 2022) and Table 2 (energy consumption)
    - ESDM, Handbook of Energy & Economic Statistics of Indonesia 2025
      (HEESI 2025), sections 6.4.2A and 6.4.2B Power Plant Production
      (printed pages 107-108) and 6.4.8 Electricity System Performance
      (printed page 117)
    - PLN Statistics / ESDM Pusdatin, electricity sales by customer
      group and region, 2017-2024 (average energy shares of the nodes,
      get_average_energy_shares)
"""

import functools
import logging
import os
import re

import holidays
import numpy
import pandas
import utils.entities

# Define the file and sheet with the annual PLN electricity sales.
SALES_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "socio_economic_data_sources",
    "manual_downloads",
    "esdm_pusdastin",
    "PLN_electricity_sales_by_customer_group_and_region_2017-2024.xlsx",
)
SALES_SHEET_NAME = "Node_totals"

# Define the folder of the PLN files.
PLN_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "socio_economic_data_sources",
    "manual_downloads",
    "pln",
)

# Define the file and sheet with the hourly load shapes of the nodes,
# and the first local day of the shapes (a Sunday).
LOAD_SHAPE_FILE_PATH = os.path.join(
    PLN_FOLDER, "Indonesia_Load_Shapes_Peaks_GridNodes.xlsx"
)
LOAD_SHAPE_SHEET_NAME = "Load_Shape_pu"
LOAD_SHAPE_START = pandas.Timestamp("2017-01-01")

# Define the holidays whose 2017 load is moved to their dates in each
# year, by their names in the holidays package (in Indonesian, as in
# assemble.py), with the number of days before and after them that move
# with them. The other public holidays move without extra days. Lebaran
# (Idul Fitri) moves with the week before and after it (collective leave
# and "mudik" travel, about 18 June - 2 July in 2017), Christmas with
# Christmas Eve and 26 December, and New Year with 2 January.
HOLIDAY_COUNTRY_CODE = "ID"
HOLIDAY_WINDOWS = {
    "Hari Raya Idul Fitri": (7, 7),
    "Hari Raya Natal": (1, 1),
    "Tahun Baru Masehi": (0, 1),
}

# Define the file and sheet with the annual energy consumption of the
# nodes.
ENERGY_FILE_PATH = os.path.join(
    PLN_FOLDER, "Indonesia_PLN_Peak_Energy_LoadFactor_2017-2025.xlsx"
)
ENERGY_SHEET_NAME = "Grid_Node_Energy_GWh"

# Define the national annual targets of the profile of Indonesia, from
# content-handbook-of-energy-and-economic-statistics-of-indonesia-
# 2025.pdf (HEESI 2025) in the PLN folder:
# - on_grid_generation (GWh): 2017-2024, "Total On Grid" of section
#   6.4.2A Power Plant Production (PLN production and PLN purchases from
#   captive power and IPP, printed page 107). 2025, section 6.4.2B
#   (printed page 108): PLN sub total (190,970) + PLN electricity
#   purchase from IPP, captive power and PPU (158,913).
# - peak_load (MW): section 6.4.8 Electricity System Performance
#   (printed page 117), except 2018, 2020 and 2022, where the HEESI peak
#   load and load factor are inconsistent with the on-grid generation.
#   The peaks of Statistik PLN ("Indonesia - published total" of the
#   Peak_Load_MW tab of ENERGY_FILE_PATH) are used for these years:
#   with the published load factors, they give the on-grid generation.
# The 2025 values are unaudited.
NATIONAL_TARGETS = pandas.DataFrame(
    {
        "on_grid_generation": [
            254660, 267085, 278942, 274851, 289471,
            308095, 323321, 343892, 190970 + 158913,
        ],
        "peak_load": [
            38797, 38769.93, 41671, 40059.74, 42785,
            41800.90, 58282, 61288, 65134,
        ],
    },
    index=pandas.Index(range(2017, 2026), name="year"),
)

# Define the tolerance and maximum number of iterations of the
# iterative proportional fitting of the node profiles.
FITTING_TOLERANCE = 1e-9
FITTING_MAX_ITERATIONS = 1000

# Map the grid nodes of the sales file to the codes of the subdivisions.
CODES_OF_NODES = {
    "ID-JAW": "IDN_JAW",
    "ID-BTM": "IDN_BTM",
    "ID-SUM": "IDN_SUM",
    "ID-KAL": "IDN_KAL",
    "ID-SUL": "IDN_SUL",
    "ID-NUS": "IDN_NUS",
    "ID-MAL": "IDN_MAL",
    "ID-PAP": "IDN_PAP",
}


def redistribute() -> bool:
    """
    Return a boolean indicating if the data can be redistributed.

    Returns
    -------
    bool
        True if the data can be redistributed, False otherwise.
    """
    logging.debug(
        "Synthetic profile built from a 2017 Indonesian load shape and "
        "PLN statistics; redistribution terms unclear."
    )
    return False


def get_available_requests(code: str = "IDN") -> None:
    """
    Get the available requests.

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


@functools.lru_cache(maxsize=1)
def read_annual_sales() -> pandas.DataFrame:
    """
    Read the annual PLN electricity sales of each grid node.

    Returns
    -------
    pandas.DataFrame
        The annual electricity sales in GWh, with the years as index
        and the codes of the subdivisions as columns.
    """
    sales = pandas.read_excel(SALES_FILE_PATH, sheet_name=SALES_SHEET_NAME, header=3)
    node_column = sales.columns[0]

    # Keep the node rows of the main table, which ends at the
    # "Sum of nodes" row (the rows below detail the mixed Riau values).
    end_of_table = sales.index[sales[node_column] == "Sum of nodes"][0]
    sum_of_nodes = sales.loc[end_of_table]
    sales = sales.loc[: end_of_table - 1]
    sales = sales[sales[node_column].isin(CODES_OF_NODES)]

    # Keep the year columns (e.g., 2017 or "2025 (calculated)").
    year_columns = {
        column: int(str(column)[:4])
        for column in sales.columns
        if re.match(r"^\d{4}", str(column))
    }
    sum_of_nodes = sum_of_nodes[list(year_columns)].astype(float)
    sales = (
        sales.set_index(node_column)[list(year_columns)]
        .astype(float)
        .rename(index=CODES_OF_NODES, columns=year_columns)
        .T
    )
    sales.index.name = "year"
    sales.columns.name = None

    # Check that all the nodes are present and add up to the total.
    missing_nodes = set(CODES_OF_NODES.values()) - set(sales.columns)
    if missing_nodes:
        raise ValueError(f"Nodes missing in the sales file: {missing_nodes}.")
    difference = (sales.sum(axis=1) - sum_of_nodes.to_numpy()).abs()
    if (difference > 1).any():
        logging.warning(
            "The node sales do not add up to the 'Sum of nodes' row:\n"
            f"{difference[difference > 1]}"
        )

    return sales


def get_average_energy_shares() -> pandas.Series:
    """
    Get the average share of each grid node in the PLN electricity
    sales of Indonesia.

    The share of each node in the sum of the nodes is calculated for
    each year of the sales file and averaged over the years. The sales
    of 2025 in the file are themselves calculated with the average
    shares of 2017-2024, so including them does not change the average.

    Returns
    -------
    pandas.Series
        The average share of each node, with the codes of the
        subdivisions as index. The shares sum to 1.
    """
    sales = read_annual_sales()
    shares = sales.div(sales.sum(axis=1), axis=0).mean()
    return shares / shares.sum()


@functools.lru_cache(maxsize=1)
def read_load_shapes() -> pandas.DataFrame:
    """
    Read the 2017 hourly load shape of each grid node.

    Returns
    -------
    pandas.DataFrame
        The hourly load in per unit of the node's own annual peak,
        indexed by the local (wall-clock) start of the hour, without
        time zone information, and with the codes of the subdivisions
        as columns.
    """
    logging.info(f"Reading the load shapes from {LOAD_SHAPE_FILE_PATH}.")
    raw = pandas.read_excel(
        LOAD_SHAPE_FILE_PATH, sheet_name=LOAD_SHAPE_SHEET_NAME, header=None
    )

    # The first row holds the series names (provinces, grid nodes and
    # Indonesia). The data starts on the fifth row, with the start of
    # each hour in the first column.
    node_codes = list(CODES_OF_NODES.values())
    names = raw.iloc[0]
    missing_nodes = set(node_codes) - set(names)
    if missing_nodes:
        raise ValueError(f"Nodes missing in the load shapes: {missing_nodes}.")
    columns = [names[names == code].index[0] for code in node_codes]

    data = raw.iloc[4:]
    shapes = data[columns].astype(float)
    shapes.columns = node_codes
    shapes.index = pandas.DatetimeIndex(pandas.to_datetime(data[0]))
    shapes.index.name = None

    # Check that the shapes cover 52 full weeks from LOAD_SHAPE_START.
    expected_index = pandas.date_range(
        LOAD_SHAPE_START, periods=52 * 7 * 24, freq="1h"
    )
    if not shapes.index.equals(expected_index) or shapes.isna().any().any():
        raise ValueError(
            "The load shapes must cover 52 full weeks of hourly values "
            f"from {LOAD_SHAPE_START.date()}."
        )

    return shapes


@functools.lru_cache(maxsize=1)
def read_annual_energy() -> pandas.DataFrame:
    """
    Read the annual energy consumption of each grid node.

    Returns
    -------
    pandas.DataFrame
        The annual energy consumption in GWh, with the years as index
        and the codes of the subdivisions as columns.
    """
    table = pandas.read_excel(
        ENERGY_FILE_PATH, sheet_name=ENERGY_SHEET_NAME, header=3
    )
    node_column = table.columns[0]
    node_codes = list(CODES_OF_NODES.values())
    table = table[table[node_column].isin(node_codes)].set_index(node_column)

    missing_nodes = set(node_codes) - set(table.index)
    if missing_nodes:
        raise ValueError(f"Nodes missing in {ENERGY_SHEET_NAME}: {missing_nodes}.")

    # Keep the year columns (read as 2017 or 2017.0).
    year_columns = {
        column: int(float(column))
        for column in table.columns
        if re.fullmatch(r"\d{4}(\.0)?", str(column))
    }
    table = (
        table.loc[node_codes, list(year_columns)]
        .astype(float)
        .rename(columns=year_columns)
        .T
    )
    table.index.name = "year"
    table.columns.name = None
    return table


def _get_holiday_days(year: int) -> dict[pandas.Timestamp, tuple[str, int]]:
    """
    Get the days of the holidays of a year, with the days around them.

    Parameters
    ----------
    year : int
        The year of interest.

    Returns
    -------
    dict[pandas.Timestamp, tuple[str, int]]
        For each day of the year that is a holiday or in the window of
        days around a holiday (HOLIDAY_WINDOWS), the name of the holiday
        and the offset of the day from it (in days). Where windows
        overlap, the holidays of HOLIDAY_WINDOWS take precedence.
    """
    country_holidays = holidays.country_holidays(HOLIDAY_COUNTRY_CODE, years=year)

    # List the holidays, with the holidays of HOLIDAY_WINDOWS last so
    # that their days overwrite the others.
    holidays_of_year = sorted(
        (
            (pandas.Timestamp(date), name)
            for date in country_holidays
            for name in country_holidays.get_list(date)
        ),
        key=lambda holiday: holiday[1] in HOLIDAY_WINDOWS,
    )

    holiday_days = {}
    for date, name in holidays_of_year:
        days_before, days_after = HOLIDAY_WINDOWS.get(name, (0, 0))
        for offset in range(-days_before, days_after + 1):
            day = date + pandas.Timedelta(days=offset)
            if day.year == year:
                holiday_days[day] = (name, offset)
    return holiday_days


def _map_shape_to_year(shape: pandas.Series, year: int) -> pandas.Series:
    """
    Map the 2017 hourly load shape onto the calendar of another year.

    The holidays of the year, and the days around them (HOLIDAY_WINDOWS),
    take the 2017 day of the same holiday and offset, so that the load
    drops on the dates of the holidays of the year. The other days take
    the 2017 day with the same weekday and the closest day of the year
    (the same shift, of at most 3 days, for the whole year). If that day
    is a holiday (or in the window of a holiday) in 2017, or is outside
    the 364 days of the shape, the day with the same weekday in the
    closest week that is not is used instead.

    Holidays of the year that are not in 2017 (e.g., election days, and
    Easter Sunday, which is a holiday from 2024) are treated as normal
    days.

    Parameters
    ----------
    shape : pandas.Series
        The 2017 hourly load shape, indexed by the local time.
    year : int
        The target year.

    Returns
    -------
    pandas.Series
        The hourly load shape of the target year, indexed by the local
        time, without time zone information.
    """
    days_in_shape = len(shape) // 24
    target_days = pandas.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")

    # Get the day of the shape (0 to days_in_shape - 1) of each holiday
    # and offset in 2017, and the days of the shape to avoid for the
    # normal days.
    source_holiday_days = {
        holiday: (day - LOAD_SHAPE_START).days
        for day, holiday in _get_holiday_days(LOAD_SHAPE_START.year).items()
        if 0 <= (day - LOAD_SHAPE_START).days < days_in_shape
    }
    days_to_avoid = set(source_holiday_days.values())
    target_holiday_days = _get_holiday_days(year)

    # Shift (in days) that aligns the weekdays, between -3 and 3.
    shift = (target_days[0].dayofweek - LOAD_SHAPE_START.dayofweek) % 7
    if shift > 3:
        shift -= 7

    source_days = []
    for target_day in target_days:
        # Holidays take the 2017 day of the same holiday and offset.
        holiday = target_holiday_days.get(target_day)
        if holiday in source_holiday_days:
            source_days.append(source_holiday_days[holiday])
            continue

        # Other days take the 2017 day with the same weekday in the
        # closest week that is in the shape and not a 2017 holiday.
        day = target_day.dayofyear - 1 + shift
        source_day = next(
            day + 7 * weeks
            for weeks in sorted(range(-53, 54), key=abs)
            if 0 <= day + 7 * weeks < days_in_shape
            and day + 7 * weeks not in days_to_avoid
        )
        source_days.append(source_day)

    values = shape.to_numpy().reshape(days_in_shape, 24)[source_days].ravel()
    index = pandas.date_range(f"{year}-01-01", periods=len(values), freq="1h")
    return pandas.Series(values, index=index)


def _build_base_node_demand(code: str) -> pandas.Series:
    """
    Build the base hourly demand of a grid node.

    The load shape of each year is scaled to the node's annual energy
    consumption of the year.

    Parameters
    ----------
    code : str
        The code of the subdivision (e.g., IDN_JAW).

    Returns
    -------
    pandas.Series
        The base hourly demand in MW, with a timezone-aware index.
    """
    shape = read_load_shapes()[code]
    energy = read_annual_energy()[code].dropna()

    demand_of_years = []
    for year in energy.index:
        # Scale the load shape of the year to the annual energy (GWh ->
        # MWh). Each step lasts one hour, so the hourly demand in MW
        # equals the hourly energy in MWh, and the hourly demand sums
        # to the annual energy.
        shape_of_year = _map_shape_to_year(shape, year)
        demand_of_years.append(
            energy[year] * 1000 * shape_of_year / shape_of_year.sum()
        )

    if not demand_of_years:
        return pandas.Series(dtype=float)

    demand = pandas.concat(demand_of_years)

    # The load shapes are in local wall-clock time. Ambiguous and
    # non-existent times only occur in time zones with daylight saving
    # time, which is not the case in Indonesia.
    demand.index = demand.index.tz_localize(
        utils.entities.get_time_zone(code), ambiguous="NaT", nonexistent="NaT"
    )
    return demand[demand.index.notna()]


def _solve_exponent(shape: numpy.ndarray, load_factor: float) -> float:
    """
    Find the exponent k so that the load factor of shape**k is the target.

    The shape is normalised by its peak (maximum of 1), so shape**k
    keeps its peak of 1 for any k, and its mean (the load factor)
    decreases when k increases.

    Parameters
    ----------
    shape : numpy.ndarray
        The hourly load shape, in per unit of its peak.
    load_factor : float
        The target load factor, between 0 and 1.

    Returns
    -------
    float
        The exponent k.

    Raises
    ------
    ValueError
        If the target load factor cannot be reached.
    """
    lower, upper = 1e-3, 100.0
    if not (shape**upper).mean() < load_factor < (shape**lower).mean():
        raise ValueError(f"The load factor {load_factor} cannot be reached.")

    # Bisect on the logarithm of k.
    for _ in range(200):
        middle = (lower * upper) ** 0.5
        if (shape**middle).mean() > load_factor:
            lower = middle
        else:
            upper = middle
    return (lower * upper) ** 0.5


def _fit_to_targets(
    base: numpy.ndarray, hourly_target: numpy.ndarray, energy_target: numpy.ndarray
) -> numpy.ndarray:
    """
    Fit the base node profiles to the hourly and annual energy targets.

    Iterative proportional fitting: the hours (rows) and the nodes
    (columns) are rescaled in turn until the nodes add up to the
    hourly target and each node's annual energy equals its target.
    The hourly target and the energy targets must have the same total.

    Parameters
    ----------
    base : numpy.ndarray
        The base hourly demand, with the hours as rows and the nodes as
        columns.
    hourly_target : numpy.ndarray
        The target sum of the nodes in each hour.
    energy_target : numpy.ndarray
        The target annual energy of each node.

    Returns
    -------
    numpy.ndarray
        The fitted hourly demand, with the same shape as base.
    """
    fitted = base.copy()
    for _ in range(FITTING_MAX_ITERATIONS):
        fitted *= (hourly_target / fitted.sum(axis=1))[:, None]
        fitted *= energy_target / fitted.sum(axis=0)
        hourly_error = numpy.abs(fitted.sum(axis=1) / hourly_target - 1).max()
        if hourly_error < FITTING_TOLERANCE:
            break
    else:
        logging.warning(
            "The fitting of the node profiles did not converge "
            f"(maximum hourly error {hourly_error:.2e})."
        )

    # End on the hours, so that the nodes add up exactly to the target.
    fitted *= (hourly_target / fitted.sum(axis=1))[:, None]
    return fitted


@functools.lru_cache(maxsize=1)
def get_demands() -> pandas.DataFrame:
    """
    Build the hourly demand of Indonesia and its grid nodes.

    For each year, the base profile of Indonesia (sum of the base node
    profiles) is reshaped to match the national on-grid generation and
    peak load (NATIONAL_TARGETS), and split into the nodes by iterative
    proportional fitting.

    Returns
    -------
    pandas.DataFrame
        The hourly demand in MW, with a timezone-aware index (time zone
        of IDN) and the codes of IDN and of the subdivisions as columns.
    """
    time_zone = utils.entities.get_time_zone("IDN")
    node_codes = list(CODES_OF_NODES.values())

    # Combine the base node profiles at the same instant, over the hours
    # covered by all the nodes.
    base = (
        pandas.concat(
            [
                _build_base_node_demand(code).tz_convert("UTC").rename(code)
                for code in node_codes
            ],
            axis=1,
        )
        .dropna()
        .tz_convert(time_zone)
    )
    energy = read_annual_energy()

    demand_of_years = []
    for year, base_of_year in base.groupby(base.index.year):
        if year not in NATIONAL_TARGETS.index or year not in energy.index:
            logging.warning(f"Skipping {year}: no national or node energy data.")
            continue
        peak_load = NATIONAL_TARGETS.loc[year, "peak_load"]
        generation = NATIONAL_TARGETS.loc[year, "on_grid_generation"] * 1000

        # Reshape the national base profile to the peak load and the
        # load factor implied by the on-grid generation (over the
        # actual number of hours of the year, 8,784 in leap years).
        load_factor = generation / (peak_load * len(base_of_year))
        national_base = base_of_year.sum(axis=1).to_numpy()
        national_shape = national_base / national_base.max()
        exponent = _solve_exponent(national_shape, load_factor)
        national_target = peak_load * national_shape**exponent

        # Split the national energy into the nodes with their shares of
        # the node energy consumption of the year.
        node_energy = energy.loc[year, node_codes].to_numpy()
        energy_target = national_target.sum() * node_energy / node_energy.sum()

        fitted = _fit_to_targets(
            base_of_year.to_numpy(), national_target, energy_target
        )
        demand_of_year = pandas.DataFrame(
            fitted, index=base_of_year.index, columns=node_codes
        )
        demand_of_year.insert(0, "IDN", demand_of_year.sum(axis=1))
        demand_of_years.append(demand_of_year)

        logging.info(
            f"IDN {year}: exponent {exponent:.3f}, peak "
            f"{demand_of_year['IDN'].max():.0f} MW, load factor "
            f"{demand_of_year['IDN'].mean() / demand_of_year['IDN'].max():.4f}, "
            f"energy {demand_of_year['IDN'].sum() / 1e6:.1f} TWh "
            f"({demand_of_year['IDN'].sum() / 1000 / node_energy.sum():.3f} x "
            "node energy consumption)."
        )

    return pandas.concat(demand_of_years)


def download_and_extract_data(code: str = "IDN") -> pandas.Series:
    """
    Build the hourly electricity demand of a country or subdivision.

    Parameters
    ----------
    code : str
        The code of the country (IDN) or of a subdivision of
        CODES_OF_NODES (e.g., IDN_JAW).

    Returns
    -------
    electricity_demand_time_series : pandas.Series
        The hourly electricity demand time series in MW, with a
        timezone-aware index.

    Raises
    ------
    ValueError
        If the code is not IDN or a code of CODES_OF_NODES.
    """
    if code != "IDN" and code not in CODES_OF_NODES.values():
        raise ValueError(f"Code {code} is not available in ESDM.")

    logging.info(f"Building the hourly demand of {code}.")

    demand = get_demands()[code].rename(None)
    return demand.tz_convert(utils.entities.get_time_zone(code))


if __name__ == "__main__":
    for code in ["IDN", *CODES_OF_NODES.values()]:
        print(code)
        print(download_and_extract_data(code))


