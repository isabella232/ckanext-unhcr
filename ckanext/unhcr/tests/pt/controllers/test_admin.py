# -*- coding: utf-8 -*-

import pytest
from ckan.lib import search
import ckan.model as model
from ckan.plugins import toolkit
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.jobs import _process_dataset_fields
from ckanext.unhcr.tests import factories


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestAdminController(object):

    def test_index_sysadmin(self, app):
        user = core_factories.Sysadmin()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app.get('/ckan-admin', extra_environ=env, status=200)

    def test_index_not_authorized(self, app):
        user = core_factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app.get('/ckan-admin', extra_environ=env, status=403)


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate', 'with_request_context')
class TestSearchIndexController(object):

    def test_search_index_not_admin(self, app):
        user = core_factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app.get('/ckan-admin/search_index', extra_environ=env, status=403)

    def test_search_index_sysadmin(self, app):
        user = core_factories.Sysadmin()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app.get('/ckan-admin/search_index', extra_environ=env, status=200)

    def test_search_index_rebuild_not_admin(self, app):
        user = core_factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app.post('/ckan-admin/search_index/rebuild', extra_environ=env, status=403)

    def test_search_index_rebuild_sysadmin(self, app):
        user = core_factories.Sysadmin()
        data_dict = { 'q': '*:*', 'rows': 0,}
        context = { 'ignore_auth': True }

        # create a dataset
        factories.Dataset()
        package_index = search.index_for(model.Package)
        # clear the index
        package_index.clear()
        # package_search tell us there are 0 datasets
        packages = toolkit.get_action('package_search')(context, data_dict)
        assert 0 == packages['count']

        # invoke a search_index_rebuild
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app.post('/ckan-admin/search_index/rebuild', extra_environ=env, status=200)

        # now package_search will tell us there is 1 dataset
        packages = toolkit.get_action('package_search')(context, data_dict)
        assert 1 == packages['count']


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestGISSearchIndex(object):
    def setup(self):
        # these geographies are all related in a partent/child hierarchy
        self.hierarchy = {
            'IRQ': factories.Geography(
                pcode='IRQ',
                iso3='IRQ',
                gis_name='Iraq',
                hierarchy_pcode='IRQ'
            ),
            '20IRQ015': factories.Geography(
                pcode='20IRQ015',
                iso3='IRQ',
                gis_name='Ninewa',
                hierarchy_pcode='20IRQ015',
            ),
            '20IRQ015004': factories.Geography(
                pcode='20IRQ015004',
                iso3='IRQ',
                gis_name='Mosul',
                hierarchy_pcode='20IRQ015004',
            ),
            '20IRQ015004159': factories.Geography(
                pcode='IRQr000019225',
                iso3='IRQ',
                gis_name='Mosul',
                hierarchy_pcode='20IRQ015004159',
            ),
        }
        # some other geographies that aren't related to our 'main' hierarchy
        self.unrelated = {
            'BRZ': factories.Geography(
                pcode='BRZ', iso3='BRZ', gis_name='Brazil', hierarchy_pcode='BRZ'
            ),
            '20DEU010004': factories.Geography(
                pcode='20DEU010004',
                iso3='DEU',
                gis_name='Regierungsbezirk Dusseldorf',
                hierarchy_pcode='20DEU010004',
            ),
        }
        self.geogs = {**self.hierarchy, **self.unrelated}

        self.no_gis_dataset = factories.Dataset()
        self.gis_dataset1 = factories.Dataset(
            name="gis1",
            geographies=','.join([self.hierarchy['20IRQ015004159'].globalid, self.unrelated['BRZ'].globalid])
        )
        self.gis_dataset2 = factories.Dataset(
            name="gis2",
            geographies=self.unrelated['20DEU010004'].globalid
        )
        self.sysadmin = core_factories.Sysadmin(name='sysadmin', id='sysadmin')

    def test_search_geographies(self, app):

        # clear and rebuild the index
        package_index = search.index_for(model.Package)
        package_index.clear()
        search.rebuild()

        expected = []
        for key, geo in self.geogs.items():
            expected.extend([geo.gis_name, geo.pcode])

        data_dicts = [{'q': term} for term in expected]
        context = {'ignore_auth': True}
        for data_dict in data_dicts:
            packages = toolkit.get_action('package_search')(context, data_dict)

            # Check responses
            from_gis2 = [
                self.unrelated['20DEU010004'].pcode,
                self.unrelated['20DEU010004'].gis_name
            ]
            if data_dict['q'] in from_gis2:
                should_be = self.gis_dataset2['id']
            else:
                should_be = self.gis_dataset1['id']

            assert should_be in [result['id'] for result in packages['results']]
