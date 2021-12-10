import datetime
import mock
import pytest
from ckan import model
from ckan.plugins import toolkit
from ckan.tests.helpers import call_action
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.tests import factories
from ckanext.unhcr.actions import user_list
from ckanext.unhcr.activity import create_curation_activity
from ckanext.unhcr.commands import expired_users_list, request_renewal
from ckanext.unhcr.jobs import process_last_admin_on_delete
from ckanext.unhcr.helpers import get_existing_access_request
from ckanext.unhcr.models import USER_REQUEST_TYPE_RENEWAL


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestUserActions(object):

    def test_user_create_no_duplicate_emails(self):
        user1 = core_factories.User(email='alice@unhcr.org')

        with pytest.raises(toolkit.ValidationError) as e:
            call_action(
                'user_create',
                {},
                email='alice@unhcr.org',
                name='alice',
                password='8charactersorlonger',
            )

        assert (
            e.value.error_dict['email'][0] ==
            "The email address 'alice@unhcr.org' belongs to a registered user."
        )

        call_action(
            'user_create',
            {},
            email='bob@unhcr.org',
            name='bob',
            password='8charactersorlonger',
        )

    def test_user_list(self):
        sysadmin = core_factories.Sysadmin()
        external_user = factories.ExternalUser()
        internal_user = core_factories.User()
        default_user = toolkit.get_action('get_site_user')({ 'ignore_auth': True })

        action = toolkit.get_action('user_list')
        context = {'user': sysadmin['name']}
        users = action(context, {})
        assert (1 == len(
            [
                u for u in users
                if u['external']
                and u['name'] != default_user['name']
            ])
        )
        assert (2 == len(
            [
                u for u in users
                if not u['external']
                and u['name'] != default_user['name']
            ])
        )

    def test_user_list_empty(self):
        """ fake an empty user's list """
        def return_empty_list(context, data_dict):
            return []
        context = {'return_query': False}
        data_dict = {}
        users = user_list(
            up_func=return_empty_list,
            context=context,
            data_dict=data_dict
        )
        assert len(users) == 0

    def test_user_list_query(self):
        sysadmin = core_factories.Sysadmin()
        external_user = factories.ExternalUser()
        internal_user = core_factories.User()
        default_user = toolkit.get_action('get_site_user')({'ignore_auth': True})

        action = toolkit.get_action('user_list')
        context = {'user': sysadmin['name'], 'return_query': True}
        users = action(context, {})
        assert users.count() == 4

    def test_user_list_query_empty(self):
        sysadmin = core_factories.Sysadmin()
        external_user = factories.ExternalUser()
        internal_user = core_factories.User()
        default_user = toolkit.get_action('get_site_user')({'ignore_auth': True})

        action = toolkit.get_action('user_list')
        context = {'user': sysadmin['name'], 'return_query': True}
        # add a filter to get 0 results
        users = action(context, {'email': 'not-exist@example.com'})
        assert users.count() == 0

    def test_expired_user_list(self):
        not_expired_date = datetime.date.today() + datetime.timedelta(days=35)
        about_expire_date = datetime.date.today() + datetime.timedelta(days=25)
        expired_date = datetime.date.today() - datetime.timedelta(days=5)
        user1 = factories.ExternalUser(
            name='not-expired-user',
            email='not-expired@external.org',
            expiry_date=not_expired_date
        )
        user2 = factories.ExternalUser(
            name='expired-user',
            email='expired@external.org',
            expiry_date=expired_date
        )
        user3 = factories.ExternalUser(
            name='about-expire-user',
            email='about-expired@external.org',
            expiry_date=about_expire_date
        )

        dataset = factories.Dataset()

        activity = core_factories.Activity(
            user_id=user2["id"],
            object_id=dataset["id"],
            activity_type="new package",
            data={"package": dataset, "actor": "Mr Someone"},
        )

        expired_users = expired_users_list(include_activities=True)
        assert len(expired_users) == 1
        ids = [u['id'] for u in expired_users]
        assert user1['id'] not in ids
        assert user2['id'] in ids
        assert user3['id'] not in ids

        expired_user = expired_users[0]
        activities = expired_user['activities']
        assert len(activities) == 2
        assert activities[0]['activity_type'] == activity['activity_type']
        assert activities[1]['activity_type'] == 'new user'

    def test_about_expire_user_list(self):
        not_expired_date = datetime.date.today() + datetime.timedelta(days=35)
        about_expire_date = datetime.date.today() + datetime.timedelta(days=25)
        expired_date = datetime.date.today() - datetime.timedelta(days=5)

        user1 = factories.ExternalUser(
            name='not-expired-user',
            email='not-expired@external.org',
            expiry_date=not_expired_date
        )
        user2 = factories.ExternalUser(
            name='expired-user',
            email='expired@external.org',
            expiry_date=expired_date
        )
        user3 = factories.ExternalUser(
            name='about-expire-user',
            email='about-expire@external.org',
            expiry_date=about_expire_date
        )

        dataset = factories.Dataset()

        activity = core_factories.Activity(
            user_id=user3["id"],
            object_id=dataset["id"],
            activity_type="new package",
            data={"package": dataset, "actor": "Mr Someone"},
        )

        expired_users = expired_users_list(before_expire_days=30, include_activities=True)
        assert len(expired_users) == 1
        ids = [u['id'] for u in expired_users]
        assert user1['id'] not in ids
        assert user2['id'] not in ids
        assert user3['id'] in ids

        expired_user = expired_users[0]
        activities = expired_user['activities']
        assert len(activities) == 2
        assert activities[0]['activity_type'] == activity['activity_type']
        assert activities[1]['activity_type'] == 'new user'

    @mock.patch('ckanext.unhcr.commands.notify_renewal_request')
    def test_request_renewal(self, mock_notify_renewal_request):
        user = factories.ExternalUser()
        dataset = factories.Dataset()

        activity = core_factories.Activity(
            user_id=user["id"],
            object_id=dataset["id"],
            activity_type="new package",
            data={"package": dataset, "actor": "Mr Someone"},
        )

        mock_notify_renewal_request.return_value = []
        created, reason = request_renewal(user, activity)
        assert created
        assert reason is None

        mock_notify_renewal_request.assert_called_once()
        call = mock_notify_renewal_request.call_args_list[0]
        args, kwargs = call
        user_id = kwargs['user_id']
        message = kwargs['message']
        assert user_id == user['id']
        assert 'User {} will expire on'.format(user['name']) in message
        assert 'Last activity: "{}" registered on'.format(activity['activity_type']) in message

        created, reason = request_renewal(user, activity)
        assert not created
        assert reason == 'The request already exists'

    @mock.patch('ckanext.unhcr.commands.notify_renewal_request')
    def test_users_who_can_approve(self, mock_notify_renewal_request):
        """ Check what users can approve a renewal """
        user = factories.ExternalUser()
        container_admin = core_factories.User()
        container_member = core_factories.User()
        curator = core_factories.User()
        container = factories.DataContainer(
            users=[
                {"name": container_admin["name"], "capacity": "admin"},
                {"name": container_member["name"], "capacity": "member"},
            ]
        )
        dataset = factories.Dataset(
            user=user,
            owner_org=container['id']
        )

        activity = create_curation_activity(
            'dataset_approved',
            dataset['id'],
            dataset['name'],
            curator['id'],
            message='x'
        )

        mock_notify_renewal_request.return_value = []
        created, reason = request_renewal(user, activity)
        assert created
        assert reason is None
        mock_notify_renewal_request.assert_called_once()

        access_requests = get_existing_access_request(
            user_id=user['id'],
            object_id=user['id'],
            status='requested',
        )
        access_request = access_requests[0]
        users_who_can_approve = access_request.data.get('users_who_can_approve')
        assert user['id'] not in users_who_can_approve
        assert container_member['id'] not in users_who_can_approve

        assert container_admin['id'] in users_who_can_approve
        assert curator['id'] in users_who_can_approve

    def test_user_show(self):
        sysadmin = core_factories.Sysadmin()
        external_user = factories.ExternalUser()
        internal_user = core_factories.User()

        action = toolkit.get_action('user_show')
        context = {'user': sysadmin['name']}
        assert action(context, {'id': external_user['id']})['external']
        assert not action(context, {'id': internal_user['id']})['external']

    def test_unhcr_plugin_extras_empty(self):
        user = core_factories.User()
        context = {'user': user['name']}
        user = toolkit.get_action('user_show')(context, {'id': user['id']})
        assert None is user['expiry_date']
        assert '' == user['focal_point']

    def test_unhcr_plugin_extras_with_data(self):
        user = factories.ExternalUser(focal_point='Alice')
        context = {'user': user['name']}
        user = toolkit.get_action('user_show')(context, {'id': user['id']})
        assert 'expiry_date' in user
        assert 'Alice' == user['focal_point']

    def test_fail_user_update_saml2_user(self):
        saml_user = factories.InternalUser()

        context = {'user': saml_user['name']}
        with pytest.raises(toolkit.ValidationError):
            toolkit.get_action('user_update')(context, saml_user)

    @mock.patch('ckanext.unhcr.blueprints.kobo.KoBoAPI.get_surveys')
    def test_user_update_kobo_token_saml2_user(self, kobo_surveys):
        kobo_surveys.return_value = []
        saml_user = factories.InternalUser()

        context = {'user': saml_user['name']}
        # this should not raise an exception
        saml_user['plugin_extras'] = {'unhcr': {'kobo_token': 'abc123'}}
        toolkit.get_action('user_update')(context, saml_user)
        userobj = model.User.get(saml_user['id'])
        assert userobj.plugin_extras['unhcr']['kobo_token'] == 'abc123'

    def test_user_generate_apikey_saml2_user(self):
        saml_user = factories.InternalUser()

        context = {'user': saml_user['name']}
        data_dict = {'id': saml_user['id']}
        result = toolkit.get_action('user_generate_apikey')(context, data_dict)
        assert type(result) == dict
        assert saml_user['apikey'] != result['apikey']

    def test_user_update_change_apikey_saml2_user(self):
        saml_user = factories.InternalUser()

        context = {'user': saml_user['name']}
        data_dict = saml_user.copy()
        data_dict['apikey'] = 'f00b42'
        data_dict['email'] = 'newemail@example.com'
        result = toolkit.get_action('user_update')(context, data_dict)
        assert result['email'] != 'newemail@example.com'

    def test_user_update_native_user(self):
        native_user = core_factories.User()
        context = {'user': native_user['name']}
        result = toolkit.get_action('user_update')(context, native_user)
        assert type(result) == dict

    @mock.patch('ckanext.unhcr.actions.mailer.mail_user_by_id')
    @mock.patch('ckan.plugins.toolkit.enqueue_job')
    def test_user_delete(self, mock_hook, mail_user_by_id):
        sysadmin = core_factories.Sysadmin()
        external_user = factories.ExternalUser(name='to-delete', id='to-delete')
        
        # User will leave this container orphaned after being deleted
        container = factories.DataContainer(
            user=sysadmin,
            users=[
                {'name': external_user['name'], 'capacity': 'admin'},
            ]
        )
        # the container creatopr will be added as admin
        toolkit.get_action('member_delete')(
            {'ignore_auth': True},
            {
                'id': container['id'],
                'object_type': 'user',
                'object': sysadmin['id']
            }
        )

        toolkit.get_action('user_delete')(
            {'ignore_auth': True},
            {'id': external_user['id']}
        )
        
        mock_hook.assert_called_once()
        
        assert mock_hook.call_args_list[0][0][0].__name__ == 'process_last_admin_on_delete'
        assert mock_hook.call_args_list[0][0][1][0] == container['id']

        # run the job
        process_last_admin_on_delete(container['id'])
        # and validate we have a new admin
        container = toolkit.get_action('organization_show')(
            {'ignore_auth': True},
            {'id': container['id']}
        )
        assert container['users'][0]['capacity'] == 'admin'
        assert container['users'][0]['name'] == sysadmin['name']

        # Test the extra comment in the email
        mail_user_by_id.assert_called_once()
        args_list = mail_user_by_id.call_args_list
        mail_body = args_list[0][0][2]
        assert 'You have been assigned as admin' in mail_body


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestUserAutocomplete(object):

    def test_user_autocomplete(self):
        sysadmin = core_factories.Sysadmin(name='sysadmin', id='sysadmin')
        factories.ExternalUser(
            fullname='Alice External',
            email='alice@externaluser.com',
        )
        core_factories.User(fullname='Bob Internal')
        core_factories.User(fullname='Carlos Internal')
        core_factories.User(fullname='David Internal')

        action = toolkit.get_action('user_autocomplete')
        context = {'user': sysadmin['name']}

        result = action(context, {'q': 'alic'})
        assert 0 == len(result)

        result = action(context, {'q': 'alic', 'include_external': True})
        assert 'Alice External' == result[0]['fullname']

        result = action(context, {'q': 'nal'})
        fullnames = [r['fullname'] for r in result]
        assert 'Bob Internal' in fullnames
        assert 'Carlos Internal' in fullnames
        assert 'David Internal' in fullnames

        result = action(context, {'q': 'foobar'})
        assert 0 == len(result)


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestUpdateSysadmin(object):

    def test_sysadmin_not_authorized(self):
        user1 = core_factories.User()
        user2 = core_factories.User()
        action = toolkit.get_action("user_update_sysadmin")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"user": user1["name"]},
                {'id': user1["name"], 'is_sysadmin': True}
            )
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"user": user2["name"]},
                {'id': user1["name"], 'is_sysadmin': True}
            )

    def test_sysadmin_invalid_user(self):
        user = core_factories.Sysadmin()
        action = toolkit.get_action("user_update_sysadmin")
        with pytest.raises(toolkit.ObjectNotFound):
            action(
                {"user": user["name"]},
                {'id': "fred", 'is_sysadmin': True}
            )

    def test_sysadmin_promote_success(self):
        admin = core_factories.Sysadmin()

        # create a normal user
        user = core_factories.User()

        # promote them
        action = toolkit.get_action("user_update_sysadmin")
        action({'user': admin['name']}, {'id': user['name'], 'is_sysadmin': True})

        # now they are a sysadmin
        userobj = model.User.get(user['id'])
        assert True == userobj.sysadmin

    def test_sysadmin_revoke_success(self):
        admin = core_factories.Sysadmin()

        # create another sysadmin
        user = core_factories.Sysadmin(fullname='Bob')

        # revoke their status
        action = toolkit.get_action("user_update_sysadmin")
        action({'user': admin['name']}, {'id': user['name'], 'is_sysadmin': False})

        # now they are not a sysadmin any more
        userobj = model.User.get(user['id'])
        assert False == userobj.sysadmin


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestExternalUserUpdateState(object):

    def setup(self):
        self.container1_admin = core_factories.User()
        self.container1 = factories.DataContainer(
            users=[{"name": self.container1_admin["name"], "capacity": "admin"}]
        )

    def test_target_user_is_internal(self):
        target_user = core_factories.User(
            state=model.State.PENDING,
        )
        action = toolkit.get_action("external_user_update_state")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"user": self.container1_admin["name"]},
                {'id': target_user['id'], 'state': model.State.ACTIVE}
            )

    def test_target_user_is_not_pending(self):
        target_user = factories.ExternalUser()
        action = toolkit.get_action("external_user_update_state")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"user": self.container1_admin["name"]},
                {'id': target_user['id'], 'state': model.State.ACTIVE}
            )

    def test_requesting_user_is_not_container_admin(self):
        target_user = factories.ExternalUser(state=model.State.PENDING)
        access_request_data_dict = {
            'object_id': target_user['id'],
            'object_type': 'user',
            'message': 'asdf',
            'role': 'member',
            'data': {'default_containers': [self.container1['id']]}
        }
        toolkit.get_action(u'access_request_create')(
            {'user': target_user['id'], 'ignore_auth': True},
            access_request_data_dict
        )
        requesting_user = core_factories.User()

        action = toolkit.get_action("external_user_update_state")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"user": requesting_user["name"]},
                {'id': target_user['id'], 'state': model.State.ACTIVE}
            )

    def test_renewal_not_allowed(self):
        target_user = factories.ExternalUser()
        access_request_data_dict = {
            'object_id': target_user['id'],
            'object_type': 'user',
            'message': 'asdf',
            'role': 'member',
            'data': {
                'user_request_type': USER_REQUEST_TYPE_RENEWAL,
                'users_who_can_approve': [self.container1_admin['id']]
            }
        }
        toolkit.get_action(u'access_request_create')(
            {'user': target_user['id'], 'ignore_auth': True},
            access_request_data_dict
        )
        requesting_user = core_factories.User()

        action = toolkit.get_action("external_user_update_state")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"user": requesting_user["name"]},
                {'id': target_user['id'], 'state': model.State.ACTIVE, 'renew_expiry_date': True}
            )

    def test_renewal_allowed(self):
        target_user = factories.ExternalUser()
        access_request_data_dict = {
            'object_id': target_user['id'],
            'object_type': 'user',
            'message': 'asdf',
            'role': 'member',
            'data': {
                'user_request_type': USER_REQUEST_TYPE_RENEWAL,
                'users_who_can_approve': [self.container1_admin['id']]
            }
        }
        toolkit.get_action(u'access_request_create')(
            {'user': target_user['id'], 'ignore_auth': True},
            access_request_data_dict
        )

        action = toolkit.get_action("external_user_update_state")
        action(
            {"user": self.container1_admin["name"]},
            {'id': target_user['id'], 'state': model.State.ACTIVE, 'renew_expiry_date': True}
        )

    def test_requesting_user_is_not_admin_of_required_container(self):
        target_user = factories.ExternalUser(state=model.State.PENDING)
        requesting_user = core_factories.User()
        container2 = factories.DataContainer(
            users=[{"name": requesting_user["name"], "capacity": "admin"}]
        )
        access_request_data_dict = {
            'object_id': target_user['id'],
            'object_type': 'user',
            'message': 'asdf',
            'role': 'member',
            'data': {'default_containers': [self.container1['id']]}
        }
        toolkit.get_action(u'access_request_create')(
            {'user': target_user['id'], 'ignore_auth': True},
            access_request_data_dict
        )

        action = toolkit.get_action("external_user_update_state")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"user": requesting_user["name"]},
                {'id': target_user['id'], 'state': model.State.ACTIVE}
            )

    def test_no_access_request(self):
        target_user = factories.ExternalUser(state=model.State.PENDING)
        action = toolkit.get_action("external_user_update_state")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"user": self.container1_admin["name"]},
                {'id': target_user['id'], 'state': model.State.ACTIVE}
            )

    def test_invalid_state(self):
        target_user = factories.ExternalUser(state=model.State.PENDING)
        access_request_data_dict = {
            'object_id': target_user['id'],
            'object_type': 'user',
            'message': 'asdf',
            'role': 'member',
            'data': {'default_containers': [self.container1['id']]}
        }
        toolkit.get_action(u'access_request_create')(
            {'user': target_user['id'], 'ignore_auth': True},
            access_request_data_dict
        )

        action = toolkit.get_action("external_user_update_state")
        with pytest.raises(toolkit.ValidationError):
            action(
                {"user": self.container1_admin["name"]},
                {'id': target_user['id'], 'state': 'foobar'}
            )

    def test_user_not_found(self):
        action = toolkit.get_action("external_user_update_state")
        with pytest.raises(toolkit.ObjectNotFound):
            action(
                {"user": self.container1_admin["name"]},
                {'id': 'does-not-exist', 'state': model.State.ACTIVE}
            )

    def test_success(self):
        target_user = factories.ExternalUser(state=model.State.PENDING)
        access_request_data_dict = {
            'object_id': target_user['id'],
            'object_type': 'user',
            'message': 'asdf',
            'role': 'member',
            'data': {'default_containers': [self.container1['id']]}
        }
        toolkit.get_action(u'access_request_create')(
            {'user': target_user['id'], 'ignore_auth': True},
            access_request_data_dict
        )

        action = toolkit.get_action("external_user_update_state")
        action(
            {"user": self.container1_admin["name"]},
            {'id': target_user['id'], 'state': model.State.ACTIVE}
        )

        user = toolkit.get_action("user_show")(
            {"ignore_auth": True}, {"id": target_user['id']}
        )
        assert model.State.ACTIVE == user['state']
