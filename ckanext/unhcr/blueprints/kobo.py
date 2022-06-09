import copy
from flask import Blueprint, make_response
import ckan.plugins.toolkit as toolkit
from ckanext.unhcr.utils import require_editor_user
from ckanext.unhcr.jobs import update_pkg_kobo_resources, update_kobo_resource
from ckanext.unhcr.kobo.api import KoBoAPI, KoBoSurvey
from ckanext.unhcr.kobo.exceptions import KoboApiError, KoboMissingAssetIdError, KoBoUserTokenMissingError
from ckanext.unhcr.kobo.kobo_dataset import KoboDataset


unhcr_kobo_blueprint = Blueprint(
    'unhcr_kobo',
    __name__,
    url_prefix=u'/kobo'
)


def _make_json_response(msg=None, status_int=200, extra_headers={}, error_msg=None, extra_data={}):

    ok = error_msg is None
    data = {"ok": ok}
    if error_msg:
        data["error"] = error_msg
    else:
        data["message"] = msg
    headers = {"Content-Type": "application/json"}
    headers.update(extra_headers)
    data.update(extra_data)
    return make_response(data, status_int, headers)


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
        message = 'Missing KoBoToolbox token.'
        toolkit.h.flash_error(message)
        return toolkit.redirect_to('unhcr_kobo.index')
    plugin_extras = {} if user_obj.plugin_extras is None else copy.deepcopy(user_obj.plugin_extras)
    old_token = plugin_extras.get('unhcr', {}).get('kobo_token')

    if token != old_token:

        current_user_dict = toolkit.get_action('user_show')(
            {'ignore_auth': True},
            {'id': user_obj.id, 'include_plugin_extras': True}
        )

        if not plugin_extras.get('unhcr'):
            plugin_extras['unhcr'] = {}
        plugin_extras['unhcr']['kobo_token'] = token
        current_user_dict['plugin_extras'] = plugin_extras
        try:
            toolkit.get_action('user_update')(
                {'user': user_obj.name, 'validate_token': not token.startswith('test_')},
                current_user_dict
            )
        except toolkit.ValidationError as e:
            if e.error_dict and 'kobo_token' in e.error_dict:
                message = 'Invalid KoBoToolbox token. Please try again.'
            else:
                message = 'Unknown KoBoToolbox token error: {}.'.format(e)
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
        message = 'Unexpected KoBoToolbox error getting surveys: {}'.format(e)
        toolkit.h.flash_error(message)
        return toolkit.redirect_to('unhcr_kobo.index')

    for survey in surveys:
        kd = KoboDataset(survey['uid'])
        pkg = kd.get_package(raise_multiple_error=False)
        survey['ridl_package'] = pkg
        if pkg:
            download_statuses = [res.get('kobo_details', {}).get('kobo_download_status') for res in pkg['resources']]
            survey['update_is_running'] = 'pending' in download_statuses

    extra_vars = {
        'surveys': surveys,
    }
    return toolkit.render('kobo/surveys.html', extra_vars)


@require_editor_user
def enqueue_survey_package_update():
    """ Update all survey resources
        Returns an API dict response """
    user_obj = toolkit.c.userobj

    kobo_asset_id = toolkit.request.form.get('kobo_asset_id')

    if not kobo_asset_id:
        message = 'Missing KoBoToolbox asset ID.'
        return _make_json_response(status_int=404, error_msg=message)

    kd = KoboDataset(kobo_asset_id)
    try:
        import_status = kd.get_import_status()
    except KoboMissingAssetIdError:
        message = 'Dataset not found for this KoBoToolbox asset ID.'
        return _make_json_response(status_int=404, error_msg=message)

    # check if an update is "pending" (but not stalled)
    if import_status == 'pending':
        message = 'There is a pending update for this survey.'
        return _make_json_response(status_int=400, error_msg=message)

    job = toolkit.enqueue_job(update_pkg_kobo_resources, [kobo_asset_id, user_obj.id], title='Enqueue survey update')
    return _make_json_response(msg="Job started {}".format(job.id))


@require_editor_user
def enqueue_survey_resource_update():
    """ Update all survey resources
        Returns an API dict response """
    user_obj = toolkit.c.userobj

    resource_id = toolkit.request.form.get('kobo_resource_id')

    if not resource_id:
        message = 'Missing resource ID.'
        return _make_json_response(status_int=404, error_msg=message)

    job = toolkit.enqueue_job(update_kobo_resource, [resource_id, user_obj.id], title='Preparing to update kobo resource')
    return _make_json_response(msg="Job started {}".format(job.id))


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

unhcr_kobo_blueprint.add_url_rule(
    rule=u'/enqueue-survey-package-update',
    view_func=enqueue_survey_package_update,
    methods=['POST'],
    strict_slashes=False,
)

unhcr_kobo_blueprint.add_url_rule(
    rule=u'/enqueue-survey-resource-update',
    view_func=enqueue_survey_resource_update,
    methods=['POST'],
    strict_slashes=False,
)