from flask import Blueprint
from ckan import model
import ckan.plugins.toolkit as toolkit
from ckanext.unhcr.utils import require_editor_user
from ckanext.unhcr.kobo.api import KoBoAPI
from ckanext.unhcr.kobo.exceptions import KoboApiError
from ckanext.unhcr.kobo.kobo_dataset import KoboDataset


unhcr_kobo_blueprint = Blueprint(
    'unhcr_kobo',
    __name__,
    url_prefix=u'/kobo'
)


@require_editor_user
def index():
    user_obj = toolkit.c.userobj
    plugin_extras = {} if user_obj.plugin_extras is None else user_obj.plugin_extras
    kobo_token = plugin_extras.get('unhcr', {}).get('kobo_token')
    extra_vars = {
        'kobo_token': kobo_token
    }
    return toolkit.render('kobo/index.html', extra_vars)


@require_editor_user
def update_token():
    """ POST a new token """
    user_obj = toolkit.c.userobj

    token = toolkit.request.form.get('kobo_token')
    if not token:
        message = 'Missing KoBo token.'
        toolkit.h.flash_error(message)
        return toolkit.redirect_to('unhcr_kobo.index')
    plugin_extras = {} if user_obj.plugin_extras is None else user_obj.plugin_extras
    old_token = plugin_extras.get('unhcr', {}).get('kobo_token')

    if token != old_token:
        try:
            toolkit.get_action('user_update')(
                {'user': user_obj.name, 'validate_token': not token.startswith('test_')},
                {'id': user_obj.id, 'plugin_extras': {'unhcr':  {'kobo_token': token}}}
            )
        except toolkit.ValidationError as e:
            if e.error_dict and 'kobo_token' in e.error_dict:
                message = 'Invalid KoBo token. Please try again.'
            else:
                message = 'Unknown KoBo token error: {}.'.format(e)
            toolkit.h.flash_error(message)
            return toolkit.redirect_to('unhcr_kobo.index')

    return toolkit.redirect_to('unhcr_kobo.kobo_surveys')


@require_editor_user
def remove_token():
    """ Delete existing KoBo token """
    user_obj = toolkit.c.userobj

    try:
        toolkit.get_action('user_update')(
            {'user': user_obj.name},
            {'id': user_obj.id, 'plugin_extras': {'unhcr':  {'kobo_token': 'REMOVE'}}}
        )
    except toolkit.ValidationError as e:
        message = 'Error removing token: {}.'.format(e)
        toolkit.h.flash_error(message)

    return toolkit.redirect_to('unhcr_kobo.index')


@require_editor_user
def kobo_surveys():
    """ KoBo surveys page """
    user_obj = toolkit.c.userobj

    plugin_extras = {} if user_obj.plugin_extras is None else user_obj.plugin_extras
    token = plugin_extras.get('unhcr', {}).get('kobo_token')

    # check if the token is valid
    kobo_url = toolkit.config.get('ckanext.unhcr.kobo_url', 'https://kobo.unhcr.org')
    kobo = KoBoAPI(token, kobo_url)

    try:
        surveys = kobo.get_surveys()
    except KoboApiError as e:
        message = 'Unexpected KoBo error getting surveys: {}'.format(e)
        toolkit.h.flash_error(message)
        return toolkit.redirect_to('unhcr_kobo.index')

    for survey in surveys:
        survey['ridl_package'] = KoboDataset(survey['uid']).get_package(raise_multiple_error=False)

    extra_vars = {
        'surveys': surveys,
    }
    return toolkit.render('kobo/surveys.html', extra_vars)


unhcr_kobo_blueprint.add_url_rule(
    rule=u'/',
    view_func=index,
    methods=['GET'],
    strict_slashes=False,
)

unhcr_kobo_blueprint.add_url_rule(
    rule=u'/update-token',
    view_func=update_token,
    methods=['POST'],
    strict_slashes=False,
)

unhcr_kobo_blueprint.add_url_rule(
    rule=u'/remove-token',
    view_func=remove_token,
    methods=['POST'],
    strict_slashes=False,
)

unhcr_kobo_blueprint.add_url_rule(
    rule=u'/surveys',
    view_func=kobo_surveys,
    methods=['GET'],
    strict_slashes=False,
)
