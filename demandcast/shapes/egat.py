# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This script generates the shapes of the four regions of Thailand
    used with the data of the Electricity Generating Authority of
    Thailand (EGAT) and of the National Statistical Office of Thailand
    (NSO):

    - THA_CEN: Metropolitan and Central (Bangkok Metropolis and the NSO
      Central Region, which includes the provinces often classed as
      East and West, e.g., Chon Buri, Rayong, and Kanchanaburi);
    - THA_NOR: North (NSO Northern Region);
    - THA_NEA: Northeast (NSO Northeastern Region);
    - THA_SOU: South (NSO Southern Region).

    The 77 provinces are grouped as in the NSO registered population
    data (retrievals/socio_economic_data_sources/nso_thailand.py), so
    that the shapes match the population of the regions. The regions of
    the Natural Earth database are not used, as they differ from the
    NSO regions (e.g., Nakhon Sawan and Uthai Thani are in the NSO
    Northern Region).

    Sources:
    - https://www.egat.co.th
    - https://www.nso.go.th (Statistical Data Warehouse)
"""

import os

import cartopy.io.shapereader
import geopandas
import pandas

# Define the region of each province, as named in the NSO data.
codes_of_thai_provinces = {
    # THA_CEN: 26 provinces.
    "Ang Thong": "THA_CEN",
    "Bangkok": "THA_CEN",
    "Chachoengsao": "THA_CEN",
    "Chai Nat": "THA_CEN",
    "Chanthaburi": "THA_CEN",
    "Chon Buri": "THA_CEN",
    "Kanchanaburi": "THA_CEN",
    "Lop Buri": "THA_CEN",
    "Nakhon Nayok": "THA_CEN",
    "Nakhon Pathom": "THA_CEN",
    "Nonthaburi": "THA_CEN",
    "Pathum Thani": "THA_CEN",
    "Phetchaburi": "THA_CEN",
    "Phra Nakhon Si Ayutthaya": "THA_CEN",
    "Prachin Buri": "THA_CEN",
    "Prachuap Khiri Khan": "THA_CEN",
    "Ratchaburi": "THA_CEN",
    "Rayong": "THA_CEN",
    "Sa Kaeo": "THA_CEN",
    "Samut Prakan": "THA_CEN",
    "Samut Sakhon": "THA_CEN",
    "Samut Songkhram": "THA_CEN",
    "Saraburi": "THA_CEN",
    "Sing Buri": "THA_CEN",
    "Suphan Buri": "THA_CEN",
    "Trat": "THA_CEN",
    # THA_NOR: 17 provinces.
    "Chiang Mai": "THA_NOR",
    "Chiang Rai": "THA_NOR",
    "Kamphaeng Phet": "THA_NOR",
    "Lampang": "THA_NOR",
    "Lamphun": "THA_NOR",
    "Mae Hong Son": "THA_NOR",
    "Nakhon Sawan": "THA_NOR",
    "Nan": "THA_NOR",
    "Phayao": "THA_NOR",
    "Phetchabun": "THA_NOR",
    "Phichit": "THA_NOR",
    "Phitsanulok": "THA_NOR",
    "Phrae": "THA_NOR",
    "Sukhothai": "THA_NOR",
    "Tak": "THA_NOR",
    "Uthai Thani": "THA_NOR",
    "Uttaradit": "THA_NOR",
    # THA_NEA: 20 provinces.
    "Amnat Charoen": "THA_NEA",
    "Bueng Kan": "THA_NEA",
    "Buri Ram": "THA_NEA",
    "Chaiyaphum": "THA_NEA",
    "Kalasin": "THA_NEA",
    "Khon Kaen": "THA_NEA",
    "Loei": "THA_NEA",
    "Maha Sarakham": "THA_NEA",
    "Mukdahan": "THA_NEA",
    "Nakhon Phanom": "THA_NEA",
    "Nakhon Ratchasima": "THA_NEA",
    "Nong Bua Lam Phu": "THA_NEA",
    "Nong Khai": "THA_NEA",
    "Roi Et": "THA_NEA",
    "Sakon Nakhon": "THA_NEA",
    "Si Sa Ket": "THA_NEA",
    "Surin": "THA_NEA",
    "Ubon Ratchathani": "THA_NEA",
    "Udon Thani": "THA_NEA",
    "Yasothon": "THA_NEA",
    # THA_SOU: 14 provinces.
    "Chumphon": "THA_SOU",
    "Krabi": "THA_SOU",
    "Nakhon Si Thammarat": "THA_SOU",
    "Narathiwat": "THA_SOU",
    "Pattani": "THA_SOU",
    "Phang Nga": "THA_SOU",
    "Phatthalung": "THA_SOU",
    "Phuket": "THA_SOU",
    "Ranong": "THA_SOU",
    "Satun": "THA_SOU",
    "Songkhla": "THA_SOU",
    "Surat Thani": "THA_SOU",
    "Trang": "THA_SOU",
    "Yala": "THA_SOU",
}

# Define the names of the provinces in the Natural Earth database that
# differ from the NSO names (after normalisation).
aliases_of_thai_provinces = {"Bangkok Metropolis": "Bangkok"}

# Define the names of the Thai subdivisions.
names_of_thai_subdivisions = {
    "THA_CEN": "Metropolitan and Central",
    "THA_NOR": "North",
    "THA_NEA": "Northeast",
    "THA_SOU": "South",
}


def _normalise(name: str) -> str:
    """Normalise a province name (e.g., "Chon Buri" and "Chonburi")."""
    return name.lower().replace(" ", "").replace("-", "")


# Define the region of each province by its normalised name.
codes_by_normalised_name = {
    _normalise(name): code for name, code in codes_of_thai_provinces.items()
}

# Load the shapefile containing the subdivision shapes from the Natural
# Earth database. The 10m resolution is used because the 50m
# resolution does not include the provinces of Thailand.
all_shapes = cartopy.io.shapereader.natural_earth(
    resolution="10m", category="cultural", name="admin_1_states_provinces"
)

# Define a reader for the shapefile.
reader = cartopy.io.shapereader.Reader(all_shapes)

# Read the shapefiles of all Thai provinces.
province_shapes = [
    shape
    for shape in list(reader.records())
    if shape.attributes["iso_a2"] == "TH"
]

# Get the region of each province, and check that all the provinces are
# mapped to a region.
regions_of_provinces = {}
for province_shape in province_shapes:
    name = province_shape.attributes["name"]
    name = aliases_of_thai_provinces.get(name, name)
    regions_of_provinces[province_shape.attributes["name"]] = (
        codes_by_normalised_name.get(_normalise(name))
    )
unmapped_provinces = sorted(
    name for name, code in regions_of_provinces.items() if code is None
)
if unmapped_provinces:
    raise ValueError(
        "The following provinces are not mapped to a subdivision: "
        f"{', '.join(unmapped_provinces)}."
    )
if len(province_shapes) != len(codes_of_thai_provinces):
    raise ValueError(
        f"Expected {len(codes_of_thai_provinces)} provinces, but found "
        f"{len(province_shapes)} in the Natural Earth database."
    )

# Create a DataFrame from the shapes of the provinces.
provinces = pandas.DataFrame(columns=["name", "code", "parent", "geometry"])
for province_shape in province_shapes:
    province = pandas.Series(
        {
            "name": province_shape.attributes["name"],
            "code": province_shape.attributes["iso_3166_2"],
            "parent": regions_of_provinces[province_shape.attributes["name"]],
            "geometry": province_shape.geometry,
        }
    )
    provinces = pandas.concat(
        [provinces, province.to_frame().T], ignore_index=True
    )

# Add the coordinate reference system to the GeoDataFrame.
provinces = geopandas.GeoDataFrame(
    provinces, geometry="geometry", crs="EPSG:4326"
)

# Merge the provinces belonging to the same subdivision.
subdivisions = provinces.dissolve(by="parent")

# Reset the index of the GeoDataFrame.
subdivisions = subdivisions.reset_index()

# Drop the columns that are not needed.
subdivisions = subdivisions[["name", "parent", "geometry"]]

# Rename the columns of the GeoDataFrame.
subdivisions = subdivisions.rename(columns={"parent": "code"})

# Add the names of the subdivisions to the GeoDataFrame.
for subdivision_code in subdivisions["code"]:
    subdivisions.loc[subdivisions["code"] == subdivision_code, "name"] = (
        names_of_thai_subdivisions[subdivision_code]
    )

# Set the precision of the geometry to a grid size of 0.005 degrees.
# This is done to remove small spikes in the shapes that cause issues
# when plotting the shapes.
subdivisions["geometry"] = subdivisions["geometry"].set_precision(0.005)

# Add the coordinate reference system (CRS) to the shapefile.
subdivisions = subdivisions.set_crs(epsg=4326)

# Save the shapes of the subdivisions to a shapefile.
shapes_dir = os.path.join(os.path.dirname(__file__), "egat")
os.makedirs(shapes_dir, exist_ok=True)
subdivisions.to_file(
    os.path.join(shapes_dir, "egat.shp"), driver="ESRI Shapefile"
)
