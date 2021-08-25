import os
import tempfile
from werkzeug.datastructures import FileStorage as FlaskFileStorage
from ckan.lib.munge import munge_title_to_name
from ckan.plugins import toolkit
from ckanext.unhcr.kobo.api import KoBoAPI, KoBoSurvey
from ckanext.unhcr.kobo.exceptions import KoBoDuplicatedDatasetError, KoboMissingAssetIdError


DOWNLOAD_PENDING_MSG = 'The resource is pending download.'


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

    def create_kobo_resources(self, context, pkg_dict, user_obj):
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

        # Create JSON, CSV and XLS data resources
        self.create_data_resources(context, pkg_dict, survey)
        return

    def create_questionnaire_resource(self, context, pkg_dict, survey):
        """ Create a resource for the questionnaire """

        local_file = survey.download_questionnaire(destination_path=self.upload_path)

        resource = {
            'package_id': pkg_dict['id'],
            'upload': FlaskFileStorage(filename=local_file, stream=open(local_file, 'rb')),
            'name': 'Questionnaire XLS',
            'description': 'Questionnaire imported from the KoBo survey',
            'format': 'xls',
            'url_type': 'upload',
            'type': 'attachment',
            'visibility': 'public',
            'file_type': 'questionnaire',
            'kobo_type': 'questionnaire',
        }

        action = toolkit.get_action("resource_create")
        resource = action(context, resource)

        return resource

    def create_data_resources(self, context, pkg_dict, survey):
        """ Create multiple resources for the survey data """
        from ckanext.unhcr.jobs import download_kobo_export

        date_range_start, date_range_end = survey.get_submission_times()
        if date_range_start is None:
            # we can use the inacurate creation and modification dates from the survey
            date_range_start = survey.asset.get('date_created')
            date_range_end = survey.asset.get('date_modified')

        resources = []
        # create empty resources to be downloaded later
        f = tempfile.NamedTemporaryFile()

        for data_resource_format in ['json', 'csv', 'xls']:
            # JSON do not require an export
            if data_resource_format != 'json':
                # create the export for the expected format (this starts an async process at KoBo)
                export = survey.create_export(dformat=data_resource_format)
                export_id = export['uid']
            else:
                export_id = None

            description = '{} data imported from the KoBo survey. {}'.format(data_resource_format.upper(), DOWNLOAD_PENDING_MSG)
            resource = {
                'package_id': pkg_dict['id'],
                'name': 'Survey {} data'.format(data_resource_format),
                'description': description,
                'url_type': 'upload',
                'upload': FlaskFileStorage(filename=f.name, stream=open(f.name, 'rb')),
                'format': data_resource_format,
                'type': 'data',
                'version': '1',
                'date_range_start': date_range_start,
                'date_range_end': date_range_end,
                'visibility': 'restricted',
                'process_status': 'raw',
                'identifiability': 'personally_identifiable',
                'file_type': 'microdata',
                'kobo_type': 'data',
                'kobo_details': {
                    'kobo_export_id': export_id,
                    'kobo_asset_id': self.kobo_asset_id,
                    'kobo_download_status': 'pending',
                    'kobo_download_attempts': 0,
                }
            }

            action = toolkit.get_action("resource_create")
            resource = action(context, resource)
            resources.append(resource)

            # Start a job to download the file
            toolkit.enqueue_job(download_kobo_export, [resource['id']])

        return resources

    def update_resource(self, resource_dict, local_file, user_name):
        """ Update the resource with real data """

        context = {'user': user_name}
        if not resource_dict:
            raise toolkit.ValidationError({'resource': ["empty resource to update"]})
        kobo_details = resource_dict.get('kobo_details')
        if not kobo_details:
            raise toolkit.ValidationError({'kobo_details': ["kobo_details is missing from resource {}".format(resource_dict)]})
        kobo_download_attempts = kobo_details.get('kobo_download_attempts', 0)

        kobo_details['kobo_download_status'] = 'complete'
        kobo_details['kobo_download_attempts'] = kobo_download_attempts + 1

        resource = toolkit.get_action('resource_patch')(
            context,
            {
                'id': resource_dict['id'],
                'url_type': 'upload',
                'upload': FlaskFileStorage(filename=local_file, stream=open(local_file, 'rb')),
                'description': resource_dict['description'].replace(DOWNLOAD_PENDING_MSG, ''),
                'kobo_details': kobo_details,
            }
        )
        return resource
