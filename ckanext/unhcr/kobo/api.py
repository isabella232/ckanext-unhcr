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
        self.base_url = '{}/api/v2/'.format(kobo_url)
        self.surveys = None

    def _get(self, resource_url, return_json=True):
        """ Get any api/v2 resource in JSON format (or base response) """
        url = resource_url if resource_url.startswith('http') else self.base_url + resource_url
        try:
            response = requests.get(url, headers={'Authorization': 'Token ' + self.token})
            response.raise_for_status()
        except (ConnectionError, HTTPError, Timeout) as e:
            logger.error('Error getting KoBo resource {}: {}'.format(resource_url, e))
            raise KoboApiError('Error requesting data from Kobo {}'.format(e))

        if return_json:
            return response.json()
        else:
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

    def get_csv_data(self):
        """ get final text data for CSV file """
        raise NotImplementedError('CSV data is not ready')

    def get_xls_data(self):
        """ get final binary data for XLS file """
        raise NotImplementedError('CSV data is not ready')

    def download_questionnaire(self, destination_path, dformat='xls'):
        """ Download survey questionnaire as XLS or XML """
        if dformat not in ['xls', 'xml']:
            raise KoBoSurveyError('Invalid format: {}'.format(dformat))

        file_name = '{}.{}'.format(self.asset_id, dformat)
        url = 'assets/{}'.format(file_name)
        response = self.kobo_api._get(url, return_json=False)

        file_path = os.path.join(destination_path, file_name)
        open(file_path, 'wb').write(response.content)

        return file_path

    def download_data(self, destination_path, dformat='json'):
        """ Download survey data """
        if dformat not in ['json', 'xls', 'csv']:
            raise KoBoSurveyError('Invalid format: {}'.format(dformat))

        file_name = '{}_data.{}'.format(self.asset_id, dformat)
        data = self.load_data()

        file_path = os.path.join(destination_path, file_name)

        if dformat == 'json':
            final_data = json.dumps(data, indent=4)
            open(file_path, 'w').write(final_data)
        elif dformat == 'xls':
            final_data = self.get_xls_data()
            open(file_path, 'wb').write(final_data)
        elif dformat == 'csv':
            final_data = self.get_csv_data()
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
