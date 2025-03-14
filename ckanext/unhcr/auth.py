import logging
from ckan import model
from ckan.authz import has_user_permission_for_group_or_org
from ckan.plugins import toolkit
from ckanext.saml2auth.helpers import is_default_login_enabled
from ckan.logic.auth import get_resource_object
import ckanext.datastore.logic.auth as auth_datastore_core
from ckanext.unhcr import helpers
from ckanext.unhcr.kobo.api import KoBoAPI
from ckanext.unhcr.models import AccessRequest, USER_REQUEST_TYPE_NEW, USER_REQUEST_TYPE_RENEWAL
from ckanext.unhcr.utils import get_module_functions, is_saml2_user
log = logging.getLogger(__name__)


# General

def restrict_access_to_get_auth_functions():
    '''
    By default, all GET actions in CKAN core allow anonymous access (non
    logged in users). This is done by applying an allow_anonymous_access
    to the function itself. Rather than reimplementing all auth functions
    in our extension just to apply the `toolkit.auth_disallow_anonymous_access`
    decorator and redirect to the core one, we automate this process by
    importing all GET auth functions automatically (and setting the flag to
    False).
    '''

    core_auth_functions = get_module_functions('ckan.logic.auth.get')
    skip_actions = [
        'help_show',  # Let's not overreact
        'site_read',  # Because of madness in the API controller
        'organization_list_for_user',  # Because of #4097
        'get_site_user',
        'user_reset',  # saml2
        'request_reset',  # saml2
    ]

    overriden_auth_functions = {}
    for key, value in core_auth_functions.items():

        if key in skip_actions:
            continue
        auth_function = toolkit.auth_disallow_anonymous_access(value)
        overriden_auth_functions[key] = auth_function

    # Handle these separately
    overriden_auth_functions['site_read'] = site_read
    overriden_auth_functions['organization_list_for_user'] = \
        organization_list_for_user

    return overriden_auth_functions


@toolkit.auth_allow_anonymous_access
def site_read(context, data_dict):
    if toolkit.request.path.startswith('/api'):
        # Let individual API actions deal with their auth
        return {'success': True}

    userobj = context.get('auth_user_obj')
    if not userobj:
        return {'success': False}

    # we've granted external users site_read for the home page, but we
    # want to deny site_read for all other pages that only need site_read
    if userobj.external and toolkit.request.path != '/':
        return {'success': False}

    return {'success': True}


# Organization

@toolkit.auth_allow_anonymous_access
@toolkit.chained_auth_function
def organization_list_for_user(next_auth, context, data_dict):
    if not context.get('user'):
        return {'success': False}
    else:
        return next_auth(context, data_dict)


@toolkit.chained_auth_function
def organization_show(next_auth, context, data_dict):
    user = context.get('auth_user_obj')
    if not user:
        return next_auth(context, data_dict)
    if user.external:
        deposit = helpers.get_data_deposit()
        if data_dict.get('id') in [deposit['name'], deposit['id']]:
            return {'success': True}
        else:
            return {'success': False}
    return next_auth(context, data_dict)


def organization_list_all_fields(context, data_dict):
    try:
        toolkit.check_access('organization_list', context, data_dict)
        return {'success': True}
    except toolkit.NotAuthorized:
        return {'success': False}


@toolkit.chained_auth_function
def organization_create(next_auth, context, data_dict):
    user_orgs = toolkit.get_action('organization_list_for_user')(context, {})

    # Allow to see `Request data container` button if user is an admin for an org
    if not data_dict:
        for user_org in user_orgs:
            if user_org['capacity'] == 'admin':
                return {'success': True}

    # Base access check
    result = next_auth(context, data_dict)
    if not result['success']:
        return result

    # Check parent organization access
    if data_dict:
        for user_org in user_orgs:

            # Looking for orgs only where user is admin
            if user_org['capacity'] != 'admin':
                continue

            # Looking for only approved orgs
            if user_org['state'] != 'active':
                continue

            # Allow if parent matches
            for group in data_dict.get('groups', []):
                if group['name'] == user_org['name']:
                    return {'success': True}

    return {'success': False, 'msg': 'Not allowed to create a data container'}


def group_list_authz(context, data_dict):
    return {'success': True}


# Package
@toolkit.chained_auth_function
def package_create(next_auth, context, data_dict):
    # Data deposit
    if not data_dict:
        try:
            # All users can deposit datasets
            if (
                toolkit.request.path == '/deposited-dataset/new' or
                toolkit.request.path.startswith('/deposited-dataset/edit/')
            ):
                return {'success': True}
        except (TypeError, RuntimeError):
            return {
                'success': False,
                'msg': 'package_create requires either a web request or a data_dict'
            }
    else:
        deposit = helpers.get_data_deposit()
        if deposit['id'] == data_dict.get('owner_org'):
            return {'success': True}

    # Data container
    context['model'] = context.get('model') or model
    return next_auth(context, data_dict)

@toolkit.chained_auth_function
def package_update(next_auth, context, data_dict):

    # Get dataset
    dataset_id = None
    if data_dict:
        dataset_id = data_dict['id']
    if context.get('package'):
        dataset_id = context['package'].id
    dataset = toolkit.get_action('package_show')(context, {'id': dataset_id})

    # Deposited dataset
    if dataset['type'] == 'deposited-dataset':
        curation = helpers.get_deposited_dataset_user_curation_status(
            dataset, getattr(context.get('auth_user_obj'), 'id', None))
        if 'edit' in curation['actions']:
            return {'success': True}
        return {'success': False, 'msg': 'Not authorized to edit deposited dataset'}

    # Regular dataset
    return next_auth(context, data_dict)

def package_kobo_update(context, data_dict):
    """ Check if current user is manager of the KoBo survey """
    kobo_asset_id = data_dict.get('kobo_asset_id')
    if not kobo_asset_id:
        return {'success': False, 'msg': 'No kobo_asset_id provided'}
    user_obj = model.User.get(context['user'])
    plugin_extras = {} if user_obj.plugin_extras is None else user_obj.plugin_extras
    kobo_token = plugin_extras.get('unhcr', {}).get('kobo_token')
    if not kobo_token:
        return {'success': False, 'msg': 'KoBo token is not defined'}
    kobo_url = toolkit.config.get('ckanext.unhcr.kobo_url', 'https://kobo.unhcr.org')
    kobo_api = KoBoAPI(kobo_token, kobo_url)
    survey = kobo_api.get_asset(kobo_asset_id)
    if survey['user_is_manager']:
        return {'success': True}
    else:
        return {'success': False, 'msg': 'Not authorized to update the survey'}

def package_internal_activity_list(context, data_dict):
    try:
        toolkit.check_access('package_update', context, data_dict)
        return {'success': True}
    except toolkit.NotAuthorized:
        return {'success': False}


# Resource

def resource_download(context, data_dict):
    '''
    This is a new auth function that specifically controls access to the download
    of a resource file, as opposed to seeing the metadata of a resource (handled
    by `resource_show`

    If this resource is marked as public or private in the custom visibility
    field, the authorization check is deferred to `resource_show` as the standard
    logic applies (we assume that the necessary validators are applied to keep
    `visibility` and `private` fields in sync).

    If this resource is marked as `restricted` then only users belonging to
    the dataset organization can download the file.
    '''

    # Prepare all the parts
    context['model'] = context.get('model') or model
    user = context.get('user')
    resource = get_resource_object(context, data_dict)
    dataset = toolkit.get_action('package_show')(
        {'ignore_auth': True}, {'id': resource.package_id})
    visibility = resource.extras.get('visibility')

    # Use default check
    user_id = getattr(context.get('auth_user_obj'), 'id', None)
    is_deposit = dataset.get('type') == 'deposited-dataset'
    if is_deposit:
        is_depositor = dataset.get('creator_user_id') == user_id
        curators = [u['id'] for u in helpers.get_data_curation_users(dataset)]
        is_curator = user_id in curators
    else:
        is_depositor = False
        is_curator = False

    if not user or is_depositor or is_curator or not visibility or visibility != 'restricted':
        try:
            toolkit.check_access('resource_show', context, data_dict)
            return {'success': True}
        except toolkit.NotAuthorized:
            return {'success': False}

    # Restricted visibility (public metadata but private downloads)
    if dataset.get('owner_org'):
        user_orgs = toolkit.get_action('organization_list_for_user')(
            {'ignore_auth': True}, {'id': user})
        user_in_owner_org = any(
            org['id'] == dataset['owner_org'] for org in user_orgs)
        if user_in_owner_org:
            return {'success': True}

    # Check if the user is a dataset collaborator
    action = toolkit.get_action('package_collaborator_list_for_user')
    if user and action:
        datasets = action(context, {'id': user})
        return {
            'success': resource.package_id in [
                d['package_id'] for d in datasets
            ]
        }

    return {'success': False}


@toolkit.chained_auth_function
def datastore_info(next_auth, context, data_dict):
    parent_auth = auth_datastore_core.datastore_auth(
        context,
        data_dict,
        'resource_download'
    )
    if not parent_auth['success']:
        return parent_auth
    return next_auth(context, data_dict)


@toolkit.chained_auth_function
def datastore_search(next_auth, context, data_dict):
    parent_auth = auth_datastore_core.datastore_auth(
        context,
        data_dict,
        'resource_download'
    )
    if not parent_auth['success']:
        return parent_auth
    return next_auth(context, data_dict)


@toolkit.chained_auth_function
def datastore_search_sql(next_auth, context, data_dict):
    '''need access to view all tables in query'''

    for name in context['table_names']:
        name_auth = auth_datastore_core.datastore_auth(
            dict(context),  # required because check_access mutates context
            {'id': name},
            'resource_download')
        if not name_auth['success']:
            return {
                'success': False,
                'msg': 'Not authorized to read resource.'}
    return next_auth(context, data_dict)


def datasets_validation_report(context, data_dict):
    return {'success': False}


def scan_submit(context, data_dict):
    try:
        toolkit.check_access('resource_update', context, data_dict)
        return {'success': True}
    except toolkit.NotAuthorized:
        return {'success': False}


def scan_hook(context, data_dict):
    try:
        toolkit.check_access('resource_update', context, data_dict)
        return {'success': True}
    except toolkit.NotAuthorized:
        return {'success': False}


@toolkit.chained_auth_function
def package_collaborator_create(next_auth, context, data_dict):
    dataset = toolkit.get_action('package_show')(
        {'ignore_auth': True}, {'id': data_dict['id']})
    if dataset['type'] == 'deposited-dataset':
        return {'success': False, 'msg': "Can't add collaborators to a Data Deposit"}
    return next_auth(context, data_dict)


# Access Requests

def access_request_list_for_user(context, data_dict):
    user = context.get('user')
    orgs = toolkit.get_action("organization_list_for_user")(
        {"user": user},
        {"id": user, "permission": "admin"}
    )

    return {'success': len(orgs) > 0}


def access_request_update(context, data_dict):
    user = context.get('user')
    request_id = toolkit.get_or_bust(data_dict, "id")
    request = model.Session.query(AccessRequest).get(request_id)
    if not request:
        raise toolkit.ObjectNotFound("Access Request not found")
    if request.object_type not in ['organization', 'package', 'user']:
        raise toolkit.Invalid("Unknown Object Type")

    if request.object_type == 'package':
        package = toolkit.get_action('package_show')(
            context, {'id': request.object_id}
        )
        org_id = package['owner_org']
        return {
            'success': has_user_permission_for_group_or_org(
                org_id, user, 'admin'
            )
        }
    elif request.object_type == 'organization':
        org_id = request.object_id
        return {
            'success': has_user_permission_for_group_or_org(
                org_id, user, 'admin'
            )
        }
    elif request.object_type == 'user':
        data_dict = {
            'id': request.object_id,
            'renew_expiry_date': request.data.get('user_request_type', USER_REQUEST_TYPE_NEW) == USER_REQUEST_TYPE_RENEWAL
        }
        return external_user_update_state(context, data_dict)


def access_request_create(context, data_dict):
    return {'success': bool(context.get('user'))}


def external_user_update_state(context, data_dict):
    # New users only can be approved by admins and renewal could also be approved by curators/editors

    renew_expiry_date = data_dict.pop('renew_expiry_date', False)
    m = context.get('model', model)
    request_userobj = context.get('auth_user_obj')
    if not request_userobj:
        return {'success': False}

    target_user_id = toolkit.get_or_bust(data_dict, "id")
    target_userobj = m.User.get(target_user_id)
    if not target_userobj:
        raise toolkit.ObjectNotFound("User not found")

    # request_userobj is the user who is trying to perform the action
    # target_userobj is the user we're trying to modify

    if not target_userobj.external:
        return {'success': False, 'msg': "Can only perform this action on an external user"}

    access_requests = model.Session.query(AccessRequest).filter(
        AccessRequest.user_id==target_userobj.id,
        AccessRequest.object_id==target_userobj.id,
        AccessRequest.status=='requested',
        AccessRequest.object_type=='user',
    ).all()

    if renew_expiry_date:
        renewal_requests = [
            req for req in access_requests
            if req.data.get('user_request_type', USER_REQUEST_TYPE_NEW) == USER_REQUEST_TYPE_RENEWAL
        ]
        if len(renewal_requests) != 1:
            return {
                'success': False,
                'msg': "User must be associated with exactly one pending renewal request"
            }
        renewal_request = renewal_requests[0]
        # Just a renewal, only "users_who_can_approve" are allowed
        return {'success': request_userobj.id in renewal_request.data.get('users_who_can_approve')}

    # ==========================================
    # This is a new user asking for permission

    if target_userobj.state != m.State.PENDING:
        return {'success': False, 'msg': "Can only change state of a 'pending' user"}

    if not access_requests:
        access_requests_new_user = []
    else:
        access_requests_new_user = [
            req for req in access_requests
            if req.data.get('user_request_type', USER_REQUEST_TYPE_NEW) == USER_REQUEST_TYPE_NEW
        ]
    if len(access_requests_new_user) != 1:
        return {
            'success': False,
            'msg': "User must be associated with exactly one pending access request"
        }

    for container in access_requests_new_user[0].data['default_containers']:
        if has_user_permission_for_group_or_org(
            container, request_userobj.id, 'admin'
        ):
            return {'success': True}

    return {'success': False}


def geography_autocomplete(context, data_dict):
    return {'success': True}


def geography_show(context, data_dict):
    return {'success': True}


# Admin

def user_update_sysadmin(context, data_dict):
    return {'success': False}


def search_index_rebuild(context, data_dict):
    return {'success': False}


@toolkit.chained_auth_function
def user_show(next_auth, context, data_dict):
    auth_user_obj = context.get('auth_user_obj')
    if not auth_user_obj:
        return {'success': False}
    if auth_user_obj.external:
        if context['user'] == data_dict['id'] or auth_user_obj.id == data_dict['id']:
            return next_auth(context, data_dict)
        return {'success': False}
    return next_auth(context, data_dict)


# Password resets

def _get_user(username_or_email):
    userobj = model.User.get(username_or_email)
    if userobj:
        return userobj
    users = model.User.by_email(username_or_email)
    if len(users) == 1:
        return users[0]
    return None


@toolkit.chained_auth_function
@toolkit.auth_allow_anonymous_access
@toolkit.auth_sysadmins_check
def user_reset(next_auth, context, data_dict):
    if is_default_login_enabled():
        return next_auth(context, data_dict)
    return {'success': False, 'msg': 'Users cannot reset passwords.'}


@toolkit.chained_auth_function
@toolkit.auth_allow_anonymous_access
@toolkit.auth_sysadmins_check
def request_reset(next_auth, context, data_dict):
    username_or_email = toolkit.request.form.get('user', '')
    method = toolkit.request.method

    if is_default_login_enabled():
        userobj = _get_user(username_or_email)
        if (
            method == 'GET' or userobj is None or
            (method == 'POST' and not is_saml2_user(userobj))
        ):
            return next_auth(context, data_dict)
    return {'success': False, 'msg': 'Users cannot reset passwords.'}
