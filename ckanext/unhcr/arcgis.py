from time import sleep
import requests


LAYERS = [
    'wrl_polbnd_int_1m_a_unhcr',
    'wrl_prp_p_unhcr_PoC',
    'wrl_polbnd_adm1_a_unhcr',
    'wrl_polbnd_adm2_a_unhcr',
    'wrl_prp_p_unhcr_ALL',
]


base_params = {
    # values we have chosen
    'where': '1=1',
    'outFields': '*',
    'returnGeometry': 'false',  # for now
    'orderByFields': 'objectid',
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


def _merge_dicts(*args):
    out_dct = {}
    for arg in args:
        out_dct.update(arg)
    return out_dct


def import_geographies():
    for layer in LAYERS:
        base_url = 'https://gis.unhcr.org/arcgis/rest/services/core_v2/{}/MapServer/0/query'.format(layer)
        has_next_page = True
        pagination_params = {
            'resultOffset': 0,
            'resultRecordCount': 1000,
        }

        while has_next_page:
            r = requests.get(
                base_url,
                params=_merge_dicts(base_params, pagination_params)
            )
            r.raise_for_status()
            geoj = r.json()

            # TODO: insert data in table(s)

            sleep(5)  # avoid the ban-hammer
            has_next_page = bool(geoj.get('exceededTransferLimit'))
            pagination_params['resultOffset'] = (
                pagination_params['resultOffset'] +
                pagination_params['resultRecordCount']
            )
