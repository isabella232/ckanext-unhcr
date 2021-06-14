# -*- coding: utf-8 -*-

import pytest
from ckan import model
from ckan.plugins import toolkit
from ckan.tests import helpers as core_helpers
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.tests import factories, mocks
from ckanext.unhcr import helpers
from ckanext.unhcr.activity import create_download_activity, create_curation_activity


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestActivityListActions(object):
    def setup(self):
        self.sysadmin = core_factories.Sysadmin(name='sysadmin', id='sysadmin')
        self.container1_admin = core_factories.User()
        self.container1_member = core_factories.User()
        self.container1 = factories.DataContainer(
            users=[
                {"name": self.container1_admin["name"], "capacity": "admin"},
                {"name": self.container1_member["name"], "capacity": "member"},
            ]
        )
        self.dataset1 = factories.Dataset(
            owner_org=self.container1["id"], visibility="restricted"
        )
        self.resource1 = factories.Resource(
            package_id=self.dataset1['id'],
            upload=mocks.FakeFileStorage(),
            url = "http://fakeurl/test.txt",
            url_type='upload',
        )
        create_curation_activity(
            'dataset_approved',
            self.dataset1['id'],
            self.dataset1['name'],
            self.sysadmin['id'],
            message='asdf'
        )
        create_download_activity({'user': self.sysadmin['name']}, self.resource1['id'])
        toolkit.get_action('activity_create')({'ignore_auth':True}, {
            'user_id': self.sysadmin['name'],
            'object_id': self.dataset1['id'],
            'activity_type': 'changed package',
            'data': {}
        })

    def test_package_activity_list(self):
        context = {'user': self.sysadmin['name']}
        data_dict = {'id': self.dataset1['name']}
        activities = toolkit.get_action('package_activity_list')(context, data_dict)
        assert 1 == len(activities)
        assert 'changed package' == activities[0]['activity_type']

    def test_dashboard_activity_list(self):
        context = {'user': self.sysadmin['name']}
        data_dict = {'id': self.sysadmin['name']}
        activities = toolkit.get_action('user_activity_list')(context, data_dict)
        assert 1 == len(activities)
        assert 'changed package' == activities[0]['activity_type']

    def test_user_activity_list(self):
        context = {'user': self.sysadmin['name']}
        data_dict = {'id': self.sysadmin['name']}
        activities = toolkit.get_action('user_activity_list')(context, data_dict)
        assert 1 == len(activities)
        assert 'changed package' == activities[0]['activity_type']

    def test_organization_activity_list(self):
        context = {'user': self.sysadmin['name']}
        data_dict = {'id': self.container1['id']}
        activities = toolkit.get_action('organization_activity_list')(context, data_dict)
        assert 1 == len(activities)
        assert 'changed package' == activities[0]['activity_type']

    def test_package_internal_activity_list_container_admin(self):
        context = {'user': self.container1_admin['name']}
        data_dict = {'id': self.dataset1['id']}
        activities = toolkit.get_action('package_internal_activity_list')(context, data_dict)
        # a container admin can see all the internal activities
        assert 2 == len(activities)
        assert 'download resource' == activities[0]['activity_type']
        assert 'changed curation state' == activities[1]['activity_type']

    def test_package_internal_activity_list_dataset_editor(self):
        collaborator = core_factories.User()
        core_helpers.call_action(
            'package_collaborator_create',
            id=self.dataset1['id'],
            user_id=collaborator['id'],
            capacity='editor',
        )
        context = {'user': collaborator['name'],}
        data_dict = {'id': self.dataset1['id']}
        activities = toolkit.get_action('package_internal_activity_list')(context, data_dict)
        # a dataset editor can only see the curation activities
        assert 1 == len(activities)
        assert 'changed curation state' == activities[0]['activity_type']

    def test_package_internal_activity_list_container_member(self):
        context = {'user': self.container1_member['name']}
        data_dict = {'id': self.dataset1['id']}
        action = toolkit.get_action('package_internal_activity_list')
        # a container member can't see any internal activities
        with pytest.raises(toolkit.NotAuthorized):
            action(context, data_dict)

    def test_package_internal_activity_list_unprivileged_user(self):
        normal_user = core_factories.User()
        context = {'user': normal_user['name']}
        data_dict = {'id': self.dataset1['id']}
        action = toolkit.get_action('package_internal_activity_list')
        # an unprivileged user can't see any internal activities
        with pytest.raises(toolkit.NotAuthorized):
            action(context, data_dict)
