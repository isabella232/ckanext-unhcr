from ckanext.unhcr.kobo.exceptions import KoboApiError
from functools import wraps
import datetime
import logging
import time

from ckan import model
from ckan.authz import get_group_or_org_admin_ids
from ckanext.unhcr import utils
from ckanext.unhcr.helpers import get_random_sysadmin
from ckanext.unhcr.kobo.filters import process_resource_kobo_filters
import ckan.plugins.toolkit as toolkit


log = logging.getLogger(__name__)


# Module API

def process_dataset_on_create(package_id):
    context = {'model': model, 'job': True, 'ignore_auth': True}

    # Pause excecution
    time.sleep(3)

    # Process dataset_fields
    _process_dataset_fields(package_id)

    # Create back references
    package = toolkit.get_action('package_show')(context.copy(), {'id': package_id})
    link_package_ids = utils.normalize_list(package.get('linked_datasets', []))
    _create_link_package_back_references(package_id, link_package_ids)


def process_dataset_on_delete(package_id):
    context = {'model': model, 'job': True, 'ignore_auth': True}

    # Delete back references
    package = toolkit.get_action('package_show')(context.copy(), {'id': package_id})
    link_package_ids = utils.normalize_list(package.get('linked_datasets', []))
    _delete_link_package_back_references(package_id, link_package_ids)


def process_dataset_on_update(package_id):

    # Pause execution
    time.sleep(3)

    # Process dataset_fields
    _process_dataset_fields(package_id)

    # Prepare back references
    link_package_ids = _get_link_package_ids_from_revisions(package_id)

    # Create back references
    created_link_package_ids = set(link_package_ids['next']).difference(link_package_ids['prev'])
    _create_link_package_back_references(package_id, created_link_package_ids)

    # Delete back references
    removed_link_package_ids = set(link_package_ids['prev']).difference(link_package_ids['next'])
    _delete_link_package_back_references(package_id, removed_link_package_ids)


def _define_new_admin_member(group_id):
    """ A data-container require a fallback admin.
        Check if this group has a parent and define its admin
        If container has no parent then pick one from sysadmins.
        """
    data_container = toolkit.get_action('organization_show')(
        {'ignore_auth': True},
        {'id': group_id, 'include_groups': True}
    )
    if len(data_container['groups']) > 0:
        for parent in data_container['groups']:
            if 'id' not in parent:
                parent = toolkit.get_action('organization_show')(
                    {'ignore_auth': True},
                    {'id': parent['name']}
                )
            admins = get_group_or_org_admin_ids(parent['id'])
            if len(admins) > 0:
                admin = model.User.get(admins[0])
                return admin

    return get_random_sysadmin()


def process_last_admin_on_delete(org_id):
    """ The only admin of a data container was deleted a we need to assign
        a fallback admin and notify sysadmin """

    new_admin = _define_new_admin_member(org_id)
    context = {'model': model, 'job': True, 'ignore_auth': True, 'user': new_admin.name}

    extra_msg = 'You have been assigned as admin of this Data Container because the previous admin user was deleted'

    member_create = toolkit.get_action("organization_member_create")
    return member_create(
        context,
        {
            'id': org_id,
            'username': new_admin.name,
            'role': 'admin',
            'extra_mail_msg': extra_msg
        }
    )


# Internal

def _process_dataset_fields(package_id):
    """ Process some specific fields that depend on others.
        These fields should be updated every time we save a
        package (create or update). """

    # Get package
    package_show = toolkit.get_action('package_show')
    package = package_show({'job': True, 'ignore_auth': True}, {'id': package_id})

    # Modify package
    package = _modify_package(package)

    # Update package
    default_user = toolkit.get_action('get_site_user')({'ignore_auth': True})

    # we only want to update visibility for resources, nothing else
    to_update_resources = [{'id': res['id'], 'visibility': res['visibility']} for res in package['resources']]

    data_dict = {
        'match': {'id': package['id']},
        'update': {
            'process_status': package['process_status'],
            'identifiability': package['identifiability'],
            'visibility': package['visibility'],
            'date_range_start': package['date_range_start'],
            'date_range_end': package['date_range_end'],
            'resources': to_update_resources,
        },
    }
    package_revise = toolkit.get_action('package_revise')
    package_revise({'job': True, 'user': default_user['name']}, data_dict)


def _modify_package(package):

    # Update resources before update package
    for resource in package.get('resources', []):
        if resource.get('identifiability') == 'personally_identifiable':
            resource['visibility'] = 'restricted'

    # data_range
    package = _modify_date_range(package, 'date_range_start', 'date_range_end')

    # process_status
    weights = {'raw': 3, 'cleaned': 2, 'anonymized': 1}
    package = _modify_weighted_field(package, 'process_status', weights)

    # identifiability
    weights = {'personally_identifiable': 4, 'anonymized_enclave': 3, 'anonymized_scientific': 2,  'anonymized_public': 1}
    package = _modify_weighted_field(package, 'identifiability', weights)

    # visibility
    # if some of the resources is restricted then the package will be restricted
    weights = {'restricted': 2, 'public': 1}
    package = _modify_weighted_field(package, 'visibility', weights, default_value='public')

    return package


def _modify_date_range(package, key_start, key_end):

    # Reset for generated
    package[key_start] = None
    package[key_end] = None

    # Iterate resources
    for resource in package['resources']:
        if resource.get(key_start, resource.get(key_end)) is None:
            continue
        # We could compare dates as strings because it's guarnateed to be YYYY-MM-DD
        package[key_start] = min(filter(None, [package[key_start], resource[key_start]]))
        package[key_end] = max(filter(None, [package[key_end], resource[key_end]]))

    return package


def _modify_weighted_field(package, key, weights, default_value=None):
    """ Set a Package level field considering the MAX value for the same field at all resources """

    # Reset for generated
    package[key] = default_value

    # Iterate resources
    for resource in package['resources']:
        if resource.get(key) is None:
            continue
        package_weight = weights.get(package.get(key), 0)
        resource_weight = weights.get(resource.get(key), 0)
        if resource_weight > package_weight:
            package[key] = resource[key]

    return package


def _create_link_package_back_references(package_id, link_package_ids):
    pass


def _delete_link_package_back_references(package_id, link_package_ids):
    pass


def _get_link_package_ids_from_revisions(package_id):
    # TODO: fix backlinks https://github.com/okfn/ckanext-unhcr/issues/577
    return {'prev': [], 'next': []}


# KoBo

def update_pkg_kobo_resources(kobo_asset_id, user_id):
    """ update all resources with new submissions for a KoBo dataset """
    from ckanext.unhcr.kobo.kobo_dataset import KoboDataset
    kd = KoboDataset(kobo_asset_id)
    kd.update_all_resources(user_id)


def update_kobo_resource(resource_id, user_id):
    """ Update a kobo resource
        For data resources: create an export and download the data in a new job
        For custom json resources: Just downloads the data
        For questionnaires: Donwload the questionnaire file and update the resource
        """

    log.info('Updating {} resource'.format(resource_id))
    _, survey, resource, _ = _prepare_kobo_download(resource_id)
    if resource.get('kobo_type') == 'questionnaire':
        log.info('Updating questionnaire')
        return toolkit.enqueue_job(
            download_kobo_file,
            [resource['id']],
            title='Preparing to update questionnaire resource'
        )

    user_obj = model.User.get(user_id)

    dformat = resource['format'].lower()
    if dformat != 'json':
        export_params = process_resource_kobo_filters(resource['kobo_details'])
        # create the export for the expected format (this starts an async process at KoBo)
        log.info('Preparing export {}'.format(export_params))
        export_params['dformat'] = dformat
        export = survey.create_export(**export_params)
        export_id = export['uid']
    else:
        export_id = ''

    # prepare the update
    kobo_details = resource['kobo_details']
    date_range_start, date_range_end = survey.get_submission_times()
    patch_resource = {
        'id': resource['id'],
        'date_range_start': date_range_start,
        'date_range_end': date_range_end,
        'kobo_details': kobo_details
    }
    patch_resource['kobo_details']['kobo_export_id'] = export_id
    patch_resource['kobo_details']['kobo_download_status'] = 'pending'
    patch_resource['kobo_details']['kobo_download_attempts'] = 0
    patch_resource['kobo_details']['kobo_last_updated'] = datetime.datetime.utcnow().isoformat()

    toolkit.get_action('resource_patch')(
        {'user': user_obj.name, 'job': True},
        patch_resource,
    )

    # send this job to queue
    return toolkit.enqueue_job(
        download_kobo_file,
        [resource['id']],
        title='Preparing to update {} resource'.format(dformat)
    )


def _kobo_job_error(kd, resource, user_obj, error):
    log.error(error)
    kd.update_kobo_details(
        resource,
        user_obj.name,
        {
            "kobo_download_status": "error",
            "kobo_last_error_response": error,
        }
    )


def kobo_job_exception_handler(func):
    """ Capture all possible error in this Job """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as e:
            resource_id = args[0]
            kd, _, resource, user_obj = _prepare_kobo_download(resource_id)
            error = 'Error downloading KoBo resource: {}'.format(e)
            _kobo_job_error(kd, resource, user_obj, error)
    return wrapper


def _prepare_kobo_download(resource_id):
    from ckanext.unhcr.kobo.api import KoBoAPI, KoBoSurvey
    from ckanext.unhcr.kobo.kobo_dataset import KoboDataset

    context = {'ignore_auth': True}
    resource = toolkit.get_action('resource_show')(context, {'id': resource_id})
    kobo_details = resource.get('kobo_details')
    package = toolkit.get_action('package_show')(context, {'id': resource['package_id']})
    if not package:
        raise toolkit.ValidationError({'package': ["Missing package for {}".format(resource['package_id'])]})
    user_id = package['creator_user_id']
    user_obj = model.User.get(user_id)
    plugin_extras = {} if user_obj.plugin_extras is None else user_obj.plugin_extras
    kobo_token = plugin_extras.get('unhcr', {}).get('kobo_token')
    kobo_url = toolkit.config.get('ckanext.unhcr.kobo_url', 'https://kobo.unhcr.org')
    kobo_api = KoBoAPI(kobo_token, kobo_url, cache_prefix=user_obj.name)

    kobo_asset_id = kobo_details['kobo_asset_id']
    kd = KoboDataset(kobo_asset_id)
    survey = KoBoSurvey(kobo_asset_id, kobo_api)
    return kd, survey, resource, user_obj


@kobo_job_exception_handler
def download_kobo_file(resource_id):
    """ Job for download pending data from a KoBo. """

    kd, survey, resource, user_obj = _prepare_kobo_download(resource_id)
    kobo_details = resource.get('kobo_details')

    if resource['kobo_type'] == 'questionnaire':
        try:
            local_file = survey.download_questionnaire(destination_path=kd.upload_path)
        except (KoboApiError, ValueError) as e:
            _kobo_job_error(kd, resource, user_obj, 'Error downloading questionnaire {}'.format(e))
            return
        kd.update_resource(resource, local_file, user_obj.name)
        return

    if resource['format'].lower() == 'json':
        try:
            local_file = survey.download_json_data(
                destination_path=kd.upload_path,
                resource_name=resource.get('name', 'unnamed-resource')
            )
        except (KoboApiError, ValueError) as e:
            _kobo_job_error(kd, resource, user_obj, 'Error downloading json kobo data {}'.format(e))
            return

        kd.update_resource(resource, local_file, user_obj.name)
        return

    # CSV and XLS require export and download
    export_id = kobo_details['kobo_export_id']
    if not export_id:
        raise toolkit.ValidationError(
            {
                'kobo_export_id': [
                    "Missing kobo_export_id at resource {}, {}".format(resource, kobo_details)
                ]
            }
        )
    export = survey.get_export(export_id)
    if export['status'] == 'complete':
        data_url = export['result']

        try:
            local_file = survey.download_data(
                destination_path=kd.upload_path,
                resource_name=resource.get('name', 'unnamed-resource'),
                dformat=resource['format'],
                url=data_url
            )
        except (KoboApiError, ValueError) as e:
            _kobo_job_error(kd, resource, user_obj, 'Error downloading kobo data {}'.format(e))
            return

        kd.update_resource(resource, local_file, user_obj.name)

    elif export['status'] in ['processing', 'created']:
        # wait and re-schedule
        kobo_download_attempts = kobo_details['kobo_download_attempts'] + 1
        if kobo_download_attempts > 5:
            error = 'Failed to download KoBoToolbox data resource {}. ' \
                    'Last export status from KoBo: {}'.format(resource['id'], export)
            _kobo_job_error(kd, resource, user_obj, error)
        else:
            kd.update_kobo_details(resource, user_obj.name, {"kobo_download_attempts": kobo_download_attempts})
            time.sleep(30 * kobo_download_attempts)
            toolkit.enqueue_job(
                download_kobo_file,
                [resource['id']],
                title='Re-scheduling KoBoToolbox download: {}'.format(kobo_download_attempts)
            )
    else:  # status = 'error' or unknown
        error = 'KoBo export error for resource {}. ' \
                'Last export status from KoBo: {}'.format(resource['id'], export)
        _kobo_job_error(kd, resource, user_obj, error)
