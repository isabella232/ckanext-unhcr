import datetime
import mock
import pytest
from sqlalchemy import select, and_
import ckan.model as model
from ckan.plugins import toolkit
from ckan.tests import helpers as core_helpers
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.actions import _validate_kobo_filters
from ckanext.unhcr.tests import factories, mocks


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate', 'with_request_context')
class TestResourceViews(object):

    def setup(self):

        # Users
        self.sysadmin = core_factories.Sysadmin(name='sysadmin', id='sysadmin')
        self.user1 = core_factories.User(name='user1', id='user1')
        self.user2 = core_factories.User(name='user2', id='user2')
        self.user3 = core_factories.User(name='user3', id='user3')

        # Containers
        self.container1 = factories.DataContainer(
            name='container1',
            id='container1',
            users=[
                {'name': 'user1', 'capacity': 'admin'},
            ],
        )
        self.container2 = factories.DataContainer(
            name='container2',
            id='container2',
            users=[
                {'name': 'user2', 'capacity': 'admin'},
            ],
        )

        # Datasets
        self.dataset1 = factories.Dataset(
            name='dataset1',
            title='Test Dataset 1',
            owner_org='container1',
            data_collection_technique = 'f2f',
            sampling_procedure = 'nonprobability',
            operational_purpose_of_data = 'cartography',
            user=self.user1,
        )

        # Resources
        self.resource1 = factories.Resource(
            name='resource1',
            package_id='dataset1',
            url_type='upload',
            visibility='restricted',
            upload=mocks.FakeFileStorage(),
        )

    # Helpers

    def make_resource_copy_request(self, app, dataset_id=None, resource_id=None, user=None, **kwargs):
        url = '/dataset/%s/resource_copy/%s' % (dataset_id, resource_id)
        env = {'REMOTE_USER': user.encode('ascii')} if user else {}
        resp = app.get(url=url, extra_environ=env, **kwargs)
        return resp

    def make_resource_download_request(self, app, dataset_id, resource_id, user=None, **kwargs):
        url = '/dataset/{dataset}/resource/{resource}/download'.format(
            dataset=dataset_id,
            resource=resource_id,
        )
        env = {'REMOTE_USER': user.encode('ascii')} if user else {}
        resp = app.get(url=url, extra_environ=env, **kwargs)
        return resp


    # Resource Copy

    def test_resource_copy(self, app):
        resp = self.make_resource_copy_request(
            app, dataset_id='dataset1', resource_id=self.resource1['id'], user='user1',
            status=200
        )
        assert 'action="/dataset/dataset1/resource/new"' in resp.body
        assert 'resource1 (copy)' in resp.body
        assert 'anonymized_public' in resp.body
        assert 'Add'in resp.body

    def test_resource_copy_no_access(self, app):
        resp = self.make_resource_copy_request(
            app, dataset_id='dataset1', resource_id=self.resource1['id'], user='user2',
            status=403
        )

    def test_resource_copy_bad_resource(self, app):
        resp = self.make_resource_copy_request(
            app, dataset_id='dataset1', resource_id='bad', user='user1',
            status=404
        )


    # Resource Download

    def test_resource_download_anonymous(self, app):
        resp = self.make_resource_download_request(
            app, dataset_id='dataset1', resource_id=self.resource1['id'], user=None,
            status=403
        )

    def test_resource_download_no_access(self, app):
        resp = self.make_resource_download_request(
            app, dataset_id='dataset1', resource_id=self.resource1['id'], user='user3',
            status=403
        )

    def test_resource_download_collaborator(self, app):
        core_helpers.call_action(
            'package_collaborator_create',
            id='dataset1',
            user_id='user3',
            capacity='member',
        )
        resp = self.make_resource_download_request(
            app, dataset_id='dataset1', resource_id=self.resource1['id'], user='user3',
            status=200
        )

    def test_resource_download_bad_resource(self, app):
        resp = self.make_resource_download_request(
            app, dataset_id='dataset1', resource_id='bad', user='user1',
            status=404
        )

    def test_resource_download_blocked(self, app):
        toolkit.get_action('task_status_update')(
            {
                'ignore_auth': True,
                # task_status_update wants a user object
                # for no reason, even with 'ignore_auth': True
                # give it an empty string to keep it happy
                'user': ''
            },
            {
                'entity_id': self.resource1['id'],
                'entity_type': 'resource',
                'task_type': 'clamav',
                'last_updated': datetime.datetime.utcnow().isoformat(),
                'state': 'complete',
                'key': 'clamav',
                'value': '{"data": {"status_code": 1}}',
                'error': 'null',
            }
        )

        resp = self.make_resource_download_request(
            app, dataset_id='dataset1', resource_id=self.resource1['id'], user='user1',
            status=404
        )

    def test_resource_download_valid(self, app):
        sql = select([
            model.Activity
        ]).where(
            and_(
                model.Activity.activity_type == 'download resource',
                model.Activity.object_id == self.dataset1['id'],
                model.Activity.user_id == 'user1',
            )
        )

        # before we start, this user has never downloaded this resource before
        result = model.Session.execute(sql).fetchall()
        assert 0 == len(result)

        resp = self.make_resource_download_request(
            app, dataset_id='dataset1', resource_id=self.resource1['id'], user='user1',
            status=200
        )

        # after we've downloaded the resource, we should also
        # have also logged a 'download resource' action for this user/resource
        result = model.Session.execute(sql).fetchall()
        assert 1 == len(result)

    # Resource Upload

    def test_edit_resource_works(self, app):
        url = toolkit.url_for(
            'resource.edit',
            id=self.dataset1['id'],
            resource_id=self.resource1['id']
        )
        env = {'REMOTE_USER': self.sysadmin['name'].encode('ascii')}

        # Mock a resource edit payload
        data = {
            'id': self.resource1['id'],
            'name': self.resource1['name'],
            'type': self.resource1['type'],
            'description': 'updated',
            'format': self.resource1['format'],
            'file_type': self.resource1['file_type'],
            'date_range_start': self.resource1['date_range_start'],
            'date_range_end': self.resource1['date_range_end'],
            'version': self.resource1['version'],
            'process_status': self.resource1['process_status'],
            'identifiability': self.resource1['identifiability'],
            'visibility': self.resource1['visibility'],
            'url': 'test.txt',
            'save': ''

        }

        resp = app.post(url, data=data, extra_environ=env, status=200)

        assert 'The form contains invalid entries:' not in resp.body

    def test_edit_resource_must_provide_upload(self, app):
        url = toolkit.url_for(
            'resource.edit',
            id=self.dataset1['id'],
            resource_id=self.resource1['id']
        )
        env = {'REMOTE_USER': self.sysadmin['name'].encode('ascii')}

        # Mock a resource edit payload
        data = {
            'id': self.resource1['id'],
            'name': self.resource1['name'],
            'type': self.resource1['type'],
            'description': 'updated',
            'format': self.resource1['format'],
            'file_type': self.resource1['file_type'],
            'date_range_start': self.resource1['date_range_start'],
            'date_range_end': self.resource1['date_range_end'],
            'version': self.resource1['version'],
            'process_status': self.resource1['process_status'],
            'identifiability': self.resource1['identifiability'],
            'visibility': self.resource1['visibility'],
            'url': '',
            'clear_upload': 'true',
            'save': ''

        }

        resp = app.post(url, data=data, extra_environ=env, status=200)

        assert 'The form contains invalid entries:' in resp.body
        assert 'All data resources require an uploaded file' in resp.body

@pytest.mark.usefixtures('clean_db', 'unhcr_migrate', 'with_request_context')
class TestKoboResources:

    @mock.patch('ckanext.unhcr.kobo.kobo_dataset.KoboDataset.create_kobo_resources')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_total_submissions')
    def setup(self, submissions, create_kobo_resources):

        # required to create KoBo dataset
        submissions.return_value = 1

        # Users
        self.sysadmin = core_factories.Sysadmin(name='sysadmin', id='sysadmin')
        self.kobo_user = factories.InternalKoBoUser(name='kobo_user', id='kobo_user')

        # Containers
        self.container1 = factories.DataContainer(
            name='container1',
            id='container1',
            users=[
                {'name': self.kobo_user['name'], 'capacity': 'admin'},
            ],
        )

        self.kobo_dataset = factories.Dataset(
            name='kobo-dataset',
            title='KoBo Dataset',
            owner_org='container1',
            data_collection_technique = 'f2f',
            sampling_procedure = 'nonprobability',
            operational_purpose_of_data = 'cartography',
            user=self.kobo_user,
            kobo_asset_id='test_1234',
        )

        self.kobo_resource = factories.Resource(
            name='kobo-resource',
            package_id='kobo-dataset',
            url_type='upload',
            visibility='restricted',
            upload=mocks.FakeFileStorage(),
            url='original-file.csv',
            kobo_type='data',
            kobo_details={
                'kobo_filter_fields_from_all_versions': True,
                'kobo_filter_group_sep' : '/',
                'kobo_filter_fields': ['field1', 'field2'],
                'kobo_filter_query': {'a': 1},
                'kobo_filter_multiple_select': 'both',
                'kobo_filter_hierarchy_in_labels': True,
            }
        )

    def test_edit_kobo_resource_must_preserve_upload(self, app):
        
        url = toolkit.url_for(
            'resource.edit',
            id=self.kobo_dataset['id'],
            resource_id=self.kobo_resource['id']
        )
        env = {'REMOTE_USER': self.kobo_user['name']}

        # Mock a resource edit payload
        form_data = {
            'description': 'updated',
            'url_type': 'upload',
            'upload': mocks.FakeFileStorage(filename='different-file.csv'),

            # this is manually added to the update form as hidden fields:
            'original_url': self.kobo_resource['url'],
            'kobo_type': 'data',

            'url': 'different-file.csv',
            'clear_upload': '',

            'kobo_filter_fields_from_all_versions': 'true',
            'kobo_filter_group_sep' : '/',
            'kobo_filter_fields': '',
            'kobo_filter_query': '',
            'kobo_filter_multiple_select': 'both',
            'kobo_filter_hierarchy_in_labels': 'true',
            'kobo_filter_formats': 'csv',

            'save': ''

        }
        data = dict(self.kobo_resource, **form_data)
        resp = app.post(url, data=data, extra_environ=env, status=200)

        assert 'The form contains invalid entries:' in resp.body
        assert 'You cannot update a KoBoToolbox data file directly, please re-import the data instead' in resp.body

    def test_edit_data_kobo_resource_detect_no_changes(self, app):
        """ Updating a KoBo resource with no filter changes """

        original_dict = self.kobo_resource.copy()
        # Mock a resource edit payload
        original_dict.update({
            'kobo_filter_fields_from_all_versions': 'true',
            'kobo_filter_fields': ['field1', 'field2'],
            'kobo_filter_query': "{'a': 1}",
            'kobo_filter_multiple_select': 'both',
            'kobo_filter_hierarchy_in_labels': 'true',
            'kobo_filter_formats': 'csv',
            'kobo_filter_group_sep': '/',
        })
        changes = _validate_kobo_filters(original_dict)
        print(changes)
        assert len(changes) == 0

    def test_edit_data_kobo_resource_detect_no_query_changes(self, app):
        """ Updating the query to a KoBo resource with no changes """

        original_dict = self.kobo_resource.copy()
        # Mock a resource edit payload
        original_dict.update({
            'kobo_filter_fields_from_all_versions': 'true',
            'kobo_filter_fields': ['field1', 'field2'],
            'kobo_filter_query': "{'a': 1}",
            'kobo_filter_multiple_select': 'both',
            'kobo_filter_hierarchy_in_labels': 'true',
            'kobo_filter_formats': 'csv',
            'kobo_filter_group_sep': '/',
        })
        changes = _validate_kobo_filters(original_dict)
        print(changes)
        assert len(changes) == 0

    def test_edit_data_kobo_resource_detect_changed_fields(self, app):
        """ Updating a KoBo resource must detect filter changes """

        original_dict = self.kobo_resource.copy()
        # Mock a resource edit payload
        original_dict.update({
            # only changed field
            'kobo_filter_fields_from_all_versions': 'false',

            'kobo_filter_fields': ['field1', 'field2'],
            'kobo_filter_query': "{'a': 1}",
            'kobo_filter_multiple_select': 'both',
            'kobo_filter_hierarchy_in_labels': 'true',
            'kobo_filter_formats': 'csv',
            'kobo_filter_group_sep': '/',
        })
        
        changes = _validate_kobo_filters(original_dict)
        print(changes)
        assert 'kobo_filter_fields_from_all_versions' in changes
        assert len(changes) == 1

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    @mock.patch('ckan.lib.helpers.helper_functions.datastore_dictionary')
    def test_edit_data_kobo_resource_filters_must_trigger_sync(self, dd, enqueue_job, app):
        """ Updating a KoBo resource and changing some filters should trigger a kobo resource sync """
        """ 
        #TODO datastore_dictionary uses the datastore_test db which is not ready
        It seems the "ckan datastore set-permissions" command only runs for main datastore db
        ERROR if removed:
        sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedTable) relation "_table_metadata" does not exist
        """

        url = toolkit.url_for(
            'resource.edit',
            id=self.kobo_dataset['id'],
            resource_id=self.kobo_resource['id']
        )
        env = {'REMOTE_USER': self.sysadmin['name'].encode('ascii')}

        # Mock a resource edit payload
        form_data = {
            'id': self.kobo_resource['id'],
            'name': self.kobo_resource['name'],
            'type': self.kobo_resource['type'],
            'description': 'updated',
            'format': self.kobo_resource['format'],
            'file_type': self.kobo_resource['file_type'],
            'date_range_start': self.kobo_resource['date_range_start'],
            'date_range_end': self.kobo_resource['date_range_end'],
            'version': self.kobo_resource['version'],
            'process_status': self.kobo_resource['process_status'],
            'identifiability': self.kobo_resource['identifiability'],
            'visibility': self.kobo_resource['visibility'],
            'url': self.kobo_resource['url'],
            'cache_last_updated': '',

            'kobo_type': 'data',
            'kobo_filter_fields_from_all_versions': 'true',
            'kobo_filter_group_sep' : '/',
            'kobo_filter_fields': ['field1', 'field2'],
            'kobo_filter_query': "{'a': 1}",
            'kobo_filter_multiple_select': 'both',
            # changed
            'kobo_filter_hierarchy_in_labels': 'false',

            'clear_upload': '',
            'save': 'go-metadata'

        }
        data = dict(self.kobo_resource, **form_data)
        resp = app.post(url, data=data, extra_environ=env, status=200)
        jobs_called = [fn[0][0].__name__ for fn in enqueue_job.call_args_list]
        assert 'update_kobo_resource' in jobs_called
