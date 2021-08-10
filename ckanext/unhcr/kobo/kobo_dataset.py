from ckan.lib.munge import munge_title_to_name, munge_name
from ckan.plugins import toolkit
from ckanext.unhcr.kobo.api import KoBoAPI
from ckanext.unhcr.kobo.exceptions import KoBoDuplicatedDatasetError


class KoboDataset:
    def __init__(self, kobo_asset_id, package_dict=None):
        self.kobo_asset_id = kobo_asset_id
        self.package_dict = package_dict

    def get_package(self):
        """ Check if the kobo_asset_id already exist and return it
            Raises an error if multiple packages exists
            Returns: package: if exists (or None)
            """

        search_dict = {
            'q': '*:*',
            'fq': (
                'kobo_asset_id:{}'.format(self.kobo_asset_id)
            ),
            'include_private': True,
            'include_drafts': True,  # For unfinished import processes
        }
        packages = toolkit.get_action('package_search')({'ignore_auth': True}, search_dict)
        total = packages['count']
        # We only expect one dataset
        if total > 1:
            duplicates = [pkg['name'] for pkg in packages['results']]
            error = 'Duplicated dataset with KoBo ID {}: {}'.format(
                self.kobo_asset_id,
                duplicates
            )
            raise KoBoDuplicatedDatasetError(error)
        elif total == 1:
            package = packages['results'][0]
            return package
        else:
            return None

    def get_initial_package(self, user_obj):
        """ Get the initial package from the kobo asset.
            Require the user to get the token and to validate
            ownership on the asset.
            Return a pkg_dict or raises an error """

        plugin_extras = {} if user_obj.plugin_extras is None else user_obj.plugin_extras
        kobo_token = plugin_extras.get('unhcr', {}).get('kobo_token')
        kobo_url = toolkit.config.get('ckanext.unhcr.kobo_url', 'https://kobo.unhcr.org')
        kobo_api = KoBoAPI(kobo_token, kobo_url)
        asset = kobo_api.get_asset(self.kobo_asset_id)

        pkg = {
            'title': asset['name'],
            'notes': self._build_asset_notes(asset),
            'original_id': asset['uid'],
            'extras': [
                {'key': 'kobo_asset_id', 'value': self.kobo_asset_id},
                {'key': 'kobo_owner', 'value': asset['owner__username']},
                {'key': 'kobo_sector', 'value': asset['settings'].get('sector')},
                {'key': 'kobo_country', 'value': asset['settings'].get('country')},
            ],
        }

        return pkg

    def _build_asset_notes(self, asset):
        """ Build starting notes from asset info """
        starting_notes = 'Dataset imported from KoBo toolbox'
        starting_notes += '\nKoBo owner: {}'.format(asset['owner__username'])

        sector = asset['settings'].get('sector')
        if sector:
            starting_notes += '\nSector: {}'.format(sector['label'])

        country = asset['settings'].get('country')
        if country:
            starting_notes += '\nCountry: {} ({})'.format(country['label'], country['value'])

        original_description = asset['settings'].get('description')
        if original_description:
            starting_notes += '\nOriginal resource description: {}'.format(original_description)

        return starting_notes

    def initialize_package(self, context, pkg_dict):
        """ After KoBo pkg created we need to create basic resources.
            Uses context from the package_create call and the created dataset """

        # # create resources
        # new_resource_dict = {
        #     'package_id': pkg_dict['id'],
        #     'url': 'https://test.com',
        #     # 'url_type': 'upload', ?
        #     'type': 'data',
        #     'file_type': '',  # use file_type field options in form
        #     # 'identifiability': 'anonymized_public',
        #     # 'date_range_start': '2018-01-01',
        #     # 'date_range_end': '2019-01-01',
        #     # 'process_status': 'anonymized',
        #     # 'visibility': 'public',
        # }

        # action = toolkit.get_action("resource_create")
        # resource = action(
        #     context,
        #     new_resource_dict
        # )

        # return resource

        # 626
        return
