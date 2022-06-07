import base64
import json
import logging
import os
import requests
from redis import Redis, ConnectionPool
from redis.exceptions import ConnectionError
from requests.exceptions import ConnectionError, HTTPError, Timeout
from ckan.common import config
from ckanext.unhcr.kobo import VALID_KOBO_EXPORT_FORMATS
from ckanext.unhcr.kobo.exceptions import KoboApiError, KoBoSurveyError


logger = logging.getLogger(__name__)


class KoBoAPI:
    """ About KoBo API
        https://support.kobotoolbox.org/api.html
    """
    def __init__(self, token, kobo_url, cache_prefix):
        self.token = token
        self.kobo_url = kobo_url
        self.base_url = '{}/api/v2/'.format(kobo_url)
        self.surveys = None
        self._user = None
        # We use RIDL user name as prefix because we call same URL for different users
        self.cache_prefix = cache_prefix
        self.cache_seconds = int(config.get('ckanext.unhcr.kobo_cache_seconds', '600'))
        redis_url = config.get('ckan.redis.url', 'redis://localhost:6379/0')
        if self.cache_seconds == 0:
            self.cache = None
        else:
            try:
                redis_pool = ConnectionPool.from_url(redis_url)
                self.cache = Redis(connection_pool=redis_pool)
            except ConnectionError:
                logger.error('Error connecting to Redis cache: {} {} {}'.format(redis_url))
                self.cache = None

    def _get(self, resource_url, return_json=True, force=False):
        """ Get any api/v2 resource in JSON format (or base response)
            For JSON responses we use a Redis cache to avoid hitting KoBoToolbox too often
            Force=True to skip cache
            """
        url = resource_url if resource_url.startswith('http') else self.base_url + resource_url
        logger.info('Getting KoBoToolbox resource: {}'.format(resource_url))
        if return_json:
            if self.cache and not force:
                # Different users calls the same URLs so we need to use the users as a part of the cache key
                cache_name = '{}__{}'.format(self.cache_prefix, url)
                cache_key = base64.b64encode(cache_name.encode())
                if self.cache.get(cache_key):
                    data = json.loads(self.cache.get(cache_key))
                    logger.info('Using cache for KoBo response: {} :: {}'.format(self.cache_prefix, resource_url))
                    return data

            logger.info('Resource not cached: {} :: {}'.format(self.cache_prefix, resource_url))

        try:
            response = requests.get(url, headers={'Authorization': 'Token ' + self.token})
            response.raise_for_status()
        except (ConnectionError, HTTPError, Timeout) as e:
            logger.error('Error getting KoBoToolbox resource {}: {}'.format(resource_url, e))
            raise KoboApiError('Error requesting data from KoBoToolbox {}'.format(e))

        if return_json:
            try:
                data = response.json()
            except ValueError:  # includes simplejson.decoder.JSONDecodeError
                logger.error('Error parsing KoBoToolbox response: \n{}'.format(response.text))
                raise
            if self.cache:
                self.cache.set(cache_key, json.dumps(data), ex=self.cache_seconds)
            return data
        else:
            return response

    def _post(self, resource_url, data):
        """ POST to KoBo API """
        url = resource_url if resource_url.startswith('http') else self.base_url + resource_url
        try:
            response = requests.post(url, json=data, headers={'Authorization': 'Token ' + self.token})
            response.raise_for_status()
        except (ConnectionError, HTTPError, Timeout) as e:
            logger.error('Error posting KoBoToolbox {}: {}'.format(resource_url, e))
            raise KoboApiError('Error posting data to KoBoToolbox {}: data: {} :: {}'.format(e, data, response.text))

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

        # add permission information
        # detect if user has permission to manage the survey
        for survey in self.surveys:
            survey['user_is_manager'] = self._detect_manager_permission(survey)

        return self.surveys

    def get_asset(self, asset_id):
        """ get a single asset """
        resource_url = 'assets/{}.json'.format(asset_id)
        asset = self._get(resource_url)
        asset['user_is_manager'] = self._detect_manager_permission(asset)

        return asset

    @property
    def current_user(self):
        if self._user is None:
            url = '{}/me'.format(self.kobo_url)
            self._user = self._get(url)
        return self._user

    def _detect_manager_permission(self, survey):
        user_name = self.current_user['username']
        manager_permission_id = '{}permissions/manage_asset.json'.format(self.base_url)
        user_id = '{}users/{}.json'.format(self.base_url, user_name)
        permissions = survey.get('permissions', [])
        manage_permissions = [
            p for p in permissions 
            if p['permission'] == manager_permission_id and p['user'] == user_id
        ]
        return len(manage_permissions) > 0

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
        if self.asset is None:
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

    def get_total_submissions(self):
        """ Count all submissions for a survey """
        self.load_asset()
        return self.asset['deployment__submission_count']

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

        logger.info('Downloading questionnaire for asset {}'.format(self.asset_id))
        file_name = '{}.{}'.format(self.asset_id, dformat)
        url = 'assets/{}'.format(file_name)
        response = self.kobo_api._get(url, return_json=False)

        file_path = os.path.join(destination_path, file_name)
        open(file_path, 'wb').write(response.content)

        return file_path

    def download_json_data(self, destination_path, resource_name):
        """ Download JSON survey data (do not require export) """
        file_name = '{}__{}_data.json'.format(resource_name, self.asset_id)
        file_path = os.path.join(destination_path, file_name)

        data = self.load_data()
        final_data = json.dumps(data, indent=4)
        open(file_path, 'w').write(final_data)

        return file_path

    def download_data(self, destination_path, resource_name, dformat, url):
        """ Download survey data (require previous export) """
        if dformat.lower() not in VALID_KOBO_EXPORT_FORMATS.keys():
            raise KoBoSurveyError('Invalid format: {}'.format(dformat))

        extension = 'zip' if dformat.lower() == 'spss_labels' else dformat.lower()
        file_name = '{}__{}_data.{}'.format(resource_name, self.asset_id, extension)
        file_path = os.path.join(destination_path, file_name)
        # require private download
        response = self.kobo_api._get(url, return_json=False)
        if dformat.lower() in ['xls', 'spss_labels']:
            final_data = response.content
            open(file_path, 'wb').write(final_data)
        else:  # csv and geojson are text files
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

    def create_export(
        self,
        dformat='csv',
        fields_from_all_versions=True,
        group_sep='/',
        hierarchy_in_labels=True,
        lang='_default',
        multiple_select='both',
        flatten=True,
        fields=None,
        query=None
    ):
        """ Create a data dump. Check https://kobo.unhcr.org/exports/ """

        if dformat.lower() not in ['csv', 'xls', 'geojson', 'spss_labels']:
            raise KoBoSurveyError('Invalid export format: {}'.format(dformat))

        payload = {
            "fields_from_all_versions": fields_from_all_versions,
            "group_sep": group_sep,
            "hierarchy_in_labels": hierarchy_in_labels,
            "lang": lang,
            "multiple_select": multiple_select,
            "type": dformat.lower(),
            "flatten": flatten,
        }

        if query:
            payload["query"] = query

        if fields:
            payload["fields"] = fields

        # To use the Query param is required to use /assets/ASSSET_ID
        # The simpler URL /exports require source and do not allow querying
        export_post_url = '{}assets/{}/exports/?format=json'.format(self.kobo_api.base_url, self.asset_id)
        response = self.kobo_api._post(export_post_url, payload)

        data = response.json()
        logger.info('KoBoToolbox Export created {}'.format(data))
        return data
