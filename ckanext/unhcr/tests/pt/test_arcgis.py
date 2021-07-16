import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import ckanext.unhcr.arcgis as arcgis
import pytest
import responses
from ckan import model
from ckanext.unhcr.models import Geography, GisStatus
from requests.exceptions import HTTPError
from sqlalchemy import func


def _mock_json_call(url, json_file, *, method=responses.GET, status=200, **kwargs):
    body = json.load(open(json_file, encoding="utf-8"))
    responses.add(method, url, json=body, status=status, **kwargs)


def _mock_arcgis_api_calls(layers):
    base_path = Path(__file__).parent / 'arcgis_responses'
    for layer in layers:
        _mock_json_call(
            arcgis.URL_TEMPLATE.format(layer),
            base_path / 'onepage' / f'{layer}.json',
        )


def _run_import():
    with redirect_stdout(StringIO()):
        arcgis.import_geographies()


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
@responses.activate
def test_importer():
    _mock_arcgis_api_calls(arcgis.LAYERS)

    _run_import()

    totals = {
        t.layer: t.count for t in
        model.Session.query(
            Geography.layer,
            func.count().label('count')
        ).group_by(
            Geography.layer
        ).all()
    }

    assert 3 == totals['wrl_polbnd_int_1m_a_unhcr']
    assert 3 == totals['wrl_polbnd_adm1_a_unhcr']
    assert 3 == totals['wrl_polbnd_adm2_a_unhcr']

    # wrl_prp_p_unhcr_ALL contains 4 total records, 3 of them are also PoCs
    assert 3 == totals['wrl_prp_p_unhcr_PoC']
    assert 4 == totals['wrl_prp_p_unhcr_ALL'] + totals['wrl_prp_p_unhcr_PoC']


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
@responses.activate
def test_pagination():
    layers = [
        'wrl_polbnd_int_1m_a_unhcr',
        'wrl_polbnd_adm2_a_unhcr',
        'wrl_prp_p_unhcr_PoC',
        'wrl_prp_p_unhcr_ALL',
    ]
    _mock_arcgis_api_calls(layers)

    base_path = Path(__file__).parent / 'arcgis_responses'
    _mock_json_call(
        arcgis.URL_TEMPLATE.format('wrl_polbnd_adm1_a_unhcr'),
        base_path / 'paginated' / 'wrl_polbnd_adm1_a_unhcr_page1.json',
    )
    _mock_json_call(
        arcgis.URL_TEMPLATE.format('wrl_polbnd_adm1_a_unhcr'),
        base_path / 'paginated' / 'wrl_polbnd_adm1_a_unhcr_page2.json',
    )

    _run_import()

    total = model.Session.query(
        Geography.layer,
        func.count().label('count')
    ).group_by(
        Geography.layer
    ).filter(
        Geography.layer == 'wrl_polbnd_adm1_a_unhcr'
    ).all()

    assert 6 == total[0].count


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
@responses.activate
def test_flaky_api_recovery():
    # introduce some noise
    responses.add(
        responses.GET,
        arcgis.URL_TEMPLATE.format('wrl_polbnd_int_1m_a_unhcr'),
        json={'error': 'oh no'},
        status=500
    )
    for i in range(0, 2):
        responses.add(
            responses.GET,
            arcgis.URL_TEMPLATE.format('wrl_prp_p_unhcr_ALL'),
            json={'error': 'oh no'},
            status=500
        )

    _mock_arcgis_api_calls(arcgis.LAYERS)

    # if some requests fail we will retry them and the import will continue
    _run_import()

    total = model.Session.query(
        func.count(Geography.globalid).label('count')
    ).all()

    assert 13 == total[0].count


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
@responses.activate
def test_bad_api_response():
    for i in range(0, 4):
        responses.add(
            responses.GET,
            arcgis.URL_TEMPLATE.format('wrl_polbnd_int_1m_a_unhcr'),
            json={'error': 'oh no'},
            status=500
        )

    _mock_arcgis_api_calls(arcgis.LAYERS)

    # if the same request fails consistently, we should eventually fail
    with pytest.raises(HTTPError):
        _run_import()


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
@responses.activate
def test_deactivate_country():
    # Create dummy record Yugoslavia
    # this country won't be in our list of current countries when we import
    arcgis.upsert_features(
        model.Session,
        {
            'YUG': Geography(
                globalid='YUG',
                pcode='YUG',
                iso3='YUG',
                gis_name='Yugoslavia',
                gis_status=GisStatus.ACTIVE,
                layer='wrl_polbnd_int_1m_a_unhcr',
                hierarchy_pcode='YUG',
            )
        },
    )
    model.Session.commit()

    _mock_arcgis_api_calls(arcgis.LAYERS)

    _run_import()

    yugoslavia = model.Session.query(
        Geography
    ).filter(
        Geography.globalid == 'YUG'
    ).one()

    assert GisStatus.INACTIVE == yugoslavia.gis_status
