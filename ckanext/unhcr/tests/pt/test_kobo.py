import datetime
import json
import mock
import pytest
import tempfile
from ckan import model
from ckan.plugins import toolkit
from ckanext.unhcr.jobs import download_kobo_file
from ckanext.unhcr.models import DEFAULT_GEOGRAPHY_CODE
from ckanext.unhcr.tests import factories, mocks


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate', 'with_request_context')
class TestKoBo(object):

    def setup(self):
        # Users
        self.internal_user = factories.InternalUser()
        self.internal_editor_user = factories.InternalUser()
        self.kobo_user = factories.InternalKoBoUser()
        self.internal_admin_user = factories.InternalUser()
        self.external_user = factories.ExternalUser()

        self.data_container = factories.DataContainer(
            users=[
                {'name': self.internal_admin_user['name'], 'capacity': 'admin'},
                {'name': self.internal_editor_user['name'], 'capacity': 'editor'},
                {'name': self.kobo_user['name'], 'capacity': 'editor'},
            ]
        )

    # Helpers ========================
    def get_assets_list(self):
        response = json.load(open('ckanext/unhcr/kobo/api_sample_data/assets.json'))
        return response['results']

    def get_asset(self, asset_id):
        return json.load(open('ckanext/unhcr/kobo/api_sample_data/asset_{}.json'.format(asset_id)))

    # Tests ========================
    def test_internal_no_editor_user_dashboad_kobo_link_ok(self, app):
        environ = {
            'REMOTE_USER': self.internal_user['name']
        }

        resp = app.get('/dashboard/', extra_environ=environ)
        assert 'KoBoToolbox' not in resp.body

    def test_internal_editor_user_dashboad_kobo_link_ok(self, app):
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }

        resp = app.get('/dashboard/', extra_environ=environ)
        assert 'KoBoToolbox' in resp.body

    def test_internal_admin_user_dashboad_kobo_link_ok(self, app):
        environ = {
            'REMOTE_USER': self.internal_admin_user['name']
        }

        resp = app.get('/dashboard/', extra_environ=environ)
        assert 'KoBoToolbox' in resp.body

    def test_external_user_dashboad_no_kobo_link(self, app):
        environ = {
            'REMOTE_USER': self.external_user['name']
        }

        resp = app.get('/dashboard/', extra_environ=environ)
        assert 'KoBoToolbox' not in resp.body

    def test_external_user_no_kobo(self, app):
        environ = {
            'REMOTE_USER': self.external_user['name']
        }

        resp = app.get('/kobo/', extra_environ=environ)
        assert resp.status_code == 403

    def test_external_user_no_remove_kobo_token(self, app):
        environ = {
            'REMOTE_USER': self.external_user['name']
        }

        resp = app.post('/kobo/remove-token', extra_environ=environ)
        assert resp.status_code == 403

    def test_external_user_no_kobo_surveys(self, app):
        environ = {
            'REMOTE_USER': self.external_user['name']
        }

        resp = app.get('/kobo/surveys', extra_environ=environ)
        assert resp.status_code == 403

    @mock.patch('ckanext.unhcr.blueprints.kobo.KoBoAPI.get_surveys')
    @mock.patch('ckanext.unhcr.blueprints.kobo.KoBoAPI.current_user')
    def test_internal_user_get_surveys(self, current_user, kobo_surveys, app):
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }

        asset_list = self.get_assets_list()
        assert 'url' in asset_list[1]
        assert 'TEST aaZSQ29VRHJmofjGSfDDv4' == asset_list[1]['name']
        kobo_surveys.return_value = asset_list
        current_user.return_value = {'username': 'avazquez'}

        resp = app.get('/kobo/surveys', extra_environ=environ)
        assert resp.status_code == 200
        assert '<h1>My KoBoToolbox Surveys</h1>' in resp.body
        # Test import URL (only for managed surveys)
        assert '/dataset/new?kobo_asset_id=Z2' in resp.body
        assert '/dataset/new?kobo_asset_id=XXXXXXXXXXXX' not in resp.body
        assert 'This KoBoToolbox survey has not been deployed' in resp.body
        assert 'TEST aaZSQ29VRHJmofjGSfDDv4' in resp.body

    def test_internal_user_setup_token(self, app):
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }

        resp = app.post(
            '/kobo/update-token',
            data={'kobo_token': 'test_abc123'},
            extra_environ=environ
        )
        assert resp.status_code == 200
        assert "Missing KoBoToolbox token" not in resp.body
        assert "Invalid KoBoToolbox token" not in resp.body
        assert "Unknown KoBoToolbox token" not in resp.body
        userobj = model.User.get(self.internal_editor_user['id'])
        assert userobj.plugin_extras['unhcr']['kobo_token'] == 'test_abc123'

    def test_internal_user_remove_token(self, app):
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }
        # set up the first token
        resp = app.post(
            '/kobo/update-token',
            data={'kobo_token': 'test_abc123'},
            extra_environ=environ
        )

        assert resp.status_code == 200
        userobj = model.User.get(self.internal_editor_user['id'])
        assert userobj.plugin_extras['unhcr']['kobo_token'] == 'test_abc123'

        # Change the token
        resp = app.post(
            '/kobo/update-token',
            data={'kobo_token': 'test_abc124'},
            extra_environ=environ
        )

        assert resp.status_code == 200
        userobj = model.User.get(self.internal_editor_user['id'])
        assert userobj.plugin_extras['unhcr']['kobo_token'] == 'test_abc124'

        # Remove the token
        resp = app.post(
            '/kobo/remove-token',
            extra_environ=environ
        )
        assert resp.status_code == 200
        assert "Error removing token" not in resp.body
        userobj = model.User.get(self.internal_editor_user['id'])
        print(userobj.plugin_extras)
        assert 'kobo_token' not in userobj.plugin_extras['unhcr']

    @mock.patch('ckan.lib.helpers.helper_functions.get_kobo_initial_dataset')
    @mock.patch('ckan.lib.helpers.helper_functions.get_kobo_survey')
    def test_create_pkg_frm_asset_error(self, kobo_survey, initial, app):
        """ Try to import from invalid asset_id"""

        initial.return_value = {}, {'kobo_dataset': ['Some error']}
        kobo_survey.return_value = {}
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }
        # set up the first token
        resp = app.get('/dataset/new?kobo_asset_id=not-exists', extra_environ=environ)

        assert resp.status_code == 200
        assert "Some error" in resp.body

    @mock.patch('ckan.lib.helpers.helper_functions.get_kobo_initial_dataset')
    @mock.patch('ckan.lib.helpers.helper_functions.get_kobo_survey')
    def test_create_pkg_frm_valid_asset(self, kobo_survey, initial, app):
        """ Try to import from valid asset_id"""

        initial.return_value = {'title': 'KoBoToolbox Survey Name XX'}, {}
        kobo_survey.return_value = {}
        
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }
        # set up the first token
        resp = app.get('/dataset/new?kobo_asset_id=aaZSQ29VRHJmofjGSfDDv4', extra_environ=environ)

        assert resp.status_code == 200
        assert "KoBoToolbox error: Error requesting data from KoBoToolbox 404" not in resp.body
        # Assert we use the KoBo name as Package Title
        assert "KoBoToolbox Survey Name XX" in resp.body
        assert "Next: Describe KoBoToolbox resources" in resp.body

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_submission_times')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.create_export')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_total_submissions')
    def test_post_new_pkg_from_kobo_starts_jobs(self, submissions, create_export, sub_times,mock_hook, app):
        """ Try to import KoBo resource """

        submissions.return_value = 1
        create_export.return_value = {'uid': 'kobo_export_id'}
        sub_times.return_value = ['2021-01-01', '2021-02-01']
        mock_hook.return_value = None

        environ = {
            'REMOTE_USER': self.kobo_user['name']
        }
        data = {
            '_ckan_phase': 'dataset_new_1',
            'pkg_name': '',
            'kobo_asset_id': 'some_kobo_id',
            'title': 'Some Survey',
            'name': 'some-survey',
            'notes': 'Dataset imported from KoBoToolbox, bla, bla',
            'tag_string': '',
            'url': '',
            'owner_org': self.data_container['name'],
            'external_access_level': 'not_available',
            'original_id': 'some_kobo_id',
            'data_collector': 'ACF,UNHCR',
            'geographies': DEFAULT_GEOGRAPHY_CODE,
            'keywords': 9,
            'unit_of_measurement': 'meters',
            'geog_coverage': '',
            'data_collection_technique': 'nf',
            'archived': 'False',
            # kobo filters
            'include_questionnaire': 'true',
            'save': '',
        }

        url = toolkit.url_for('dataset.new')
        app.post(
            url,
            data=data,
            extra_environ=environ,
            follow_redirects=True
        )

        submissions.assert_called()
        create_export.assert_called()
        sub_times.assert_called()
        # download_kobo_file should be called 2 times
        # One for the default CSV format and the other for the questionnaire
        mock_calls = [fn[0][0].__name__ for fn in mock_hook.call_args_list]
        assert mock_calls.count('download_kobo_file') == 2
        mock_titles = [fn[1].get('title') for fn in mock_hook.call_args_list]
        assert 'Download KoBoToolbox questionnaire' in mock_titles
        assert 'Download KoBoToolbox survey csv data' in mock_titles

    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_submission_times')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.create_export')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_total_submissions')
    def test_post_new_pkg_multiple_formats_from_kobo_starts_jobs(self, submissions, create_export, sub_times,mock_hook, app):
        """ Try to import KoBo resource """

        submissions.return_value = 1
        create_export.return_value = {'uid': 'kobo_export_id'}
        sub_times.return_value = ['2021-01-01', '2021-02-01']
        mock_hook.return_value = None

        environ = {
            'REMOTE_USER': self.kobo_user['name']
        }
        data = {
            '_ckan_phase': 'dataset_new_1',
            'pkg_name': '',
            'kobo_asset_id': 'some_kobo_id',
            'title': 'Some Survey',
            'name': 'some-survey',
            'notes': 'Dataset imported from KoBoToolbox, bla, bla',
            'tag_string': '',
            'url': '',
            'owner_org': self.data_container['name'],
            'external_access_level': 'not_available',
            'original_id': 'some_kobo_id',
            'data_collector': 'ACF,UNHCR',
            'geographies': DEFAULT_GEOGRAPHY_CODE,
            'keywords': 9,
            'unit_of_measurement': 'meters',
            'geog_coverage': '',
            'data_collection_technique': 'nf',
            'archived': 'False',
            # kobo filters
            'include_questionnaire': 'true',
            'formats': ['csv', 'spss_labels', 'xls', 'geojson'],
            'save': '',
        }

        url = toolkit.url_for('dataset.new')
        app.post(
            url,
            data=data,
            extra_environ=environ,
            follow_redirects=True
        )

        submissions.assert_called()
        create_export.assert_called()
        sub_times.assert_called()
        # download_kobo_file should be called 5 times
        # One for the questionnaire and then the 4 formats
        mock_calls = [fn[0][0].__name__ for fn in mock_hook.call_args_list]
        assert mock_calls.count('download_kobo_file') == 5

        mock_titles = [fn[1].get('title') for fn in mock_hook.call_args_list]
        assert 'Download KoBoToolbox questionnaire' in mock_titles
        assert 'Download KoBoToolbox survey csv data' in mock_titles
        assert 'Download KoBoToolbox survey spss_labels data' in mock_titles
        assert 'Download KoBoToolbox survey xls data' in mock_titles
        assert 'Download KoBoToolbox survey geojson data' in mock_titles

@pytest.mark.usefixtures('clean_db', 'unhcr_migrate', 'with_request_context')
class TestKoBoJobs(object):

    @mock.patch('ckanext.unhcr.kobo.kobo_dataset.KoboDataset.create_kobo_resources')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_total_submissions')
    def setup(self, get_total_submissions, create_kobo_resources):
        get_total_submissions.return_value = 5  # any, > 0
        self.kobo_user = factories.InternalKoBoUser()
        self.internal_user = factories.InternalUser()
        self.data_container = factories.DataContainer(
            users=[
                {'name': self.kobo_user['name'], 'capacity': 'editor'},
                {'name': self.internal_user['name'], 'capacity': 'member'},
            ]
        )
        self.kobo_test_asset_id = 'test_kobo_id_1234'
        self.kobo_dataset = factories.Dataset(
            name='kobo-dataset',
            title='KoBo Dataset',
            owner_org=self.data_container['name'],
            data_collection_technique='f2f',
            sampling_procedure='nonprobability',
            operational_purpose_of_data='cartography',
            user=self.kobo_user,
            kobo_asset_id=self.kobo_test_asset_id,
        )

        base_resource = dict(
            name='kobo-resource',
            package_id='kobo-dataset',
            url_type='upload',
            visibility='restricted',
            upload=mocks.FakeFileStorage(),
            url='original-file.csv',
            format='csv',
            kobo_type='data',
            kobo_details={
                'kobo_export_id': 'test_export_id',
                'kobo_asset_id': self.kobo_test_asset_id,
                'kobo_download_status': 'pending',
                'kobo_download_attempts': 1,
                'kobo_last_updated': datetime.datetime.utcnow().isoformat(),
            }
        )
        self.kobo_resource = factories.Resource(
            **base_resource
        )

        base_resource['kobo_details']['kobo_download_attempts'] = 5
        base_resource['upload'] = mocks.FakeFileStorage()

        self.kobo_resource_last_attempt = factories.Resource(
            **base_resource
        )

    @mock.patch('ckanext.unhcr.blueprints.kobo.KoBoAPI.get_asset')
    def test_kobo_dataset_page_allow_update(self, asset, app):
        """
        Test that the dataset page show the check for updates
        only for write permission users and KoBo managers
        """
        environ = {
            'REMOTE_USER': self.kobo_user['name']
        }
        asset.return_value = {'user_is_manager': True}
        resp = app.get('/dataset/{}'.format(self.kobo_dataset['name']), extra_environ=environ)
        assert resp.status_code == 200
        assert "Update KoBo data" in resp.body

    @mock.patch('ckanext.unhcr.blueprints.kobo.KoBoAPI.get_asset')
    def test_kobo_dataset_page_not_allow_update(self, asset, app):
        """
        Test that the dataset page show the check for updates
        only for write permission users and KoBo managers
        """
        environ = {
            'REMOTE_USER': self.kobo_user['name']
        }
        asset.return_value = {'user_is_manager': False}
        resp = app.get('/dataset/{}'.format(self.kobo_dataset['name']), extra_environ=environ)
        assert resp.status_code == 200
        assert "Update KoBo data" not in resp.body

    def test_kobo_dataset_page_avoid_update(self, app):
        """
        Test that the dataset page hide the check for updates for user without write permission
        """
        environ = {
            'REMOTE_USER': self.internal_user['name']
        }
        resp = app.get('/dataset/{}'.format(self.kobo_dataset['name']), extra_environ=environ)
        assert resp.status_code == 200
        assert "Update KoBoToolbox data" not in resp.body

    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_export')
    @mock.patch('ckanext.unhcr.kobo.kobo_dataset.KoboDataset.update_kobo_details')
    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_total_submissions')
    def test_pending_download_kobo_file(self, get_total_submissions, enqueue_job, update_kobo_details, get_export):
        """ test download_kobo_file job function to update a resource"""
        get_total_submissions.return_value = 5  # any, > 0
        get_export.return_value = {
            'uid': 'new_export_uid',
            'url': 'https://kobo.unhcr.org/exports/new_export_uid/',
            'status': 'processing'
        }
        update_kobo_details.return_value = {}

        download_kobo_file(self.kobo_resource['id'])

        # test we update the download_attempts counter
        assert update_kobo_details.call_args_list[0][0][2]['kobo_download_attempts'] == 2

        # assert we call again to download_kobo_file function
        jobs_called = [fn[0][0].__name__ for fn in enqueue_job.call_args_list]
        assert 'download_kobo_file' in jobs_called

    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_export')
    @mock.patch('ckanext.unhcr.kobo.kobo_dataset.KoboDataset.update_kobo_details')
    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    @mock.patch('ckanext.unhcr.kobo.api.KoBoSurvey.get_total_submissions')
    def test_failed_download_kobo_file(self, get_total_submissions, enqueue_job, update_kobo_details, get_export):
        """ test download_kobo_file failed after 5 attempts """
        get_total_submissions.return_value = 5  # any, > 0
        get_export.return_value = {
            'uid': 'new_export_uid',
            'url': 'https://kobo.unhcr.org/exports/new_export_uid/',
            'status': 'processing'
        }
        update_kobo_details.return_value = {}

        download_kobo_file(self.kobo_resource_last_attempt['id'])

        # test we update the download_attempts counter
        print(update_kobo_details.call_args_list[0][0][2])
        assert update_kobo_details.call_args_list[0][0][2]['kobo_download_status'] == 'error'

        # assert we DON'T call again to download_kobo_file function
        jobs_called = [fn[0][0].__name__ for fn in enqueue_job.call_args_list]
        assert 'download_kobo_file' not in jobs_called
