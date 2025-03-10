# -*- coding: utf-8 -*-

from flask import Blueprint
from ckan import model
import ckan.plugins.toolkit as toolkit
from ckanext.unhcr.mailer import notify_rejection
from ckanext.unhcr.utils import require_user


unhcr_access_requests_blueprint = Blueprint(
    'unhcr_access_requests',
    __name__,
    url_prefix=u'/access-requests'
)


@require_user
def approve(request_id):
    try:
        toolkit.get_action('access_request_update')(
            {'user': toolkit.c.user}, {'id': request_id, 'status': 'approved'}
        )
    except toolkit.ObjectNotFound as e:
        return toolkit.abort(404, toolkit._(str(e)))
    except toolkit.NotAuthorized:
        return toolkit.abort(403, toolkit._(u'Not Authorized to approve this request'))

    toolkit.h.flash_success('Access Request Approved')

    return toolkit.redirect_to('unhcr_dashboard.requests')


@require_user
def reject(request_id):
    message = toolkit.request.form.get('message')
    if not message:
        return toolkit.abort(400, "'message' is required")

    try:
        request = toolkit.get_action('access_request_update')(
            {'user': toolkit.c.user}, {'id': request_id, 'status': 'rejected'}
        )

        notify_rejection(request, message)

    except toolkit.ObjectNotFound as e:
        return toolkit.abort(404, toolkit._(str(e)))
    except toolkit.NotAuthorized:
        return toolkit.abort(403, toolkit._(u'Not Authorized to reject this request'))

    toolkit.h.flash_success('Access Request Rejected')

    return toolkit.redirect_to('unhcr_dashboard.requests')


unhcr_access_requests_blueprint.add_url_rule(
    rule=u'/approve/<request_id>',
    view_func=approve,
    methods=['POST']
)

unhcr_access_requests_blueprint.add_url_rule(
    rule=u'/reject/<request_id>',
    view_func=reject,
    methods=['POST']
)
