# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This script generates the shapes of the three regions of Vietnam
    used with the data of the National Power System and Market Operator
    of Vietnam (NSMO) (retrievals/electricity_demand_data_sources/
    nsmo.py):

    - VNM_NOR: North (the 27 provinces served by the Northern Power
      Corporation, from Ha Tinh northwards, and Hanoi);
    - VNM_CEN: Central (the 13 provinces served by the Central Power
      Corporation, from Quang Binh to Khanh Hoa, and the Central
      Highlands of Kon Tum, Gia Lai, Dak Lak, and Dak Nong);
    - VNM_SOU: South (the 21 provinces served by the Southern Power
      Corporation, from Lam Dong, Ninh Thuan, and Binh Thuan southwards,
      and Ho Chi Minh City).

    The 63 provinces before the 2025 administrative reform are used, as
    in the Natural Earth database. The provinces are identified by their
    ISO 3166-2 codes, because some of the province names in the Natural
    Earth database are wrong (e.g., VN-53, Bac Kan, is named after the
    Northeast region).

    Sources:
    - https://www.nsmo.vn
    - https://www.naturalearthdata.com
"""

import os

import cartopy.io.shapereader
import geopandas

# Define the region of each province, by its ISO 3166-2 code.
codes_of_vietnamese_provinces = {
    # VNM_NOR: 28 provinces.
    "VN-01": "VNM_NOR",  # Lai Chau
    "VN-02": "VNM_NOR",  # Lao Cai
    "VN-03": "VNM_NOR",  # Ha Giang
    "VN-04": "VNM_NOR",  # Cao Bang
    "VN-05": "VNM_NOR",  # Son La
    "VN-06": "VNM_NOR",  # Yen Bai
    "VN-07": "VNM_NOR",  # Tuyen Quang
    "VN-09": "VNM_NOR",  # Lang Son
    "VN-13": "VNM_NOR",  # Quang Ninh
    "VN-14": "VNM_NOR",  # Hoa Binh
    "VN-18": "VNM_NOR",  # Ninh Binh
    "VN-20": "VNM_NOR",  # Thai Binh
    "VN-21": "VNM_NOR",  # Thanh Hoa
    "VN-22": "VNM_NOR",  # Nghe An
    "VN-23": "VNM_NOR",  # Ha Tinh
    "VN-53": "VNM_NOR",  # Bac Kan
    "VN-54": "VNM_NOR",  # Bac Giang
    "VN-56": "VNM_NOR",  # Bac Ninh
    "VN-61": "VNM_NOR",  # Hai Duong
    "VN-63": "VNM_NOR",  # Ha Nam
    "VN-66": "VNM_NOR",  # Hung Yen
    "VN-67": "VNM_NOR",  # Nam Dinh
    "VN-68": "VNM_NOR",  # Phu Tho
    "VN-69": "VNM_NOR",  # Thai Nguyen
    "VN-70": "VNM_NOR",  # Vinh Phuc
    "VN-71": "VNM_NOR",  # Dien Bien
    "VN-HN": "VNM_NOR",  # Ha Noi
    "VN-HP": "VNM_NOR",  # Hai Phong
    # VNM_CEN: 13 provinces.
    "VN-24": "VNM_CEN",  # Quang Binh
    "VN-25": "VNM_CEN",  # Quang Tri
    "VN-26": "VNM_CEN",  # Thua Thien - Hue
    "VN-DN": "VNM_CEN",  # Da Nang
    "VN-27": "VNM_CEN",  # Quang Nam
    "VN-29": "VNM_CEN",  # Quang Ngai
    "VN-31": "VNM_CEN",  # Binh Dinh
    "VN-32": "VNM_CEN",  # Phu Yen
    "VN-34": "VNM_CEN",  # Khanh Hoa
    "VN-28": "VNM_CEN",  # Kon Tum
    "VN-30": "VNM_CEN",  # Gia Lai
    "VN-33": "VNM_CEN",  # Dak Lak
    "VN-72": "VNM_CEN",  # Dak Nong
    # VNM_SOU: 22 provinces.
    "VN-35": "VNM_SOU",  # Lam Dong
    "VN-36": "VNM_SOU",  # Ninh Thuan
    "VN-40": "VNM_SOU",  # Binh Thuan
    "VN-37": "VNM_SOU",  # Tay Ninh
    "VN-39": "VNM_SOU",  # Dong Nai
    "VN-43": "VNM_SOU",  # Ba Ria - Vung Tau
    "VN-57": "VNM_SOU",  # Binh Duong
    "VN-58": "VNM_SOU",  # Binh Phuoc
    "VN-SG": "VNM_SOU",  # Ho Chi Minh City
    "VN-41": "VNM_SOU",  # Long An
    "VN-44": "VNM_SOU",  # An Giang
    "VN-45": "VNM_SOU",  # Dong Thap
    "VN-46": "VNM_SOU",  # Tien Giang
    "VN-47": "VNM_SOU",  # Kien Giang
    "VN-49": "VNM_SOU",  # Vinh Long
    "VN-50": "VNM_SOU",  # Ben Tre
    "VN-51": "VNM_SOU",  # Tra Vinh
    "VN-52": "VNM_SOU",  # Soc Trang
    "VN-55": "VNM_SOU",  # Bac Lieu
    "VN-59": "VNM_SOU",  # Ca Mau
    "VN-73": "VNM_SOU",  # Hau Giang
    "VN-CT": "VNM_SOU",  # Can Tho
}

# Define the names of the Vietnamese subdivisions.
names_of_vietnamese_subdivisions = {
    "VNM_NOR": "North",
    "VNM_CEN": "Central",
    "VNM_SOU": "South",
}

# Load the shapefile containing the subdivision shapes from the Natural
# Earth database. The 10m resolution is used because the 50m
# resolution does not include the provinces of Vietnam.
all_shapes = cartopy.io.shapereader.natural_earth(
    resolution="10m", category="cultural", name="admin_1_states_provinces"
)

# Define a reader for the shapefile.
reader = cartopy.io.shapereader.Reader(all_shapes)

# Read the shapes of all Vietnamese provinces.
province_shapes = [
    shape
    for shape in list(reader.records())
    if shape.attributes["iso_a2"] == "VN"
]

# Check that all the provinces are mapped to a region, and that all the
# mapped provinces are in the Natural Earth database.
province_codes = {shape.attributes["iso_3166_2"] for shape in province_shapes}
unmapped_provinces = sorted(
    province_codes - set(codes_of_vietnamese_provinces)
)
missing_provinces = sorted(
    set(codes_of_vietnamese_provinces) - province_codes
)
if unmapped_provinces or missing_provinces:
    raise ValueError(
        "Mismatch between the Natural Earth provinces and the mapping. "
        f"Unmapped: {unmapped_provinces}. Missing: {missing_provinces}."
    )

# Create a GeoDataFrame from the shapes of the provinces.
provinces = geopandas.GeoDataFrame(
    {
        "code": [
            codes_of_vietnamese_provinces[shape.attributes["iso_3166_2"]]
            for shape in province_shapes
        ],
        "geometry": [shape.geometry for shape in province_shapes],
    },
    geometry="geometry",
    crs="EPSG:4326",
)

# Merge the provinces belonging to the same region.
subdivisions = provinces.dissolve(by="code").reset_index()

# Add the names of the regions to the GeoDataFrame.
subdivisions["name"] = subdivisions["code"].map(
    names_of_vietnamese_subdivisions
)
subdivisions = subdivisions[["name", "code", "geometry"]]

# Set the precision of the geometry to a grid size of 0.005 degrees.
# This is done to remove small spikes in the shapes that cause issues
# when plotting the shapes.
subdivisions["geometry"] = subdivisions["geometry"].set_precision(0.005)

# Save the shapes of the regions to a shapefile.
shapes_dir = os.path.join(os.path.dirname(__file__), "nsmo")
os.makedirs(shapes_dir, exist_ok=True)
subdivisions.to_file(
    os.path.join(shapes_dir, "nsmo.shp"), driver="ESRI Shapefile"
)
