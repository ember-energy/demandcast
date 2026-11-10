# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module builds the hourly electricity demand profile of the data
    centres in any country or subdivision, from the average diurnal
    profiles of the data centres connected to the network of UK Power
    Networks (UKPN).

    Each hour of a country or subdivision is mapped, by its local hour of
    the day, to the UKPN normalised weekday shape (Monday to Friday) or
    weekend shape (Saturday and Sunday). The half-hourly UKPN shapes are
    averaged into hourly values, and the shapes of the data centre types
    are weighted by DC_TYPE_WEIGHTS. The profile is then rescaled so that
    its mean over the period is 1, so that multiplying it by the average
    demand of the data centres gives their hourly demand with the right
    total energy.

    The UKPN shapes are measured at the grid connection, so they already
    include the cooling and other loads of the data centres. The average
    demand must therefore also be at the grid connection:

    - contracted (grid) capacity x utilisation, with PUE = 1; or
    - IT capacity x IT utilisation x PUE.

    The capacity is the commissioned IT capacity of the data centres of
    each grid node of COUNTRY, for SCENARIO (Low, Mid, High, or Suitable
    sites) and YEAR (2026, the existing capacity, or 2030, only the
    capacity added between 2026 and 2030), read from
    "DC Demand Scenarios - ASEAN.xlsx" with
    retrievals/socio_economic_data_sources/dc_scenarios.py. By default
    (USE_WORKBOOK_PARAMETERS), the occupancy, utilisation, and PUE are
    also those of the workbook for COUNTRY and SCENARIO, so that the
    average demand is the average grid draw of the workbook:

        IT capacity x occupancy x utilisation x PUE.

    YEAR only selects the capacity: the calendar of the profile (week
    days and public holidays) is set by START_DATE and END_DATE.

    The countries and subdivisions are the keys of CAPACITY_MW, with the
    codes of demandcast: the ISO Alpha-3 code of the country (e.g., SGP),
    optionally followed by the code of the subdivision (e.g., PHL_LU).
    The local time zone of each code is taken from utils.entities, unless
    it is set in TIME_ZONES, and the public holidays from the holidays
    package, for the country and, if set in HOLIDAY_SUBDIVISIONS, the
    subdivision.

    Run ukpn_data_centres.py first to create the UKPN diurnal profiles.

    Usage (from the demandcast folder):

        uv run retrievals/electricity_demand_data_sources/iso_data_centre_demand.py

    By default, run_all() builds the profiles of the capacity added by
    2030 for all the scenarios, countries, and grid nodes of the
    workbook (skipping the grid nodes without capacity). Call run()
    instead to build only the profiles of SCENARIO, YEAR, and COUNTRY.
"""  # noqa: W505

import logging
import os
import re
import sys
from datetime import datetime, tzinfo

import holidays
import matplotlib.pyplot as plt
import pandas
import pycountry_convert
import pytz

# Define the demandcast folder, and add it to the path to import utils.
DEMANDCAST_DIRECTORY = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, DEMANDCAST_DIRECTORY)

import utils.entities  # noqa: E402
from retrievals.socio_economic_data_sources import dc_scenarios  # noqa: E402

# Define the first and last day of the profile (DD-MM-YYYY, inclusive).
START_DATE = "01-01-2025"
END_DATE = "31-12-2025"
DATE_FORMAT = "%d-%m-%Y"

# Define the weight of the UKPN shape of each data centre type (e.g.,
# most data centres in the Philippines are co-located sites).
DC_TYPE_WEIGHTS = {"Co-located": 1.0, "Enterprise": 0.0}

# Define whether the public holidays use the weekend shape. In the UKPN
# data, bank holidays are close to weekends.
TREAT_HOLIDAYS_AS_WEEKENDS = True

# Define the time zones (e.g., "Asia/Manila") of the codes whose time
# zone is not found, or is wrong, in utils.entities.
TIME_ZONES: dict[str, str] = {}

# Define the subdivision codes of the holidays package (e.g., "CA" for
# USA_CAL) of the codes with regional public holidays. The other codes
# use the national public holidays.
HOLIDAY_SUBDIVISIONS: dict[str, str] = {}

# Define the scenario, the year, and the country of the capacity of the
# data centres, read from "DC Demand Scenarios - ASEAN.xlsx" (see
# retrievals/socio_economic_data_sources/dc_scenarios.py). The scenario
# and the year are added to the name of the saved files.
# - SCENARIO: "Low", "Mid", "High", or "Suitable sites".
# - YEAR: 2026 (existing capacity) or 2030 (only the capacity added by
#   2030, without the existing capacity).
# - COUNTRY: PHL, IDN, MYS, SGP, THA, or VNM.
SCENARIO = "Suitable sites"
YEAR = 2030
COUNTRY = "SGP"

# Define the countries or subdivisions (demandcast codes, e.g., PHL_LU)
# and the commissioned IT capacity of their data centres (MW): one
# profile is built for each grid node of COUNTRY (e.g., PHL_LU, PHL_VI,
# and PHL_MI). If a capacity is None, only the normalised profile is
# saved.
CAPACITY_MW: dict[str, float | None] = dc_scenarios.get_capacities(
    SCENARIO, YEAR, COUNTRY
)

# Define whether the occupancy, utilisation, and PUE are taken from the
# workbook, for COUNTRY and SCENARIO (True), or from the values below
# (False).
USE_WORKBOOK_PARAMETERS = True

# Define the parameters of the average demand of the data centres,
# either as one value for all codes or as a dictionary by code. If
# UTILISATION or OCCUPANCY is None, only the normalised profile is
# saved. Use PUE = 1 if CAPACITY_MW is the contracted (grid) capacity,
# and the PUE of the country if CAPACITY_MW is the IT capacity (as in
# the workbook).
OCCUPANCY: float | dict[str, float] | None = 0.85
UTILISATION: float | dict[str, float] | None = 0.72
PUE: float | dict[str, float] = 1.55
if USE_WORKBOOK_PARAMETERS:
    _parameters = dc_scenarios.get_conversion_parameters(SCENARIO, COUNTRY)
    OCCUPANCY = _parameters["Occupancy"]
    UTILISATION = _parameters["Utilisation"]
    PUE = _parameters["PUE"]

# Define the folder of the UKPN results.
UKPN_DIRECTORY = os.path.join(
    DEMANDCAST_DIRECTORY, "data", "data_centre_demand_profiles"
)

# Define the date of the UKPN results to use (YYYY-MM-DD). If None, the
# latest results are used.
UKPN_DATE = None

# Define the folder where the profiles are saved, in a sub-folder of the
# ISO Alpha-3 code of the country (e.g., PHL).
RESULT_DIRECTORY = UKPN_DIRECTORY

def _get_parameter(
    value: float | dict[str, float] | None, code: str
) -> float | None:
    """
    Get the value of a parameter of the average demand for a code.

    Parameters
    ----------
    value : float, dict, or None
        The value of the parameter, for all codes or by code.
    code : str
        The code of the country or subdivision (e.g., PHL_LU).

    Returns
    -------
    float or None
        The value of the parameter for the code, or None if not set.
    """
    if isinstance(value, dict):
        return value.get(code)
    return value


def _get_time_zone(code: str) -> tzinfo:
    """
    Get the local time zone of a country or subdivision.

    Parameters
    ----------
    code : str
        The code of the country or subdivision (e.g., PHL_LU).

    Returns
    -------
    datetime.tzinfo
        The time zone of TIME_ZONES, or of utils.entities if the code is
        not in TIME_ZONES. If the subdivision is not in utils.entities,
        the time zone of its country is used.
    """
    if code in TIME_ZONES:
        return pytz.timezone(TIME_ZONES[code])
    try:
        return utils.entities.get_time_zone(code)
    except ValueError:
        if "_" not in code:
            raise
        time_zone = utils.entities.get_time_zone(code.split("_")[0])
        logging.warning(
            f"No time zone for {code} in utils.entities. Using the time zone "
            f"of its country ({time_zone}). Set it in TIME_ZONES if it differs."
        )
        return time_zone


def _get_public_holidays(code: str, years: range) -> set:
    """
    Get the public holidays of a country or subdivision.

    Parameters
    ----------
    code : str
        The code of the country or subdivision (e.g., PHL_LU).
    years : range
        The years of the public holidays.

    Returns
    -------
    set
        The dates of the public holidays, or an empty set if the country
        or subdivision is not in the holidays package.
    """
    country_code = pycountry_convert.country_alpha3_to_country_alpha2(
        code.split("_")[0]
    )
    try:
        public_holidays = holidays.country_holidays(
            country_code, subdiv=HOLIDAY_SUBDIVISIONS.get(code), years=years
        )
    except NotImplementedError:
        logging.warning(
            f"No public holidays for {code} in the holidays package. Only "
            "Saturdays and Sundays use the weekend shape."
        )
        return set()
    return set(public_holidays)


def _get_ukpn_diurnal_profiles_path() -> str:
    """
    Get the path of the UKPN diurnal profiles.

    Returns
    -------
    str
        The path of diurnal_profiles.csv in the UKPN results of
        UKPN_DATE, or in the latest UKPN results if UKPN_DATE is None.

    Raises
    ------
    FileNotFoundError
        If there are no UKPN diurnal profiles.
    """
    if UKPN_DATE is not None:
        dates = [UKPN_DATE]
    else:
        dates = sorted(
            (
                folder
                for folder in os.listdir(UKPN_DIRECTORY)
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder)
            ),
            reverse=True,
        )

    for date in dates:
        path = os.path.join(UKPN_DIRECTORY, date, "diurnal_profiles.csv")
        if os.path.exists(path):
            return path

    raise FileNotFoundError(
        f"No UKPN diurnal profiles found in {UKPN_DIRECTORY}. Run "
        "ukpn_data_centres.py first."
    )


def get_hourly_shapes(diurnal_profiles_path: str) -> pandas.DataFrame:
    """
    Get the hourly weekday and weekend shapes from the UKPN profiles.

    Parameters
    ----------
    diurnal_profiles_path : str
        The path of the UKPN diurnal profiles.

    Returns
    -------
    pandas.DataFrame
        The normalised shape (1 = site average), weighted by
        DC_TYPE_WEIGHTS, by day type (weekday or weekend) and local hour
        of the day.

    Raises
    ------
    ValueError
        If a data centre type of DC_TYPE_WEIGHTS is not in the UKPN
        profiles, or if the weights do not sum to a positive value.
    """
    diurnal_profiles = pandas.read_csv(diurnal_profiles_path)

    missing_types = set(DC_TYPE_WEIGHTS) - set(diurnal_profiles["dc_type"])
    if missing_types:
        raise ValueError(
            f"The data centre types {sorted(missing_types)} are not in "
            f"{diurnal_profiles_path}."
        )
    total_weight = sum(DC_TYPE_WEIGHTS.values())
    if total_weight <= 0:
        raise ValueError("The weights of the data centre types must sum to > 0.")

    # Weight the shapes of the data centre types.
    shapes = diurnal_profiles.pivot(
        index=["day_type", "half_hour"],
        columns="dc_type",
        values="mean_normalised",
    )
    shapes = (
        sum(shapes[dc_type] * weight for dc_type, weight in DC_TYPE_WEIGHTS.items())
        / total_weight
    ).rename("shape")

    # Average the two half-hours of each hour (e.g., 00:00 and 00:30 for
    # the hour starting at 00:00).
    shapes = shapes.reset_index()
    shapes["hour"] = shapes["half_hour"].str[:2].astype(int)
    return shapes.groupby(["day_type", "hour"])["shape"].mean().reset_index()


def build_hourly_profile(
    hourly_shapes: pandas.DataFrame,
    start_date: str,
    end_date: str,
    code: str,
    capacity_mw: float | None,
) -> pandas.DataFrame:
    """
    Build the hourly demand profile of the data centres of a code.

    Parameters
    ----------
    hourly_shapes : pandas.DataFrame
        The output of get_hourly_shapes.
    start_date : str
        The first day of the profile (DATE_FORMAT).
    end_date : str
        The last day of the profile (DATE_FORMAT), included.
    code : str
        The code of the country or subdivision (e.g., PHL_LU).
    capacity_mw : float or None
        The capacity of the data centres of the country or subdivision.

    Returns
    -------
    pandas.DataFrame
        The hourly profile with the local and UTC time, the day type, the
        normalised demand (mean of 1 over the period), and the demand in
        MW if capacity_mw, UTILISATION, OCCUPANCY are set.
    """
    start = datetime.strptime(start_date, DATE_FORMAT)
    end = datetime.strptime(end_date, DATE_FORMAT)
    if end < start:
        raise ValueError(f"The end date {end_date} is before {start_date}.")

    local_time = pandas.Series(
        pandas.date_range(
            start,
            end.replace(hour=23),
            freq="h",
            tz=_get_time_zone(code),
        )
    )

    # Get the day type of each hour.
    is_weekend = local_time.dt.dayofweek >= 5
    if TREAT_HOLIDAYS_AS_WEEKENDS:
        public_holidays = _get_public_holidays(code, range(start.year, end.year + 1))
        is_weekend |= local_time.dt.date.isin(public_holidays)

    profile = pandas.DataFrame(
        {
            "Time (UTC)": local_time.dt.tz_convert("UTC"),
            "Local time": local_time,
            "day_type": is_weekend.map({False: "Weekday", True: "Weekend"}),
            "hour": local_time.dt.hour,
        }
    )

    # Map each hour to the shape of its day type and local hour.
    profile = profile.merge(hourly_shapes, on=["day_type", "hour"], how="left")

    # Rescale the profile so that its mean over the period is 1.
    profile["Normalised demand"] = profile["shape"] / profile["shape"].mean()
    profile = profile.rename(columns={"day_type": "Day type"}).drop(
        columns=["hour", "shape"]
    )

    utilisation = _get_parameter(UTILISATION, code)
    occupancy = _get_parameter(OCCUPANCY, code)
    pue = _get_parameter(PUE, code)
    if None not in (capacity_mw, utilisation, occupancy, pue):
        average_demand = capacity_mw * utilisation * pue * occupancy
        profile["Demand (MW)"] = average_demand * profile["Normalised demand"]
        logging.info(
            f"Average demand: {average_demand:.3f} MW "
            f"({capacity_mw} MW x {utilisation} x {occupancy} x PUE {pue})."
        )

    return profile


def plot_profile(
    hourly_shapes: pandas.DataFrame,
    profile: pandas.DataFrame,
    code: str,
    file_path: str,
) -> None:
    """
    Plot the hourly shapes and the first two weeks of the profile.

    Parameters
    ----------
    hourly_shapes : pandas.DataFrame
        The output of get_hourly_shapes.
    profile : pandas.DataFrame
        The output of build_hourly_profile.
    code : str
        The code of the subdivision (e.g., PHL_LU).
    file_path : str
        The path of the figure.
    """
    fig, axes = plt.subplots(
        1, 2, figsize=(14, 5), gridspec_kw={"width_ratios": [1, 2]}
    )

    for day_type, shape in hourly_shapes.groupby("day_type"):
        axes[0].plot(shape["hour"], shape["shape"], marker="o", label=day_type)
    axes[0].set_xticks(range(0, 24, 3))
    axes[0].set_xlabel("Local hour")
    axes[0].set_ylabel("UKPN utilisation / site mean")
    axes[0].set_title("Hourly shapes")
    axes[0].legend()

    column = "Demand (MW)" if "Demand (MW)" in profile else "Normalised demand"
    two_weeks = profile[
        profile["Local time"] < profile["Local time"].iloc[0] + pandas.Timedelta(days=14)
    ]
    axes[1].plot(two_weeks["Local time"], two_weeks[column])
    axes[1].set_xlabel(f"Local time ({profile['Local time'].dt.tz})")
    axes[1].set_ylabel(column)
    axes[1].set_title("First two weeks of the profile")
    axes[1].tick_params(axis="x", rotation=30)

    for ax in axes:
        ax.grid(True, linestyle="--", alpha=0.6)
    weights = ", ".join(f"{t}: {w}" for t, w in DC_TYPE_WEIGHTS.items())
    fig.suptitle(
        f"{code} data centres, {SCENARIO} scenario, {YEAR} capacity: "
        f"hourly demand profile ({weights})",
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(file_path, dpi=150)
    plt.close(fig)


def run() -> None:
    """
    Build and save the hourly demand profile of the data centres of each
    country or subdivision of CAPACITY_MW.

    Each profile is saved in
    data/data_centre_demand_profiles/<ISO Alpha-3 code>/<YYYY-MM-DD>/ as a
    CSV and a Parquet file with a figure, named
    <code>_data_centre_demand_<scenario>_<year>_<start>_<end>_<YYYYmmdd-HHMMSS>
    where <year> is the year of the capacity (e.g.,
    phl_lu_data_centre_demand_high_2030_20250101_20251231_20260930-120000).
    """
    diurnal_profiles_path = _get_ukpn_diurnal_profiles_path()
    logging.info(f"Reading the UKPN diurnal profiles from {diurnal_profiles_path}.")

    hourly_shapes = get_hourly_shapes(diurnal_profiles_path)

    # Name the files with the period of the profile and the current time,
    # so that previous runs are not overwritten.
    date_current = datetime.now().strftime("%Y-%m-%d")
    time_current = datetime.now().strftime("%Y%m%d-%H%M%S")
    start, end = (
        datetime.strptime(date, DATE_FORMAT).strftime("%Y%m%d")
        for date in (START_DATE, END_DATE)
    )

    scenario = re.sub(r"\W+", "_", SCENARIO.strip().lower()).strip("_")

    for code, capacity_mw in CAPACITY_MW.items():
        logging.info(
            f"Building the hourly profile of {code} ({SCENARIO} scenario, "
            f"{YEAR} capacity: {capacity_mw} MW)."
        )
        profile = build_hourly_profile(
            hourly_shapes, START_DATE, END_DATE, code, capacity_mw
        )

        # Save the files in a sub-folder of the country and of the
        # current date (YYYY-MM-DD).
        result_directory = os.path.join(
            RESULT_DIRECTORY, code.split("_")[0], date_current
        )
        os.makedirs(result_directory, exist_ok=True)
        file_path = os.path.join(
            result_directory,
            f"{code.lower()}_data_centre_demand_{scenario}_{YEAR}_"
            f"{time_current}",
        )
        profile.to_csv(f"{file_path}.csv", index=False)
        profile.to_parquet(f"{file_path}.parquet", index=False)
        plot_profile(hourly_shapes, profile, code, f"{file_path}.png")

        logging.info(
            f"Saved the hourly profile of {code} ({len(profile)} hours) to "
            f"{file_path}.csv."
        )


def run_all(
    year: int = 2030,
    scenarios: list[str] | None = None,
    countries: list[str] | None = None,
    skip_zero_capacity: bool = True,
) -> None:
    """
    Build and save the profiles of all scenarios and countries.

    For each scenario and country, the capacity and the conversion
    parameters are read from the workbook, and run() saves one profile
    for each grid node of the country.

    Parameters
    ----------
    year : int, optional
        The year of the capacity: 2026 (existing) or 2030 (added by
        2030).
    scenarios : list[str], optional
        The scenarios. By default, all the scenarios of the workbook.
    countries : list[str], optional
        The ISO Alpha-3 codes of the countries. By default, all the
        countries of the workbook.
    skip_zero_capacity : bool, optional
        Whether to skip the grid nodes without capacity, whose profile
        would only contain zeros.
    """
    # The settings are module-level variables read by run() and the
    # functions it calls, so they are reassigned for each combination.
    global SCENARIO, YEAR, COUNTRY, CAPACITY_MW, OCCUPANCY, UTILISATION, PUE

    scenarios = scenarios or dc_scenarios.SCENARIOS
    countries = countries or list(dc_scenarios.NODES)

    for scenario in scenarios:
        for country in countries:
            SCENARIO, YEAR, COUNTRY = scenario, year, country

            CAPACITY_MW = dc_scenarios.get_capacities(scenario, year, country)
            if skip_zero_capacity:
                CAPACITY_MW = {
                    code: mw for code, mw in CAPACITY_MW.items() if mw > 0
                }
            if not CAPACITY_MW:
                logging.info(
                    f"Skipping {country} ({scenario} scenario, {year}): no "
                    "grid node with capacity."
                )
                continue

            if USE_WORKBOOK_PARAMETERS:
                parameters = dc_scenarios.get_conversion_parameters(
                    scenario, country
                )
                OCCUPANCY = parameters["Occupancy"]
                UTILISATION = parameters["Utilisation"]
                PUE = parameters["PUE"]

            logging.info(f"Running {country}, {scenario} scenario, {year}.")
            run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    # Build the profiles of the capacity added by 2030 for all scenarios,
    # countries, and grid nodes. Use run() instead to build only the
    # profiles of SCENARIO, YEAR, and COUNTRY defined above.
    run_all(year=2030)
