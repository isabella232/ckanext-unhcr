# -*- coding: utf-8 -*-

import json
from time import sleep
import requests
from requests.exceptions import RequestException
from retry import retry
from sqlalchemy import func, text
from ckan import model
from ckanext.unhcr.models import (
    Geography,
    GisStatus,
    ADMIN1,
    ADMIN2,
    COUNTRY,
    POC,
    PRP,
)


def get_gis_status(properties):
    """
    This covers two cases:

    1. Towns and cities are generally stable over time (although sometimes
    something like a Refugee Camp or temporary settlement may disappear).
    This means most Reference Places just have a gis_status == null.
    We can consider this to be the same as "active" for our purposes.

    2. Countries are not versioned - the record just won't have a
    gis_status key so we just assume all countries are active
    """
    if not properties.get('gis_status', None):
        return GisStatus.ACTIVE

    # If gis_status exists and is not NULL,
    # it should be either 13 (active) or 14 (inactive)
    gis_status_lookup = {
        13: GisStatus.INACTIVE,
        14: GisStatus.ACTIVE
    }
    return gis_status_lookup[properties['gis_status']]


def get_geography_record(layer, feature):
    properties = feature['properties']

    if 'hierarchy_pcode' not in properties:
        properties['hierarchy_pcode'] = properties['pcode']

    return Geography(
        pcode=properties['pcode'],
        iso3=properties['iso3'],
        gis_name=properties['gis_name'],
        gis_status=get_gis_status(properties),
        layer=layer,
        hierarchy_pcode=properties['hierarchy_pcode'],
        secondary_territory=properties['secondary_territory'],
    )


@retry(RequestException, tries=3, delay=10)
def request_wrapper(*args, **kwargs):
    """
    The Geoportal API is quite flaky and sometimes responds with a error
    but then the same request works a few seconds later.

    Wrapping this function with a retry decorator mitigates this
    """
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r


def merge_dicts(*args):
    out_dct = {}
    for arg in args:
        out_dct.update(arg)
    return out_dct


def upsert_features(session, features):
    existing_features = session.query(
        Geography
    ).filter(
        Geography.pcode.in_(features.keys())
    ).all()

    for rec in existing_features:
        # merge features that already exist in the DB, pop them off as we go
        session.merge(features.pop(rec.pcode))

    # add anything we've got left that didn't match an existing record
    session.add_all(features.values())


def print_summary(session):
    summary = session.query(
        Geography.layer,
        Geography.gis_status,
        func.count().label('count'),
    ).group_by(
        Geography.layer,
        Geography.gis_status,
    )
    print('Summary of Geography table:')
    print('---')
    for row in summary:
        print(
            '{} | {} | {}'.format(
                row.layer.ljust(26),
                row.gis_status.ljust(9),
                str(row.count).rjust(7)
            )
        )


URL_TEMPLATE = 'https://gis.unhcr.org/arcgis/rest/services/core_v2/{}/MapServer/0/query'


LAYERS = [
    COUNTRY['layer_name'],
    ADMIN1['layer_name'],
    ADMIN2['layer_name'],

    # Order is significant here. We import the PRPs first,
    # then we import PoCs and overwrite layer='wrl_prp_p_unhcr_PoC'
    # for any PRPs that are also a PoC.
    PRP['layer_name'],
    POC['layer_name'],
]


BASE_PARAMS = {
    # values we have chosen
    'where': 'gis_name IS NOT NULL',
    'outFields': '*',
    'returnGeometry': 'false',  # for now
    'orderByFields': 'globalid',
    'outSR': '4326',
    'f': 'geojson',

    # defaults
    'datumTransformation': '',
    'gdbVersion': '',
    'geometry': '',
    'geometryPrecision': '',
    'geometryType': 'esriGeometryEnvelope',
    'groupByFieldsForStatistics': '',
    'inSR': '',
    'maxAllowableOffset': '',
    'objectIds': '',
    'outStatistics': '',
    'parameterValues': '',
    'queryByDistance': '',
    'rangeValues': '',
    'relationParam': '',
    'resultOffset': '',
    'resultRecordCount': '',
    'returnCountOnly': 'false',
    'returnDistinctValues': 'false',
    'returnExtentsOnly': 'false',
    'returnIdsOnly': 'false',
    'returnM': 'false',
    'returnTrueCurves': 'false',
    'returnZ': 'false',
    'spatialRel': 'esriSpatialRelIntersects',
    'text': '',
    'time': '',
}


def import_geographies(data={}, verbose=False, **kwargs):
    """
    Countries are not versioned, so the first thing we're going to to is
    set all the countries to inactive but not commit the transaction yet.

    When we start looping over layers,
    the first layer we will process is the countries.

    When we call .commit() for the first time at the end of the first loop:
    - Any countries in the ArcGIS layer will be upserted
      (and we'll set the gis_status to GisStatus.ACTIVE)
    - Any countries that were in our DB but aren't in the ArcGIS layer
      will be set to inactive

    data parameter it's a dict and used to track this process internals
        even if the process failed or not finished
    kwargs is used to override default query params
      *****
      If we use the "where" param to update only some countries,
        we need to skip the inactivation for all countries
      *****
    """

    model.Session.query(
        Geography
    ).filter(
        text(kwargs.get('where', 'gis_name IS NOT NULL'))
    ).update(
        {Geography.gis_status: GisStatus.INACTIVE},
        synchronize_session=False
    )

    data['finished'] = False
    data['imported_geos'] = 0
    for layer in LAYERS:
        base_url = URL_TEMPLATE.format(layer)
        has_next_page = True
        pagination_params = {
            'resultOffset': 0,
            'resultRecordCount': 1000,
        }

        while has_next_page:
            print("calling {} with resultOffset {}".format(
                base_url,
                pagination_params['resultOffset']
            ))
            final_query_params = merge_dicts(BASE_PARAMS, pagination_params, kwargs)
            r = request_wrapper(
                base_url,
                params=final_query_params
            )
            """
            Note we are passing r.content (bytes) to json.loads() here instead
            of r.json() here because the responses are not served with the
            correct character encoding header. This causes requests to decode
            the response incorrectly and .json() gives us mangled text.
            """
            geoj = json.loads(r.content)
            # Server can respond with status=200 and "error" in the response
            if geoj.get('error'):
                data['error'] = geoj['error']
                print('ERROR in query: {}'.format(data['error']))
                break
            features = geoj['features']
            if verbose:
                print('Page content {} features.'.format(len(features)))

            if len(features) == 0:
                print(' - No features found in layer {}'.format(layer))
                break

            for feature in features:
                feature['properties']['secondary_territory'] = bool(int(feature['properties'].get('secondary_territory', 0)))

                if 'pcode' not in feature['properties']:
                    # secondary territories don't have pCode but a objectid field)
                    # for countries, we just want the ISO3 (to detect parents properly)
                    
                    if feature['properties']['secondary_territory']:
                        pcode = '{}-{}'.format(
                            feature['properties']['iso3'],
                            feature['properties'].get('objectid')
                        )
                    else:
                        pcode = feature['properties']['iso3']

                    feature['properties']['pcode'] = pcode
            
                if verbose:
                    print(' - {} {} {}: {}'.format(
                        feature['properties'].get('pcode'),
                        feature['properties'].get('iso3'),
                        feature['properties'].get('hierarchy_pcode'),
                        feature['properties'].get('gis_name')
                        )
                    )
            print("importing {} features..".format(len(features)))

            features_to_upsert = {
                f['properties']['pcode']: get_geography_record(layer, f)
                for f in features
            }
            upsert_features(model.Session, features_to_upsert)
            model.Session.commit()

            sleep(5)  # avoid the ban-hammer
            has_next_page = bool(geoj.get('exceededTransferLimit'))
            pagination_params['resultOffset'] = (
                pagination_params['resultOffset'] +
                pagination_params['resultRecordCount']
            )
            data['imported_geos'] += len(features)

    print('\n..Finished importing geographies')
    print_summary(model.Session)
    data['finished'] = True
