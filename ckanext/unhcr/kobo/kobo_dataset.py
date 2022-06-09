import datetime
import logging
import os
import tempfile
from dateutil.parser import parse as parse_date
from werkzeug.datastructures import FileStorage as FlaskFileStorage
from ckan.lib.munge import munge_title_to_name
from ckan.plugins import toolkit
from ckanext.unhcr.kobo.api import KoBoAPI, KoBoSurvey
from ckanext.unhcr.kobo.exceptions import (
    KoBoDuplicatedDatasetError,
    KoboMissingAssetIdError,
    KoBoEmptySurveyError,
    KoBoUserTokenMissingError
)
from ckanext.unhcr.kobo.filters import process_pkg_kobo_filters


logger = logging.getLogger(__name__)
DOWNLOAD_PENDING_MSG = 'The resource is pending download.'


class KoboDataset:
    def __init__(self, kobo_asset_id, package_dict=None):
        if not kobo_asset_id:
            raise KoboMissingAssetIdError('Missing kobo_asset_id')
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

    def get_package(self, raise_multiple_error=True, raise_none_error=False):
        """ Check if the kobo_asset_id already exist and return it
            Raises an error if multiple packages exists
            Returns: package: if exists (or None)
            """
        if self.package_dict:
            return self.package_dict

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
            error = 'Duplicated dataset with KoBoToolbox ID {}: {}'.format(
                self.kobo_asset_id,
                duplicates
            )
            if raise_multiple_error:
                raise KoBoDuplicatedDatasetError(error)
            else:
                # returns first
                self.package_dict = packages['results'][0]
                return packages['results'][0]
        elif total == 1:
            package = packages['results'][0]
            self.package_dict = package
            return package
        else:
            if raise_none_error:
                raise KoboMissingAssetIdError('No KoBoToolbox package found for asset {}'.format(self.kobo_asset_id))
            return None

    def get_import_status(self):
        """ Return the kobo import status at a dataset level
            "error" at least one resource have error
            "stalled" if we have pending resources from a long time
            "pending" at least one resource pending (not stalled) without error
            "complete" all resources are complete """

        kobo_package = self.get_package(raise_none_error=True)
        statuses = []
        for res in kobo_package['resources']:
            if res.get('kobo_type') not in ['data', 'questionnaire']:
                continue
            kobo_details = res.get('kobo_details')
            if not kobo_details:
                continue

            status = res['kobo_details']['kobo_download_status']
            if status == 'error':
                return 'error'
            if status == 'pending':
                # check if stalled
                updated = res['kobo_details']['kobo_last_updated']
                date_updated = parse_date(updated)
                if datetime.datetime.now() - date_updated > datetime.timedelta(hours=1):
                    statuses.append('stalled')
                else:
                    statuses.append('pending')

        if 'stalled' in statuses:
            return 'stalled'
        elif 'pending' in statuses:
            return 'pending'

        return 'complete'

    def get_kobo_api(self, user_obj):
        """ Return the KoboAPI object for a CKAN user """
        if not self.kobo_api:
            plugin_extras = {} if user_obj.plugin_extras is None else user_obj.plugin_extras
            kobo_token = plugin_extras.get('unhcr', {}).get('kobo_token')
            if not kobo_token:
                raise KoBoUserTokenMissingError()
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
        starting_notes = 'Dataset imported from KoBoToolbox'
        starting_notes += '\nKoBoToolbox owner: {}'.format(asset['owner__username'])

        sector = asset['settings'].get('sector')
        if sector:
            # KoBo "settings" field is a JSON field. We can't be sure in its internal structure
            # Check https://github.com/okfn/ckanext-unhcr/issues/823
            if type(sector) == dict:
                starting_notes += '\nSector: {}'.format(sector['label'])

        country = asset['settings'].get('country')
        if country:
            # KoBo "settings" field is a JSON field. We can't be sure in its internal structure
            # Check https://github.com/okfn/ckanext-unhcr/issues/823
            if type(country) == dict:
                starting_notes += '\nCountry: {} ({})'.format(country['label'], country['value'])

        original_description = asset['settings'].get('description')
        if original_description:
            starting_notes += '\nOriginal resource description: {}'.format(original_description)

        return starting_notes

    def create_kobo_resources(self, context, pkg_dict, user_obj, kobo_filters):
        """ After KoBo pkg created we need to create basic resources.
            Uses context from the package_create call and the created dataset """

        kobo_asset_id = pkg_dict.get('kobo_asset_id')
        if not kobo_asset_id:
            raise KoboMissingAssetIdError('Missing kobo_asset_id in package')

        # TODO this should be a job. Here we just need to initialize the resources
        kobo_api = self.get_kobo_api(user_obj)
        survey = KoBoSurvey(kobo_asset_id, kobo_api)

        if survey.get_total_submissions() == 0:
            raise KoBoEmptySurveyError('KoBoToolbox survey has no submissions')

        # create the export for the expected formats (this starts an async process at KoBo)
        final_kobo_filters = process_pkg_kobo_filters(kobo_filters)
        
        if final_kobo_filters['include_questionnaire']:
            # Create a resource for the questionnaire
            self.create_questionnaire_resource(context, pkg_dict)

        # Create JSON, CSV and XLS data resources
        self.create_data_resources(context, pkg_dict, survey, final_kobo_filters)
        return

    def create_questionnaire_resource(self, context, pkg_dict):
        """ Create a resource for the questionnaire """
        from ckanext.unhcr.jobs import download_kobo_file

        # create empty resources to be updated later
        f = tempfile.NamedTemporaryFile()

        resource = {
            'package_id': pkg_dict['id'],
            'upload': FlaskFileStorage(filename=f.name, stream=open(f.name, 'rb')),
            'name': 'Questionnaire XLS',
            'description': 'Questionnaire imported from the KoBo survey',
            'format': 'xls',
            'url_type': 'upload',
            'type': 'attachment',
            'visibility': 'public',
            'file_type': 'questionnaire',
            'kobo_type': 'questionnaire',
            'kobo_details': {
                'kobo_asset_id': self.kobo_asset_id,
                'kobo_download_status': 'pending',
                'kobo_download_attempts': 0,
                'kobo_last_updated': datetime.datetime.utcnow().isoformat()
            }
        }

        action = toolkit.get_action("resource_create")
        resource = action(context, resource)

        # Start a job to download the questionnaire
        toolkit.enqueue_job(download_kobo_file, [resource['id']], title='Download KoBoToolbox questionnaire')

        return resource

    def create_data_resources(self, context, pkg_dict, survey, kobo_filters):
        """ Create multiple resources for the survey data """
        from ckanext.unhcr.jobs import download_kobo_file

        date_range_start, date_range_end = survey.get_submission_times()
        if date_range_start is None:
            survey.load_asset()  # required to get the dates
            # we can use the inacurate creation and modification dates from the survey
            # those are DateTimes and we need just Dates
            date_created = parse_date(survey.asset.get('date_created'))
            date_modified = parse_date(survey.asset.get('date_modified'))

            date_range_start = date_created.strftime('%Y-%m-%d')
            date_range_end = date_modified.strftime('%Y-%m-%d')

        resources = []
        # create empty resources to be updated later
        f = tempfile.NamedTemporaryFile()

        logger.info('Kobo filters: {}'.format(kobo_filters))
        for data_resource_format in kobo_filters['formats']:
            # JSON do not require an export
            if data_resource_format != 'json':

                params = kobo_filters.copy()
                params['dformat'] = data_resource_format
                params.pop('include_questionnaire')
                params.pop('formats')
                logger.info('Preparing export {}'.format(params))
                export = survey.create_export(**params)
                export_id = export['uid']
            else:
                export_id = None

            description = '{} data imported from the KoBoToolbox survey. {}'.format(data_resource_format.upper(), DOWNLOAD_PENDING_MSG)
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
                    'kobo_last_updated': datetime.datetime.utcnow().isoformat(),
                    # keep track on filters to show and to be able to update the resource in the future
                    'kobo_filter_fields_from_all_versions': kobo_filters['fields_from_all_versions'],
                    'kobo_filter_group_sep': kobo_filters['group_sep'],
                    'kobo_filter_fields': kobo_filters['fields'],
                    'kobo_filter_query': kobo_filters['query'],
                    'kobo_filter_multiple_select': kobo_filters['multiple_select'],
                    'kobo_filter_hierarchy_in_labels': kobo_filters['hierarchy_in_labels'],
                }
            }

            action = toolkit.get_action("resource_create")
            context.update({'skip_clamav_scan': True})
            resource = action(context, resource)
            resources.append(resource)

            # Start a job to download the file
            toolkit.enqueue_job(download_kobo_file, [resource['id']], title='Download KoBoToolbox survey {} data'.format(data_resource_format))

        return resources

    def update_kobo_details(self, resource_dict, user_name, new_kobo_details):
        """ Update just details to a KoBo resource """

        context = {'user': user_name, 'job': True}
        if not resource_dict:
            raise toolkit.ValidationError({'resource': ["empty resource to update"]})
        kobo_details = resource_dict.get('kobo_details')
        if not kobo_details:
            raise toolkit.ValidationError({'kobo_details': ["kobo_details is missing from resource {}".format(resource_dict)]})

        kobo_details.update(new_kobo_details)
        kobo_details['kobo_last_updated'] = datetime.datetime.utcnow().isoformat()

        resource = toolkit.get_action('resource_patch')(
            context,
            {
                'id': resource_dict['id'],
                'kobo_details': kobo_details,
            }
        )
        return resource

    def update_resource(self, resource_dict, local_file, user_name):
        """ Update the resource with real data """
        logger.info('Updating resource {} from file {}'.format(resource_dict['id'], local_file))
        context = {'user': user_name, 'job': True}
        if not resource_dict:
            raise toolkit.ValidationError({'resource': ["empty resource to update"]})
        kobo_details = resource_dict.get('kobo_details')
        if not kobo_details:
            raise toolkit.ValidationError({'kobo_details': ["kobo_details is missing from resource {}".format(resource_dict)]})
        kobo_download_attempts = kobo_details.get('kobo_download_attempts', 0)

        kobo_details['kobo_download_status'] = 'complete'
        kobo_details['kobo_download_attempts'] = kobo_download_attempts + 1
        kobo_details['kobo_last_updated'] = datetime.datetime.utcnow().isoformat()

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
        logger.info('Resource {} updated {}'.format(resource_dict['id'], kobo_details['kobo_last_updated']))
        return resource

    def update_all_resources(self, user_id):
        """ update all resources (and questionnaire) in the package with new submissions """
        from ckanext.unhcr.jobs import download_kobo_file, update_kobo_resource

        kobo_package = self.get_package(raise_none_error=True)
        logger.info('Updating all resources for package {}'.format(kobo_package['name']))

        # update each resource
        for resource in kobo_package['resources']:
            if resource.get('kobo_type') == 'questionnaire':
                toolkit.enqueue_job(download_kobo_file, [resource['id']], title='Preparing to update questionnaire resource')
                continue
            if resource.get('kobo_type') != 'data':
                continue
            kobo_details = resource.get('kobo_details')
            if not kobo_details:
                continue
            # this is a kobo resource we want to update
            toolkit.enqueue_job(update_kobo_resource, [resource['id'], user_id], title='Preparing to update data resource')
