# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module povides utility functions to read the configuration
    files of various scripts.
"""

import argparse
import glob
import logging
import os
from datetime import datetime

import yaml


def read_folders_structure() -> dict[str, str]:
    """
    Read the folders structure.

    This function reads the folders structure from a yaml file located
    in the 'utils' directory. The yaml file should contain a dictionary
    where keys are folder names and values are their paths relative to
    the root folder. The root folder is determined as the parent
    directory of the current file's directory.

    Returns
    -------
    folders_structure : dict[str, str]
        A dictionary containing the folders structure, where keys are
        folder names and values are their paths.
    """
    # Get the absolute path to the root folder.
    root_folder = os.path.normpath(
        os.path.join(os.path.abspath(os.path.dirname(__file__)), "..")
    )

    # Define the default path to the yaml file.
    folders_structure_file_path = os.path.join(
        root_folder, "config", "directories_config.yaml"
    )

    # Read the folders structure from the file.
    with open(folders_structure_file_path, "r") as file:
        folders_structure = yaml.safe_load(file)

    # Add the root folder to the folders structure.
    folders_structure["root_folder"] = root_folder

    # Iterate over the folders structure, concatenate the paths if
    # multiple folders are defined, and normalize the paths.
    for key, value in folders_structure.items():
        # Add the root folder to the path but skip the root folder key.
        if key != "root_folder":
            if isinstance(value, list):
                # If the value is a list, unpack the list.
                folders_structure[key] = os.path.join(root_folder, *value)
            else:
                folders_structure[key] = os.path.join(root_folder, value)

    return folders_structure


def _is_date_folder_name(string: str) -> bool:
    """
    Check if a string is a valid date in YYYY-MM-DD format.

    Parameters
    ----------
    string : str
        The string to check.

    Returns
    -------
    bool
        True if the string is a valid date, False otherwise.
    """
    try:
        datetime.strptime(string, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def get_dated_folder(folder_key: str) -> str:
    """
    Get the folder of the current date inside a data folder.

    This function returns the path of a subfolder named after the
    current date (YYYY-MM-DD) inside the folder defined by the given
    key in the folders structure, and creates it if needed.

    Parameters
    ----------
    folder_key : str
        The key of the folder in the folders structure.

    Returns
    -------
    dated_folder : str
        The path to the folder of the current date.
    """
    dated_folder = os.path.join(
        read_folders_structure()[folder_key],
        datetime.today().strftime("%Y-%m-%d"),
    )
    os.makedirs(dated_folder, exist_ok=True)

    return dated_folder


def find_latest_files(folder_key: str, file_pattern: str) -> list[str]:
    """
    Find the most recent version of the files matching a pattern.

    This function searches the dated subfolders (YYYY-MM-DD) of the
    folder defined by the given key in the folders structure, from the
    most recent to the oldest, and then the folder itself (for files
    saved before dated subfolders were introduced). For each file name
    matching the pattern, only the most recent version is returned.

    Parameters
    ----------
    folder_key : str
        The key of the folder in the folders structure.
    file_pattern : str
        The glob pattern of the file names.

    Returns
    -------
    list[str]
        The paths to the most recent version of each matching file.
    """
    folder = read_folders_structure()[folder_key]

    if not os.path.isdir(folder):
        return []

    # Define the folders to search, from the most recent dated
    # subfolder to the oldest, followed by the folder itself.
    dated_subfolders = sorted(
        [
            os.path.join(folder, subfolder)
            for subfolder in os.listdir(folder)
            if os.path.isdir(os.path.join(folder, subfolder))
            and _is_date_folder_name(subfolder)
        ],
        reverse=True,
    )
    folders_to_search = dated_subfolders + [folder]

    # Keep the most recent version of each file name.
    latest_files: dict[str, str] = {}
    for folder_to_search in folders_to_search:
        for file_path in glob.glob(os.path.join(folder_to_search, file_pattern)):
            latest_files.setdefault(os.path.basename(file_path), file_path)

    return sorted(latest_files.values())


def find_latest_file(folder_key: str, file_name: str) -> str | None:
    """
    Find the most recent version of a file.

    Parameters
    ----------
    folder_key : str
        The key of the folder in the folders structure.
    file_name : str
        The name of the file.

    Returns
    -------
    str | None
        The path to the most recent version of the file, or None if the
        file is not found.
    """
    latest_files = find_latest_files(folder_key, glob.escape(file_name))

    return latest_files[0] if latest_files else None


def read_configuration(
    script_name: str,
    script_description: str,
) -> dict:
    """
    Read a configuration file in yaml format.

    Parameters
    ----------
    script_name : str
        The name of the script for which the configuration is read.
    script_description : str
        A brief description of the script.

    Returns
    -------
    config : dict[str, Any]
        A dictionary containing the configuration parameters.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist.
    """
    # Create a parser for the command line arguments.
    parser = argparse.ArgumentParser(description=script_description)

    # Add the argument for the config file path.
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=f"./config/{script_name}_config.yaml",
        help=(
            "The path to config file "
            f"(default: ./config/{script_name}_config.yaml)."
        ),
        required=False,
    )

    # Extract the config file path.
    config_file_path = parser.parse_args().config

    if not os.path.exists(config_file_path):
        raise FileNotFoundError(
            f"The configuration file '{config_file_path}' does not exist."
        )

    # Read the configuration file.
    with open(config_file_path, "r") as file:
        config = yaml.safe_load(file)

    return config


def set_up_logging(process: str) -> None:
    """
    Set up the logging configuration.

    Parameters
    ----------
    process : str
        The name of the process for which the logging is set up.
    """
    # Define the log file name.
    log_file_name = (
        process + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
    )

    # Get the log files directory and create it if it does not exist.
    log_files_directory = read_folders_structure()["log_files_folder"]
    os.makedirs(log_files_directory, exist_ok=True)

    # Set up the logging configuration.
    logging.basicConfig(
        filename=os.path.join(log_files_directory, log_file_name),
        level=logging.INFO,
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
