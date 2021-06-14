# -*- coding: utf-8 -*-

import mock
import pytest
import ckan.model as model
from ckan.plugins import toolkit
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.models import AccessRequest
from ckanext.unhcr.tests import factories


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate', 'with_request_context')
class TestUserController(object):

    def test_sysadmin_not_authorized(self, app):
        user = core_factories.User()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app.post('/user/sysadmin', data={}, extra_environ=env, status=403)

    def test_sysadmin_invalid_user(self, app):
        user = core_factories.Sysadmin()
        env = {'REMOTE_USER': user['name'].encode('ascii')}
        app.post(
            '/user/sysadmin',
            data={'id': 'fred', 'status': '1' },
            extra_environ=env,
            status=404
        )

    def test_sysadmin_promote_success(self, app):
        admin = core_factories.Sysadmin()
        env = {'REMOTE_USER': admin['name'].encode('ascii')}

        # create a normal user
        user = core_factories.User(fullname='Alice')

        # promote them
        resp = app.post(
            '/user/sysadmin',
            data={'id': user['id'], 'status': '1' },
            extra_environ=env,
            status=200,
        )
        assert (
            'Promoted Alice to sysadmin' in
            resp.body
        )

        # now they are a sysadmin
        userobj = model.User.get(user['id'])
        assert userobj.sysadmin

    def test_sysadmin_revoke_success(self, app):
        admin = core_factories.Sysadmin()
        env = {'REMOTE_USER': admin['name'].encode('ascii')}

        # create another sysadmin
        user = core_factories.Sysadmin(fullname='Bob')

        # revoke their status
        resp = app.post(
            '/user/sysadmin',
            data={'id': user['id'], 'status': '0' },
            extra_environ=env,
            status=200,
        )
        assert (
            'Revoked sysadmin permission from Bob' in
            resp.body
        )

        # now they are not a sysadmin any more
        userobj = model.User.get(user['id'])
        assert not userobj.sysadmin


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestUserRegister(object):

    def setup(self):
        self.sysadmin = core_factories.Sysadmin()
        self.container = factories.DataContainer()
        self.payload = {
            'name': 'externaluser',
            'fullname': 'New External User',
            'email': 'fred@externaluser.com',
            'password1': 'TestPassword1',
            'password2': 'TestPassword1',
            'message': 'I can haz access?',
            'focal_point': 'REACH',
            'container': self.container['id'],
        }

    def test_custom_fields(self, app):
        resp = app.get(toolkit.url_for('user.register'))
        assert resp.status_code == 200
        assert (
            'Please describe the dataset(s) you would like to submit' in
            resp.body
        )
        assert (
            '<textarea id="field-message"' in
            resp.body
        )
        assert (
            'Please select the region where the data was collected' in
            resp.body
        )
        assert (
            '<select id="field-container"' in
            resp.body
        )

    def test_register_success(self, app):
        mock_mailer = mock.Mock()
        with mock.patch('ckan.plugins.toolkit.enqueue_job', mock_mailer):
            resp = app.post(toolkit.url_for('user.register'), data=self.payload)


        # we should have created a user object with pending state
        user = toolkit.get_action('user_show')(
            {'ignore_auth': True},
            {'id': 'externaluser'}
        )
        assert model.State.PENDING == user['state']

        # we should have created an access request for an admin to approve/reject
        assert (
            1 ==
            len(model.Session.query(AccessRequest).filter(
                AccessRequest.object_id == user['id'],
                AccessRequest.user_id == user['id'],
                AccessRequest.status == 'requested'
            ).all())
        )

        # we should have sent an email to someone to approve/reject the account
        mock_mailer.assert_called_once()
        assert self.sysadmin['name'] == mock_mailer.call_args[0][1][0]
        assert (
            '[UNHCR RIDL] - Request for new user account' ==
            mock_mailer.call_args[0][1][1]
        )

        # 'success' page content
        assert resp.status_code == 200
        assert 'Partner Account Requested' in resp.body
        assert "We'll send an email with further instructions" in resp.body

    def test_register_empty_message(self, app):
        self.payload['message'] = ''
        resp = app.post(toolkit.url_for('user.register'), data=self.payload)
        assert "&#39;message&#39; is required" in resp.body
        action = toolkit.get_action("user_show")
        with pytest.raises(toolkit.ObjectNotFound):
            action(
                {'ignore_auth': True},
                {'id': 'externaluser'}
            )

    def test_register_empty_focal_point(self, app):
        self.payload['focal_point'] = ''
        resp = app.post(toolkit.url_for('user.register'), data=self.payload)
        assert "A focal point must be specified" in resp.body
        action = toolkit.get_action("user_show")
        with pytest.raises(toolkit.ObjectNotFound):
            action(
                {'ignore_auth': True},
                {'id': 'externaluser'}
            )

    def test_no_containers(self, app):
        self.payload['container'] = ''
        resp = app.post(toolkit.url_for('user.register'), data=self.payload)
        assert "A region must be specified" in resp.body
        action = toolkit.get_action("user_show")
        with pytest.raises(toolkit.ObjectNotFound):
            action(
                {'ignore_auth': True},
                {'id': 'externaluser'}
            )

    def test_internal_user(self, app):
        self.payload['email'] = 'fred@unhcr.org'
        resp = app.post(toolkit.url_for('user.register'), data=self.payload)
        assert (
            "Users with an @unhcr.org email may not register for a partner account."
            in resp.body
        )
        action = toolkit.get_action("user_show")
        with pytest.raises(toolkit.ObjectNotFound):
            action(
                {'ignore_auth': True},
                {'id': 'externaluser'}
            )

    def test_logged_in(self, app):
        user = core_factories.User()

        with app.flask_app.test_request_context():
            app.get(
                toolkit.url_for('user.register'),
                extra_environ={'REMOTE_USER': user['name'].encode('ascii')},
                status=403
            )

        with app.flask_app.test_request_context():
            app.get(
                toolkit.url_for('user.register'),
                extra_environ={'REMOTE_USER': self.sysadmin['name'].encode('ascii')},
                status=403
            )

        with app.flask_app.test_request_context():
            app.post(
                toolkit.url_for('user.register'),
                data=self.payload,
                extra_environ={'REMOTE_USER': user['name'].encode('ascii')},
                status=403
            )

        with app.flask_app.test_request_context():
            app.post(
                toolkit.url_for('user.register'),
                data=self.payload,
                extra_environ={'REMOTE_USER': self.sysadmin['name'].encode('ascii')},
                status=403
            )


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestPasswordReset(object):

    def setup(self):
        saml_user = core_factories.User(name='saml2user', email='saml2@unhcr.org')
        userobj = model.User.get(saml_user['id'])
        userobj.plugin_extras = {'saml2auth': { 'saml_id': 'abc123' }}
        model.Session.commit()
        core_factories.User(name='nativeuser', email='native@unhcr.org')

    @pytest.mark.ckan_config('ckanext.saml2auth.enable_ckan_internal_login', True)
    def test_password_reset_get_form_native_users_enabled(self, app):
        print(toolkit.url_for('user.request_reset'))
        app.get(toolkit.url_for('user.request_reset'), status=200)

    @pytest.mark.ckan_config('ckanext.saml2auth.enable_ckan_internal_login', False)
    def test_password_reset_get_form_native_users_disabled(self, app):
        app.get(toolkit.url_for('user.request_reset'), status=403)

    @pytest.mark.ckan_config('ckanext.saml2auth.enable_ckan_internal_login', True)
    @pytest.mark.parametrize(
        "user, exp_code, exp_message",
        [
            ('saml2user', 403, "Unauthorized to request reset password."),
            ('saml2@unhcr.org', 403, "Unauthorized to request reset password."),

            # these two are still going to be a 403 because we aren't logged in
            # but we should be redirected back to the login page 403
            # instead of an error message 403
            ('nativeuser', 403, "You must be logged in to access the RIDL site."),
            ('native@unhcr.org', 403, "You must be logged in to access the RIDL site."),
        ]
    )
    def test_password_reset_submit_form_native_users_enabled(
        self, app, user, exp_code, exp_message
    ):
        resp = app.post(
            toolkit.url_for('user.request_reset'),
            data={'user': user},
            status=exp_code
        )
        assert exp_message in resp.body

    @pytest.mark.ckan_config('ckanext.saml2auth.enable_ckan_internal_login', False)
    @pytest.mark.parametrize(
        "user, exp_code, exp_message",
        [
            ('saml2user', 403, "Unauthorized to request reset password."),
            ('saml2@unhcr.org', 403, "Unauthorized to request reset password."),
            ('nativeuser', 403, "Unauthorized to request reset password."),
            ('native@unhcr.org', 403, "Unauthorized to request reset password."),
        ]
    )
    def test_password_reset_submit_form_native_users_disabled(
        self, app, user, exp_code, exp_message
    ):
        resp = app.post(
            toolkit.url_for('user.request_reset'),
            data={'user': user},
            status=exp_code
        )
        assert exp_message in resp.body
