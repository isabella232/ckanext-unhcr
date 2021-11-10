# -*- coding: utf-8 -*-

from flask import Blueprint
import ckan.model as model
import ckan.plugins.toolkit as toolkit
from ckanext.unhcr.utils import require_user


unhcr_system_activities_blueprint = Blueprint(
    'unhcr_system_activities',
    __name__,
    url_prefix=u'/ckan-admin/system_activities'
)


@require_user
def index():
    try:
        toolkit.check_access('sysadmin', {'user': toolkit.c.user})
    except toolkit.NotAuthorized:
        return toolkit.abort(403, 'Not authorized to manage search index')

    return toolkit.render('admin/system_activities.html')


unhcr_system_activities_blueprint.add_url_rule(
    rule=u'/',
    view_func=index,
    methods=['GET',],
    strict_slashes=False,
)
