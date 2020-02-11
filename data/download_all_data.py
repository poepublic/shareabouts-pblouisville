#/usr/bin/env python3

import csv
import functools
import itertools
import json
import multiprocessing as mp
import os
import requests
import requests.adapters
import requests.packages.urllib3.util.retry
import sys

USERNAME = os.environ["USERNAME"]
PASSWORD = os.environ["PASSWORD"]
initial_url = 'https://shareaboutsapi.poepublic.com/api/v2/louisvilleky/datasets/pb-louisville-2018/places?page_size=5&include_submissions=true&include_private=true'

def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
    session=None,
):
    session = session or requests.Session()
    retry = requests.packages.urllib3.util.retry.Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

session = requests_retry_session(retries=10)
session.auth = (USERNAME, PASSWORD)
session.headers = {"Content-type": "application/json", "X-Shareabouts-Silent": "True"}

pages = []

def download_page(session, url):
    print(f'Downloading page {url}', file=sys.stderr)
    response = session.get(url)
    page = response.json()
    return page

initial_page = download_page(session, initial_url)
pages.append(initial_page)

num_pages = initial_page['metadata']['num_pages']
page_urls = [f'{initial_url}&page={n + 1}' for n in range(1, num_pages)]

session_download_page = functools.partial(download_page, session)
with mp.Pool(8) as p:
    pages += p.map(session_download_page, page_urls)

full_data = {
    'type': 'FeatureCollection',
    'features': list(itertools.chain.from_iterable(
        page['features'] for page in pages
    ))
}

# print(json.dumps(full_data, indent=1, sort_keys=True))

comments = list(itertools.chain.from_iterable(
    feature['properties']['submission_sets'].get('comments', [])
    for feature in full_data['features']
))

comments = [
    {
        'id': c['id'],
        'place_id': c['place'].split('/')[-1],
        'comment': c['comment'],
        'submitter': c['submitter'],
        'submitter_name': c['submitter_name'],
        'created_datetime': c['created_datetime'],
        'user_token': c['user_token'],
        'visible': c['visible']
    }
    for c in filter(None, comments)
]

writer = csv.DictWriter(sys.stdout, fieldnames=['id', 'place_id', 'comment', 'submitter', 'submitter_name', 'created_datetime', 'user_token', 'visible'])
writer.writeheader()
writer.writerows(comments)
