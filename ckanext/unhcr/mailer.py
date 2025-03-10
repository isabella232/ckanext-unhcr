# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
import itertools
import logging
from ckan import model
from ckan.plugins import toolkit
from ckan.lib import jinja_extensions
from ckan.lib import mailer as core_mailer
from ckan.lib.dictization import model_dictize
from ckanext.unhcr import helpers
from ckanext.unhcr.models import USER_REQUEST_TYPE_RENEWAL


log = logging.getLogger(__name__)


def render_jinja2(template_name, extra_vars):
    env = jinja_extensions.Environment(
        **jinja_extensions.get_jinja_env_options()
    )
    template = env.get_template(template_name)
    return template.render(**extra_vars)


# General

def mail_user(user, subj, body, headers={}):
    try:
        headers.setdefault('Content-Type', 'text/html; charset=UTF-8')
        core_mailer.mail_user(user, subj, body, headers=headers)
    except Exception as exception:
        log.exception(exception)


def mail_user_by_id(user_id, subj, body, headers={}):
    user = model.User.get(user_id)
    return mail_user(user, subj, body, headers=headers)


def get_base_context():
    context = {
        'site_title': toolkit.config.get('ckan.site_title'),
        'site_url': toolkit.config.get('ckan.site_url'),
    }
    return context


# Data Container

def compose_container_email_subj(container, event):
    return '[UNHCR RIDL] Data Container %s: %s' % (event.capitalize(), container['title'])


def compose_container_email_body(container, user, event):
    context = get_base_context()
    context['recipient'] = user.display_name
    context['container'] = container
    context['container_url'] = toolkit.url_for('data-container.read', id=container['name'], qualified=True)
    return render_jinja2('emails/container/%s.html' % event, context)


def compose_request_container_email_body(container, recipient, requesting_user):
    context = get_base_context()
    context['recipient'] = recipient.display_name
    context['container'] = container
    context['container_url'] = toolkit.url_for('data-container.read', id=container['name'], qualified=True)
    context['requesting_user'] = requesting_user
    context['h'] = toolkit.h
    return render_jinja2('emails/container/request.html', context)


# Data Deposit

def compose_curation_email_subj(dataset):
    return '[UNHCR RIDL] Curation: %s' % dataset.get('title')


def compose_curation_email_body(dataset, curation, recipient, event, message=None):
    context = get_base_context()
    context['recipient'] = recipient
    context['dataset'] = dataset
    context['dataset_url'] = toolkit.url_for(
        dataset['type'] + '.read',
        id=dataset['name'],
        qualified=True
    )
    context['curation'] = curation
    context['message'] = message
    return render_jinja2('emails/curation/%s.html' % event, context)


# Membership

def compose_membership_email_subj(container):
    return '[UNHCR RIDL] Membership: %s' % container.get('title')


def compose_membership_email_body(container, user_dict, event, extra_mail_msg=None):
    context = get_base_context()
    context['recipient'] = user_dict.get('fullname') or user_dict.get('name')
    context['container'] = container
    context['extra_mail_msg'] = extra_mail_msg

    # single
    if isinstance(container, dict):
        context['container_url'] = toolkit.url_for('data-container.read', id=container['name'], qualified=True)
    # multiple
    else:
        for item in container:
            item['url'] = toolkit.url_for('data-container.read', id=item['name'], qualified=True)
        context['container_url'] = toolkit.url_for('data-container.index', qualified=True)
    return render_jinja2('emails/membership/%s.html' % event, context)


# Weekly Summary

def _get_new_packages(context, start_time):
    data_dict = {
        'q': '*:*',
        'fq': (
            '-type:deposited-dataset AND ' +\
            'metadata_created:[{} TO NOW]'.format(start_time)
        ),
        'sort': 'metadata_created desc',
        'include_private': True,
    }
    query = toolkit.get_action('package_search')(context, data_dict)
    packages = query['results']

    for package in packages:
        group = model.Group.get(package['organization']['id'])
        parents = group.get_parent_group_hierarchy(type='data-container')
        if not parents:
            root_parent = group
        else:
            root_parent = parents[0]
        package['root_parent'] = root_parent

    packages = sorted(packages, key=lambda x: x['root_parent'].id)
    grouped_packages = itertools.groupby(packages, lambda x: x['root_parent'])

    return [
        {"container": container, "datasets": list(packages)}
        for container, packages in grouped_packages
    ]


def _get_new_deposits(context, start_time):
    data_dict = {
        'q': '*:*',
        'fq': (
            'type:deposited-dataset AND ' +\
            '-curation_state:review AND ' +\
            'metadata_created:[{} TO NOW]'.format(start_time)
        ),
        'sort': 'metadata_created desc',
        'include_private': True,
    }
    packages = toolkit.get_action('package_search')(context, data_dict)
    return packages['results']


def _get_deposits_awaiting_review(context, start_time):
    data_dict = {
        'q': '*:*',
        'fq': (
            'type:deposited-dataset AND ' +\
            'curation_state:review AND ' +\
            'metadata_created:[{} TO NOW]'.format(start_time)
        ),
        'sort': 'metadata_created desc',
        'include_private': True,
    }
    packages = toolkit.get_action('package_search')(context, data_dict)
    return packages['results']


def compose_summary_email_body(user_dict):
    context = get_base_context()

    start_time = datetime.now() - timedelta(days=7)
    context['start_date'] = start_time.strftime('%A %B %e %Y')
    query_start_time = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    context['recipient'] = user_dict.get('fullname') or user_dict.get('name')
    context['datasets_url'] = toolkit.url_for(
        'search',
        q=(
            '-type:deposited-dataset AND ' +\
            'metadata_created:[{} TO NOW]'.format(query_start_time)
        ),
        sort='metadata_created desc',
        qualified=True
    )
    context['deposits_url'] = toolkit.url_for(
        'search',
        q=(
            'type:deposited-dataset AND ' +\
            'metadata_created:[{} TO NOW]'.format(query_start_time)
        ),
        sort='metadata_created desc',
        qualified=True
    )

    action_context = { 'user': user_dict['name'] }
    context['new_datasets'] = _get_new_packages(action_context, query_start_time)
    context['new_datasets_total'] = sum([len(n['datasets']) for n in context['new_datasets']])
    context['new_deposits'] = _get_new_deposits(action_context, query_start_time)
    context['new_deposits_total'] = len(context['new_deposits'])
    context['awaiting_review'] = _get_deposits_awaiting_review(
        action_context,
        query_start_time
    )
    context['awaiting_review_total'] = len(context['awaiting_review'])

    context['h'] = toolkit.h

    return {
        'total_events': (
            context['new_datasets_total'] +\
            context['new_deposits_total'] +\
            context['awaiting_review_total']
        ),
        'body': render_jinja2('emails/curation/summary.html', context)
    }


def get_summary_email_recipients():
    # summary emails are sent to sysadmins
    # and members of the curation team
    recipients = []

    deposit_group = helpers.get_data_deposit()
    curators = toolkit.get_action('member_list')(
        {'ignore_auth': True},
        {'id': deposit_group['id']}
    )
    curator_ids = [c[0] for c in curators]

    all_users = toolkit.get_action('user_list')({ 'ignore_auth': True, 'keep_email': True }, {})
    default_user = toolkit.get_action('get_site_user')({ 'ignore_auth': True })

    for user in all_users:
        if user['name'] == default_user['name']:
            continue
        if user['sysadmin'] or user['id'] in curator_ids:
            recipients.append(user)

    return recipients


# Access Requests

def _get_sysadmins():
    context = {"ignore_auth": True, "model": model}
    sysadmins = helpers.get_valid_sysadmins()
    return [model_dictize.user_dictize(user, context) for user in sysadmins]


def get_container_request_access_email_recipients(container_dict):
    context = {"ignore_auth": True}
    default_user = toolkit.get_action("get_site_user")(context)

    try:
        data_dict = {"id": container_dict["id"], "include_users": True}
        org = toolkit.get_action("organization_show")(context, data_dict)
        recipients = [
            user for user in org["users"]
            if user["capacity"] == "admin" and user["name"] != default_user["name"]
        ]
        for user in recipients:
            user.pop("capacity")
    except toolkit.ObjectNotFound:
        recipients = []

    # if we couldn't find any org admins, fall back to sysadmins
    if not recipients:
        recipients = _get_sysadmins()

    return recipients


def get_dataset_request_access_email_recipients(package_dict):
    return get_container_request_access_email_recipients({"id": package_dict["owner_org"]})


def get_user_account_request_access_email_recipients(containers):
    # This email is sent to admins of all containers in `containers` arg plus sysadmins
    recipients = _get_sysadmins()
    for container in containers:
        recipients = recipients + get_container_request_access_email_recipients(
            {"id": container}
        )
    for user in recipients:
        user.pop('default_containers', None)
    recipients = [
        dict(tup) for tup in {tuple(sorted(r.items())) for r in recipients}
    ]  # de-dupe
    return recipients


def compose_dataset_request_access_email_subj(package_dict):
    return '[UNHCR RIDL] - Request for access to dataset: "{}"'.format(
        package_dict['name']
    )


def compose_container_request_access_email_subj(container_dict):
    return '[UNHCR RIDL] - Request for access to container: "{}"'.format(
        container_dict['display_name']
    )


def compose_user_request_access_email_subj():
    return '[UNHCR RIDL] - Request for new user account'


def compose_request_access_email_body(object_type, recipient, obj, requesting_user, message):
    context = get_base_context()
    context['object_type'] = object_type
    context['recipient'] = recipient
    context['object'] = obj
    context['requesting_user'] = requesting_user
    context['message'] = message
    context['dashboard_url'] = toolkit.url_for(
        'unhcr_dashboard.requests',
        qualified=True,
    )
    context['h'] = toolkit.h

    # include default_containers names for user requests
    if object_type == 'user':
        containers = [
            model.Group.get(container_id)
            for container_id in obj['default_containers']
        ]
        container_titles = [container.title for container in containers if container and container.name != 'data-deposit']
        obj['container_titles'] = container_titles

    return render_jinja2('emails/access_requests/access_request.html', context)


def compose_request_rejected_email_subj(obj):
    return '[UNHCR RIDL] - Request for access to: "{}"'.format(obj['name'])


def compose_request_rejected_email_body(object_type, recipient, obj, message):
    context = get_base_context()
    context['object_type'] = object_type
    context['recipient'] = recipient
    context['object'] = obj
    context['message'] = message
    context['h'] = toolkit.h

    return render_jinja2('emails/access_requests/rejection.html', context)


def compose_account_approved_email_subj():
    return '[UNHCR RIDL] - User account approved'


def compose_account_approved_email_body(recipient):
    context = get_base_context()
    context['recipient'] = recipient
    context['login_url'] = toolkit.url_for('user.login', _external=True)
    context['h'] = toolkit.h

    return render_jinja2('emails/user/account_approved.html', context)


def notify_renewal_request(user_id, message, recipient_ids):
    """ A user require to renew their account.
        Ask all related related users to validate this request """

    user = model.User.get(user_id)
    subj = 'Renewal request for {}'.format(user.name)
    context = {
        'requesting_user': user,
        'message': message,
        'h': toolkit.h
    }

    if recipient_ids == []:
        recipient_ids = [sysadmin['id'] for sysadmin in _get_sysadmins()]
    for recipient_id in recipient_ids:
        recipient = model.User.get(recipient_id)
        context['recipient'] = recipient
        body = render_jinja2('emails/access_requests/access_renewal_request.html', context)
        toolkit.enqueue_job(mail_user_by_id, [recipient_id, subj, body], title="notify_renewal_request")

    return recipient_ids


def notify_rejection(request, message):
    recipient = model.User.get(request['user_id'])
    obj = toolkit.get_action('{}_show'.format(request['object_type']))(
        {'user': toolkit.c.user}, {'id': request['object_id']}
    )
    if request['object_type'] == 'user':
        if request['data'].get('user_request_type') == USER_REQUEST_TYPE_RENEWAL:
            # we don't notify renewal rejections
            return
        subj = '[UNHCR RIDL] - User account rejected'
    else:
        subj = compose_request_rejected_email_subj(obj)
    body = compose_request_rejected_email_body(request['object_type'], recipient, obj, message)
    mail_user_by_id(recipient.name, subj, body)


# Clam AV Scan


def get_infected_file_email_recipients():
    return _get_sysadmins()


def compose_infected_file_email_subj():
    return '[UNHCR RIDL] - Infected file found'


def compose_infected_file_email_body(recipient, resource_name, package_id, resource_id, clamav_report):
    context = get_base_context()

    context['recipient'] = recipient
    context['resource_name'] = resource_name
    context['resource_url'] = toolkit.url_for(
        'resource.read',
        id=package_id,
        resource_id=resource_id,
        qualified=True
    )
    context['clamav_report'] = clamav_report
    context['h'] = toolkit.h

    return render_jinja2('emails/resource/infected_file.html', context)


# Collaborators

def _compose_collaborator_email_subj(dataset):
    return u'{0} - Notification about collaborator role for {1}'.format(
        toolkit.config.get('ckan.site_title'), dataset.title)


def _compose_collaborator_email_body(user, dataset, role, event):
    dataset_link = toolkit.url_for('dataset.read', id=dataset.id, qualified=True)
    context = get_base_context()
    context.update({
        'user_name': user.fullname or user.name,
        'role': role,
        'dataset_title': dataset.title,
        'dataset_link': dataset_link
    })
    return render_jinja2(
        'collaborators/emails/{0}_collaborator.html'.format(event),
        context)


def mail_notification_to_collaborator(dataset_id, user_id, capacity, event):
    user = model.User.get(user_id)
    dataset = model.Package.get(dataset_id)

    try:
        subj = _compose_collaborator_email_subj(dataset)
        body = _compose_collaborator_email_body(user, dataset, capacity, event)
        core_mailer.mail_user(user, subj, body, headers={
            'Content-Type': 'text/html; charset=UTF-8'
        })
    except core_mailer.MailerException as exception:
        log.exception(exception)
