import logging
import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout
from ckanext.unhcr.kobo.exceptions import KoboApiError


logger = logging.getLogger(__name__)


class KoBoAPI:
    """ About KoBolo API
        https://support.kobotoolbox.org/api.html
    """
    def __init__(self, token, kobo_url):
        self.token = token
        self.base_url = '{}/api/v2/'.format(kobo_url)
        self.surveys = None

    def _get(self, resource_url):
        """ Get any api/v2 resource in JSON format """
        url = resource_url if resource_url.startswith('http') else self.base_url + resource_url
        try:
            response = requests.get(url, headers={'Authorization': 'Token ' + self.token})
            response.raise_for_status()
        except (ConnectionError, HTTPError, Timeout) as e:
            logger.error('Error getting KoBo resource {}: {}'.format(resource_url, e))
            raise KoboApiError('Error requesting data from Kobo {}'.format(e))

        return response.json()

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
        except Exception:
            return False
        return True
