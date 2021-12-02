
import datetime
import pytest
from ckan.plugins import toolkit
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.tests import factories


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestGeographyAutoComplete:
    def setup(self):
        factories.Geography(
            pcode='20IRQ015',
            iso3='IRQ',
            gis_name='Ninewa',
            hierarchy_pcode='20IRQ015',
            last_modified=datetime.datetime(2021,11,10,3,4,5),
        )
        factories.Geography(
            pcode='20IRQ015004',
            iso3='IRQ',
            gis_name='Mosul',
            hierarchy_pcode='20IRQ015004',
            last_modified=datetime.datetime(2021,11,10,3,4,6),
        )
        factories.Geography(
            pcode='IRQr000019225',
            iso3='IRQ',
            gis_name='Mosul',
            hierarchy_pcode='20IRQ015004159',
            last_modified=datetime.datetime(2021,11,10,3,4,7),
        )
        self.user = core_factories.User()

    def test_valid(self):
        results = toolkit.get_action('geography_autocomplete')(
            {'user': self.user['name']},
            {'q': 'mos'}
        )

        assert ['Mosul', 'Mosul'] == [r['gis_name'] for r in results[0]['children']]

    def test_only_active(self):
        factories.Geography(
            pcode='IRQr000013901',
            iso3='IRQ',
            gis_name='Mosul Jadida',
            gis_status='inactive',  # inactive geographies should be excluded
            hierarchy_pcode='20IRQ015004160'
        )

        results = toolkit.get_action('geography_autocomplete')(
            {'user': self.user['name']},
            {'q': 'mos'}
        )

        assert ['Mosul', 'Mosul'] == [r['gis_name'] for r in results[0]['children']]

    def test_missing_q(self):
        with pytest.raises(toolkit.ValidationError):
            toolkit.get_action('geography_autocomplete')(
                {'user': self.user['name']},
                {}
            )


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestGeographyShow:

    def setup(self):
        self.geog = factories.Geography()
        self.user = core_factories.User()

    def test_valid(self):
        geog = toolkit.get_action('geography_show')(
            {'user': self.user['name']},
            {'id': self.geog.pcode}
        )
        assert self.geog.pcode == geog['pcode']
        assert self.geog.display_full_name == geog['name']

    def test_invalid_id(self):
        with pytest.raises(toolkit.ObjectNotFound):
            toolkit.get_action('geography_show')(
                {'user': self.user['name']},
                {'id': 'not-an-id'}
            )

    def test_missing_id(self):
        with pytest.raises(toolkit.ValidationError):
            toolkit.get_action('geography_show')(
                {'user': self.user['name']},
                {}
            )
