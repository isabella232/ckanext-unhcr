# -*- coding: utf-8 -*-

import pytest
import mock
from ckan import model
from ckan.plugins import toolkit
from ckan.tests import helpers as core_helpers
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.tests import factories, mocks


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestDatastoreAuthRestrictedDownloads(object):

    def setup(self):
        # Users
        self.normal_user = core_factories.User()
        self.org_user = core_factories.User()
        self.sysadmin = core_factories.Sysadmin()

        # Containers
        self.container = factories.DataContainer(
            users=[
                {'name': self.org_user['name'], 'capacity': 'member'},
            ]
        )

        # Datasets
        self.dataset = factories.Dataset(
            owner_org=self.container['id'],
        )
        self.resource = factories.Resource(
            package_id=self.dataset['id'],
            url_type='datastore',
            upload=mocks.FakeFileStorage(),
            visibility='restricted',
        )

        # Actions
        core_helpers.call_action('datastore_create',
            resource_id=self.resource['id'],
            records=[{'a': 1, 'b': 2}],
            force=True,
        )

    def _get_context(self, user):
        return {
            'user': user['name'],
            'model': model,
        }

    def test_datastore_info_perms(self):

        context = self._get_context(self.normal_user)
        with pytest.raises(toolkit.NotAuthorized):
            core_helpers.call_auth(
                'datastore_info',
                context=context,
                id=self.resource['id'],
            )

        context = self._get_context(self.org_user)
        assert core_helpers.call_auth('datastore_info', context=context,
            id=self.resource['id'])

        context = self._get_context(self.sysadmin)
        assert core_helpers.call_auth('datastore_info', context=context,
            id=self.resource['id'])

    def test_datastore_search_perms(self):

        context = self._get_context(self.normal_user)
        with pytest.raises(toolkit.NotAuthorized):
            core_helpers.call_auth(
                'datastore_search',
                context=context,
                resource_id=self.resource['id'],
            )

        context = self._get_context(self.org_user)
        assert core_helpers.call_auth('datastore_search', context=context,
            resource_id=self.resource['id'])

        context = self._get_context(self.sysadmin)
        assert core_helpers.call_auth('datastore_search', context=context,
            resource_id=self.resource['id'])

    def test_datastore_search_sql_perms(self):

        context = self._get_context(self.normal_user)
        context['table_names'] = [self.resource['id']]
        with pytest.raises(toolkit.NotAuthorized):
            core_helpers.call_auth(
                'datastore_search_sql',
                context=context,
                resource_id=self.resource['id'],
            )

        context = self._get_context(self.org_user)
        context['table_names'] = [self.resource['id']]
        assert core_helpers.call_auth('datastore_search_sql', context=context,
            resource_id=self.resource['id'])

        context = self._get_context(self.sysadmin)
        context['table_names'] = [self.resource['id']]
        assert core_helpers.call_auth('datastore_search_sql', context=context,
            resource_id=self.resource['id'])
