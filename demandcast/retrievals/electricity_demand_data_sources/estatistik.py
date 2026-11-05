# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module builds 10-minute electricity demand profiles for Sabah
    and Sarawak (Malaysia).

    1. The monthly electricity consumption of Sabah and Sarawak is read
       from table "Jadual 18.3 Sbh & Swk" of the DOSM eStatistik
       "B18 Pertanian & Elektrik" workbooks, which are downloaded
       manually. Each workbook is a vintage (e.g. 12_2024 = published
       with data up to Dec 2024). Workbooks overlap, so for each month
       the value from the latest vintage is kept.
    2. The 10-minute load of Peninsular Malaysia (GSO) gives the load
       shape: for each local month, the share of each 10-minute
       interval's energy (MW * 1/6 h) in the monthly energy.
    3. Load profile of Sabah/Sarawak = share * monthly consumption,
       converted back from energy per 10 minutes to MW.

    The latest GSO file of Peninsular Malaysia (MYS_PEN_gso.csv) in the
    most recent dated folder of data/electricity_demand is used, and the
    outputs are saved in that same folder.

    Data corrections:
    - Sabah, Mar and Apr 2022: the reported values (147 and 168 GWh,
      against ~470 GWh in the surrounding months) are treated as
      errors. They are rebuilt from the month-on-month changes of 2023:
      Mar 2022 = Feb 2022 + (Mar 2023 - Feb 2023) and
      Apr 2022 = Mar 2022 + (Apr 2023 - Mar 2023).
    - Sarawak, 2023: the latest vintages report ~2,100 GWh per month,
      well below 2022 and 2024. The values of the 12_2023 vintage are
      used instead.

    Data caveats:
    - Sarawak, 2022: the monthly values are flagged as estimates ("e")
      in the source and are almost flat (~2,730 GWh every month), so
      the seasonality of 2022 comes only from the Peninsular load
      shape within each month, not from the monthly totals.
    - Most recent monthly values of both regions are flagged as
      estimates and may be revised in future vintages.

    Source: https://www.dosm.gov.my (eStatistik, Table 18.3)

    Usage (from the demandcast/demandcast folder):
        uv run python retrievals/electricity_demand_data_sources/estatistik.py
"""  # noqa: W505

import logging
import pathlib
import re

import pandas

# Folder with the manually downloaded eStatistik workbooks.
ESTATISTIK_FOLDER = (
    pathlib.Path(__file__).resolve().parents[1]
    / "socio_economic_data_sources"
    / "manual_downloads"
    / "estatistik"
)

# Folder with the retrieved electricity demand data, in dated subfolders
# (YYYY-MM-DD). The 10-minute load of Peninsular Malaysia from GSO is
# read from the latest one that contains it.
ELECTRICITY_DEMAND_FOLDER = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "electricity_demand"
)
PENINSULAR_LOAD_FILE_NAME = "MYS_PEN_gso.csv"

# Use the values of a specific vintage (file "..._MM_YYYY") instead of
# the latest one, as {(region, year): "YYYY-MM"}.
VINTAGE_OVERRIDES = {("Sarawak", 2023): "2023-12"}

SHEET_NAME = "Jadual 18.3 Sbh & Swk"
TIME_ZONE = "Asia/Kuala_Lumpur"

# Map demandcast codes to the regions in the eStatistik table.
CODE_TO_REGION = {"MYS_SAB": "Sabah", "MYS_SAR": "Sarawak"}

# Minimum share of 10-minute intervals that must be present in a month
# of the Peninsular load for it to be used as a load shape. Missing
# intervals would otherwise concentrate the monthly energy in fewer
# intervals.
MIN_MONTHLY_COVERAGE = 0.95

# Malay and English month abbreviations (first three letters).
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mac": 3,
    "mar": 3,
    "apr": 4,
    "mei": 5,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ogo": 8,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "oct": 10,
    "nov": 11,
    "dis": 12,
    "dec": 12,
}


def redistribute() -> bool:
    """
    Return a boolean indicating if the data can be redistributed.

    Returns
    -------
    bool
        True if the data can be redistributed, False otherwise.
    """
    logging.debug("Derived from DOSM statistics and GSO load data.")
    return False


def get_available_requests(code: str | None = None) -> None:
    """
    Get the available requests.

    All the data is built at once, so there are no separate requests.

    Parameters
    ----------
    code : str, optional
        The code of the subdivision.

    Returns
    -------
    None
    """
    return None


def get_url() -> str:
    """
    Get the URL of the eStatistik website.

    Returns
    -------
    str
        The URL of the data source.
    """
    return "https://www.dosm.gov.my/portal-main/release-content/estatistik"


def _to_number(value) -> float | None:
    """
    Convert a cell to a number.

    Text such as "2,123.6r" (revised) is cleaned. Flags such as "e" or
    "p" that contain no number return None.
    """
    if isinstance(value, (int, float)):
        return None if pandas.isna(value) else float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.\-]", "", value.replace(",", ""))
        if re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
            return float(cleaned)
    return None


def _get_vintage(file_path: pathlib.Path) -> pandas.Timestamp:
    """
    Get the vintage of a workbook from its file name (e.g. "..._12_2024").
    """
    match = re.search(r"(\d{2})_(\d{4})\.xlsx?$", file_path.name)
    if match is None:
        raise ValueError(f"Cannot read the vintage from {file_path.name}.")
    return pandas.Timestamp(
        year=int(match.group(2)), month=int(match.group(1)), day=1
    )


def _read_workbook(file_path: pathlib.Path) -> pandas.DataFrame:
    """
    Read the monthly consumption of Sabah and Sarawak from one workbook.

    The column positions differ between vintages, so each monthly row
    is located by its month label, and the numbers to its right are
    read in order: Sabah generation, Sabah consumption, Sarawak
    generation, Sarawak consumption.

    Parameters
    ----------
    file_path : pathlib.Path
        The path of the workbook.

    Returns
    -------
    pandas.DataFrame
        Monthly consumption in GWh, indexed by month start, with columns
        "Sabah" and "Sarawak".
    """
    sheet = pandas.read_excel(file_path, sheet_name=SHEET_NAME, header=None)

    records = []
    year = None
    for row in sheet.itertuples(index=False):
        cells = list(row)

        # Find the month label in the first columns. The year is in a
        # cell before it (e.g. 2013, "2017 p", "2021p") and only on the
        # first month of each year, so it is carried forward.
        month = None
        month_column = None
        for column, cell in enumerate(cells[:4]):
            if isinstance(cell, str) and cell.strip()[:3].lower() in MONTHS:
                month = MONTHS[cell.strip()[:3].lower()]
                month_column = column
                break
            year_match = re.match(r"^\s*(\d{4})", str(cell))
            if year_match and 1990 < int(year_match.group(1)) < 2100:
                year = int(year_match.group(1))

        if month is None or year is None:
            continue

        numbers = [
            number
            for number in map(_to_number, cells[month_column + 1 :])
            if number is not None
        ]

        if len(numbers) == 4:
            sabah, sarawak = numbers[1], numbers[3]
        elif len(numbers) == 2:
            # Only Sabah is reported (e.g. Jan 2013 in some vintages).
            sabah, sarawak = numbers[1], None
        else:
            logging.warning(
                f"{file_path.name}: unexpected row for {year}-{month:02d}: "
                f"{cells}. Skipping."
            )
            continue

        records.append(
            {
                "month": pandas.Timestamp(year=year, month=month, day=1),
                "Sabah": sabah,
                "Sarawak": sarawak,
            }
        )

    return pandas.DataFrame(records).set_index("month")


def read_monthly_consumption() -> pandas.DataFrame:
    """
    Read the monthly consumption of Sabah and Sarawak from all vintages.

    For months reported in several workbooks, the value from the latest
    vintage is kept, separately for Sabah and Sarawak.

    Returns
    -------
    pandas.DataFrame
        Monthly consumption in GWh, indexed by month start, with columns
        "Sabah" and "Sarawak".
    """
    file_paths = sorted(
        (
            path
            for path in ESTATISTIK_FOLDER.iterdir()
            # Skip the "~$" lock files that Excel creates for open files.
            if path.suffix in (".xls", ".xlsx")
            and not path.name.startswith("~$")
        ),
        key=_get_vintage,
    )
    if not file_paths:
        raise FileNotFoundError(f"No workbooks found in {ESTATISTIK_FOLDER}.")

    monthly_consumption = None
    vintages = {}
    for file_path in file_paths:
        logging.info(f"Reading {file_path.name}.")
        vintage = _read_workbook(file_path)
        vintages[_get_vintage(file_path)] = vintage
        if monthly_consumption is None:
            monthly_consumption = vintage
        else:
            # Values of the newer vintage replace the older ones; months
            # missing in the newer vintage keep the older values.
            monthly_consumption = vintage.combine_first(monthly_consumption)

    monthly_consumption = monthly_consumption.sort_index()

    # Use specific vintages where the latest values are implausible.
    for (region, year), vintage_month in VINTAGE_OVERRIDES.items():
        values = vintages[pandas.Timestamp(vintage_month)].loc[str(year), region]
        logging.info(
            f"Using the {vintage_month} vintage for {region} {year} "
            f"({values.sum():.0f} GWh instead of "
            f"{monthly_consumption.loc[str(year), region].sum():.0f} GWh)."
        )
        monthly_consumption.loc[values.index, region] = values

    return _fix_sabah_2022(monthly_consumption)


def _fix_sabah_2022(monthly_consumption: pandas.DataFrame) -> pandas.DataFrame:
    """
    Rebuild the implausible Sabah values of Mar and Apr 2022.

    Each month is the previous month plus the change between the same
    two months of 2023:
    Mar 2022 = Feb 2022 + (Mar 2023 - Feb 2023) and
    Apr 2022 = Mar 2022 + (Apr 2023 - Mar 2023).

    Parameters
    ----------
    monthly_consumption : pandas.DataFrame
        Monthly consumption in GWh, indexed by month start.

    Returns
    -------
    pandas.DataFrame
        The monthly consumption with the corrected values.
    """
    sabah = monthly_consumption["Sabah"]
    for month in (3, 4):
        current = pandas.Timestamp(year=2022, month=month, day=1)
        previous = pandas.Timestamp(year=2022, month=month - 1, day=1)
        change_2023 = (
            sabah[pandas.Timestamp(year=2023, month=month, day=1)]
            - sabah[pandas.Timestamp(year=2023, month=month - 1, day=1)]
        )
        corrected = sabah[previous] + change_2023
        logging.info(
            f"Sabah {current:%Y-%m}: replacing {sabah[current]:.1f} GWh "
            f"with {corrected:.1f} GWh."
        )
        sabah[current] = corrected

    monthly_consumption["Sabah"] = sabah
    return monthly_consumption


def find_peninsular_load_file() -> pathlib.Path:
    """
    Find the latest GSO file of Peninsular Malaysia.

    Returns
    -------
    pathlib.Path
        The MYS_PEN_gso.csv file in the most recent dated subfolder
        (YYYY-MM-DD) of the electricity demand folder.
    """
    candidates = [
        folder / PENINSULAR_LOAD_FILE_NAME
        for folder in ELECTRICITY_DEMAND_FOLDER.iterdir()
        if folder.is_dir()
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder.name)
        and (folder / PENINSULAR_LOAD_FILE_NAME).exists()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No {PENINSULAR_LOAD_FILE_NAME} found in the dated subfolders "
            f"of {ELECTRICITY_DEMAND_FOLDER}. Retrieve the GSO data for "
            "MYS_PEN first."
        )

    latest = max(candidates, key=lambda path: path.parent.name)
    logging.info(f"Using the Peninsular load from {latest}.")
    return latest


def read_peninsular_load(file_path: pathlib.Path) -> pandas.Series:
    """
    Read the 10-minute load of Peninsular Malaysia from GSO.

    Parameters
    ----------
    file_path : pathlib.Path
        The path of the MYS_PEN_gso.csv file.

    Returns
    -------
    pandas.Series
        The load in MW, indexed by local time (Asia/Kuala_Lumpur).
    """
    load = pandas.read_csv(file_path, index_col="Time (UTC)", parse_dates=True)[
        "Load (MW)"
    ]
    load.index = load.index.tz_localize("UTC").tz_convert(TIME_ZONE)

    return load.dropna().sort_index()


def get_load_shape(peninsular_load: pandas.Series) -> pandas.Series:
    """
    Get the share of each 10-minute interval in its monthly energy.

    The energy of each interval is MW * 1/6 h; the shares sum to 1 in
    each local month. Months with less than MIN_MONTHLY_COVERAGE of the
    expected intervals are removed.

    Parameters
    ----------
    peninsular_load : pandas.Series
        The 10-minute load in MW, indexed by local time.

    Returns
    -------
    pandas.Series
        The share of each interval in its monthly energy.
    """
    interval_energy = peninsular_load / 6  # MWh per 10 minutes
    month = interval_energy.index.tz_localize(None).to_period("M")

    monthly_energy = interval_energy.groupby(month).transform("sum")
    load_shape = interval_energy / monthly_energy

    # Remove months with too many missing intervals.
    count = interval_energy.groupby(month).count()
    expected = pandas.Series(
        [period.days_in_month * 24 * 6 for period in count.index],
        index=count.index,
    )
    coverage = count / expected
    incomplete = coverage[coverage < MIN_MONTHLY_COVERAGE]
    for period, value in incomplete.items():
        logging.warning(
            f"Peninsular load covers {value:.0%} of {period}. Month skipped."
        )

    return load_shape[~month.isin(incomplete.index)]


def download_and_extract_data(
    code: str, peninsular_load_file: pathlib.Path | None = None
) -> pandas.Series:
    """
    Build the 10-minute load profile of Sabah or Sarawak.

    Parameters
    ----------
    code : str
        The code of the subdivision ("MYS_SAB" or "MYS_SAR").
    peninsular_load_file : pathlib.Path, optional
        The GSO file of Peninsular Malaysia. If None, the latest one is
        used.

    Returns
    -------
    pandas.Series
        The load in MW, indexed by local time (Asia/Kuala_Lumpur).
    """
    if code not in CODE_TO_REGION:
        raise ValueError(
            f"Code {code} is not supported. Supported codes: "
            f"{list(CODE_TO_REGION)}."
        )
    region = CODE_TO_REGION[code]

    # Monthly consumption in MWh (the table is in million kWh = GWh).
    monthly_consumption = read_monthly_consumption()[region].dropna() * 1000
    monthly_consumption.index = monthly_consumption.index.to_period("M")

    if peninsular_load_file is None:
        peninsular_load_file = find_peninsular_load_file()
    load_shape = get_load_shape(read_peninsular_load(peninsular_load_file))
    month = load_shape.index.tz_localize(None).to_period("M")

    # Keep only months with both a load shape and a monthly value.
    in_both = month.isin(monthly_consumption.index)
    load_shape, month = load_shape[in_both], month[in_both]

    # Energy per interval (MWh) = share * monthly energy; MW = MWh * 6.
    load = load_shape * monthly_consumption.reindex(month).to_numpy() * 6

    logging.info(
        f"{code}: built {len(load)} 10-minute values from "
        f"{month.min()} to {month.max()}."
    )

    return load.rename("Load (MW)")


def main() -> None:
    """
    Build and save the load profiles of Sabah and Sarawak.

    The files are saved next to the latest Peninsular load file, in the
    same format (time in UTC, load in MW).
    """
    peninsular_load_file = find_peninsular_load_file()
    for code in CODE_TO_REGION:
        load = download_and_extract_data(code, peninsular_load_file)
        load.index = load.index.tz_convert("UTC").tz_localize(None)
        load.index.name = "Time (UTC)"

        output = peninsular_load_file.parent / f"{code}_estatistik"
        load.to_frame().to_csv(output.with_suffix(".csv"))
        load.to_frame().to_parquet(output.with_suffix(".parquet"))
        logging.info(f"Saved {output.with_suffix('.csv')}.")


# Data source of the 10-minute profile of each Malaysian subdivision.
SOURCE_BY_CODE = {"MYS_PEN": "gso", "MYS_SAB": "estatistik", "MYS_SAR": "estatistik"}


def resample_to_hourly(
    code: str, year: int = 2025, folder: pathlib.Path | None = None
) -> pandas.Series:
    """
    Resample the 10-minute load profile of a subdivision to hourly.

    Steps:
    1. Read the 10-minute profile ({code}_{source}.parquet) and keep
       the local year (Asia/Kuala_Lumpur).
    2. Resample: each hour is the mean of the six 10-minute values in
       it, labelled by the start of the hour.
    3. Fill: hours without any 10-minute value (gaps in the GSO data)
       are filled by linear interpolation.
    4. Rescale (Sabah and Sarawak only): each local month is scaled so
       that its hourly energy equals the monthly consumption from
       eStatistik. The Peninsula is measured data and is not rescaled.

    The result is saved as {code}_hr_{source}.csv and .parquet in the
    same folder.

    Parameters
    ----------
    code : str
        The code of the subdivision ("MYS_PEN", "MYS_SAB" or "MYS_SAR").
    year : int, optional
        The local year to keep.
    folder : pathlib.Path, optional
        The folder with the 10-minute profile. If None, the folder of
        the latest Peninsular load file is used.

    Returns
    -------
    pandas.Series
        The hourly load in MW, indexed by time in UTC.
    """
    if code not in SOURCE_BY_CODE:
        raise ValueError(
            f"Code {code} is not supported. Supported codes: "
            f"{list(SOURCE_BY_CODE)}."
        )
    source = SOURCE_BY_CODE[code]

    if folder is None:
        folder = find_peninsular_load_file().parent

    load = pandas.read_csv(
        folder / f"{code}_{source}.csv", index_col="Time (UTC)", parse_dates=True
    )["Load (MW)"]

    # Select the local year, then resample to hourly means.
    load.index = load.index.tz_localize("UTC").tz_convert(TIME_ZONE)
    load = load[load.index.year == year]
    hourly_load = load.resample("1h", label="left", closed="left").mean()

    # Fill hours without any 10-minute values by linear interpolation,
    # as for MYS_PEN_hr_gso.
    expected_hours = pandas.date_range(
        f"{year}-01-01", f"{year + 1}-01-01", freq="1h", tz=TIME_ZONE,
        inclusive="left",
    )
    hourly_load = hourly_load.reindex(expected_hours)
    missing_hours = hourly_load.isna().sum()
    if missing_hours:
        logging.warning(
            f"{code} {year}: {missing_hours} hours without data, filled by "
            "linear interpolation."
        )
        hourly_load = hourly_load.interpolate(
            method="linear", limit_direction="both"
        )

    # Rescale each month to the monthly consumption (MWh). Hourly MW
    # summed over a month is the monthly energy in MWh.
    if code in CODE_TO_REGION:
        monthly_consumption = (
            read_monthly_consumption()[CODE_TO_REGION[code]] * 1000
        )
        monthly_consumption.index = monthly_consumption.index.to_period("M")

        month = hourly_load.index.tz_localize(None).to_period("M")
        hourly_energy = hourly_load.groupby(month).transform("sum")
        target_energy = monthly_consumption.reindex(month).to_numpy()
        scale = target_energy / hourly_energy.to_numpy()

        if pandas.isna(scale).any():
            raise ValueError(
                f"{code} {year}: monthly consumption missing for "
                f"{sorted(set(month[pandas.isna(scale)].astype(str)))}."
            )
        logging.info(
            f"{code} {year}: monthly scale factors between "
            f"{scale.min():.4f} and {scale.max():.4f}."
        )
        hourly_load = hourly_load * scale

    hourly_load.index = hourly_load.index.tz_convert("UTC").tz_localize(None)
    hourly_load.index.name = "Time (UTC)"
    hourly_load.name = "Load (MW)"

    output = folder / f"{code}_hr_{source}"
    hourly_load.to_frame().to_csv(output.with_suffix(".csv"))
    hourly_load.to_frame().to_parquet(output.with_suffix(".parquet"))
    logging.info(
        f"Saved {len(hourly_load)} hourly values to "
        f"{output.with_suffix('.csv')}."
    )

    return hourly_load


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
    for code in SOURCE_BY_CODE:
        resample_to_hourly(code, year=2025)
