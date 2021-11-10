from ckan import model
import ckan.plugins.toolkit as toolkit


def create_download_activity(context, resource_id):
    """
    Log a 'resource download' activity in the activity stream
    """
    user = context['user']
    user_id = None
    user_by_name = model.User.by_name(user)
    if user_by_name is not None:
        user_id = user_by_name.id

    resource = toolkit.get_action('resource_show')(context.copy(), {'id': resource_id})

    activity_dict = {
        'activity_type': 'download resource',
        'user_id': user_id,
        'object_id': resource['package_id'],
        'data': resource
    }

    activity_create_context = {
        'model': model,
        'user': user_id or user,
        'defer_commit': False,
        'ignore_auth': True,
    }

    create_activity = toolkit.get_action('activity_create')
    create_activity(activity_create_context, activity_dict)


def create_curation_activity(
        activity_type, dataset_id, dataset_name, user_id,
        message=None, **kwargs):
    """
    Log a 'changed curation state' activity in the activity stream
    """
    activity_context = {'ignore_auth': True}
    data_dict = {
        'user_id': user_id,
        'object_id': dataset_id,
        'activity_type': 'changed curation state',
        'data': {
            'curation_activity': activity_type,
            'package': {'name': dataset_name, 'id': dataset_id},
        }
    }
    if message:
        data_dict['data']['message'] = message
    if kwargs:
        for key, value in kwargs.items():
            data_dict['data'][key] = value

    return toolkit.get_action('activity_create')(activity_context, data_dict)


def create_system_activity(title, description, extra_data={}):
    """
    Log a System level activity
    """
    site_user = toolkit.get_action('get_site_user')({'ignore_auth': True}, {})
    context = {'user': site_user['name'], 'ignore_auth': True}

    data = {
        'title': title,
        'description': description,
        'extras': extra_data
    }
    activity_dict = {
        'activity_type': 'system activity',
        'user_id': site_user['name'],
        'object_id': '0',
        'data': data
    }

    create_activity = toolkit.get_action('activity_create')
    activity = create_activity(context, activity_dict)
    return activity
