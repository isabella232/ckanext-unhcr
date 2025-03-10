# -*- coding: utf-8 -*-

import datetime
import json
import mock
import pytest
import re
import responses
import tempfile
from dateutil.parser import parse as parse_date
from werkzeug.datastructures import FileStorage as FlaskFileStorage
from ckan.plugins import toolkit
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.tests import factories
from ckanext.unhcr.kobo.kobo_dataset import DOWNLOAD_PENDING_MSG


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
class TestClamAVActions(object):

    def setup(self):
        self.sysadmin = core_factories.Sysadmin()
        self.dataset = factories.Dataset()
        self.resource = factories.Resource(
            package_id=self.dataset['id'],
            url_type='upload',
            last_modified=datetime.datetime.utcnow(),
        )

    def get_task(self):
        return toolkit.get_action('task_status_show')(
            {'user': self.sysadmin['name']},
            {
                'entity_id': self.resource['id'],
                'task_type': 'clamav',
                'key': 'clamav'
            }
        )

    def insert_pending_task(self):
        return toolkit.get_action('task_status_update')(
            {'ignore_auth': True},
            {
                'entity_id': self.resource['id'],
                'entity_type': 'resource',
                'task_type': 'clamav',
                'last_updated': datetime.datetime.utcnow().isoformat(),
                'state': 'pending',
                'key': 'clamav',
                'value': '{}',
                'error': 'null',
            }
        )

    @responses.activate
    @pytest.mark.ckan_config('ckanext.unhcr.clamav_url', 'http://clamav:1234')
    def test_scan_submit_valid(self):
        responses.add_passthru(re.compile(r'^http:\/\/.*solr/.*$'))
        responses.add(responses.POST, 'http://clamav:1234/job', status=200)

        result = toolkit.get_action("scan_submit")(
            {'user': self.sysadmin['name']},
            {'id': self.resource['id']}
        )
        assert result

        assert responses.assert_call_count('http://clamav:1234/job', 1)
        request_body = json.loads(responses.calls[0].request.body)
        assert request_body['api_key']
        assert request_body['result_url'].endswith('/api/3/action/scan_hook')
        site_url = toolkit.config.get('ckan.site_url')
        assert site_url == request_body['metadata']['ckan_url']
        assert self.resource['id'] == request_body['metadata']['resource_id']

        task = self.get_task()
        assert u'pending' == task['state']

    @responses.activate
    @pytest.mark.ckan_config('ckanext.unhcr.clamav_url', 'http://clamav:1234')
    def test_scan_submit_duplicate_task(self):
        responses.add_passthru(re.compile(r'^http:\/\/.*solr/.*$'))

        self.insert_pending_task()

        result = toolkit.get_action("scan_submit")(
            {'user': self.sysadmin['name']},
            {'id': self.resource['id']}
        )
        assert not(result)

    @responses.activate
    def test_scan_submit_base_url_not_set(self):
        responses.add_passthru(re.compile(r'^http:\/\/.*solr/.*$'))

        result = toolkit.get_action("scan_submit")(
            {'user': self.sysadmin['name']},
            {'id': self.resource['id']}
        )
        assert not(result)
        assert responses.assert_call_count('http://clamav:1234/job', 0)

        task = self.get_task()
        assert u'error' == task['state']

    @responses.activate
    @pytest.mark.ckan_config('ckanext.unhcr.clamav_url', 'http://clamav:1234')
    def test_scan_submit_failure(self):
        responses.add_passthru(re.compile(r'^http:\/\/.*solr/.*$'))
        responses.add(responses.POST, 'http://clamav:1234/job', status=500)

        with pytest.raises(toolkit.ValidationError):
            toolkit.get_action("scan_submit")(
                {'user': self.sysadmin['name']},
                {'id': self.resource['id']}
            )

        task = self.get_task()
        assert u'error' == task['state']

    def test_scan_submit_invalid_params(self):
        with pytest.raises(toolkit.ValidationError):
            toolkit.get_action("scan_submit")(
                {'user': self.sysadmin['name']},
                {}
            )

    def test_scan_hook_complete_file_clean(self):
        self.insert_pending_task()

        mock_mailer = mock.Mock()
        with mock.patch('ckanext.unhcr.mailer.mail_user_by_id', mock_mailer):
            toolkit.get_action("scan_hook")(
                {'user': self.sysadmin['name']},
                {
                    "status": "complete",
                    "data": {
                        "status_code": 0,
                        "status_text": "SUCCESSFUL SCAN, FILE CLEAN",
                        "description": "/tmp/tmp37q_kv9u: OK\n\n----------- SCAN SUMMARY -----------\nKnown viruses: 8945669\nEngine version: 0.102.4\nScanned directories: 0\nScanned files: 1\nInfected files: 0\nData scanned: 0.00 MB\nData read: 0.00 MB (ratio 0.00:1)\nTime: 25.064 sec (0 m 25 s)\n"
                    },
                    "metadata": {
                        "resource_id": self.resource['id'],
                    }
                }
            )

        task = self.get_task()
        assert u'complete' == task['state']

        mock_mailer.assert_not_called()

    def test_scan_hook_complete_file_infected(self):
        self.insert_pending_task()

        mock_mailer = mock.Mock()
        with mock.patch('ckanext.unhcr.mailer.mail_user_by_id', mock_mailer):
            toolkit.get_action("scan_hook")(
                {'user': self.sysadmin['name']},
                {
                    "status": "complete",
                    "data": {
                        "status_code": 1,
                        "status_text": "SUCCESSFUL SCAN, FILE INFECTED",
                        "description": "/tmp/tmpmmy4xf83: Win.Test.EICAR_HDB-1 FOUND\n\n----------- SCAN SUMMARY -----------\nKnown viruses: 8945582\nEngine version: 0.102.4\nScanned directories: 0\nScanned files: 1\nInfected files: 1\nData scanned: 0.00 MB\nData read: 0.00 MB (ratio 0.00:1)\nTime: 27.025 sec (0 m 27 s)\n"
                    },
                    "metadata": {
                        "resource_id": self.resource['id'],
                    }
                }
            )

        task = self.get_task()
        assert u'complete' == task['state']

        mock_mailer.assert_called_once()

        assert self.sysadmin['id'] == mock_mailer.call_args[0][0]
        assert "[UNHCR RIDL] - Infected file found" == mock_mailer.call_args[0][1]
        assert "was scanned and found to be infected" in mock_mailer.call_args[0][2]
        assert "Win.Test.EICAR_HDB-1 FOUND" in mock_mailer.call_args[0][2]

    @pytest.mark.ckan_config('ckanext.unhcr.error_emails', 'errors@okfn.org fred@example.com')
    def test_scan_hook_error(self):
        self.insert_pending_task()

        mock_mailer = mock.Mock()
        with mock.patch('ckan.lib.mailer.mail_recipient', mock_mailer):
            toolkit.get_action("scan_hook")(
                {'user': self.sysadmin['name']},
                {
                    "status": "error",
                    "data": None,
                    "error": {"message": "oh no"},
                    "metadata": {
                        "resource_id": self.resource['id'],
                    }
                }
            )

        task = self.get_task()
        assert u'error' == task['state']
        assert u'{"message": "oh no"}' == task['error']

        assert 2 == mock_mailer.call_count
        assert 'errors@okfn.org' == mock_mailer.call_args_list[0][0][1]
        assert 'fred@example.com' == mock_mailer.call_args_list[1][0][1]
        assert '[UNHCR RIDL] Error performing Clam AV Scan' == mock_mailer.call_args[0][2]

    def test_scan_hook_other(self):
        self.insert_pending_task()

        toolkit.get_action("scan_hook")(
            {'user': self.sysadmin['name']},
            {
                "status": "some other status",
                "metadata": {
                    "resource_id": self.resource['id'],
                }
            }
        )
        task = self.get_task()
        assert u'some other status' == task['state']

    @responses.activate
    @pytest.mark.ckan_config('ckanext.unhcr.clamav_url', 'http://clamav:1234')
    def test_scan_hook_resubmit_not_required(self):
        responses.add_passthru(re.compile(r'^http:\/\/.*solr/.*$'))
        responses.add(responses.POST, 'http://clamav:1234/job', status=200)

        self.insert_pending_task()

        toolkit.get_action("scan_hook")(
            {'user': self.sysadmin['name']},
            {
                "status": "complete",
                "data": {
                    "status_code": 0,
                        "status_text": "SUCCESSFUL SCAN, FILE CLEAN",
                        "description": "/tmp/tmp37q_kv9u: OK...",
                },
                "metadata": {
                    "resource_id": self.resource['id'],
                    'original_url': self.resource['url'],
                    'task_created': self.resource['last_modified'],
                }
            }
        )

        assert responses.assert_call_count('http://clamav:1234/job', 0)

    @responses.activate
    @pytest.mark.ckan_config('ckanext.unhcr.clamav_url', 'http://clamav:1234')
    def test_scan_hook_resubmit_required_changed_url(self):
        responses.add_passthru(re.compile(r'^http:\/\/.*solr/.*$'))
        responses.add(responses.POST, 'http://clamav:1234/job', status=200)

        self.insert_pending_task()

        toolkit.get_action("scan_hook")(
            {'user': self.sysadmin['name']},
            {
                "status": "complete",
                "data": {
                    "status_code": 0,
                        "status_text": "SUCCESSFUL SCAN, FILE CLEAN",
                        "description": "/tmp/tmp37q_kv9u: OK...",
                },
                "metadata": {
                    "resource_id": self.resource['id'],
                    'original_url': 'not the same url stored on the task'
                }
            }
        )

        assert responses.assert_call_count('http://clamav:1234/job', 1)

    @responses.activate
    @pytest.mark.ckan_config('ckanext.unhcr.clamav_url', 'http://clamav:1234')
    def test_scan_hook_resubmit_required_more_recent_date(self):
        responses.add_passthru(re.compile(r'^http:\/\/.*solr/.*$'))
        responses.add(responses.POST, 'http://clamav:1234/job', status=200)

        self.insert_pending_task()

        last_modified = parse_date(self.resource['last_modified'])
        task_created = last_modified - datetime.timedelta(minutes=1)
        toolkit.get_action("scan_hook")(
            {'user': self.sysadmin['name']},
            {
                "status": "complete",
                "data": {
                    "status_code": 0,
                    "status_text": "SUCCESSFUL SCAN, FILE CLEAN",
                    "description": "/tmp/tmp37q_kv9u: OK...",
                },
                "metadata": {
                    "resource_id": self.resource['id'],
                    'task_created': task_created.isoformat(),
                }
            }
        )

        assert responses.assert_call_count('http://clamav:1234/job', 1)

    def test_scan_hook_invalid_params(self):
        with pytest.raises(toolkit.ValidationError):
            toolkit.get_action("scan_hook")(
                {'user': self.sysadmin['name']},
                {}
            )
        with pytest.raises(toolkit.ValidationError):
            toolkit.get_action("scan_hook")(
                {'user': self.sysadmin['name']},
                {
                    "status": "completed",
                }
            )
        with pytest.raises(toolkit.ValidationError):
            toolkit.get_action("scan_hook")(
                {'user': self.sysadmin['name']},
                {
                    "status": "completed",
                    "metadata": {}
                }
            )

    def test_after_resource_create_scan_submit_hook_called(self):

        f = tempfile.NamedTemporaryFile()
        new_resource_dict = {
            'package_id': self.dataset['id'],
            'url_type': 'upload',
            'upload': FlaskFileStorage(filename=f.name, stream=open(f.name, 'rb')),
            'type': 'data',
            'file_type': 'microdata',
            'identifiability': 'anonymized_public',
            'date_range_start': '2018-01-01',
            'date_range_end': '2019-01-01',
            'process_status': 'anonymized',
            'visibility': 'public',
            'version': '1',
        }
        action = toolkit.get_action("resource_create")

        action_call = mock.Mock()
        action_call.return_value = lambda conext, data_dict: True
        with mock.patch('ckan.plugins.toolkit.get_action', action_call):
            action({'user': self.sysadmin['name']}, new_resource_dict)

        action_call.assert_called_with('scan_submit')

    def test_after_kobo_resource_create_scan_submit_hook_not_called(self):

        f = tempfile.NamedTemporaryFile()
        new_resource_dict = {
            'package_id': self.dataset['id'],
            'url_type': 'upload',
            'upload': FlaskFileStorage(filename=f.name, stream=open(f.name, 'rb')),
            'type': 'data',
            'file_type': 'microdata',
            'identifiability': 'anonymized_public',
            'date_range_start': '2018-01-01',
            'date_range_end': '2019-01-01',
            'process_status': 'anonymized',
            'visibility': 'public',
            'version': '1',
        }
        action = toolkit.get_action("resource_create")

        action_call = mock.Mock()
        action_call.return_value = lambda conext, data_dict: True
        with mock.patch('ckan.plugins.toolkit.get_action', action_call):
            ctx = {
                'user': self.sysadmin['name'],
                'skip_clamav_scan': True,
            }
            action(ctx, new_resource_dict)

        mock_calls = [fn[0][0] for fn in action_call.call_args_list]
        assert 'scan_submit' not in mock_calls

    def test_after_kobo_resource_create_scan_submit_hook_called(self):

        f = tempfile.NamedTemporaryFile()
        new_resource_dict = {
            'package_id': self.dataset['id'],
            'url_type': 'upload',
            'upload': FlaskFileStorage(filename=f.name, stream=open(f.name, 'rb')),
            'type': 'data',
            'file_type': 'microdata',
            'identifiability': 'anonymized_public',
            'date_range_start': '2018-01-01',
            'date_range_end': '2019-01-01',
            'process_status': 'anonymized',
            'visibility': 'public',
            'version': '1',
        }
        action = toolkit.get_action("resource_create")

        action_call = mock.Mock()
        action_call.return_value = lambda conext, data_dict: True
        with mock.patch('ckan.plugins.toolkit.get_action', action_call):
            ctx = {
                'user': self.sysadmin['name']
            }
            action(ctx, new_resource_dict)

        action_call.assert_called()
        mock_calls = [fn[0][0] for fn in action_call.call_args_list]
        assert 'scan_submit' in mock_calls
