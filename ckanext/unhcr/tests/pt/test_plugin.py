# -*- coding: utf-8 -*-

import pytest
import mock
from ckan.plugins import toolkit
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.models import DEFAULT_GEOGRAPHY_CODE
from ckanext.unhcr.tests import factories, mocks


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestHooks(object):

    def setup(self):

        self.user = core_factories.Sysadmin(name='sysadmin', id='sysadmin')
        self.kobo_user = factories.InternalKoBoUser(name='kobo_user', id='kobo_user')

        self.container = factories.DataContainer(
            users=[
                {'name': self.kobo_user['name'], 'capacity': 'editor'},
            ]
        )

        self.dataset = factories.Dataset(owner_org=self.container['id'])
        self.resource = factories.Resource(
            package_id=self.dataset['id'],
            url_type='upload',
        )

        self.new_package_dict = {
            'external_access_level': 'public_use',
            'keywords': ['1'],
            'archived': 'False',
            'data_collector': 'test',
            'data_collection_technique': 'nf',
            'name': 'test',
            'notes': 'test',
            'unit_of_measurement': 'test',
            'title': 'test',
            'owner_org': self.container['id'],
            'state': 'active',
            'geographies': DEFAULT_GEOGRAPHY_CODE,
        }
        self.new_resource_dict = {
            'package_id': self.dataset['id'],
            'url': 'http://fakeurl/test.txt',
            'url_type': 'upload',
            'type': 'data',
            'file_type': 'microdata',
            'identifiability': 'anonymized_public',
            'date_range_start': '2018-01-01',
            'date_range_end': '2019-01-01',
            'process_status': 'anonymized',
            'visibility': 'public',
            'version': '1',
        }

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_resource_create_hook_called(self, mock_hook):
        action = toolkit.get_action("resource_create")
        resource = action({'user': self.user['name']}, self.new_resource_dict)
        mock_hook.assert_called_once()
        assert 'process_dataset_on_update' == mock_hook.call_args_list[0][0][0].__name__
        assert resource['package_id'] == mock_hook.call_args_list[0][0][1][0]

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_resource_create_hook_not_called(self, mock_hook):
        action = toolkit.get_action("resource_create")
        action({'user': self.user['name'], 'job': True}, self.new_resource_dict)
        mock_hook.assert_not_called()

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_create_hook_called(self, mock_hook):
        action = toolkit.get_action("package_create")
        dataset = action({'user': self.user['name']}, self.new_package_dict)
        mock_hook.assert_called_once()
        assert 'process_dataset_on_create' == mock_hook.call_args_list[0][0][0].__name__
        assert dataset['id'] == mock_hook.call_args_list[0][0][1][0]

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_create_hook_not_called_job(self, mock_hook):
        action = toolkit.get_action("package_create")
        dataset = action({'user': self.user['name'], 'job': True}, self.new_package_dict)
        mock_hook.assert_not_called()

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_create_hook_not_called_defer_commit(self, mock_hook):
        action = toolkit.get_action("package_create")
        dataset = action({'user': self.user['name'], 'defer_commit': True}, self.new_package_dict)
        mock_hook.assert_not_called()

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_create_hook_not_called_not_active(self, mock_hook):
        action = toolkit.get_action("package_create")
        self.new_package_dict['state'] = 'pending'
        dataset = action({'user': self.user['name']}, self.new_package_dict)
        mock_hook.assert_not_called()

    @mock.patch('ckanext.unhcr.kobo.kobo_dataset.KoboDataset.create_kobo_resources')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_total_submissions')
    def test_after_package_create_hook_kobo(self, submissions, mock_hook):
        """ New datasets using 'kobo_asset_id' should be initilized """
        submissions.return_value = 1
        action = toolkit.get_action("package_create")
        self.new_package_dict['kobo_asset_id'] = 'test_id01'
        dataset = action({'user': self.kobo_user['name']}, self.new_package_dict)
        mock_hook.assert_called_once()

    @mock.patch('ckanext.unhcr.kobo.kobo_dataset.KoboDataset.create_kobo_resources')
    def test_after_package_create_no_hook_kobo(self, mock_hook):
        """ New datasets NOT using 'kobo_asset_id' should NOT be initilized """
        action = toolkit.get_action("package_create")
        dataset = action({'user': self.user['name']}, self.new_package_dict)
        mock_hook.assert_not_called()

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_resource_update_hook_called(self, mock_hook):
        action = toolkit.get_action("resource_update")
        action({'user': self.user['name']}, self.resource)
        assert mock_hook.call_count == 2
        assert 'process_dataset_on_update' == mock_hook.call_args_list[0][0][0].__name__
        assert self.resource['package_id'] == mock_hook.call_args_list[0][0][1][0]
        assert 'process_dataset_on_update' == mock_hook.call_args_list[1][0][0].__name__
        assert self.resource['package_id'] == mock_hook.call_args_list[1][0][1][0]

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_resource_update_hook_not_called(self, mock_hook):
        action = toolkit.get_action("resource_update")
        action({'user': self.user['name'], 'job': True}, self.resource)
        mock_hook.assert_not_called()

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_resource_patch_hook_called(self, mock_hook):
        action = toolkit.get_action("resource_patch")
        action({'user': self.user['name']}, {'id': self.resource['id'], 'description': 'asdf'})
        assert mock_hook.call_count == 2
        assert 'process_dataset_on_update' == mock_hook.call_args_list[0][0][0].__name__
        assert self.resource['package_id'] == mock_hook.call_args_list[0][0][1][0]
        assert 'process_dataset_on_update' == mock_hook.call_args_list[1][0][0].__name__
        assert self.resource['package_id'] == mock_hook.call_args_list[1][0][1][0]

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_resource_patch_hook_not_called(self, mock_hook):
        action = toolkit.get_action("resource_patch")
        action({'user': self.user['name'], 'job': True}, {'id': self.resource['id'], 'description': 'asdf'})
        mock_hook.assert_not_called()

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_update_hook_called(self, mock_hook):
        action = toolkit.get_action("package_update")
        action({'user': self.user['name']}, self.dataset)
        mock_hook.assert_called_once()
        assert 'process_dataset_on_update' == mock_hook.call_args_list[0][0][0].__name__
        assert self.dataset['id'] == mock_hook.call_args_list[0][0][1][0]

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_update_hook_not_called(self, mock_hook):
        action = toolkit.get_action("package_update")
        action({'user': self.user['name'], 'job': True}, self.dataset)
        action({'user': self.user['name'], 'defer_commit': True}, self.dataset)
        self.dataset['state'] = 'pending'
        action({'user': self.user['name']}, self.dataset)
        mock_hook.assert_not_called()

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_patch_hook_called(self, mock_hook):
        action = toolkit.get_action("package_patch")
        action({'user': self.user['name']}, {'id': self.dataset['id'], 'version': 2})
        mock_hook.assert_called_once()
        assert 'process_dataset_on_update' == mock_hook.call_args_list[0][0][0].__name__
        assert self.dataset['id'] == mock_hook.call_args_list[0][0][1][0]

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_patch_hook_not_called(self, mock_hook):
        action = toolkit.get_action("package_patch")
        action({'user': self.user['name'], 'job': True}, {'id': self.dataset['id'], 'version': 2})
        action({'user': self.user['name'], 'defer_commit': True}, {'id': self.dataset['id'], 'version': 3})
        action({'user': self.user['name']}, {'id': self.dataset['id'], 'state': 'pending'})
        action({'user': self.user['name']}, {'id': self.dataset['id'], 'version': 4})
        mock_hook.assert_not_called()

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_resource_delete_hook_called(self, mock_hook):
        action = toolkit.get_action("resource_delete")
        action({'user': self.user['name']}, {'id': self.resource['id']})
        mock_hook.assert_called_once()
        assert 'process_dataset_on_update' == mock_hook.call_args_list[0][0][0].__name__
        assert self.resource['package_id'] == mock_hook.call_args_list[0][0][1][0]

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_resource_delete_hook_not_called(self, mock_hook):
        action = toolkit.get_action("resource_delete")
        action({'user': self.user['name'], 'job': True}, self.resource)
        mock_hook.assert_not_called()

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_delete_hook_called(self, mock_hook):
        action = toolkit.get_action("package_delete")
        action({'user': self.user['name']}, {'id': self.dataset['id']})
        assert 'process_dataset_on_delete' == mock_hook.call_args_list[0][0][0].__name__
        assert self.dataset['id'] == mock_hook.call_args_list[0][0][1][0]

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_after_package_delete_hook_not_called(self, mock_hook):
        action = toolkit.get_action("package_delete")
        action({'user': self.user['name'], 'job': True}, self.dataset)
        mock_hook.assert_not_called()
