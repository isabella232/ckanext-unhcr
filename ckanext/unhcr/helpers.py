import datetime
import logging
import os
import re
from sqlalchemy import func
from dateutil.parser import parse as parse_date
from urllib.parse import quote
from jinja2 import Markup, escape
from ckan import model
from ckan.lib import uploader
from operator import itemgetter
from ckan.authz import get_group_or_org_admin_ids
from ckan.logic import ValidationError
from ckan.plugins import toolkit, plugin_loaded
import ckan.lib.helpers as core_helpers
import ckan.lib.plugins as lib_plugins
from ckanext.hierarchy import helpers as hierarchy_helpers
from ckanext.scheming.helpers import (
    scheming_get_dataset_schema, scheming_field_by_name, scheming_get_organization_schema
)
from ckanext.unhcr import __VERSION__
from ckanext.unhcr.models import AccessRequest, USER_REQUEST_TYPE_NEW, DEFAULT_GEOGRAPHY_CODE
from ckanext.unhcr.kobo import ALL_KOBO_EXPORT_FORMATS, FIXED_FIELDS_KOBO_EXPORT
from ckanext.unhcr.kobo.exceptions import KoboApiError
from ckanext.unhcr.kobo.kobo_dataset import KoboDataset


log = logging.getLogger(__name__)

# Core overrides

@core_helpers.core_helper
def new_activities(*args, **kwargs):
    try:
        return core_helpers.new_activities(*args, **kwargs)
    except toolkit.NotAuthorized:
        return 0


@core_helpers.core_helper
def dashboard_activity_stream(*args, **kwargs):
    try:
        return core_helpers.dashboard_activity_stream(*args, **kwargs)
    except toolkit.NotAuthorized:
        return []


@core_helpers.core_helper
def url_for(*args, **kw):
    return core_helpers.url_for(*args, **kw)


# General

def get_data_container(id):
    context = {'model': model, 'ignore_auth': True}
    return toolkit.get_action('organization_show')(context, {'id': id})


def get_all_data_containers(
    exclude_ids=None,
    include_ids=None,
    include_unknown=False,
    userobj=None,
    dataset=None,
):
    if not exclude_ids:
        exclude_ids = []
    if not include_ids:
        include_ids = []
    include_ids = [id_ for id_ in include_ids if id_ and id_ != 'unknown']
    if not userobj:
        userobj = toolkit.c.userobj

    data_containers = []
    context = {'model': model, 'ignore_auth': True}
    orgs = toolkit.get_action('organization_list_all_fields')(context, {})

    for org in orgs:
        if org['id'] in exclude_ids:
            continue

        if org['approval_status'] != u'approved':
            continue

        if org['id'] in include_ids:
            data_containers.append(org)
            continue

        if userobj.external and (
            'visible_external' not in org or not org['visible_external']
        ):
            continue

        if (
            # we're editing an existing dataset, not creating a new one
            dataset

            # curators and sysadmins can always change the target to anything
            and not user_is_curator(userobj)
            and not userobj.sysadmin

            # external users can always change the target of their own dataset to any visible_external container
            and not userobj.external

            # if I'm editing my own deposit, I can always change the target to anything
            and 'creator_user_id' in dataset and dataset['creator_user_id'] != userobj.id
        ):
            user_orgs = toolkit.get_action('organization_list_for_user')(
                context,
                {'id': userobj.id, "permission": "admin"}
            )
            user_orgs_ids = [o['id'] for o in user_orgs]
            if org['id'] not in user_orgs_ids:
                continue

        data_containers.append(org)

    if include_unknown:
        data_containers.insert(0, {
            'id': 'unknown',
            'name': 'unknown',
            'title': 'Unknown',
            'display_name': 'Unknown',
        })
    return data_containers


def get_dataset_count():
    return toolkit.get_action('package_search')(
        {}, {'fq': 'dataset_type:dataset', 'rows': 1})['count']


# Hierarchy

def get_allowable_parent_groups(group_id):
    deposit = get_data_deposit()
    if group_id:
        groups = hierarchy_helpers.get_allowable_parent_groups(group_id)
    else:
        groups = model.Group.all(group_type='data-container')
    org_list_func = toolkit.get_action('organization_list_for_user')
    user_admins = org_list_func({'ignore_auth': True}, {'id': toolkit.c.userobj.id, 'permission': 'admin'})
    user_admins_names = [org['name'] for org in user_admins]
    allowed_groups = []
    for group in groups:
        if group.name == deposit.get('name'):
            continue
        if group.name not in user_admins_names:
            continue
        allowed_groups.append(group)
    return allowed_groups


def render_tree(top_nodes=None):
    '''Returns HTML for a hierarchy of all data containers'''
    context = {'model': model, 'session': model.Session}
    if not top_nodes:
        top_nodes = toolkit.get_action('group_tree')(
            context,
            data_dict={'type': 'data-container'})

    # Remove data deposit
    deposit = get_data_deposit()
    top_nodes = filter(lambda node: node['id'] != deposit['id'], top_nodes)

    return _render_tree(top_nodes)


def _render_tree(top_nodes):
    html = '<ul class="hierarchy-tree-top">'
    for node in top_nodes:
        html += _render_tree_node(node)
    return html + '</ul>'


def _render_tree_node(node):
    html = '<a href="/data-container/{}">{}</a>'.format(
        node['name'], node['title'])
    if node['children']:
        html += '<ul class="hierarchy-tree">'
        for child in node['children']:
            html += _render_tree_node(child)
        html += '</ul>'

    if node['highlighted']:
        html = '<li id="node_{}" class="highlighted">{}</li>'.format(
            node['name'], html)
    else:
        html = '<li id="node_{}">{}</li>'.format(node['name'], html)
    return html


# Access restriction

def page_authorized():
    blueprint, view = toolkit.get_endpoint()

    if (
        blueprint == 'error'
        and view == 'document'
        and toolkit.c.code
        and toolkit.c.code[0] != '403'
    ):
        return True

    allowed_blueprints = [
        'user',  # most actions are defined in the core 'user' blueprint
        'unhcr_user',  # we override some actions in the 'unhcr_user' blueprint
    ]
    allowed_views = [
        'logged_in',
        'logged_out',
        'logged_out_page',
        'logged_out_redirect',
        'login',
        'perform_reset',
        'register',
        'request_reset',
    ]
    return (
        toolkit.c.userobj
        or (
            blueprint in allowed_blueprints
            and view in allowed_views
        )
    )


def get_came_from_param():
    return toolkit.request.environ.get('CKAN_CURRENT_URL', '')


def user_is_curator(userobj=None):
    if not userobj:
        userobj = toolkit.c.userobj
    group = get_data_deposit()
    try:
        users = toolkit.get_action('member_list')(
            { 'ignore_auth': True },
            { 'id': group['id'] }
        )
    except toolkit.ObjectNotFound:
        return False
    user_ids = [u[0] for u in users]
    user_id = userobj.id
    return user_id in user_ids


def user_orgs(permission, user_name=None):
    if not user_name:
        user_name = toolkit.c.user
    orgs = toolkit.get_action("organization_list_for_user")(
        {"user": user_name},
        {"id": user_name, "permission": permission}
    )
    return orgs


def user_is_container_admin(user_name=None):
    orgs = user_orgs(permission='admin', user_name=user_name)
    return len(orgs) > 0


def user_is_editor(user_name=None):
    orgs = user_orgs(permission='create_dataset', user_name=user_name)
    return len(orgs) > 0


def get_kobo_token():
    user = toolkit.c.userobj
    if user.plugin_extras is None:
        return None
    return user.plugin_extras.get('unhcr', {}).get('kobo_token')


def get_kobo_url():
    return toolkit.config.get('ckanext.unhcr.kobo_url', 'https://kobo.unhcr.org')


def get_kobo_import_limit():
    return toolkit.config.get('ckanext.unhcr.kobo_import_limit', 30000)

def get_kobo_all_formats():
    return ALL_KOBO_EXPORT_FORMATS


def get_kobo_fixed_fields_export():
    return FIXED_FIELDS_KOBO_EXPORT


def get_kobo_initial_dataset(kobo_asset_id):
    """ Get package init data from KoBo asset (survey)
        Return pkd_dict, errors """
    kd = KoboDataset(kobo_asset_id)
    initial_data = errors = {}

    # package should not exists
    pkg = kd.get_package()
    if not pkg:
        try:
            initial_data = kd.get_initial_package(toolkit.c.userobj)
        except KoboApiError as e:
            errors = {
                'kobo_asset': ['KoBoToolbox error: {}'.format(e)]
            }
    else:
        errors = {
            'kobo_asset': ['This KoBoToolbox surveys has already been imported']
        }

    return initial_data, errors

def get_kobo_survey(kobo_asset_id):
    kd = KoboDataset(kobo_asset_id)
    kobo_api = kd.get_kobo_api(toolkit.c.userobj)
    return kobo_api.get_asset(kobo_asset_id)


def get_kobo_import_process_real_status(resource_id):
    """ Check if KoBo process is stalled (more than 1 hour in pending status)
        Return True if process is stalled, False otherwise """
    resource = toolkit.get_action('resource_show')({}, {'id': resource_id})
    kobo_details = resource.get('kobo_details', {})
    if kobo_details.get('kobo_download_status') != 'pending':
        return kobo_details.get('kobo_download_status')
    updated = kobo_details.get('kobo_last_updated')
    if not updated:
        return 'unknown'
    date_updated = parse_date(updated)
    if datetime.datetime.now() - date_updated > datetime.timedelta(hours=1):
        return 'stalled'
    else:
        return 'pending'


# Linked datasets

def get_linked_datasets_for_form(selected_ids=[], exclude_ids=[], context=None, user_id=None):
    context = context or {'model': model}
    user_id = user_id or toolkit.c.userobj.id

    # Prepare search query
    fq_list = []
    get_containers = toolkit.get_action('organization_list_for_user')
    containers = get_containers(context, {'id': user_id})
    deposit = get_data_deposit()
    fq_list = [
        "owner_org:{}".format(container["id"])
        for container in containers
        if container["id"] != deposit["id"]
    ]

    # Get search results
    search_datasets = toolkit.get_action('package_search')
    search = search_datasets(context, {
        'fq': ' OR '.join(fq_list),
        'include_private': True,
        'sort': 'organization asc, title asc',
        'rows': 1000,
    })

    # Get datasets
    orgs = []
    current_org = None
    selected_ids = selected_ids if isinstance(selected_ids, list) else selected_ids.strip('{}').split(',')
    for package in search['results']:

        if package['id'] in exclude_ids:
            continue
        if package.get('owner_org') and package.get('owner_org') != current_org:
            current_org = package['owner_org']

            orgs.append({'text': package['organization']['title'], 'children': []})

        dataset = {'text': package['title'], 'value': package['id']}
        if package['id'] in selected_ids:
            dataset['selected'] = 'selected'
        orgs[-1]['children'].append(dataset)

    return orgs


def get_linked_datasets_for_display(value, context=None):
    context = context or {'model': model}

    # Get datasets
    datasets = []
    ids = normalize_list(value)
    for id in ids:
        dataset = toolkit.get_action('package_show')(context, {'id': id})
        href = toolkit.url_for('dataset.read', id=dataset['name'], qualified=True)
        datasets.append({'text': dataset['title'], 'href': href})

    return datasets


def get_geographies_for_display(value):
    geogs = []
    ids = normalize_list(value)
    for id_ in ids:
        try:
            geog = toolkit.get_action('geography_show')({}, {'id': id_})
            geogs.append(geog)
        except toolkit.ObjectNotFound:
            pass
    geogs = sorted(geogs, key=lambda k: k['name'])
    return geogs


def get_default_geography():
    return DEFAULT_GEOGRAPHY_CODE

# Access requests

def get_pending_requests_total(context=None):
    context = context or {'model': model, 'user': toolkit.c.user}
    total = 0

    try:
        container_requests = toolkit.get_action('container_request_list')(
            context, {'all_fields': False}
        )
        total += container_requests['count']
    except (toolkit.NotAuthorized, toolkit.ObjectNotFound):
        pass

    try:
        access_requests = toolkit.get_action('access_request_list_for_user')(
            context, {}
        )
        total += len(access_requests)
    except (toolkit.NotAuthorized, toolkit.ObjectNotFound):
        pass

    return total


def get_existing_access_request(user_id, object_id, status):
    return model.Session.query(AccessRequest).filter(
        AccessRequest.user_id==user_id,
        AccessRequest.object_id==object_id,
        AccessRequest.status==status
    ).all()


def get_access_request_for_user(user_id):

    requests = model.Session.query(AccessRequest).filter(
        AccessRequest.object_id==user_id,
        AccessRequest.object_type=='user',
    ).all()

    for request in requests:
        if request.data.get('user_request_type', USER_REQUEST_TYPE_NEW) == USER_REQUEST_TYPE_NEW:
            return request
    return None

# Deposited datasets

cached_deposit = None
def get_data_deposit():
    '''
    Return the dict of the underlying organization for the data deposit

    This function uses a cache so it's OK to call it multiple times

    :returns: The data deposit organization dict
    :rtype: dict
    '''

    # Check cache
    deposit = None
    global cached_deposit
    if not toolkit.config.get('testing'):
        deposit = cached_deposit

    # Load from db
    if deposit is None:
        try:
            context = {'model': model, 'ignore_auth': True}
            deposit = toolkit.get_action('organization_show')(
                context, {'id': 'data-deposit'})
            if not toolkit.config.get('testing'):
                cached_deposit = deposit
        except toolkit.ObjectNotFound:
            log.error('Data Deposit is not created')
            deposit = {'id': 'data-deposit', 'name': 'data-deposit'}

    return deposit


def get_data_curation_users(dataset):
    '''
    Return a list of users that are allowed to curate a particular dataset.
    This includes:

    * Sysadmins
    * Curation team (Admins and Editors of the data-deposit org)
    * Admins of the target data container

    :param dataset: The dataset that needs to be curated
    :type dataset: dict

    :returns: A list of user dicts that can curate the dataset
    :rtype: list
    '''
    context = {'model': model, 'ignore_auth': True}
    deposit = get_data_deposit()

    # Get depadmins
    depadmins = toolkit.get_action('member_list')(context, {
        'id': deposit['id'],
        'capacity': 'admin',
        'object_type': 'user',
    })

    # Get curators
    curators = toolkit.get_action('member_list')(context, {
        'id': deposit['id'],
        'capacity': 'editor',
        'object_type': 'user',
    })

    container_admins = []
    owner_org_dest = dataset.get('owner_org_dest')
    if owner_org_dest and owner_org_dest != 'unknown':
        container_admins = toolkit.get_action('member_list')(context, {
            'id': owner_org_dest,
            'capacity': 'admin',
            'object_type': 'user',
        })

    # Get users
    users = []
    for item in depadmins + curators + container_admins:
        user = toolkit.get_action('user_show')(context, {'id': item[0]})
        user.pop('default_containers', None)
        users.append(user)

    users = [dict(tup) for tup in {tuple(u.items()) for u in users}]  # de-dupe

    # Sort users
    users = list(sorted(users, key=itemgetter('display_name', 'name')))

    return users


def get_deposited_dataset_user_curation_status(dataset, user_id):
    '''
    Returns an object describing the status of a given dataset and user
    in the context of the data deposit.

    :param dataset: A deposited dataset dict
    :type dataset: dict
    :param user_id: The id of the relevant user
    :type user_id: string

    :returns: An object with the following keys:

        * `state`: The curation state of the dataset (eg "review", "submitted",
            "draft", etc)
        * `active`: Whether the status of the dataset is "active"
        * `final_review`: Whether the depositor requested a final review
        * `error`: Validation errors of the deposited dataset
        * `role`: Role that the provided user has on this particular dataset,
            see :py:func:`~ckanext.unhcr.helpers.get_deposited_dataset_user_curation_role`
        * `is_depositor`: Whether the provided user was the original depositor
        * `is_curator`: Whether the provided user is the assigned curator to the dataset
        * `actions`: List of allowed actions for the provided user,
            see :py:func:`~ckanext.unhcr.helpers.get_deposited_dataset_user_curation_actions`
        * `contacts`: An object with the following keys (
            see :py:func:`~ckanext.unhcr.helpers.get_deposited_dataset_user_contact`
            `depositor`: an object with the original depositor user details
            `curator`: an object with the assigned curator user details
    :rtype: dict
    '''
    deposit = get_data_deposit()
    user = model.User.get(user_id)
    context = {'user': user.name, 'model': model, 'session': model.Session}


    # General
    status = {}
    status['error'] = get_dataset_validation_error_or_none(dataset, context)
    status['role'] = get_deposited_dataset_user_curation_role(user_id, dataset)
    status['state'] = dataset['curation_state']
    status['final_review'] = dataset.get('curation_final_review')
    status['active'] = dataset['state'] == 'active'

    # is_depositor/curator
    status['is_depositor'] = dataset.get('creator_user_id') == user_id
    status['is_curator'] = dataset.get('curator_id') == user_id

    # actions
    status['actions'] = get_deposited_dataset_user_curation_actions(status)

    # contacts
    status['contacts'] = {
        'depositor': get_deposited_dataset_user_contact(dataset.get('creator_user_id')),
        'curator': get_deposited_dataset_user_contact(dataset.get('curator_id')),
    }

    return status


def get_deposited_dataset_user_curation_role(user_id, dataset=None):
    '''
    Returns the role that the provided user has in the context of the
    data deposit.

    If a dataset dict is provided, the admins of the organization the
    dataset belongs to are also considered when deciding the user role.

    The available roles are:

    * admin: Can manage members of the data deposit
    * curator: Can edit and manage deposited datasets
    * container admin: Can edit and manage deposited datasets (that are
        targetted to one of the admins the user is admin of)
    * depositor: Can create new deposited datasets
    * user: No permissions available on the data deposit

    :param user_id: The user that we want to know the role of in the data
        deposit
    :type user_id: string

    :returns: The role the user has
    :rtype: string
    '''
    action = toolkit.get_action('organization_list_for_user')
    context = {'model': model, 'user': user_id}
    deposit = get_data_deposit()

    admin_orgs = action(context, {'permission': 'admin'})
    admin_orgs_ids = [org['id'] for org in admin_orgs]

    member_orgs = action(context, {'permission': 'create_dataset'})
    member_org_ids = [org['id'] for org in member_orgs]


    if deposit['id'] in admin_orgs_ids:
        return 'admin'

    if deposit['id'] in member_org_ids:
        return 'curator'

    if not dataset:
        if len(admin_orgs_ids) > 0:
            return 'container admin'
        return 'depositor'

    if (
        dataset['owner_org_dest'] != 'unknown'
        and dataset['owner_org_dest'] in admin_orgs_ids
    ):
        return 'container admin'

    if dataset['creator_user_id'] == user_id:
        return 'depositor'

    return 'user'


def get_deposited_dataset_user_curation_actions(status):
    '''
    Return a list of actions that the user is allowed to perform on a deposited
    dataset

    :param status: An object containing the following keys: "state", "is_depositor",
        "active", "role", "error", "final_review"
        (see :py:func:`~ckanext.unhcr.helpers.get_deposited_dataset_user_curation_status`
        for details.
    :type status: dict

    :returns: A list of allowed actions. Possible values are: "edit", "submit", "withdraw",
        "reject", "request_changes", "assign", "request_review", "approve"
    :rtype: list
    '''

    # Actions are for active datasets and draft ones while the depositor is still creating the dataset
    if not status['active'] and status['state'] != 'draft':
        return []

    actions = []

    # Draft
    if status['state'] == 'draft':
        if status['is_depositor']:
            actions.extend(['edit'])
            if status['active']:
                actions.extend(['submit', 'withdraw'])

    # Submitted
    if status['state'] == 'submitted':
        if status['role'] in ['admin', 'curator', 'container admin']:
            actions.extend(['edit', 'reject'])
            if status['role'] == 'admin':
                actions.extend(['assign'])
            if status['error']:
                actions.extend(['request_changes'])
            else:
                if status['final_review']:
                    actions.extend(['request_review'])
                else:
                    actions.extend(['approve'])

    # Review
    if status['state'] == 'review':
        if status['is_depositor']:
            actions.extend(['request_changes'])
            if not status['error']:
                actions.extend(['approve'])

    return actions


def get_deposited_dataset_user_contact(user_id=None):
    '''
    Returns selected attributes from the provided user id, or None if not found

    :param user_id: The provided user id
    :type user_id: string

    :returns: A user dict with the following keys: "id", "name", "display_name",
        "title" (same as "display_name"), "email", "external"
    :rtype: dict
    '''

    # Return none (no id)
    if not user_id:
        return None

    # Return none (no user)
    userobj = model.User.get(user_id)
    if not userobj:
        return None

    # Return contact
    return {
        'id': getattr(userobj, 'id'),
        'title': getattr(userobj, 'display_name'),
        'display_name': getattr(userobj, 'display_name'),
        'name': getattr(userobj, 'name'),
        'email': getattr(userobj, 'email'),
        'external': getattr(userobj, 'external'),
    }


def get_dataset_validation_error_or_none(pkg_dict, context):
    # Convert dataset
    if pkg_dict.get('type') == 'deposited-dataset':
        pkg_dict = convert_deposited_dataset_to_regular_dataset(pkg_dict)

    # Validate dataset
    package_plugin = lib_plugins.lookup_package_plugin('dataset')
    schema = package_plugin.update_package_schema()
    data, errors = lib_plugins.plugin_validate(
        package_plugin, context, pkg_dict, schema, 'package_update')
    errors.pop('owner_org', None)
    if data.get('owner_org') == 'unknown':
        errors['owner_org_dest'] = ['Missing Value']

    return ValidationError(errors) if errors else None


def convert_deposited_dataset_to_regular_dataset(pkg_dict):
    pkg_dict = pkg_dict.copy()

    # Update fields
    pkg_dict['type'] = 'dataset'
    pkg_dict['owner_org'] = pkg_dict['owner_org_dest']

    # Remove fields
    pkg_dict.pop('owner_org_dest', None)
    pkg_dict.pop('curation_state', None)
    pkg_dict.pop('curator_id', None)

    return pkg_dict


def get_dataset_validation_report(pkg_dict, error_dict):
    report = {}

    # Dataset
    report['dataset'] = {
        'fields': sorted([field for field in error_dict if field != 'resources']),
    }

    # Resources
    report['resources'] = []
    for index, resource in enumerate(pkg_dict.get('resources', [])):
        try:
            fields = sorted(error_dict['resources'][index])
        except (KeyError, IndexError):
            continue
        if fields:
            report['resources'].append({
                'id': resource['id'],
                'name': resource['name'],
                'fields': fields,
            })
    return report


def get_user_deposited_drafts():
    context = {'model': model, 'user': toolkit.c.user}

    # Get datasets
    fq_list = []
    fq_list.append('state:draft')
    fq_list.append('dataset_type:deposited-dataset')
    fq_list.append('creator_user_id:%s' % toolkit.c.userobj.id)
    data_dict = {'fq':  ' AND '.join(fq_list), 'include_drafts': True}
    datasets = toolkit.get_action('package_search')(context, data_dict)['results']

    return datasets


def get_default_container_for_user():
    context = {'model': model, 'user': toolkit.c.user}
    user = toolkit.get_action('user_show')(context, {'id': toolkit.c.user})
    if len(user['default_containers']) > 0:
        return user['default_containers'][0]
    return 'unknown'


# Internal activity

def curation_activity_message(activity):
    activity_name = activity['data']['curation_activity']

    output = ''

    if activity_name == 'dataset_deposited':
        output =  toolkit._("{actor} deposited dataset {dataset}")
    elif activity_name == 'dataset_submitted':
        output =  toolkit._("{actor} submitted dataset {dataset} for curation")
    elif activity_name == 'curator_assigned':
        curator_link = core_helpers.link_to(
            activity['data']['curator_name'],
            toolkit.url_for('user.read', id=activity['data']['curator_name'])
        )
        output =  toolkit._("{actor} assigned %s as Curator for dataset {dataset}" % curator_link)
    elif activity_name == 'curator_removed':
        output =  toolkit._("{actor} removed the assigned Curator from dataset {dataset}")
    elif activity_name == 'changes_requested':
        output =  toolkit._("{actor} unlocked {dataset} for further changes by the Depositor")
    elif activity_name == 'final_review_requested':
        output =  toolkit._("{actor} requested a final review of {dataset} from the Depositor")
    elif activity_name == 'dataset_rejected':
        output = toolkit._("{actor} rejected dataset {dataset} for publication")
    elif activity_name == 'dataset_withdrawn':
        output = toolkit._("{actor} withdrew dataset {dataset} from the data deposit")
    elif activity_name == 'dataset_approved':
        output = toolkit._("{actor} approved dataset {dataset} for publication")

    if activity['data'].get('message'):
        output = output + ' with the following message: <q class="curation-message">%s</q>' % activity['data']['message']

    return output


# Publishing

def convert_dataset_to_microdata_survey(dataset, nation, repoid):
    """ Check MDL survey specs 
        https://microdata.unhcr.org/api-documentation/catalog-admin/index.html#operation/createSurvey
        VALID_ACCESS_POLICIES = ["direct", "open", "public", "licensed", "remote", "data_na"]
        """

    # general
    survey = {
      'access_policy': 'data_na',
      'published': 0,
      'overwrite': 'no',
      'study_desc': {
          'study_info': {},
          'method': {
              'data_collection': {},
          },
      },
    }

    # repositoryid
    if repoid:
        survey['repositoryid'] = repoid.upper()

    # title_statement
    survey['study_desc']['title_statement'] = {
        'idno': dataset['name'].upper(),
        'title': dataset.get('title'),
    }

    # authority_entity
    survey['study_desc']['authoring_entity'] = [
        {
            'name': 'Office of the High Commissioner for Refugees',
            'affiliation': 'UNHCR'
        }
    ]

    # distribution_statement
    if dataset.get('maintainer'):
        survey['study_desc']['distribution_statement'] = {
            'contact': [{
                'name': dataset.get('maintainer'),
                'email': dataset.get('maintainer_email'),
            }]
        }

    # version_statement
    if dataset.get('version'):
        survey['study_desc']['version_statement'] =  {
            'version': dataset.get('version'),
        }

    # keywords
    if dataset.get('tags', []):
        survey['study_desc']['study_info']['keywords'] = []
        for tag in dataset.get('tags', []):
            survey['study_desc']['study_info']['keywords'].append(
                {'keyword': tag.get('display_name')})

    # topics
    if dataset.get('keywords', []):
        survey['study_desc']['study_info']['topics'] = []
        for value in dataset.get('keywords', []):
            survey['study_desc']['study_info']['topics'].append(
                {'topic': get_choice_label('keywords', value)})

    # abstract
    if dataset.get('notes'):
        survey['study_desc']['study_info']['abstract'] = dataset.get('notes').strip()

    # coll_dates
    if dataset.get('date_range_start') and dataset.get('date_range_end'):
        survey['study_desc']['study_info']['coll_dates'] = [
            {
              'start': dataset.get('date_range_start'),
              'end': dataset.get('date_range_end'),
            }
        ]

    # nation
    if nation:
        survey['study_desc']['study_info']['nation'] = [
            {'name': name.strip()} for name in nation.split(',')
        ]

    # geog_coverage
    if dataset.get('geog_coverage'):
        survey['study_desc']['study_info']['geog_coverage'] = dataset.get('geog_coverage')

    # analysis_unit
    if dataset.get('unit_of_measurement'):
        survey['study_desc']['study_info']['analysis_unit'] = dataset.get('unit_of_measurement')

    # data_collectors
    if dataset.get('data_collector', ''):
        survey['study_desc']['method']['data_collection']['data_collectors'] = []
        for value in normalize_list(dataset.get('data_collector', '')):
            survey['study_desc']['method']['data_collection']['data_collectors'].append(
                {'name': value})

    # sampling_procedure
    sampling_procedure = None
    if dataset.get('sampling_procedure', []):
        values = []
        for value in dataset.get('sampling_procedure', []):
            values.append(get_choice_label('sampling_procedure', value))
        survey['study_desc']['method']['data_collection']['sampling_procedure'] = ', '.join(values)
    elif dataset.get('sampling_procedure_notes'):
        survey['study_desc']['method']['data_collection']['sampling_procedure'] = dataset.get('sampling_procedure_notes').strip()

    # coll_mode
    if dataset.get('data_collection_technique'):
        survey['study_desc']['method']['data_collection']['coll_mode'] = get_choice_label(
            'data_collection_technique', dataset.get('data_collection_technique'))

    # coll_situation
    if dataset.get('data_collection_notes'):
        survey['study_desc']['method']['data_collection']['coll_situation'] = dataset.get('data_collection_notes').strip()

    # weight
    if dataset.get('weight_notes'):
        survey['study_desc']['method']['data_collection']['weight'] = dataset.get('weight_notes').strip()

    # cleaning_operations
    if dataset.get('clean_ops_notes'):
        survey['study_desc']['method']['data_collection']['cleaning_operations'] = dataset.get('clean_ops_notes').strip()

    # analysis_info
    if dataset.get('response_rate_notes'):
        survey['study_desc']['method']['analysis_info'] = {
            'response_rate': dataset.get('response_rate_notes').strip(),
          }

    return survey


def convert_resource_to_microdata_resource(resource):
    TYPES_MAPPING = {
        'microdata': 'dat/micro',
        'questionnaire': 'doc/qst',
        'report': 'doc/rep',
        'sampling_methodology': 'doc/oth',
        'infographics': 'doc/oth',
        'attachment': 'doc/oth',
        'script': 'doc/oth',
        'concept note': 'doc/oth',
        'other': 'doc/oth',
    }

    # general
    md_resource = {
        'title': resource.get('name') or 'Unnamed resource',
        'dctype': TYPES_MAPPING[resource.get('file_type', 'attachment')],
    }

    # dcformat
    if resource.get('format'):
        md_resource['dcformat'] = resource.get('format').lower()

    # description
    if resource.get('description'):
        md_resource['description'] = resource.get('description')

    return md_resource


def get_microdata_collections():
    context = {'user': toolkit.c.user}
    try:
        return toolkit.get_action('package_get_microdata_collections')(context, {})
    except (toolkit.NotAuthorized, RuntimeError):
        return None


# Misc

def current_path(action=None):
    path = toolkit.request.path
    if action == '/dataset/new':
        path = '/dataset/new'
    if path.startswith('/dataset/copy') or path.startswith('/deposited-dataset/copy'):
        path = '/dataset/new'
    return path


def get_field_label(name, is_resource=False):
    schema = scheming_get_dataset_schema('deposited-dataset')
    fields = schema['resource_fields'] if is_resource else schema['dataset_fields']
    field = scheming_field_by_name(fields, name)
    if field:
        return field.get('label', name)
    else:
        log.warning('Could not get field {} from deposited-dataset schema'.format(name))


def get_choice_label(name, value, is_resource=False):
    schema = scheming_get_dataset_schema('deposited-dataset')
    fields = schema['resource_fields'] if is_resource else schema['dataset_fields']
    field = scheming_field_by_name(fields, name)
    if field:
        for choice in field.get('choices', []):
            if choice.get('value') == value:
                return choice.get('label')
        return value
    else:
        log.warning('Could not get field {} from deposited-dataset schema'.format(name))


def get_data_container_choice_label(name, value):
    schema = scheming_get_organization_schema('data-container')
    fields = schema['fields']
    field = scheming_field_by_name(fields, name)
    if field:
        for choice in field.get('choices', []):
            if choice.get('value') == value:
                return choice.get('label')
        return value
    else:
        log.warning('Could not get field {} from data-container schema'.format(name))


def normalize_list(value):
    # It takes into account that ''.split(',') == ['']
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = value.strip('{}')
    if not value:
        return []
    return value.split(',')


def can_download(package_dict):
    """ True if the user can download ALL resources
        If one resource is not accessible, return False """
    try:
        context = {'user': toolkit.c.user}
        resources = package_dict.get('resources', [])
        if len(resources) == 0:
            return False
        for resource_dict in resources:
            # Copy context because will be filled wioth 'resource' and 'get_resource_object' 
            # inside 'resource_download' will use this resource all times
            ret = toolkit.check_access('resource_download', context.copy(), resource_dict)
        return True
    except (toolkit.NotAuthorized, toolkit.ObjectNotFound):
        return False


def can_request_access(user, pkg):
    """ Define if user is able to request access for private resources in dataset """
    resources = pkg['resources'] if type(pkg) == dict else pkg.resources
    if len(resources) == 0:
        return False
    if can_download(pkg):
        return False
    pkg_id = pkg['id'] if type(pkg) == dict else pkg.id
    access_already_requested = get_existing_access_request(user.id, pkg_id, 'requested')
    return not access_already_requested


def get_resource_file_path(resource):
    if resource.get(u'url_type') == u'upload':
        upload = uploader.get_resource_uploader(resource)
        return upload.get_path(resource[u'id'])
    return None


def add_file_name_suffix(file_name, file_suffix):
    try:
        file_base, file_extension = file_name.split('.', 1)
        return  '%s (%s).%s' % (file_base, file_suffix, file_extension)
    except ValueError:
        return  '%s (%s)' % (file_name, file_suffix)


def get_sysadmins():
    return model.Session.query(model.User).filter(model.User.sysadmin==True).all()


def get_valid_sysadmins():
    default_user = toolkit.get_action("get_site_user")({'ignore_auth': True})
    return model.Session.query(
        model.User
    ).filter(
        model.User.sysadmin == True,
        model.User.state == 'active',
        model.User.name != default_user["name"]
    )


def get_random_sysadmin():
    return get_valid_sysadmins().order_by(func.random()).first()


def get_ridl_version():
    return __VERSION__


def get_envname():
    envname = os.environ.get('ENV_NAME')
    if not envname:
        return 'dev'
    return envname.lower()


def get_google_analytics_id():
    return toolkit.config.get('ckanext.unhcr.google_analytics_id', '')


def get_max_resource_size():
    return toolkit.config.get('ckan.max_resource_size', 10)


_paragraph_re = re.compile(r'(?:\r\n|\r(?!\n)|\n){2,}')

def nl_to_br(text):
    result = u'\n\n'.join(u'<p>%s</p>' % p.replace('\n', Markup('<br>\n'))
                          for p in _paragraph_re.split(escape(text)))
    return Markup(result)


def is_plugin_loaded(plugin_name):
    return plugin_loaded(plugin_name)


def get_user_packages(user_id):
    datasets = model.Session.query(model.Package).filter_by(creator_user_id=user_id)
    return datasets


def get_user_curators(user_id):
    """ Get who approved user datasets """
    datasets = get_user_packages(user_id)
    curators = []
    for dataset in datasets:
        curations = model.Session.query(
            model.Activity
        ).filter_by(
            object_id=dataset.id,
            activity_type="changed curation state",
        ).all()
        for curation in curations:
            if curation.data.get('curation_activity') == 'dataset_approved':
                if curation.user_id not in curators:
                    curators.append(curation.user_id)

    return curators


def get_user_admins(user_id):
    """ get containers admins for user datasets """
    datasets = get_user_packages(user_id)
    user_admins = []
    for dataset in datasets:
        for admin in get_group_or_org_admin_ids(dataset.owner_org):
            if admin not in user_admins:
                user_admins.append(admin)

    return user_admins


def get_resource_value_label(field_name, resource, dataset_type='dataset'):
    schema = scheming_get_dataset_schema(dataset_type)

    for field in schema['resource_fields']:
        if field['field_name'] == field_name:
            return toolkit.render_snippet(
                'scheming/snippets/display_field.html',
                data=dict(
                    field=field, data=resource, entity_type='dataset',
                    object_type=dataset_type)
            )


def get_system_activities():
    """ Get a list of systema activities """
    # TODO this should be paginated
    limit = toolkit.config.get('ckanext.unhcr.limit_system_activities', 500)
    activities = model.Session.query(
        model.Activity
    ).filter_by(
        activity_type="system activity",
    ).order_by(
        model.Activity.timestamp.desc()
    ).limit(limit).all()

    return activities


def get_bool_arg_value(args, arg_name, default=False):
    """ Booleanize a value from a dict"""
    return toolkit.asbool(args.get(arg_name, default))
