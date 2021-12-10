import copy
import datetime
import json
import logging
import requests
from urllib.parse import urljoin
from dateutil.parser import parse as parse_date
from sqlalchemy import and_, desc, or_, select, not_
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import aliased
from ckan import model
from ckan.authz import get_group_or_org_admin_ids, has_user_permission_for_group_or_org
from ckan.plugins import toolkit
from ckan.lib import mailer as core_mailer
from ckan.lib.mailer import MailerException
import ckan.lib.plugins as lib_plugins
from ckan.lib.search import index_for, commit
import ckan.logic as core_logic
import ckan.lib.dictization.model_dictize as model_dictize
from ckanext.unhcr import helpers, mailer, utils
from ckanext.unhcr.jobs import process_last_admin_on_delete
from ckanext.unhcr.kobo.api import KoBoAPI, KoBoSurvey
from ckanext.unhcr.kobo.exceptions import KoboMissingAssetIdError, KoBoEmptySurveyError
from ckanext.unhcr.kobo.kobo_dataset import KoboDataset
from ckanext.unhcr.models import (
    AccessRequest, Geography, GisStatus, LAYER_TO_DISPLAY_NAME,
    USER_REQUEST_TYPE_NEW, USER_REQUEST_TYPE_RENEWAL
)
from ckanext.unhcr.utils import is_saml2_user


log = logging.getLogger(__name__)


def _get_user_obj(context):
    if 'user_obj' in context:
        return context['user_obj']
    user = context.get('user')
    m = context.get('model', model)
    user_obj = m.User.get(user)
    if not user_obj:
        raise toolkit.ObjectNotFound("User not found")
    return user_obj


# Package


@toolkit.chained_action
def package_update(up_func, context, data_dict):

    notify = False
    if not context.get('ignore_auth'):
        user_obj = _get_user_obj(context)
        # Decide if we need notification
        # - deposited-datset AND
        # - not a test env AND
        # - just published
        if data_dict.get('type') == 'deposited-dataset' and hasattr(user_obj, 'id'):
            dataset = toolkit.get_action('package_show')(context, {'id': data_dict['id']})
            if dataset.get('state') == 'draft' and data_dict.get('state') == 'active':
                notify = True

    # Update dataset
    dataset = up_func(context, data_dict)

    # Send notification if needed
    if notify:
        curation = helpers.get_deposited_dataset_user_curation_status(dataset, user_obj.id)
        subj = mailer.compose_curation_email_subj(dataset)
        body = mailer.compose_curation_email_body(
            dataset, curation, user_obj.display_name, 'deposit')
        mailer.mail_user_by_id(user_obj.id, subj, body)

    return dataset


@toolkit.chained_action
def package_create(up_func, context, data_dict):
    """ Create resources for KoBo assets """

    # Check if the survey is ready to import
    kobo_asset_id = data_dict.get('kobo_asset_id')
    if kobo_asset_id:
        user_obj = model.User.by_name(context['user'])
        kd = KoboDataset(kobo_asset_id)
        kobo_api = kd.get_kobo_api(user_obj)
        survey = KoBoSurvey(kobo_asset_id, kobo_api)

        if survey.get_total_submissions() == 0:
            raise toolkit.ValidationError({'kobo-survey': ['The selected KoBoToolbox survey has no submissions']})

    # check if we have some geographies from DDI fields
    if data_dict.get('country_codes'):
        # this is a list of ISO3 country codes
        country_codes = data_dict.get('country_codes').split(',')
        geographies = []
        for country_code in country_codes:
            geog = Geography.get_country_by_iso3(iso3=country_code.strip())
            if not geog:
                log.error('Country not found {}'.format(country_code))
            else:
                geographies.append(geog.pcode)
        data_dict['geographies'] = ','.join(geographies)

    # Create dataset
    dataset = up_func(context, data_dict)

    if kobo_asset_id:
        # create basic resources
        kd.create_kobo_resources(context, dataset, user_obj)

    return dataset


def package_publish_microdata(context, data_dict):
    default_error = 'Unknown microdata error'

    # Get data
    dataset_id = data_dict.get('id')
    nation = data_dict.get('nation')
    repoid = data_dict.get('repoid')

    # Check access
    toolkit.check_access('sysadmin', context)
    api_key = toolkit.config.get('ckanext.unhcr.microdata_api_key')
    if not api_key:
        raise toolkit.NotAuthorized('Microdata API Key is not set')

    # Get dataset/survey
    headers = {'X-Api-Key': api_key}
    dataset = toolkit.get_action('package_show')(context, {'id': dataset_id})
    survey = helpers.convert_dataset_to_microdata_survey(dataset, nation, repoid)
    idno = survey['study_desc']['title_statement']['idno']

    try:

        # Publish dataset
        url = 'https://microdata.unhcr.org/index.php/api/datasets/create/survey/%s' % idno
        response = requests.post(url, headers=headers, json=survey).json()
        if response.get('status') != 'success':
            raise RuntimeError(str(response.get('errors', default_error)))
        template = 'https://microdata.unhcr.org/index.php/catalog/%s'
        survey['url'] = template % response['dataset']['id']
        survey['resources'] = []
        survey['files'] = []

        # Pubish resources/files
        file_name_counter = {}
        if dataset.get('resources', []):
            url = 'https://microdata.unhcr.org/index.php/api/datasets/%s/%s'
            for resource in dataset.get('resources', []):

                # resource
                resouce_url = url % (idno, 'resources')
                md_resource = helpers.convert_resource_to_microdata_resource(resource)
                response = requests.post(
                    resouce_url, headers=headers, json=md_resource).json()
                if response.get('status') != 'success':
                    raise RuntimeError(str(response.get('errors', default_error)))
                survey['resources'].append(response['resource'])

                # file
                file_url = url % (idno, 'files')
                file_name = resource['url'].split('/')[-1]
                file_path = helpers.get_resource_file_path(resource)
                file_mime = resource['mimetype']
                if not file_name or not file_path:
                    continue
                file_name_counter.setdefault(file_name, 0)
                file_name_counter[file_name] += 1
                if file_name_counter[file_name] > 1:
                    file_name = helpers.add_file_name_suffix(
                        file_name, file_name_counter[file_name] - 1)
                with open(file_path, 'rb') as file_obj:
                    file = (file_name, file_obj, file_mime)
                    response = requests.post(
                        file_url, headers=headers, files={'file': file}).json()
                # TODO: update
                # it's a hack to overcome incorrect Microdata responses
                # unsupported file types fail this way and we are skipping them
                if not isinstance(response, dict):
                    continue
                if response.get('status') != 'success':
                    raise RuntimeError(str(response.get('errors', default_error)))
                survey['files'].append(response)

    except requests.exceptions.HTTPError as exception:
        log.exception(exception)
        raise RuntimeError('Microdata connection failed')

    return survey


def package_get_microdata_collections(context, data_dict):
    default_error = 'Unknown microdata error'

    # Check access
    toolkit.check_access('sysadmin', context)
    api_key = toolkit.config.get('ckanext.unhcr.microdata_api_key')
    if not api_key:
        raise toolkit.NotAuthorized('Microdata API Key is not set')

    try:

        # Get collections
        headers = {'X-Api-Key': api_key}
        url = 'https://microdata.unhcr.org/index.php/api/collections'
        response = requests.get(url, headers=headers).json()
        if response.get('status') != 'success':
            raise RuntimeError(str(response.get('errors', default_error)))
        collections = response['collections']

    except requests.exceptions.HTTPError as exception:
        log.exception(exception)
        raise RuntimeError('Microdata connection failed')

    return collections


@toolkit.chained_action
def package_collaborator_create(up_func, context, data_dict):

    m = context.get('model', model)
    user_id = toolkit.get_or_bust(data_dict, 'user_id')
    user = m.User.get(user_id)
    if not user:
        raise toolkit.ObjectNotFound("User not found")

    if user.external:
        message = 'Partner users can not be a dataset collaborator'
        raise toolkit.ValidationError({'message': message}, error_summary=message)

    collaborator = up_func(context, data_dict)

    mailer.mail_notification_to_collaborator(
        collaborator['package_id'],
        collaborator['user_id'],
        collaborator['capacity'],
        event='create'
    )

    return collaborator


@toolkit.chained_action
def package_collaborator_delete(up_func, context, data_dict):
    up_func(context, data_dict)

    mailer.mail_notification_to_collaborator(
        data_dict['id'],
        data_dict['user_id'],
        capacity='collaborator',
        event='delete',
    )

    return


# Organization
@toolkit.chained_action
def organization_create(up_func, context, data_dict):

    # When creating an organization, if the user is not a sysadmin it will be
    # created as pending, and sysadmins notified

    org_dict = up_func(context, data_dict)

    # We create an organization as usual because we can't set
    # state=approval_needed on creation step and then
    # we patch the organization

    # Notify sysadmins
    notify_sysadmins = False
    user = toolkit.get_action('user_show')(context, {'id': context['user']})
    if not user['sysadmin']:
        # Not a sysadmin, create as pending and notify sysadmins (if all went
        # well)
        context['__unhcr_state_pending'] = True
        org_dict = toolkit.get_action('organization_patch')(context,
            {'id': org_dict['id'], 'state': 'approval_needed'})
        notify_sysadmins = True
    if notify_sysadmins:
        try:
            for user in helpers.get_valid_sysadmins():
                if user.email:
                    subj = mailer.compose_container_email_subj(org_dict, event='request')
                    body = mailer.compose_request_container_email_body(
                        org_dict,
                        user,
                        _get_user_obj(context),
                    )
                    mailer.mail_user(user, subj, body)
        except MailerException:
            message = '[email] Data container request notification is not sent: {0}'
            log.critical(message.format(org_dict['title']))

    return org_dict


@toolkit.chained_action
def organization_member_create(up_func, context, data_dict):

    m = context.get('model', model)
    username = toolkit.get_or_bust(data_dict, 'username')
    user = m.User.get(username)
    if not user:
        raise toolkit.ObjectNotFound("User not found")

    if user.external:
        message = 'Partner users can not be an organisation member'
        raise toolkit.ValidationError({'message': message}, error_summary=message)

    if not data_dict.get('not_notify'):

        # Get container/user
        container = toolkit.get_action('organization_show')(context, {'id': data_dict['id']})
        user = toolkit.get_action('user_show')(context, {'id': data_dict['username']})
        extra_mail_msg = data_dict.get('extra_mail_msg')

        # Notify the user
        subj = mailer.compose_membership_email_subj(container)
        body = mailer.compose_membership_email_body(container, user, 'create', extra_mail_msg)
        mailer.mail_user_by_id(user['id'], subj, body)

    return up_func(context, data_dict)


@toolkit.chained_action
def organization_member_delete(up_func, context, data_dict):

    if not data_dict.get('not_notify'):

        # Get container/user
        container = toolkit.get_action('organization_show')(context, {'id': data_dict['id']})
        user = toolkit.get_action('user_show')(context, {'id': data_dict['user_id']})

        # Notify the user
        subj = mailer.compose_membership_email_subj(container)
        body = mailer.compose_membership_email_body(container, user, 'delete')
        mailer.mail_user_by_id(user['id'], subj, body)

    return up_func(context, data_dict)


def organization_list_all_fields(context, data_dict):
    """
    Customized organization_list action.
    This action is many times more efficient than calling organization_list
    https://docs.ckan.org/en/2.8/api/index.html#ckan.logic.action.get.organization_list
    with {'all_fields': True, 'include_extras': True}
    but it only allows a much more constrained list of params.

    :param type: group type (optional, default: ``'data-container'``)
    :type type: string
    :param order_by: the field to sort the list by (optional, default: ``'title'``)
    :type order_by: string
    """
    toolkit.check_access('organization_list_all_fields', context, data_dict)
    m = context.get('model', model)
    session = context.get('session', m.Session)
    group_type = data_dict.get('type', 'data-container')
    order_by = data_dict.get('order_by', 'title')

    extra_cols = [rec[0] for rec in session.query(m.GroupExtra.key).distinct()]
    group_table = m.meta.metadata.tables['group']
    group_extra_table = m.meta.metadata.tables['group_extra']
    allowed_cols = [col.key for col in group_table.columns] + extra_cols
    if order_by not in allowed_cols:
        raise toolkit.Invalid("'order_by' must be one of {}".format(allowed_cols))

    join_obj = group_table
    select_cols = [col for col in group_table.columns]
    for col in extra_cols:
        extras_alias = aliased(group_extra_table, name='extras_{}'.format(col))
        select_cols.append(extras_alias.c.value.label(col))
        join_obj = join_obj.join(
            extras_alias,
            and_(
                group_table.c.id==extras_alias.c.group_id,
                extras_alias.c.key==col,
                extras_alias.c.state=='active',
            ), isouter=True,
        )

    sql = select(
        select_cols
    ).select_from(
        join_obj
    ).where(
        and_(
            group_table.c.type==group_type,
            group_table.c.state=='active',
            group_table.c.is_organization==True,
        )
    ).order_by(
        order_by
    )
    result = session.execute(sql).fetchall()

    organization_plugin = lib_plugins.lookup_group_plugin(group_type)
    schema = organization_plugin.form_to_db_schema()

    out_list = []
    for row in result:
        raw_dict = {k:v for k,v in row.items()}
        validated_dict, errors = organization_plugin.validate(
            context,
            raw_dict,
            schema,
            'organization_show'
        )
        if errors:
            raise toolkit.ValidationError(errors)
        validated_dict['display_name'] = validated_dict['title'] or validated_dict['name']
        out_list.append(validated_dict)

    return out_list


# Pending requests

def container_request_list(context, data_dict):
    all_fields = data_dict.get('all_fields', False)

    # Check permissions
    toolkit.check_access('sysadmin', context)

    # Containers
    containers = []
    query = (model.Session
        .query(model.Group.id)
        .filter(model.Group.state == 'approval_needed')
        .filter(model.Group.is_organization == True)
        .order_by(model.Group.name))
    for item in query.all():
        if all_fields:
            container = toolkit.get_action('organization_show')(context, {'id': item.id})
        else:
            container = item.id
        containers.append(container)

    return {
        'containers': containers,
        'count': len(containers),
    }


# Activity

def _package_activity_list(
    package_id,
    limit,
    offset,
    include_hidden_activity=False,
    include_activity_types=None,
):
    q = model.activity._package_activity_query(package_id)

    if include_activity_types:
        q = q.filter(model.Activity.activity_type.in_(include_activity_types))

    if not include_hidden_activity:
        q = model.activity._filter_activitites_from_users(q)

    return model.activity._activities_at_offset(q, limit, offset)


@core_logic.validate(core_logic.schema.default_activity_list_schema)
def package_internal_activity_list(context, data_dict):
    toolkit.check_access('package_internal_activity_list', context.copy(), data_dict)
    package_id = toolkit.get_or_bust(data_dict, 'id')
    model = context['model']


    package = model.Package.get(package_id)
    if package is None:
        raise toolkit.ObjectNotFound("Package not found")
    user_is_container_admin = has_user_permission_for_group_or_org(
        package.owner_org,
        context['user'],
        'admin',
    )

    include_hidden_activity = data_dict.get('include_hidden_activity', False)

    limit = data_dict['limit']  # defaulted, limited & made an int by schema
    offset = int(data_dict.get('offset', 0))

    if user_is_container_admin:
        include_activity_types = ['changed curation state', 'download resource']
    else:
        include_activity_types = ['changed curation state']
    activity_objects = _package_activity_list(
        package.id,
        limit,
        offset,
        include_hidden_activity,
        include_activity_types,
    )

    return model_dictize.activity_list_dictize(
        activity_objects, context, include_data=True)


def _remove_internal_activities(activities):
    return [
        a for a in activities
        if a['activity_type'] not in ['changed curation state', 'download resource']
    ]


@toolkit.side_effect_free
@toolkit.chained_action
def package_activity_list(up_func, context, data_dict):
    return _remove_internal_activities(up_func(context.copy(), data_dict))


@toolkit.side_effect_free
@toolkit.chained_action
def dashboard_activity_list(up_func, context, data_dict):
    return _remove_internal_activities(up_func(context.copy(), data_dict))


@toolkit.side_effect_free
@toolkit.chained_action
def user_activity_list(up_func, context, data_dict):
    return _remove_internal_activities(up_func(context.copy(), data_dict))


@toolkit.side_effect_free
@toolkit.chained_action
def group_activity_list(up_func, context, data_dict):
    return _remove_internal_activities(up_func(context.copy(), data_dict))


@toolkit.side_effect_free
@toolkit.chained_action
def organization_activity_list(up_func, context, data_dict):
    return _remove_internal_activities(up_func(context.copy(), data_dict))


# Datastore

@toolkit.side_effect_free
def datasets_validation_report(context, data_dict):

    toolkit.check_access('datasets_validation_report', context, data_dict)
    search_params = {
        'q': '*:*',
        'include_private': True,
        'rows': 1000
    }
    query = toolkit.get_action('package_search')({'ignore_auth': True}, search_params)

    count = query['count']
    datasets = query['results']

    out = {
        'count': count,
        'datasets': [],
    }

    # get the schema
    package_plugin = lib_plugins.lookup_package_plugin('dataset')
    schema = package_plugin.update_package_schema()
    for dataset in datasets:
        data, errors = package_plugin.validate(context, dataset, schema, 'package_update')
        if errors:
            out['datasets'].append({
                'id': dataset['id'],
                'name': dataset['name'],
                'errors': errors,
            })

    return out


def _fail_task(context, task, error):
    task['error'] = json.dumps(error)
    task['state'] = 'error'
    task['last_updated'] = datetime.datetime.utcnow().isoformat()
    return toolkit.get_action('task_status_update')(context, task)


def _task_is_stale(task):
    assume_task_stale_after = datetime.timedelta(seconds=3600)
    updated = parse_date(task['last_updated'])
    time_since_last_updated = datetime.datetime.utcnow() - updated
    return time_since_last_updated > assume_task_stale_after


def _should_resubmit(context, task, metadata):
    if task['state'] != 'complete':
        return False

    try:
        resource_show = toolkit.get_action('resource_show')
        resource_dict = resource_show(context, {'id': task['entity_id']})
    except toolkit.ObjectNotFound:
        return False

    if resource_dict.get('last_modified') and metadata.get('task_created'):
        try:
            last_modified_datetime = parse_date(resource_dict['last_modified'])
            task_created_datetime = parse_date(metadata['task_created'])
            if last_modified_datetime > task_created_datetime:
                log.debug('Uploaded file more recent: {0} > {1}'.format(
                        last_modified_datetime,
                        task_created_datetime,
                    )
                )
                return True
        except ValueError:
            pass
    elif (
        resource_dict.get('url')
        and metadata.get('original_url')
        and resource_dict['url'] != metadata['original_url']
    ):
        log.debug('URLs are different: {0} != {1}'.format(
                resource_dict['url'],
                metadata['original_url'],
            )
        )
        return True

    return False


def scan_submit(context, data_dict):
    resource_id = toolkit.get_or_bust(data_dict, "id")
    toolkit.check_access('scan_submit', context, data_dict)

    clamav_service_base_url = toolkit.config.get('ckanext.unhcr.clamav_url')
    site_url = toolkit.config.get('ckan.site_url')
    callback_url = toolkit.url_for('/api/3/action/scan_hook', qualified=True)
    site_user = toolkit.get_action('get_site_user')({'ignore_auth': True}, {})

    try:
        resource_dict = toolkit.get_action('resource_show')(context, {'id': resource_id})
    except toolkit.ObjectNotFound:
        return False

    file_size = resource_dict.get('size', 0)
    if file_size is None:
        file_size = 0
    clamav_max_resource_size = int(toolkit.config.get('ckan.clamav_max_resource_size', 10)) * 1024 * 1024
    if file_size > clamav_max_resource_size:
        url = resource_dict.get('url')
        log.info(
            'Skipping file from being ClamAV analyzed (file too big, {} > {}): {}'.format(
                file_size,
                clamav_max_resource_size,
                url
            )
        )
        return True

    task = {
        'entity_id': resource_id,
        'entity_type': 'resource',
        'task_type': 'clamav',
        'last_updated': datetime.datetime.utcnow().isoformat(),
        'state': 'submitting',
        'key': 'clamav',
        'value': '{}',
        'error': 'null',
    }

    payload = json.dumps({
        'api_key': site_user['apikey'],
        'job_type': 'scan',
        'result_url': callback_url,
        'metadata': {
            'ckan_url': site_url,
            'resource_id': resource_id,
            'task_created': task['last_updated'],
            'original_url': resource_dict.get('url'),
        }
    })

    try:
        existing_task = toolkit.get_action('task_status_show')(context, {
            'entity_id': resource_id,
            'task_type': 'clamav',
            'key': 'clamav'
        })
        if (
            existing_task.get('state') == 'pending'
            and not _task_is_stale(existing_task)
        ):
            log.info(
                'A pending task was found {} for this resource, so '
                'skipping this duplicate task'.format(existing_task['id'])
            )
            return False
    except toolkit.ObjectNotFound:
        pass

    context['ignore_auth'] = True
    toolkit.get_action('task_status_update')(context, task)

    if not clamav_service_base_url:
        error = {'message': 'Could not submit to Clam AV Service.'}
        _fail_task(context, task, error)
        return False

    try:
        r = requests.post(
            urljoin(clamav_service_base_url, 'job'),
            headers={'Content-Type': 'application/json'},
            data=payload,
        )
        r.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        error = {'message': ['Could not connect to Clam AV Service.'], 'details': [str(e)]}
        _fail_task(context, task, error)
        raise toolkit.ValidationError(error)
    except requests.exceptions.HTTPError as e:
        m = 'An Error occurred while sending the job: {0}'.format(
            getattr(e, 'message', '')
        )
        try:
            body = e.response.json()
        except ValueError:
            body = e.response.text
        error = {'message': m, 'details': body, 'status_code': r.status_code}
        _fail_task(context, task, error)
        raise toolkit.ValidationError(error)

    task['value'] = r.text
    task['state'] = 'pending'
    task['last_updated'] = datetime.datetime.utcnow().isoformat(),
    toolkit.get_action('task_status_update')(context, task)

    return True


def scan_hook(context, data_dict):
    metadata, status = toolkit.get_or_bust(data_dict, ['metadata', 'status'])
    resource_id = toolkit.get_or_bust(metadata, 'resource_id')

    toolkit.check_access('scan_hook', context, {'id': resource_id})

    task = toolkit.get_action('task_status_show')(context, {
        'entity_id': resource_id,
        'task_type': 'clamav',
        'key': 'clamav'
    })

    task['state'] = status
    task['last_updated'] = datetime.datetime.utcnow().isoformat()
    task['value'] = json.dumps(data_dict)
    task['error'] = json.dumps(data_dict.get('error'))

    task = toolkit.get_action('task_status_update')({'ignore_auth': True}, task)

    if task['state'] == 'error':
        recipients = toolkit.aslist(toolkit.config.get('ckanext.unhcr.error_emails', []))
        for address in recipients:
            subj = '[UNHCR RIDL] Error performing Clam AV Scan'
            core_mailer.mail_recipient(
                'admin',
                address,
                subj,
                json.dumps(data_dict, indent=4)
            )
    elif task['state'] == 'complete' and task['value'] and data_dict.get('data'):
        scan_status = data_dict.get('data').get('status_code')
        if scan_status == 1:
            # file is infected
            resource = toolkit.get_action('resource_show')(context, {'id': resource_id})
            resource_name = resource['name'] or "Unnamed resource"
            recipients = mailer.get_infected_file_email_recipients()
            scan_report = data_dict.get('data').get('description', '')
            for recipient in recipients:
                subj = mailer.compose_infected_file_email_subj()
                body = mailer.compose_infected_file_email_body(
                    recipient,
                    resource_name,
                    resource['package_id'],
                    resource['id'],
                    scan_report
                )
                mailer.mail_user_by_id(recipient['id'], subj, body)

    if _should_resubmit(context, task, metadata):
        log.debug(
            'Resource {} has been modified, resubmitting to Clam AV'.format(resource_id)
        )
        toolkit.get_action('scan_submit')(context, {'id': resource_id})

    return data_dict


@toolkit.chained_action
def resource_create(up_func, context, data_dict):
    toolkit.check_access('resource_create', context, data_dict)
    # Data files uses the idenfiability field and should hide personal data
    # Attachment files do not use identifiability field and should not be hidden
    if data_dict.get('identifiability') == 'personally_identifiable' and data_dict.get('type') == 'data':
        data_dict['visibility'] = 'restricted'
    has_upload = data_dict.get('upload') is not None
    resource = up_func(context, data_dict)

    # Skip temporary KoBo resources (they just have empty files)
    skip_clamav_scan = context.pop('skip_clamav_scan', False)

    if has_upload and not skip_clamav_scan:
        toolkit.get_action('scan_submit')(context, {'id': resource['id']})
    return resource


@toolkit.chained_action
def resource_update(up_func, context, data_dict):
    toolkit.check_access('resource_update', context, data_dict)
    # Data files uses the idenfiability field and should hide personal data
    # Attachment files do not use identifiability field and should not be hidden
    if data_dict.get('identifiability') == 'personally_identifiable' and data_dict.get('type') == 'data':
        data_dict['visibility'] = 'restricted'

    has_upload = data_dict.get('upload') is not None

    # ensure kobo_details are not missing
    old_resource = toolkit.get_action('resource_show')(context, {'id': data_dict['id']})
    data_dict['kobo_type'] = old_resource.get('kobo_type')
    data_dict['kobo_details'] = old_resource.get('kobo_details')

    if data_dict.get('kobo_type'):
        original_url = data_dict.pop('original_url', None)
        upload_changed = original_url and data_dict.get('url') != original_url
        # if the users try to change a "kobo data file" (extra) resource with a file,
        # we should raise an error
        if upload_changed:
            raise toolkit.ValidationError(
                {'data file': ['You cannot update a KoBoToolbox data file directly, please re-import the data instead']}
            )

    resource = up_func(context, data_dict)
    if has_upload:
        toolkit.get_action('scan_submit')(context, {'id': resource['id']})
    return resource


# Access Requests

def extract_keys_by_prefix(dct, prefix):
    return {
        k.replace(prefix, '', 1): v for k, v in dct.items() if k.startswith(prefix)
    }


def dictize_access_request(req):
    package = extract_keys_by_prefix(req, 'package_')
    group = extract_keys_by_prefix(req, 'group_')
    user = extract_keys_by_prefix(req, 'user_')
    access_request = extract_keys_by_prefix(req, 'access_requests_')
    access_request['user'] = user
    access_request['object'] = group if group['id'] else package

    if access_request['object_type'] == 'user':
        access_request['is_renewal'] = access_request['data'].get('user_request_type', USER_REQUEST_TYPE_NEW) == USER_REQUEST_TYPE_RENEWAL

    return access_request


@toolkit.side_effect_free
def access_request_list_for_user(context, data_dict):
    """
    Return a list of all access requests the user can see

    :param status: ``'requested'``, ``'approved'`` or ``'rejected'``
      (default: ``'requested'``)
    :type status: string

    :returns: A list of AccessRequest objects
    :rtype: list of dictionaries
    """
    m = context.get('model', model)
    user_id = toolkit.get_or_bust(context, "user")
    status = data_dict.get("status", "requested")
    if status not in ['requested', 'approved', 'rejected']:
        raise toolkit.ValidationError('Invalid status {}'.format(status))

    user = m.User.get(user_id)
    if not user:
        raise toolkit.ObjectNotFound("User not found")

    toolkit.check_access('access_request_list_for_user', context, data_dict)

    access_requests_table = m.meta.metadata.tables["access_requests"]
    group_table = m.meta.metadata.tables["group"]
    package_table = m.meta.metadata.tables["package"]
    user_table = m.meta.metadata.tables["user"]

    select_cols = (
        [c for c in access_requests_table.columns] +
        [c for c in group_table.columns] +
        [c for c in package_table.columns] +
        [
            c for c in user_table.columns
            if c.name != 'plugin_extras'
            and c.name != 'password'
            and c.name != 'apikey'
        ]
    )

    sql = select(
        select_cols, use_labels=True,
    ).select_from(
        access_requests_table.join(
            package_table,
            and_(
                access_requests_table.c.object_type == "package",
                access_requests_table.c.object_id == package_table.c.id,
            ), isouter=True,
        ).join(
            group_table,
            and_(
                access_requests_table.c.object_type == "organization",
                access_requests_table.c.object_id == group_table.c.id,
            ), isouter=True,
        ).join(
            user_table,
            access_requests_table.c.user_id == user_table.c.id
        )
    ).order_by(
        desc(access_requests_table.c.timestamp)
    ).where(
        access_requests_table.c.status == status
    )

    if user.sysadmin:
        return [dictize_access_request(req) for req in m.Session.execute(sql).fetchall()]

    organizations = toolkit.get_action("organization_list_for_user")(
        context, {"id": user_id, "permission": "admin"}
    )

    containers = [o["id"] for o in organizations]
    if not containers:
        return []

    sql = sql.where(
        or_(
            and_(
                access_requests_table.c.object_type == "package",
                package_table.c.owner_org.in_(containers),
            ),
            and_(
                access_requests_table.c.object_type == "organization",
                access_requests_table.c.object_id.in_(containers),
            ),
            and_(
                access_requests_table.c.object_type == "user",
                or_(
                    not_(access_requests_table.c.data.has_key("user_request_type")),
                    access_requests_table.c.data["user_request_type"].astext == USER_REQUEST_TYPE_NEW,
                ),
                access_requests_table.c.data["default_containers"].has_any(array(containers)),
            ),
            and_(
                access_requests_table.c.object_type == "user",
                access_requests_table.c.data["user_request_type"].astext == USER_REQUEST_TYPE_RENEWAL,
                access_requests_table.c.data.has_key("users_who_can_approve"),
                access_requests_table.c.data["users_who_can_approve"].contains([user.id]),
            )
        )
    )

    return [dictize_access_request(req) for req in m.Session.execute(sql).fetchall()]


def _validate_status(status):
    valid = ['approved', 'rejected']
    if status not in valid:
        raise toolkit.ValidationError("'status' must be one of {}".format(str(valid)))

def _validate_role(role):
    valid = ['member', 'editor', 'admin']
    if role not in valid:
        raise toolkit.ValidationError("'role' must be one of {}".format(str(valid)))

def _validate_object_type(object_type):
    valid = ['organization', 'package', 'user']
    if object_type not in valid:
        raise toolkit.ValidationError("'object_type' must be one of {}".format(str(valid)))

def _validate_data(data):
    try:
        json.dumps(data)
    except TypeError:
        raise toolkit.ValidationError("'data' must be JSON-serializable")

def access_request_update(context, data_dict):
    """
    Approve or reject a request for access to a container or dataset

    :param id: access request id
    :type id: string
    :param status: new status value ('approved', 'rejected')
    :type status: string
    """
    m = context.get('model', model)
    request_id = toolkit.get_or_bust(data_dict, "id")
    status = toolkit.get_or_bust(data_dict, "status")
    _validate_status(status)
    request = model.Session.query(AccessRequest).get(request_id)
    if not request:
        raise toolkit.ObjectNotFound("Access Request not found")

    if request.object_type not in ['organization', 'package', 'user']:
        raise toolkit.Invalid("Unknown Object Type")

    toolkit.check_access('access_request_update', context, data_dict)

    if request.object_type == 'package':
        _data_dict = {
            'id': request.object_id,
            'user_id': request.user_id,
            'capacity': request.role,
        }
        if status == 'approved':
            toolkit.get_action('package_collaborator_create')(
                context, _data_dict
            )
    elif request.object_type == 'organization':
        _data_dict = {
            'id': request.object_id,
            'username': request.user_id,
            'role': request.role,
        }
        if status == 'approved':
            toolkit.get_action('organization_member_create')(
                context, _data_dict
            )
    elif request.object_type == 'user':
        data = request.data
        state = {'approved':  m.State.ACTIVE, 'rejected': m.State.DELETED}[status]
        _data_dict = {'id': request.object_id, 'state': state}
        renew_expiry_date = data.get('user_request_type', USER_REQUEST_TYPE_NEW) == USER_REQUEST_TYPE_RENEWAL
        _data_dict['renew_expiry_date'] = renew_expiry_date

        user = toolkit.get_action('external_user_update_state')(
            context, _data_dict
        )

        if status == 'approved' and not renew_expiry_date:
            # Notify the user
            if data.get('user_request_type', USER_REQUEST_TYPE_NEW) == USER_REQUEST_TYPE_NEW:
                subj = mailer.compose_account_approved_email_subj()
                body = mailer.compose_account_approved_email_body(user)
                mailer.mail_user_by_id(user['id'], subj, body)

    request.status = status
    request.actioned_by = model.User.by_name(context['user']).id
    model.Session.commit()
    model.Session.refresh(request)

    return {
        col.name: getattr(request, col.name)
        for col in request.__table__.columns
    }


def access_request_create(context, data_dict):
    """
    Request access to a container or dataset

    :param object_id: uuid of the container or dataset we are requesting access to
    :type object_id: string
    :param object_type: type of object we are requesting access to
        ('organization', 'package', 'user')
    :type object_type: string
    :param message: user's message to the admin who will review the request
    :type message: string
    :param role: requested level of access ('member', 'editor', 'admin')
    :type role: string
    :param data: Optional dict containing any extra info to store about the request
        The dict must be JSON-serializable
    :type data: dict
    """
    m = context.get('model', model)
    user_id = toolkit.get_or_bust(context, "user")
    user = m.User.get(user_id)
    if not user:
        raise toolkit.ObjectNotFound("User not found")

    object_id, object_type, message, role = toolkit.get_or_bust(
        data_dict,
        ['object_id', 'object_type', 'message', 'role'],
    )
    data = data_dict.get('data', {})

    # Users could ask for new account but also to renewal and expired account
    if object_type == 'user':
        user_request_type = data.get('user_request_type')
        if user_request_type is None:
            # default is a new user asking for permission
            data['user_request_type'] = USER_REQUEST_TYPE_NEW
        elif user_request_type == USER_REQUEST_TYPE_RENEWAL:
            role = 'member'  # TODO role is not really to renew an user
        elif user_request_type != USER_REQUEST_TYPE_NEW:
            raise toolkit.ValidationError({'data': ["Invalid user request type"]})

    if not message:
        raise toolkit.ValidationError({'message': ["'message' is required"]})
    _validate_role(role)
    _validate_object_type(object_type)
    _validate_data(data)

    toolkit.check_access('access_request_create', context, data_dict)

    existing_request = model.Session.query(AccessRequest).filter(
        AccessRequest.user_id==user.id,
        AccessRequest.object_id==object_id,
        AccessRequest.object_type==object_type,
        AccessRequest.status=='requested'
    ).all()
    if existing_request:
        raise toolkit.ValidationError(
            "You've already submitted a request to access this {}.".format(object_type)
        )

    request = AccessRequest(
        user_id=user.id,
        object_id=object_id,
        object_type=object_type,
        message=message,
        role=role,
        data=data,
    )
    model.Session.add(request)
    if not context.get('defer_commit'):
        model.Session.commit()
        model.Session.refresh(request)
    else:
        model.Session.flush()

    return {
        col.name: getattr(request, col.name)
        for col in request.__table__.columns
    }


def external_user_update_state(context, data_dict):
    """
    Change the status of an external user
    This could be related with a new user or a renewal of an existing user
    datadict["renew_expiry_date"] indicates if is a new user
    If new user:
        Any internal user with container admin privileges or higher
        can change the status of another user when:
        - The target user is external
        - The target user's current status is 'pending'
    If renewal:
        Any internal user with container editor privileges or higher
        can change the status of another user when:
        - The target user is external
    Additionally, a sysadmin may change the status of another user at any time.

    :param id: The id or name of the target user
    :type id: string
    :param state: The new value of User.state
    :type state: string
    """
    m = context.get('model', model)
    renew_expiry_date = data_dict.get('renew_expiry_date', False)
    user_id, state = toolkit.get_or_bust(data_dict, ['id', 'state'])

    toolkit.check_access('external_user_update_state', context, data_dict)

    if state not in [m.State.ACTIVE, m.State.DELETED]:
        raise toolkit.ValidationError('Invalid state {}'.format(state))

    user_obj = m.User.get(user_id)
    if not user_obj:
        raise toolkit.ObjectNotFound("User not found")

    if state == m.State.ACTIVE:

        if renew_expiry_date:
            plugin_extras = _init_plugin_extras(user_obj.plugin_extras)
            days = toolkit.config.get('ckanext.unhcr.external_accounts_expiry_delta', 180)
            new_expiry_date = datetime.date.today() + datetime.timedelta(days)
            plugin_extras['unhcr']['expiry_date'] = new_expiry_date.isoformat()
            user_obj.plugin_extras = plugin_extras

    user_obj.state = state
    m.Session.commit()
    m.Session.refresh(user_obj)

    return model_dictize.user_dictize(user_obj, context)


# Admin

def user_update_sysadmin(context, data_dict):
    """
    Add or remove a sysadmin user
    An authenticated sysadmin can promote an existing user to sysadmin
    or remove sysadmins priveledges from a user who already has them

    :param id: The id or name of the user
    :type id: string
    :param is_sysadmin: The new value of User.sysadmin
    :type is_sysadmin: bool
    """
    m = context.get('model', model)
    user_id, is_sysadmin = toolkit.get_or_bust(data_dict, ['id', 'is_sysadmin'])
    is_sysadmin = toolkit.asbool(is_sysadmin)

    toolkit.check_access('user_update_sysadmin', context, data_dict)

    user_obj = m.User.get(user_id)
    if not user_obj:
        raise toolkit.ObjectNotFound("User not found")
    user_obj.sysadmin = is_sysadmin
    m.Session.commit()
    m.Session.refresh(user_obj)

    return model_dictize.user_dictize(user_obj, context)


def search_index_rebuild(context, data_dict):
    toolkit.check_access('search_index_rebuild', context, data_dict)

    package_ids = [
        r[0]
        for r in model.Session.query(model.Package.id)
        .filter(model.Package.state != "deleted")
        .all()
    ]
    package_index = index_for(model.Package)
    errors = []
    context = {'model': model, 'ignore_auth': True, 'validate': False, 'use_cache': False}
    for pkg_id in package_ids:
        try:
            package_index.update_dict(
                core_logic.get_action('package_show')(context, {'id': pkg_id}),
                defer_commit=True
            )
        except Exception as e:
            errors.append('Encountered {error} processing {pkg}'.format(
                error=repr(e),
                pkg=pkg_id
            ))

    commit()
    return errors


# Autocomplete

@core_logic.schema.validator_args
def unhcr_user_autocomplete_schema(
        not_missing,
        unicode_safe,
        ignore_missing,
        natural_number_validator,
        boolean_validator
    ):
    return {
        'q': [not_missing, unicode_safe],
        'ignore_self': [ignore_missing],
        'limit': [ignore_missing, natural_number_validator],
        'include_external': [ignore_missing, boolean_validator],
    }


@core_logic.validate(unhcr_user_autocomplete_schema)
def user_autocomplete(context, data_dict):
    '''Return a list of user names that contain a string.

    :param q: the string to search for
    :type q: string
    :param limit: the maximum number of user names to return (optional,
        default: ``20``)
    :type limit: int
    :param include_external: include external users in the output (optional,
        default: ``False``)
    :type include_external: bool

    :rtype: a list of user dictionaries each with keys ``'name'``,
        ``'fullname'``, and ``'id'``
    '''
    m = context.get('model', model)
    user = toolkit.get_or_bust(context, "user")
    include_external_users = data_dict.get('include_external', False)

    toolkit.check_access('user_autocomplete', context, data_dict)

    q = data_dict['q']
    limit = data_dict.get('limit', 20)
    ignore_self = data_dict.get('ignore_self', False)

    query = model.User.search(q)
    query = query.filter(model.User.state != model.State.DELETED)
    if not include_external_users:
        conditions = [
            model.User.email.ilike('%@{}'.format(domain))
            for domain in utils.get_internal_domains()
        ]
        query = query.filter(or_(*conditions))
    if ignore_self:
        query = query.filter(model.User.name != user)
    query = query.limit(limit)

    user_list = []
    for user in query.all():
        result_dict = {}
        for k in ['id', 'name', 'fullname']:
            result_dict[k] = getattr(user, k)

        user_list.append(result_dict)

    return user_list


# Geography

def _dictize_geography(geog, include_parents=True):
    dct = {k:v for k,v in geog.__dict__.items() if not k.startswith('_')}
    dct['name'] = geog.display_full_name
    dct['layer_nice_name'] = geog.layer_nice_name
    # ensure serializable for API calls
    for k, v in dct.items():
        if not v or type(v) in [str, int]:
            continue
        if type(v) in [datetime.date, datetime.datetime]:
            dct[k] = v.isoformat()
        else:
            dct[k] = str(v)
    if include_parents:
        dct['parents'] = [
            _dictize_geography(parent, include_parents=False)
            for parent in geog.parents
            ]

    return dct


@core_logic.schema.validator_args
def unhcr_geography_autocomplete_schema(
        not_missing,
        unicode_safe,
        ignore_missing,
        natural_number_validator,
    ):
    return {
        'q': [not_missing, unicode_safe],
        'limit': [ignore_missing, natural_number_validator],
    }


@core_logic.validate(unhcr_geography_autocomplete_schema)
def geography_autocomplete(context, data_dict):
    m = context.get('model', model)
    q = data_dict['q']
    limit = data_dict.get('limit', 100)

    toolkit.check_access('geography_autocomplete', context, data_dict)

    query = m.Session.query(
        Geography
    ).filter(
        or_(
            Geography.gis_name.ilike(f'%{q}%'),
            Geography.pcode.ilike(f'%{q}%')
        )
    ).filter(
        Geography.gis_status == GisStatus.ACTIVE
    ).order_by(
        Geography.layer,
        Geography.gis_name,
    ).limit(
        limit
    )

    # Ensure groups ordered
    groups = {v: [] for k, v in LAYER_TO_DISPLAY_NAME.items()}
    for geog in query.all():
        geo = _dictize_geography(geog)
        groups[geo['layer_nice_name']].append(geo)

    ret = []
    for group_name, elements in groups.items():
        if len(elements) > 0:
            ret.append({'name': group_name, 'children': elements})
    return ret


@toolkit.side_effect_free
def geography_show(context, data_dict):
    m = context.get('model', model)
    pcode = toolkit.get_or_bust(data_dict, "id")

    toolkit.check_access('geography_show', context, data_dict)

    geog = m.Session.query(Geography).get(pcode)
    if geog:
        return _dictize_geography(geog)

    raise toolkit.ObjectNotFound("Geography not found")


# User

@toolkit.chained_action
def user_list(up_func, context, data_dict):
    """ Appends 'external' field to each user if we ask for a list of dicts """
    users = up_func(context, data_dict)

    if context.get('return_query'):
        # users is a query, not a list of dicts
        return users

    if len(users) == 0:
        return []

    m = context.get('model', model)
    users_db = (
        m.Session.query(m.User)
        .filter(m.User.id.in_([u['id'] for u in users]))
        .all()
    )
    id_to_external = {u.id: u.external for u in users_db}
    for user in users:
        user['external'] = id_to_external[user['id']]

    return users


@toolkit.chained_action
def user_show(up_func, context, data_dict):
    user = up_func(context, data_dict)
    user_obj = _get_user_obj(context)
    user['external'] = user_obj.external

    plugin_extras = _init_plugin_extras(user_obj.plugin_extras)
    unhcr_extras = _validate_plugin_extras(plugin_extras['unhcr'])
    user['focal_point'] = unhcr_extras['focal_point']
    user['expiry_date'] = unhcr_extras['expiry_date']
    user['default_containers'] = unhcr_extras['default_containers']

    return user


@toolkit.chained_action
def user_delete(up_func, context, data_dict):

    # Upstream function will delete the user and all memberships
    # Before deleting memberships, consider which ones will orphan data containers
    model = context['model']
    user_id = data_dict['id']
    user_orgs = toolkit.get_action('organization_list_for_user')(
        {'ignore_auth': True},
        {'id': user_id}
    )
    user_admin_orgs = [org for org in user_orgs if org['capacity'] == 'admin']

    # All the memberships will be deleted in CKAN core
    # We only need to fix orphan containers here
    orgs_to_fix = []
    # Check 'admin' membership
    for org in user_admin_orgs:
        # get all admins for this group
        admins = get_group_or_org_admin_ids(org['id'])
        # check if is the only admin
        if len(admins) == 1:
            log.info('User {} is the last admin for {}'.format(user_id, org['id']))
            orgs_to_fix.append(org['id'])

    # Delete user and memberships
    up_func(context, data_dict)

    # If user is deleted without error we can fix the orphan memberships
    for org_id in orgs_to_fix:
        toolkit.enqueue_job(process_last_admin_on_delete, [org_id])


@toolkit.chained_action
def user_create(up_func, context, data_dict):
    user = up_func(context, data_dict)
    user_obj = _get_user_obj(context)

    if not user_obj.external:
        return user

    if not data_dict.get('focal_point'):
        raise toolkit.ValidationError({'focal_point': ["A focal point must be specified"]})

    if not isinstance(data_dict.get('default_containers'), list):
        raise toolkit.ValidationError({'default_containers': ["Specify one or more containers"]})

    if not data_dict.get('expiry_date'):
        expiry_date = datetime.date.today() + datetime.timedelta(
            days=toolkit.config.get(
                'ckanext.unhcr.external_accounts_expiry_delta',
                180  # six months-ish
            )
        )
    else:
        expiry_date = data_dict.get('expiry_date')

    plugin_extras = _init_plugin_extras(user_obj.plugin_extras)
    plugin_extras['unhcr']['expiry_date'] = expiry_date.isoformat()
    plugin_extras['unhcr']['focal_point'] = data_dict['focal_point']
    plugin_extras['unhcr']['default_containers'] = data_dict['default_containers']
    user_obj.plugin_extras = plugin_extras

    if not context.get('defer_commit'):
        m = context.get('model', model)
        model.Session.commit()

    user['expiry_date'] = plugin_extras['unhcr']['expiry_date']
    user['focal_point'] = plugin_extras['unhcr']['focal_point']
    user['default_containers'] = plugin_extras['unhcr']['default_containers']
    return user


@toolkit.chained_action
def user_update(up_func, context, data_dict):

    if not context.get('ignore_auth'):
        user_id = toolkit.get_or_bust(data_dict, 'id')
        m = context.get('model', model)
        user_obj = m.User.get(user_id)

        if user_obj is not None and is_saml2_user(user_obj):
            # Only allow to change apiKey or kobo_token
            up_dict = toolkit.get_action('user_show')(context, {'id': user_id})

            new_api_key = data_dict.get('apikey')
            apikey_changed = new_api_key and data_dict.get('apikey') and user_obj.apikey != new_api_key
            if apikey_changed:
                up_dict['apikey'] = data_dict.get('apikey')

            plugin_extras = {} if user_obj.plugin_extras is None else user_obj.plugin_extras
            old_kobo_token = plugin_extras.get('unhcr', {}).get('kobo_token')
            new_kobo_token = data_dict.get('plugin_extras', {}).get('unhcr', {}).get('kobo_token')
            kobo_token_changed = new_kobo_token and old_kobo_token != new_kobo_token

            if kobo_token_changed:

                up_dict['plugin_extras'] = copy.deepcopy(plugin_extras)
                if 'unhcr' not in up_dict['plugin_extras']:
                    up_dict['plugin_extras']['unhcr'] = {}

                if new_kobo_token == 'REMOVE':
                    del up_dict['plugin_extras']['unhcr']['kobo_token']
                else:
                    if context.get('validate_token', True):
                        # check if the token is valid
                        kobo_url = toolkit.config.get('ckanext.unhcr.kobo_url', 'https://kobo.unhcr.org')
                        kobo = KoBoAPI(new_kobo_token, kobo_url)
                        if not kobo.test_token():
                            raise toolkit.ValidationError({'kobo_token': [
                                "KoBoToolbox token is not valid"
                            ]})
                    up_dict['plugin_extras']['unhcr']['kobo_token'] = new_kobo_token

            if apikey_changed or kobo_token_changed:
                site_user = toolkit.get_action(u'get_site_user')({u'ignore_auth': True}, {})
                context['user'] = site_user['name']
                return up_func(context, up_dict)

            raise toolkit.ValidationError({'error': [
                "User accounts managed by Single Sign-On can't be modified"
            ]})

    return up_func(context, data_dict)


def _init_plugin_extras(plugin_extras):
    out_dict = copy.deepcopy(plugin_extras)
    if not out_dict:
        out_dict = {}
    if 'unhcr' not in out_dict:
        out_dict['unhcr'] = {}
    return out_dict


def _validate_plugin_extras(extras):
    CUSTOM_FIELDS = [
        {'name': 'focal_point', 'default': ''},
        {'name': 'expiry_date', 'default': None},
        {'name': 'default_containers',  'default': []},
    ]
    if not extras:
        extras = {}
    out_dict = {}
    for field in CUSTOM_FIELDS:
        out_dict[field['name']] = extras.get(field['name'], field['default'])
    return out_dict


@toolkit.chained_action
def datastore_create(up_func, context, data_dict):
    """ fix bad fields names (usually from KoBo)
        Datastore do not allow _ before field names and
        kobo uses the _id field for any record
        """

    if data_dict.get('fields'):
        prefix = 'kobo'
        new_fields = []
        for field in data_dict.get('fields'):
            if field['id'].startswith('_'):
                new_field_name = '{}{}'.format(prefix, field['id'])
                log.warn('Datastore field name starts with _: %s, replaced as %s', field['id'], new_field_name)
                field['id'] = new_field_name
            new_fields.append(field)
        data_dict['fields'] = new_fields

        if data_dict.get('records'):
            new_records = []
            for record in data_dict.get('records'):
                new_record = {}
                for field, value in record.items():
                    if field.startswith('_'):
                        new_record['{}{}'.format(prefix, field)] = value
                    else:
                        new_record[field] = record[field]
                new_records.append(new_record)
            data_dict['records'] = new_records

    return up_func(context, data_dict)
