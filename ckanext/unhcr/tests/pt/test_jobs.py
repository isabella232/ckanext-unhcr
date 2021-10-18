# -*- coding: utf-8 -*-

import pytest
from ckantoolkit.tests import factories as core_factories
from ckan.tests import helpers
from ckanext.unhcr.jobs import _modify_package, process_dataset_on_update
from ckanext.unhcr.tests import factories, mocks


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestJobs(object):

    # date_range
    def test_modify_package_date_range(self):
        package = _modify_package({
            'date_range_start': None,
            'date_range_end': None,
            'resources': [
                {'date_range_start': '2017-01-01', 'date_range_end': '2017-06-01'},
                {'date_range_start': '2017-03-01', 'date_range_end': '2017-09-01'},
            ]
        })
        assert package['date_range_start'] == '2017-01-01'
        assert package['date_range_end'] == '2017-09-01'

    def test_modify_package_date_range_after_resource_deletion(self):
        package = _modify_package({
            'date_range_start': '2017-01-01',
            'date_range_end': '2017-09-01',
            'resources': [
                {'date_range_start': '2017-01-01', 'date_range_end': '2017-06-01'},
            ]
        })
        assert package['date_range_start'] == '2017-01-01'
        assert package['date_range_end'] == '2017-06-01'

    def test_modify_package_date_range_no_resources(self):
        package = _modify_package({
            'date_range_start': None,
            'date_range_end': None,
            'resources': [],
        })
        assert package['date_range_start'] is None
        assert package['date_range_end'] is None

    # process_status
    def test_modify_package_process_status(self):
        package = _modify_package({
            'process_status': None,
            'resources': [
                {'process_status': 'cleaned'},
                {'process_status': 'anonymized'},
            ]
        })
        assert package['process_status'] == 'cleaned'

    def test_modify_package_process_status_resource_deletion(self):
        package = _modify_package({
            'process_status': 'cleaned',
            'resources': [
                {'process_status': 'anonymized'},
            ]
        })
        assert package['process_status'] == 'anonymized'

    def test_modify_package_process_status_none(self):
        package = _modify_package({
            'process_status': None,
            'resources': [
                {'process_status': 'cleaned'},
                {'process_status': 'anonymized'},
            ]
        })
        assert package['process_status'] == 'cleaned'

    def test_modify_package_process_status_no_resources(self):
        package = _modify_package({
            'process_status': 'anonymized',
            'resources': [],
        })
        assert package['process_status'] is None

    def test_modify_package_process_status_default(self):
        package = _modify_package({
            'process_status': None,
            'resources': [],
        })
        assert package['process_status'] is None

    # privacy

    def test_modify_package_privacy(self):
        package = _modify_package({
            'identifiability': None,
            'resources': [
                {'identifiability': 'anonymized_public', 'visibility': 'public'},
            ]
        })
        assert package['identifiability'] == 'anonymized_public'
        assert package['visibility'] == 'public'

    def test_modify_package_privacy_private_false(self):
        package = _modify_package({
            'identifiability': None,
            'resources': [
                {'identifiability': 'anonymized_public', 'visibility': 'public'},
            ]
        })
        assert package['identifiability'] == 'anonymized_public'
        assert package['visibility'] == 'public'

    def test_modify_package_privacy_resource_addition(self):
        package = _modify_package({
            'identifiability': 'anonymized_public',
            'resources': [
                {'identifiability': 'anonymized_public', 'visibility': 'public'},
                {'identifiability': 'personally_identifiable', 'visibility': 'public'},
            ]
        })
        assert package['identifiability'] == 'personally_identifiable'
        assert package['visibility'] == 'restricted'

    def test_modify_package_privacy_package_none(self):
        package = _modify_package({
            'identifiability': None,
            'resources': [
                {'identifiability': 'personally_identifiable', 'visibility': 'public'},
            ]
        })
        assert package['identifiability'] == 'personally_identifiable'
        assert package['visibility'] == 'restricted'

    def test_modify_package_privacy_default(self):
        package = _modify_package({
            'identifiability': None,
            'resources': []
        })
        assert package['identifiability'] is None
        assert package['visibility'] == 'public'

    def test_modify_package_privacy_from_resources(self):
        package = _modify_package({
            'resources': [
                {'visibility': 'restricted'}
            ]
        })
        assert package['visibility'] == 'restricted'


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestReviseJobs(object):
    def setup(self):
        self.internal_user = core_factories.User()
        self.dataset = factories.Dataset(
            user=self.internal_user
        )
        self.resource = factories.Resource(
            package_id=self.dataset['id'],
            description='some description',
            visibility='public',
            identifiability='personally_identifiable',
            upload=mocks.FakeFileStorage(),
            url="http://fakeurl/test.txt",
            url_type='upload',
        )

        self.resource_visible = factories.Resource(
            package_id=self.dataset['id'],
            description='some description 2',
            visibility='public',
            identifiability='anonymized_public',
            upload=mocks.FakeFileStorage(),
            url="http://fakeurl/test2.txt",
            url_type='upload',
        )

        # Attachment type files do not use "identifiability"
        self.resource_ambiguous = factories.Resource(
            package_id=self.dataset['id'],
            description='some description 3',
            visibility='public',
            identifiability='personally_identifiable',
            upload=mocks.FakeFileStorage(),
            url="http://fakeurl/test3.txt",
            url_type='upload',
            type='attachment',
            file_type='other',
        )
    def test_package_update_job_resource_restricted(self):
        process_dataset_on_update(self.dataset['id'])
        # visibility for dataset should be updated to restricted and other field should remain intact

        resource = helpers.call_action(
            'resource_show',
            context={'user': self.internal_user['name']},
            id=self.resource['id'],
        )
        # personally_identifiable resources should restrict visibility
        assert resource['visibility'] == 'restricted'
        # other fields should remain intact
        assert resource['description'] == 'some description'

    def test_package_update_job_resource_visible(self):
        process_dataset_on_update(self.dataset['id'])

        resource = helpers.call_action(
            'resource_show',
            context={'user': self.internal_user['name']},
            id=self.resource_visible['id'],
        )
        # personally_identifiable resources should restrict visibility
        assert resource['visibility'] == 'public'
        # other fields should remain intact
        assert resource['description'] == 'some description 2'

    def test_package_update_job_resource_ambiguous(self):
        process_dataset_on_update(self.dataset['id'])

        resource = helpers.call_action(
            'resource_show',
            context={'user': self.internal_user['name']},
            id=self.resource_ambiguous['id'],
        )
        # personally_identifiable resources should restrict visibility
        assert resource['visibility'] == 'public'
        # other fields should remain intact
        assert resource['description'] == 'some description 3'

    def test_package_update_job_package(self):
        process_dataset_on_update(self.dataset['id'])

        pkg = helpers.call_action(
            'package_show',
            context={'user': self.internal_user['name']},
            id=self.dataset['id'],
        )
        # resource becomes restricted and also package
        assert pkg['visibility'] == 'restricted'
        # package should use identifiability from the more restricted resource
        assert pkg['identifiability'] == 'personally_identifiable'
