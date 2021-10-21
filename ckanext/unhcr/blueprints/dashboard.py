# -*- coding: utf-8 -*-

import logging
from flask import Blueprint
from ckan import model
from ckan.views.user import _extra_template_variables
import ckan.plugins.toolkit as toolkit
from ckanext.unhcr import helpers
from ckanext.unhcr.utils import require_user


log = logging.getLogger(__name__)


unhcr_dashboard_blueprint = Blueprint('unhcr_dashboard', __name__, url_prefix=u'/dashboard')


@require_user
def requests():
    if not helpers.user_is_container_admin() and not toolkit.c.userobj.sysadmin:
        return toolkit.abort(403, "Forbidden")

    context = {'model': model, 'user': toolkit.c.user}

    try:
        new_container_requests = toolkit.get_action('container_request_list')(
            context, {'all_fields': True}
        )
    except (toolkit.NotAuthorized, toolkit.ObjectNotFound):
        new_container_requests = []

    try:
        access_requests = toolkit.get_action('access_request_list_for_user')(
            context, {}
        )
    except (toolkit.NotAuthorized, toolkit.ObjectNotFound):
        access_requests = []

    container_access_requests = [
        req for req in access_requests if req['object_type'] == 'organization'
    ]
    dataset_access_requests = [
        req for req in access_requests if req['object_type'] == 'package'
    ]
    user_account_requests = [
        req for req in access_requests
        if req['object_type'] == 'user' and not req['is_renewal']
    ]
    user_renewal_requests = [
        req for req in access_requests
        if req['object_type'] == 'user' and req['is_renewal']
    ]

    context = {
        'model': model,
        'session': model.Session,
        'user': toolkit.c.user,
        'auth_user_obj': toolkit.c.userobj,
        'for_view': True,
    }

    template_vars = _extra_template_variables(
        context,
        {'id': toolkit.c.userobj.id, 'user_obj': toolkit.c.userobj, 'offset': 0}
    )

    template_vars['new_container_requests'] = new_container_requests
    template_vars['container_access_requests'] = container_access_requests
    template_vars['dataset_access_requests'] = dataset_access_requests
    template_vars['user_account_requests'] = user_account_requests
    template_vars['user_renewal_requests'] = user_renewal_requests

    extras_user_access_request = {}
    for uar in user_account_requests + user_renewal_requests:
        # access_request_list_for_user removes plugin_extras where focal-point lives
        user_obj = model.User.get(uar['user_id'])
        focal_point = user_obj.plugin_extras.get('unhcr', {}).get('focal_point')
        default_containers = user_obj.plugin_extras.get('unhcr', {}).get('default_containers', [])

        containers = [
            model.Group.get(container_id)
            for container_id in default_containers
        ]
        cleaned_containers = [container for container in containers if container and container.name != 'data-deposit']

        extras = {
            'default_containers': cleaned_containers,
            'focal_point': focal_point
        }
        extras_user_access_request[uar['id']] = extras

    template_vars['extras_user_access_request'] = extras_user_access_request

    return toolkit.render('user/dashboard_requests.html', template_vars)


unhcr_dashboard_blueprint.add_url_rule(
    u'/requests',
    view_func=requests
)
