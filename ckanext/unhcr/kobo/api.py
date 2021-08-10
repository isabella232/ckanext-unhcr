import json
import logging
import os
import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout
from ckanext.unhcr.kobo.exceptions import KoboApiError, KoBoSurveyError


logger = logging.getLogger(__name__)


class KoBoAPI:
    """ About KoBo API
        https://support.kobotoolbox.org/api.html
    """
    def __init__(self, token, kobo_url):
        self.token = token
        self.kobo_url = kobo_url
        self.base_url = '{}/api/v2/'.format(kobo_url)
        self.surveys = None

    def _get(self, resource_url, return_json=True):
        """ Get any api/v2 resource in JSON format (or base response) """
        url = resource_url if resource_url.startswith('http') else self.base_url + resource_url
        logger.info('Getting KoBo resource: {}'.format(resource_url))
        try:
            response = requests.get(url, headers={'Authorization': 'Token ' + self.token})
            response.raise_for_status()
        except (ConnectionError, HTTPError, Timeout) as e:
            logger.error('Error getting KoBo resource {}: {}'.format(resource_url, e))
            raise KoboApiError('Error requesting data from Kobo {}'.format(e))

        if return_json:
            try:
                data = response.json()
            except ValueError:  # includes simplejson.decoder.JSONDecodeError
                logger.error('Error parsing KoBo response: \n{}'.format(response.text))
                raise
            return data
        else:
            return response

    def _post(self, resource_url, data):
        """ POST to KoBo API """
        url = resource_url if resource_url.startswith('http') else self.base_url + resource_url
        try:
            response = requests.post(url, data=data, headers={'Authorization': 'Token ' + self.token})
            response.raise_for_status()
        except (ConnectionError, HTTPError, Timeout) as e:
            logger.error('Error posting KoBo {}: {}'.format(resource_url, e))
            raise KoboApiError('Error posting data to Kobo {}: data: {} :: {}'.format(e, data, response.text))

        return response

    def get_surveys(self, limit=100, force=False, all_pages=True):
        if self.surveys is None or force:
            next_url = 'assets.json?limit={}'.format(limit)
            surveys = []
            while next_url:
                response = self._get(resource_url=next_url)
                surveys += [survey for survey in response['results'] if survey['asset_type'] == 'survey']
                if not all_pages:
                    return surveys
                next_url = response.get('next')
            self.surveys = surveys
        return self.surveys

    def get_asset(self, asset_id):
        resource_url = 'assets/{}.json'.format(asset_id)
        return self._get(resource_url)

    def test_token(self):
        try:
            self.get_surveys(all_pages=False)
        except KoboApiError:
            return False
        return True


class KoBoSurvey:
    def __init__(self, asset_id, kobo_api):
        self.kobo_api = kobo_api
        self.asset_id = asset_id
        self.asset = None
        self.data = None

    def load_asset(self):
        """ Load basic asset metadata """
        self.asset = self.kobo_api.get_asset(self.asset_id)

    def load_data(self):
        """ Load actual data from survey """
        next_url = 'assets/{}/data.json'.format(self.asset_id)
        data = []
        while next_url:
            response = self.kobo_api._get(next_url)
            data += response['results']
            next_url = response.get('next')

        self.data = data
        return data

    def get_exports(self, export_id):
        """ Get all exports """
        resource_url = 'assets/{}/exports/?format=json'.format(self.asset_id)
        return self.kobo_api._get(resource_url)

    def get_export(self, export_id):
        """ Get a single exports """
        resource_url = 'assets/{}/exports/{}/?format=json'.format(self.asset_id, export_id)
        return self.kobo_api._get(resource_url)

    def download_questionnaire(self, destination_path, dformat='xls'):
        """ Download survey questionnaire as XLS or XML """
        if dformat.lower() not in ['xls', 'xml']:
            raise KoBoSurveyError('Invalid format: {}'.format(dformat))

        file_name = '{}.{}'.format(self.asset_id, dformat)
        url = 'assets/{}'.format(file_name)
        response = self.kobo_api._get(url, return_json=False)

        file_path = os.path.join(destination_path, file_name)
        open(file_path, 'wb').write(response.content)

        return file_path

    def download_json_data(self, destination_path):
        """ Download JSON survey data (do not require export) """
        file_name = '{}_data.json'.format(self.asset_id)
        file_path = os.path.join(destination_path, file_name)

        data = self.load_data()
        final_data = json.dumps(data, indent=4)
        open(file_path, 'w').write(final_data)

        return file_path

    def download_data(self, destination_path, dformat, url):
        """ Download survey data (require previous export) """
        if dformat.lower() not in ['xls', 'csv']:
            raise KoBoSurveyError('Invalid format: {}'.format(dformat))

        file_name = '{}_data.{}'.format(self.asset_id, dformat)
        file_path = os.path.join(destination_path, file_name)
        # require private download
        response = self.kobo_api._get(url, return_json=False)
        if dformat.lower() == 'xls':
            final_data = response.content
            open(file_path, 'wb').write(final_data)
        elif dformat.lower() == 'csv':
            final_data = response.text
            open(file_path, 'w').write(final_data)

        return file_path

    def get_submission_times(self):
        """ read all submissions and get the first and the last one """
        if self.data is None:
            self.load_data()
        if len(self.data) == 0:
            return None, None

        sorted_list = sorted(self.data, key=lambda k: k['_submission_time'])
        first_submission = sorted_list[0]
        last_submission = sorted_list[-1]

        return first_submission['_submission_time'], last_submission['_submission_time']

    def create_export(self, dformat='csv'):
        """ Create a data dump. Check https://kobo.unhcr.org/exports/ """

        if dformat.lower() not in ['csv', 'xls', 'geojson', 'spss_labels']:
            raise KoBoSurveyError('Invalid export format: {}'.format(dformat))

        # Check if the user has permission to download data before
        # TODO
        source_url = '{}assets/{}/'.format(self.kobo_api.base_url, self.asset_id)
        payload = {
            "source": source_url,
            "fields_from_all_versions": "true",
            "group_sep": "/",
            "hierarchy_in_labels": "true",
            "lang": "_default",
            "multiple_select": "both",
            "type": dformat.lower(),
            "flatten": "true"
        }

        export_post_url = '{}/exports/?format=json'.format(self.kobo_api.kobo_url)
        response = self.kobo_api._post(export_post_url, payload)

        """
        sample response
        {
            'uid': 'eTynYph8kZpeu4bvGS2cSX',
            'url': 'https://kobo.unhcr.org/exports/eTynYph8kZpeu4bvGS2cSX/',
            'status': 'processing'
        }

        and then we expect

        {
            "url": "https://kobo.unhcr.org/exports/SOME_EXPORT_ID/",
            "status": "complete",
            "messages": {},
            "uid": "ekXzzguVxBfJErts6MvCib",
            "date_created": "2021-08-06T16:29:38.061023Z",
            "last_submission_time": "2019-10-04T13:36:39Z",
            "result": "https://kobo.unhcr.org/private-media/avazquez/exports/SURVEY_NAME_-_all_versions_-_labels_-_2021-08-06-16-29-38.csv",
            "data": {
                "lang": "_default",
                "name": null,
                "type": "csv",
                "fields": [],
                "source": "https://kobo.unhcr.org/api/v2/assets/ASSET_ID/",
                "group_sep": "/",
                "multiple_select": "both",
                "hierarchy_in_labels": false,
                "processing_time_seconds": 1.808768,
                "fields_from_all_versions": true
            }
        }
        """
        data = response.json()
        logger.info('KoBo Export created {}'.format(data))
        return data
