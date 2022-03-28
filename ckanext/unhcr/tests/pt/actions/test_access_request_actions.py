import datetime
import mock
import pytest
from dateutil.parser import parse as parse_date
from ckan import model
from ckan.plugins import toolkit
from ckan.tests import helpers as core_helpers
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.models import AccessRequest, USER_REQUEST_TYPE_RENEWAL
from ckanext.unhcr.tests import factories


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestAccessRequestUpdate(object):
    def setup(self):
        self.requesting_user = core_factories.User()
        self.standard_user = core_factories.User()
        self.pending_user = factories.ExternalUser(state=model.State.PENDING)

        self.container1_admin = core_factories.User()
        self.container1_curator = core_factories.User()
        self.container1 = factories.DataContainer(
            users=[
                {"name": self.container1_admin["name"], "capacity": "admin"},
                {"name": self.container1_curator["name"], "capacity": "editor"}
            ]
        )
        self.dataset1 = factories.Dataset(
            owner_org=self.container1["id"], visibility="restricted"
        )
        self.container_request = AccessRequest(
            user_id=self.requesting_user["id"],
            object_id=self.container1["id"],
            object_type="organization",
            message="",
            role="member",
        )
        self.dataset_request = AccessRequest(
            user_id=self.requesting_user["id"],
            object_id=self.dataset1["id"],
            object_type="package",
            message="",
            role="member",
        )
        self.user_request = AccessRequest(
            user_id=self.pending_user["id"],
            object_id=self.pending_user["id"],
            object_type="user",
            message="",
            role="member",
            data={'default_containers': [self.container1["id"]]},
        )
        model.Session.add(self.container_request)
        model.Session.add(self.dataset_request)
        model.Session.add(self.user_request)
        model.Session.commit()

    def test_access_request_update_approve_container_standard_user(self):
        action = toolkit.get_action("access_request_update")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"model": model, "user": self.standard_user["name"]},
                {'id': self.container_request.id, 'status': 'approved'}
            )

        orgs = toolkit.get_action("organization_list_for_user")(
            {"ignore_auth": True},
            {"id": self.requesting_user["name"], "permission": "read"}
        )
        assert 0 == len(orgs)
        assert 'requested' == self.container_request.status
        assert None == self.container_request.actioned_by

    def test_access_request_update_approve_container_container_admin(self):
        mock_mailer = mock.Mock()
        with mock.patch('ckanext.unhcr.mailer.mail_user_by_id', mock_mailer):
            action = toolkit.get_action("access_request_update")
            action(
                {"model": model, "user": self.container1_admin["name"]},
                {'id': self.container_request.id, 'status': 'approved'}
            )

            orgs = toolkit.get_action("organization_list_for_user")(
                {"ignore_auth": True},
                {"id": self.requesting_user["name"], "permission": "read"}
            )
            assert self.container1['id'] == orgs[0]['id']
            assert 'approved' == self.container_request.status
            assert (
                self.container1_admin["id"] ==
                self.container_request.actioned_by
            )

            mock_mailer.assert_called_once()
            assert (
                self.dataset_request.user_id ==
                mock_mailer.call_args[0][0]
            )
            assert (
                "[UNHCR RIDL] Membership: {}".format(self.container1["title"])
                == mock_mailer.call_args[0][1]
            )
            assert "You have been added" in mock_mailer.call_args[0][2]

    def test_access_request_update_reject_container_standard_user(self):
        action = toolkit.get_action("access_request_update")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"model": model, "user": self.standard_user["name"]},
                {'id': self.container_request.id, 'status': 'rejected'}
            )

        orgs = toolkit.get_action("organization_list_for_user")(
            {"ignore_auth": True},
            {"id": self.requesting_user["name"], "permission": "read"}
        )
        assert 0 == len(orgs)
        assert 'requested' == self.container_request.status
        assert None is self.container_request.actioned_by

    def test_access_request_update_reject_container_container_admin(self):
        action = toolkit.get_action("access_request_update")
        action(
            {"model": model, "user": self.container1_admin["name"]},
            {'id': self.container_request.id, 'status': 'rejected'}
        )

        orgs = toolkit.get_action("organization_list_for_user")(
            {"ignore_auth": True},
            {"id": self.requesting_user["name"], "permission": "read"}
        )
        assert 0 == len(orgs)
        assert 'rejected' == self.container_request.status
        assert (
            self.container1_admin["id"] ==
            self.container_request.actioned_by
        )

    def test_access_request_update_approve_dataset_standard_user(self):
        action = toolkit.get_action("access_request_update")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"model": model, "user": self.standard_user["name"]},
                {'id': self.dataset_request.id, 'status': 'approved'}
            )

        collaborators = toolkit.get_action("package_collaborator_list")(
            {"ignore_auth": True}, {"id": self.dataset1["id"]}
        )
        assert 0 == len(collaborators)
        assert 'requested' == self.dataset_request.status
        assert None is self.dataset_request.actioned_by

    def test_access_request_update_approve_dataset_container_admin(self):
        mock_mailer = mock.Mock()
        with mock.patch('ckanext.unhcr.actions.mailer.mail_notification_to_collaborator', mock_mailer):
            action = toolkit.get_action("access_request_update")
            action(
                {"model": model, "user": self.container1_admin["name"]},
                {'id': self.dataset_request.id, 'status': 'approved'}
            )

            collaborators = toolkit.get_action("package_collaborator_list")(
                {"ignore_auth": True}, {"id": self.dataset1["id"]}
            )
            assert self.requesting_user["id"] == collaborators[0]["user_id"]
            assert 'approved' == self.dataset_request.status
            assert (
                self.container1_admin["id"] ==
                self.dataset_request.actioned_by
            )

            mock_mailer.assert_called_once()
            assert self.dataset_request.object_id == mock_mailer.call_args[0][0]
            assert self.dataset_request.user_id == mock_mailer.call_args[0][1]
            assert 'member' == mock_mailer.call_args[0][2]
            assert 'create' == mock_mailer.call_args[1]['event']

    def test_access_request_update_reject_dataset_standard_user(self):
        action = toolkit.get_action("access_request_update")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"model": model, "user": self.standard_user["name"]},
                {'id': self.dataset_request.id, 'status': 'rejected'}
            )

        collaborators = toolkit.get_action("package_collaborator_list")(
            {"ignore_auth": True}, {"id": self.dataset1["id"]}
        )
        assert 0 == len(collaborators)
        assert 'requested' == self.dataset_request.status
        assert None is self.dataset_request.actioned_by

    def test_access_request_update_reject_dataset_container_admin(self):
        action = toolkit.get_action("access_request_update")
        action(
            {"model": model, "user": self.container1_admin["name"]},
            {'id': self.dataset_request.id, 'status': 'rejected'}
        )

        collaborators = toolkit.get_action("package_collaborator_list")(
            {"ignore_auth": True}, {"id": self.dataset1["id"]}
        )
        assert 0 == len(collaborators)
        assert 'rejected' == self.dataset_request.status
        assert (
            self.container1_admin["id"] ==
            self.dataset_request.actioned_by
        )

    def test_access_request_update_approve_user_standard_user(self):
        action = toolkit.get_action("access_request_update")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"model": model, "user": self.standard_user["name"]},
                {'id': self.user_request.id, 'status': 'approved'}
            )

        user = toolkit.get_action("user_show")(
            {"ignore_auth": True}, {"id": self.pending_user["id"]}
        )
        assert model.State.PENDING == user['state']
        assert None is self.user_request.actioned_by

    def test_access_request_update_approve_user_container_admin(self):
        mock_mailer = mock.Mock()
        with mock.patch('ckanext.unhcr.mailer.mail_user_by_id', mock_mailer):
            action = toolkit.get_action("access_request_update")
            action(
                {"model": model, "user": self.container1_admin["name"]},
                {'id': self.user_request.id, 'status': 'approved'}
            )

            user = toolkit.get_action("user_show")(
                {"ignore_auth": True}, {"id": self.pending_user["id"]}
            )
            assert model.State.ACTIVE == user['state']
            assert 'approved' == self.user_request.status
            assert (
                self.container1_admin["id"] ==
                self.user_request.actioned_by
            )

            mock_mailer.assert_called_once()
            assert (
                self.pending_user["id"] ==
                mock_mailer.call_args[0][0]
            )
            assert (
                '[UNHCR RIDL] - User account approved' ==
                mock_mailer.call_args[0][1]
            )
            assert (
                "Your request for a RIDL user account has been approved" in
                mock_mailer.call_args[0][2]
            )

    def test_access_request_update_approve_user_container_curator(self):
        """ Curators can't approve new users """
        action = toolkit.get_action("access_request_update")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"model": model, "user": self.container1_curator["name"]},
                {'id': self.user_request.id, 'status': 'approved'}
            )

        user = toolkit.get_action("user_show")(
            {"ignore_auth": True}, {"id": self.pending_user["id"]}
        )
        assert model.State.PENDING == user['state']
        assert None is self.user_request.actioned_by

    def test_access_request_update_reject_user_standard_user(self):
        action = toolkit.get_action("access_request_update")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"model": model, "user": self.standard_user["name"]},
                {'id': self.user_request.id, 'status': 'rejected'}
            )

        user = toolkit.get_action("user_show")(
            {"ignore_auth": True}, {"id": self.pending_user["id"]}
        )
        assert model.State.PENDING == user['state']
        assert None is self.user_request.actioned_by

    def test_access_request_update_reject_user_container_admin(self):
        action = toolkit.get_action("access_request_update")
        action(
            {"model": model, "user": self.container1_admin["name"]},
            {'id': self.user_request.id, 'status': 'rejected'}
        )

        user = toolkit.get_action("user_show")(
            {"ignore_auth": True}, {"id": self.pending_user["id"]}
        )
        assert model.State.DELETED == user['state']
        assert 'rejected' == self.user_request.status
        assert (
            self.container1_admin["id"] ==
            self.user_request.actioned_by
        )

    def test_access_request_update_invalid_inputs(self):
        action = toolkit.get_action("access_request_update")
        with pytest.raises(toolkit.ObjectNotFound):
            action(
                {"model": model, "user": self.standard_user["name"]},
                {'id': "invalid-id", 'status': 'approved'}
            )
        with pytest.raises(toolkit.ValidationError):
            action(
                {"model": model, "user": self.standard_user["name"]},
                {'status': 'approved'}
            )
        with pytest.raises(toolkit.ValidationError):
            action(
                {"model": model, "user": self.standard_user["name"]},
                {'id': self.dataset_request.id, 'status': 'invalid-status'}
            )


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestAccessRequestListForUser(object):
    def setup(self):
        self.sysadmin = core_factories.Sysadmin()
        self.requesting_user = core_factories.User()
        self.container_member = core_factories.User()
        self.multi_container_admin = core_factories.User()
        self.multi_container_curator = core_factories.User()

        self.container1_curator = core_factories.User()
        self.container1_admin = core_factories.User()
        self.container1 = factories.DataContainer(
            users=[
                {"name": self.multi_container_admin["name"], "capacity": "admin"},
                {"name": self.container1_admin["name"], "capacity": "admin"},
                {"name": self.container_member["name"], "capacity": "member"},
                {"name": self.container1_curator["name"], "capacity": "editor"},
                {"name": self.multi_container_curator["name"], "capacity": "editor"},
            ]
        )
        self.dataset1 = factories.Dataset(
            owner_org=self.container1["id"], visibility="restricted"
        )

        self.container2_curator = core_factories.User()
        self.container2_admin = core_factories.User()
        self.container2 = factories.DataContainer(
            users=[
                {"name": self.multi_container_admin["name"], "capacity": "admin"},
                {"name": self.container2_admin["name"], "capacity": "admin"},
                {"name": self.container2_curator["name"], "capacity": "editor"},
                {"name": self.multi_container_curator["name"], "capacity": "editor"},
            ]
        )
        self.dataset2 = factories.Dataset(
            owner_org=self.container2["id"], visibility="restricted"
        )

        self.container3 = factories.DataContainer()
        self.container4_curator = core_factories.User()
        self.container4_admin = core_factories.User()
        self.container4 = factories.DataContainer(
            users=[
                {"name": self.multi_container_admin["name"], "capacity": "admin"},
                {"name": self.container4_admin["name"], "capacity": "admin"},
                {"name": self.container4_curator["name"], "capacity": "editor"},
                {"name": self.multi_container_curator["name"], "capacity": "editor"},
            ]
        )

        requests = [
            # These requests all have the default status of 'requested'
            # so they'll be returned when we call access_request_list_for_user
            # with the default arguments
            AccessRequest(
                user_id=self.requesting_user["id"],
                object_id=self.container1["id"],
                object_type="organization",
                message="",
                role="member",
            ),
            AccessRequest(
                user_id=self.requesting_user["id"],
                object_id=self.dataset1["id"],
                object_type="package",
                message="",
                role="member",
            ),
            AccessRequest(
                user_id=self.requesting_user["id"],
                object_id=self.container2["id"],
                object_type="organization",
                message="",
                role="member",
            ),
            AccessRequest(
                user_id=self.requesting_user["id"],
                object_id=self.dataset2["id"],
                object_type="package",
                message="",
                role="member",
            ),

            # This request is already approved,
            # so it will only be visible if we explicitly filter for it
            AccessRequest(
                user_id=self.requesting_user["id"],
                object_id=self.container3["id"],
                object_type="organization",
                message="",
                role="member",
                status="approved",
            ),
            AccessRequest(
                user_id=self.requesting_user["id"],
                object_id=self.container4["id"],
                object_type="organization",
                message="",
                role="member",
                status="rejected",
            ),
        ]
        for req in requests:
            model.Session.add(req)
        model.Session.commit()

    def test_access_request_list_for_user_sysadmin(self):
        context = {"model": model, "user": self.sysadmin["name"]}

        # sysadmin can see all the open access requests
        access_requests = toolkit.get_action("access_request_list_for_user")(
            context, {}
        )
        assert 4 == len(access_requests)

        # ..and if we pass "status": "approved", they can see that one too
        access_requests = toolkit.get_action("access_request_list_for_user")(
            context, {"status": "approved"}
        )
        assert 1 == len(access_requests)

        # ..and if we pass "status": "rejected", they can see that one too
        access_requests = toolkit.get_action("access_request_list_for_user")(
            context, {"status": "rejected"}
        )
        assert 1 == len(access_requests)

    def test_full_access_request_list_for_user_sysadmin(self):
        context = {"model": model, "user": self.sysadmin["name"]}

        # sysadmin can see all the access requests (even closed ones)
        access_requests = toolkit.get_action("access_request_list_for_user")(
            context, {"status": "all"}
        )
        assert 6 == len(access_requests)

    def test_access_request_list_for_user_container_admins(self):
        # container admins can only see access requests for their own container(s)
        # and datasets owned by their own container(s)
        access_requests = toolkit.get_action("access_request_list_for_user")(
            {"model": model, "user": self.container1_admin["name"]}, {}
        )
        assert 2 == len(access_requests)
        ids = [req["object_id"] for req in access_requests]
        assert self.container1["id"] in ids
        assert self.dataset1["id"] in ids

        access_requests = toolkit.get_action("access_request_list_for_user")(
            {"model": model, "user": self.container2_admin["name"]}, {}
        )
        assert 2 == len(access_requests)
        ids = [req["object_id"] for req in access_requests]
        assert self.container2["id"] in ids
        assert self.dataset2["id"] in ids

        access_requests = toolkit.get_action("access_request_list_for_user")(
            {"model": model, "user": self.multi_container_admin["name"]}, {}
        )
        assert 4 == len(access_requests)

        access_requests = toolkit.get_action("access_request_list_for_user")(
            {"model": model, "user": self.multi_container_admin["name"]},
            {"status": "all"},
        )
        assert 5 == len(access_requests)

    def test_access_request_list_for_container_curators(self):
        # container curators can't see access requests for their container(s)
        with pytest.raises(toolkit.NotAuthorized):
            toolkit.get_action("access_request_list_for_user")(
                {"model": model, "user": self.container1_curator["name"]}, {}
            )

        with pytest.raises(toolkit.NotAuthorized):
            toolkit.get_action("access_request_list_for_user")(
                {"model": model, "user": self.container2_curator["name"]}, {}
            )

        with pytest.raises(toolkit.NotAuthorized):
            toolkit.get_action("access_request_list_for_user")(
                {"model": model, "user": self.multi_container_curator["name"]}, {}
            )

    def test_access_request_list_for_user_standard_users(self):
        # standard_user is a member of a container, but not an admin
        # they shouldn't be able to see any requests
        action = toolkit.get_action("access_request_list_for_user")
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"model": model, "user": self.container_member["name"]},
                {}
            )

        # requesting_user also has no priveledges - they shouldn't be able to see any
        # requests either (including the ones they submitted themselves)
        with pytest.raises(toolkit.NotAuthorized):
            action(
                {"model": model, "user": self.requesting_user["name"]},
                {}
            )

    def test_access_request_list_invalid_inputs(self):
        action = toolkit.get_action("access_request_list_for_user")
        with pytest.raises(toolkit.ObjectNotFound):
            action(
                {"model": model, "user": "invalid-user"},
                {}
            )
        with pytest.raises(toolkit.ValidationError):
            action(
                {"model": model},
                {'status': 'requested'}
            )
        with pytest.raises(toolkit.ValidationError):
            action(
                {"model": model, "user": self.sysadmin["name"]},
                {'status': 'invalid-status'}
            )


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestRenewalAccessRequest(object):

    def setup(self):
        self.container_admin = core_factories.User()
        self.container_curator = core_factories.User()
        self.regular_user = core_factories.User()
        self.container = factories.DataContainer(
            users=[
                {"name": self.container_admin["name"], "capacity": "admin"},
                {"name": self.container_curator["name"], "capacity": "editor"}
            ]
        )

        self.about_to_expire_date = datetime.date.today() + datetime.timedelta(days=5)
        self.about_to_expire_user = factories.ExternalUser(
            expiry_date=self.about_to_expire_date,
            default_containers=[self.container['id']]
        )
        access_request_data_dict = {
            'object_id': self.about_to_expire_user['id'],
            'object_type': 'user',
            'message': 'asdf',
            'role': 'member',  # TODO this is only required to fit the schema
            'data': {
                'user_request_type': USER_REQUEST_TYPE_RENEWAL,
                'users_who_can_approve': [
                    self.container_admin['id'],
                    self.container_curator['id']
                ]
            }
        }

        # Create the renewal request
        self.request = toolkit.get_action(u'access_request_create')(
            {'user': self.about_to_expire_user['id'], 'ignore_auth': True},
            access_request_data_dict
        )

    def test_admin_renewal_success(self):

        # Approve the request
        toolkit.get_action('access_request_update')(
            {"model": model, "user": self.container_admin["name"]},
            {'id': self.request['id'], 'status': 'approved'}
        )

        # Validate changed user
        user = toolkit.get_action("user_show")(
            {"ignore_auth": True}, {"id": self.about_to_expire_user['id']}
        )

        # User should be active and expire in "external_accounts_expiry_delta" days
        assert user['state'] == model.State.ACTIVE
        new_expired_date = parse_date(user['expiry_date']).date()
        days = toolkit.config.get('ckanext.unhcr.external_accounts_expiry_delta', 180)
        assert new_expired_date == datetime.date.today() + datetime.timedelta(days)

    def test_curator_renewal_success(self):

        # Approve the request
        toolkit.get_action('access_request_update')(
            {"model": model, "user": self.container_curator["name"]},
            {'id': self.request['id'], 'status': 'approved'}
        )

        # Validate changed user
        user = toolkit.get_action("user_show")(
            {"ignore_auth": True}, {"id": self.about_to_expire_user['id']}
        )

        # User should be active and expire in "external_accounts_expiry_delta" days
        assert user['state'] == model.State.ACTIVE
        new_expired_date = parse_date(user['expiry_date']).date()
        days = toolkit.config.get('ckanext.unhcr.external_accounts_expiry_delta', 180)
        assert new_expired_date == datetime.date.today() + datetime.timedelta(days)

    def test_regular_user_renewal_approve_fail(self):

        # Try to approve the request
        with pytest.raises(toolkit.NotAuthorized):
            toolkit.get_action('access_request_update')(
                {"model": model, "user": self.regular_user["name"]},
                {'id': self.request['id'], 'status': 'approved'}
            )

    def test_admin_reject_success(self):

        # Reject the request
        toolkit.get_action('access_request_update')(
            {"model": model, "user": self.container_admin["name"]},
            {'id': self.request['id'], 'status': 'rejected'}
        )

        # Validate changed user
        user = toolkit.get_action("user_show")(
            {"ignore_auth": True}, {"id": self.about_to_expire_user['id']}
        )

        # User should be deleted and expire in same date
        assert user['state'] == model.State.DELETED
        new_expired_date = parse_date(user['expiry_date']).date()
        assert new_expired_date == self.about_to_expire_date

    def test_curator_reject_success(self):

        # Reject the request
        toolkit.get_action('access_request_update')(
            {"model": model, "user": self.container_curator["name"]},
            {'id': self.request['id'], 'status': 'rejected'}
        )

        # Validate changed user
        user = toolkit.get_action("user_show")(
            {"ignore_auth": True}, {"id": self.about_to_expire_user['id']}
        )

        # User should be deleted and expire in same date
        assert user['state'] == model.State.DELETED
        new_expired_date = parse_date(user['expiry_date']).date()
        assert new_expired_date == self.about_to_expire_date

    def test_regular_user_renewal_reject_fail(self):

        # Try to approve the request
        with pytest.raises(toolkit.NotAuthorized):
            toolkit.get_action('access_request_update')(
                {"model": model, "user": self.regular_user["name"]},
                {'id': self.request['id'], 'status': 'rejected'}
            )
