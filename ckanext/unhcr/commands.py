""" Command helpers """
import datetime
import logging
from dateutil.parser import parse as parse_date
from ckan import model
from ckan.plugins import toolkit
from ckanext.unhcr.models import AccessRequest, USER_REQUEST_TYPE_RENEWAL
from ckanext.unhcr.helpers import get_user_curators, get_user_admins
from ckanext.unhcr.mailer import notify_renewal_request


log = logging.getLogger(__name__)


def expired_users_list(before_expire_days=None, include_activities=False):
    """ Get as list of expired (or about to expire) users and their activities """
    ctx = {'ignore_auth': True}
    users = toolkit.get_action('user_list')(ctx, {})
    expired_users = []

    # check expiry_date
    for user in users:
        if not user['external']:
            # we only expire external users
            continue
        full_user = toolkit.get_action('user_show')(ctx,  {'id': user['id']})
        if full_user['expiry_date']:
            try:
                expiry_date = parse_date(full_user['expiry_date'])
            except Exception:
                log.error('Bad expiry_date: {}'.format(full_user['expiry_date']))
                continue

            now = datetime.datetime.utcnow()
            if before_expire_days is None:
                # looking for really expired users
                add_to_list = now > expiry_date
            else:
                # users about to expire
                add_to_list = now < expiry_date and now > expiry_date - datetime.timedelta(days=before_expire_days)

            if add_to_list:
                if include_activities:
                    full_user['activities'] = toolkit.get_action('user_activity_list')(ctx, {'id': user['id']})
                expired_users.append(full_user)

    return expired_users


def request_renewal(user_dict, last_activity):
    """ Request for users account renewal.
        Returns tuple:
         - created: bool. Was the request created?
         - reason: None or string. If created=False is the reason why the request was not created
    """
    # check if the request was already exists
    previous_requests = model.Session.query(AccessRequest).filter(
        AccessRequest.object_id == user_dict['id'],
        AccessRequest.object_type == 'user',
        AccessRequest.status == 'requested'
    ).all()

    if previous_requests:
        return False, 'The request already exists'

    data = {
        'user_name': user_dict['name'],
        'last_activity': last_activity.get('activity_type', 'No activities found'),
        'last_date': last_activity.get('timestamp'),
        'expire_date': parse_date(user_dict['expiry_date']).strftime('%c')
    }
    if data['last_date'] is None:
        data['last_date'] = 'Undefined'
    else:
        data['last_date'] = parse_date(data['last_date']).strftime('%c')

    message = 'User %(user_name)s will expire on %(expire_date)s. Should this user be renewed? ' \
              'Last activity: "%(last_activity)s" registered on %(last_date)s' % data

    context = {'user': user_dict['id'], 'ignore_auth': True}

    users_who_can_approve = get_user_curators(user_dict['id']) + get_user_admins(user_dict['id'])

    toolkit.get_action('access_request_create')(
        context, {
            'object_id': user_dict['id'],
            'object_type': 'user',
            'message': message,
            'role': 'member',  # this is only required to fit the schema
            'data': {
                'user_request_type': USER_REQUEST_TYPE_RENEWAL,
                'users_who_can_approve': users_who_can_approve,
            }
        }
    )

    # Notify related users to approve/reject this request
    notify_renewal_request(user_id=user_dict['id'], message=message, recipient_ids=users_who_can_approve)

    return True, None
