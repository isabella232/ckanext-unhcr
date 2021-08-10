import os
from werkzeug.datastructures import FileStorage as FlaskFileStorage
from ckan.lib.munge import munge_title_to_name
from ckan.plugins import toolkit
from ckanext.unhcr.kobo.api import KoBoAPI, KoBoSurvey
from ckanext.unhcr.kobo.exceptions import KoBoDuplicatedDatasetError, KoboMissingAssetIdError


class KoboDataset:
    def __init__(self, kobo_asset_id, package_dict=None):
        self.kobo_asset_id = kobo_asset_id
        self.package_dict = package_dict
        self.kobo_api = None  # the KoBoAPI object

        # define the path for resources
        path = toolkit.config.get('ckan.storage_path')
        self.upload_path = os.path.join(path, 'storage', 'uploads', 'surveys')
        try:
            os.makedirs(self.upload_path)
        except OSError as e:
            # errno 17 is file already exists
            if e.errno != 17:
                raise

    def get_package(self, raise_multiple_error=True):
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
            if raise_multiple_error:
                raise KoBoDuplicatedDatasetError(error)
            else:
                # returns first
                return packages['results'][0]
        elif total == 1:
            package = packages['results'][0]
            return package
        else:
            return None

    def get_kobo_api(self, user_obj):
        """ Return the KoboAPI object for a CKAN user """
        if not self.kobo_api:
            plugin_extras = {} if user_obj.plugin_extras is None else user_obj.plugin_extras
            kobo_token = plugin_extras.get('unhcr', {}).get('kobo_token')
            kobo_url = toolkit.config.get('ckanext.unhcr.kobo_url', 'https://kobo.unhcr.org')
            self.kobo_api = KoBoAPI(kobo_token, kobo_url)

        return self.kobo_api

    def get_initial_package(self, user_obj):
        """ Get the initial package from the kobo asset.
            Require the user to get the token and to validate
            ownership on the asset.
            Return a pkg_dict or raises an error """

        kobo_api = self.get_kobo_api(user_obj)
        asset = kobo_api.get_asset(self.kobo_asset_id)

        pkg = {
            'title': asset['name'],
            'name': munge_title_to_name(asset['name']),
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

    def initialize_package(self, context, pkg_dict, user_obj):
        """ After KoBo pkg created we need to create basic resources.
            Uses context from the package_create call and the created dataset """

        kobo_asset_id = pkg_dict.get('kobo_asset_id')
        if not kobo_asset_id:
            raise KoboMissingAssetIdError('Missing kobo_asset_id in package')

        # TODO this should be a job. Here we just need to initialize the resources
        kobo_api = self.get_kobo_api(user_obj)
        survey = KoBoSurvey(kobo_asset_id, kobo_api)
        # Create a resource for the questionnaire
        self.create_questionnaire_resource(context, pkg_dict, survey)

        # Create data resource
        self.create_data_resource(context, pkg_dict, survey)
        return

    def create_questionnaire_resource(self, context, pkg_dict, survey):
        """ Create a resource for the questionnaire """

        local_file = survey.download_questionnaire(destination_path=self.upload_path)

        resource = {
            'package_id': pkg_dict['id'],
            'upload': FlaskFileStorage(filename=local_file, stream=open(local_file, 'rb')),
            'name': 'Questionnaire XLS',
            'description': '[Special resources] Automatic questionnaire from KoBo survey',
            'format': 'xls',
            'url_type': 'upload',
            'type': 'attachment',  # | data
            'visibility': 'public',  # |  restricted
            'file_type': 'questionnaire',  # | microdata | report | sampling_methodology | infographics | script | concept note | other
            # mark this resources as special
            'extras': {'special': 'questionnaire'}
        }

        action = toolkit.get_action("resource_create")
        resource = action(context, resource)

        return resource

    def create_data_resource(self, context, pkg_dict, survey):
        """ Create a resource for the survey data """

        local_file = survey.download_data(destination_path=self.upload_path, dformat='json')
        date_range_start, date_range_end = survey.get_submission_times()
        if date_range_start is None:
            # we can use the inacurate creation and modification dates from the survey
            date_range_start = survey.asset.get('date_created')
            date_range_end = survey.asset.get('date_modified')

        resource = {
            'package_id': pkg_dict['id'],
            'upload': FlaskFileStorage(filename=local_file, stream=open(local_file, 'rb')),
            'name': 'Survey JSON data',
            'description': '[Special resources] Automatic Data from KoBo survey',
            'format': 'json',
            'url_type': 'upload',
            'type': 'data',
            'version': '1',
            'date_range_start': date_range_start,
            'date_range_end': date_range_end,
            'visibility': 'restricted',
            'process_status': 'raw',
            'identifiability': 'personally_identifiable',
            'file_type': 'microdata',
            # mark this resources as special
            'extras': {'special': 'data'}
        }

        action = toolkit.get_action("resource_create")
        resource = action(context, resource)

        return resource
