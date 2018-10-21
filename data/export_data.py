from collections import OrderedDict
import csv
import json
import maya
import os
import requests
from shapely import geometry
import sys

# Set up the URL and the requests session.
USERNAME = os.environ["USERNAME"]
PASSWORD = os.environ["PASSWORD"]
IDEAS_URL = "https://shareaboutsapi.poepublic.com/api/v2/louisvilleky/datasets/pb-louisville-2018/places?include_private"

session = requests.Session()
session.auth = (USERNAME, PASSWORD)
session.headers = {"Content-type": "application/json", "X-Shareabouts-Silent": "True"}

# Download all the ideas.
url = IDEAS_URL
pages = []
while url:
    print(f"Downloading from {url}", file=sys.stderr)
    response = session.get(url)
    page = response.json()
    pages.append(page)
    url = page["metadata"]["next"]

# Load in the council district boundaries.
with open("../data/districts.geojson") as districts_file:
    districts = json.load(districts_file)["features"]

for d in districts:
    d["geometry"] = geometry.shape(d["geometry"])

# Load in the neighborhood boundaries.
with open("../data/neighborhoods.geojson") as neighborhoods_file:
    neighborhoods = json.load(neighborhoods_file)["features"]

for n in neighborhoods:
    n["geometry"] = geometry.shape(n["geometry"])

# Compile the data.
def find_containing_feature(features, geom):
    g = geometry.shape(geom)
    for feature in features:
        if feature["geometry"].contains(g):
            return feature


def find_district(_, geom):
    feature = find_containing_feature(districts, geom)
    if feature is None:
        return ""
    return feature["properties"]["COUNDIST"]


def find_neighborhood(_, geom):
    feature = find_containing_feature(neighborhoods, geom)
    if feature is None:
        return ""
    return feature["properties"]["NH_NAME"]


def get_submitter_name(props, _):
    name = None

    if props["submitter"]:
        name = props["submitter"]["name"]

    if "submitter_name" in props:
        assert name is None, str(props)
        name = props["submitter_name"]

    if "private-submitter_name" in props:
        assert name is None, str(props)
        name = props["private-submitter_name"]

    return name


header_map = OrderedDict(
    [
        # Idea Information
        ("ID", "id"),
        ("Idea", "title"),
        (
            "Submitted At",
            (
                lambda props, geom: maya.parse(props["created_datetime"])
                .datetime(to_timezone="US/Eastern", naive=True)
                .isoformat()
            ),
        ),
        (
            "# of Comments",
            (
                lambda props, geom: (props["submission_sets"] or {})
                .get("comments", {})
                .get("length", 0)
            ),
        ),
        (
            "# of Support",
            (
                lambda props, geom: (props["submission_sets"] or {})
                .get("support", {})
                .get("length", 0)
            ),
        ),
        (
            "URL",
            (
                lambda props, geom: f'https://ourmoneyourvoice.herokuapp.com/place/{props["id"]}'
            ),
        ),
        # Idea Location Information
        ("Approx. Location", "location"),
        ("Lat", (lambda props, geom: geom["coordinates"][1])),
        ("Lng", (lambda props, geom: geom["coordinates"][0])),
        ("District", find_district),
        ("Neighborhood", find_neighborhood),
        # Submitter Information
        ("Submitter Name", get_submitter_name),
        ("Requested Anonymity?", "private-anonymous_name"),
        ("Submitter District/Neighborhood", "private-neighborhood"),
        ("Submitter Phone #", "private-phone"),
        ("Submitter Email", "private-email"),
        ("Submitter Preferred Contact", "private-preferred_contact"),
        ("Volunteer for Community Rep?", "private-communityrep"),
        ("Submitter ID", "user_token"),
    ]
)


def get_prop_from_idea(idea, getter):
    if isinstance(getter, str):
        return idea["properties"].get(getter)
    else:
        return getter(idea["properties"], idea["geometry"])


# Spit out the ideas
writer = csv.writer(sys.stdout)
writer.writerow(header_map.keys())
for page in pages:
    for idea in page["features"]:
        row = [get_prop_from_idea(idea, getter) for getter in header_map.values()]
        writer.writerow(row)
