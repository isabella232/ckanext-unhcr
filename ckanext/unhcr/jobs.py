import logging
import time

from ckan import model
from ckanext.unhcr import utils
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


# Internal

def _process_dataset_fields(package_id):

    # Get package
    package_show = toolkit.get_action('package_show')
    package = package_show({'job': True, 'ignore_auth': True}, {'id': package_id})

    # Modify package
    package = _modify_package(package)

    # Update package
    default_user = toolkit.get_action('get_site_user')({ 'ignore_auth': True })
    data_dict = {
        'match': {'id': package['id']},
        'update': {
            'process_status': package['process_status'],
            'identifiability': package['identifiability'],
            'visibility': package['visibility'],
            'date_range_start': package['date_range_start'],
            'date_range_end': package['date_range_end'],
        },
    }
    package_revise = toolkit.get_action('package_revise')
    package_revise({'job': True, 'user': default_user['name']}, data_dict)


def _modify_package(package):

    # data_range
    package = _modify_date_range(package, 'date_range_start', 'date_range_end')

    # process_status
    weights = {'raw' : 3, 'cleaned': 2, 'anonymized': 1}
    package = _modify_weighted_field(package, 'process_status', weights)

    # identifiability
    weights = {'personally_identifiable' : 4, 'anonymized_enclave': 3, 'anonymized_scientific': 2,  'anonymized_public': 1}
    package = _modify_weighted_field(package, 'identifiability', weights)

    # visibility
    # TODO: clarify what level of anonymization required
    if package['identifiability'] == 'personally_identifiable':
        package['visibility'] = 'restricted'

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


def _modify_weighted_field(package, key, weights):

    # Reset for generated
    package[key] = None

    # Iterate resources
    for resource in package['resources']:
        if resource.get(key) is None:
            continue
        package_weight = weights.get(package[key], 0)
        resource_weight = weights.get(resource[key], 0)
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
