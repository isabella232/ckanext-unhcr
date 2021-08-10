import json
import mock
import pytest
from ckan import model
from ckanext.unhcr.tests import factories


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate', 'with_request_context')
class TestKoBo(object):

    def setup(self):
        # Users
        self.internal_user = factories.InternalUser()
        self.internal_editor_user = factories.InternalUser()
        self.internal_admin_user = factories.InternalUser()
        self.external_user = factories.ExternalUser()

        self.data_container = factories.DataContainer(
            users=[
                {'name': self.internal_admin_user['name'], 'capacity': 'admin'},
                {'name': self.internal_editor_user['name'], 'capacity': 'editor'},
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
        assert 'KoBo Toolbox' not in resp.body

    def test_internal_editor_user_dashboad_kobo_link_ok(self, app):
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }

        resp = app.get('/dashboard/', extra_environ=environ)
        assert 'KoBo Toolbox' in resp.body

    def test_internal_admin_user_dashboad_kobo_link_ok(self, app):
        environ = {
            'REMOTE_USER': self.internal_admin_user['name']
        }

        resp = app.get('/dashboard/', extra_environ=environ)
        assert 'KoBo Toolbox' in resp.body

    def test_external_user_dashboad_no_kobo_link(self, app):
        environ = {
            'REMOTE_USER': self.external_user['name']
        }

        resp = app.get('/dashboard/', extra_environ=environ)
        assert 'KoBo Toolbox' not in resp.body

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
    def test_internal_user_get_surveys(self, kobo_surveys, app):
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }

        asset_list = self.get_assets_list()
        assert 'url' in asset_list[1]
        assert 'TEST aaZSQ29VRHJmofjGSfDDv4' == asset_list[1]['name']
        kobo_surveys.return_value = asset_list

        resp = app.get('/kobo/surveys', extra_environ=environ)
        assert resp.status_code == 200
        assert '<h1>My KoBo Surveys</h1>' in resp.body
        # Test import URL
        assert '/dataset/new?kobo_asset_id=' in resp.body
        assert 'This KoBo survey has not been deployed' in resp.body
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
        assert "Missing KoBo token" not in resp.body
        assert "Invalid KoBo token" not in resp.body
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
    def test_create_pkg_frm_asset_error(self, initial, app):
        """ Try to import from invalid asset_id"""

        initial.return_value = {}, {'kobo_dataset': ['Some error']}
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }
        # set up the first token
        resp = app.get('/dataset/new?kobo_asset_id=not-exists', extra_environ=environ)

        assert resp.status_code == 200
        assert "Some error" in resp.body

    @mock.patch('ckan.lib.helpers.helper_functions.get_kobo_initial_dataset')
    def test_create_pkg_frm_valid_asset(self, initial, app):
        """ Try to import from invalid asset_id"""

        initial.return_value = {'title': 'Kobo Survey Name XX'}, {}
        environ = {
            'REMOTE_USER': self.internal_editor_user['name']
        }
        # set up the first token
        resp = app.get('/dataset/new?kobo_asset_id=aaZSQ29VRHJmofjGSfDDv4', extra_environ=environ)

        assert resp.status_code == 200
        assert "KoBo error: Error requesting data from Kobo 404" not in resp.body
        # Assert we use the KoBo name as Package Title
        assert "Kobo Survey Name XX" in resp.body
