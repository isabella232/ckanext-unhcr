from flask import Blueprint, make_response
import ckan.plugins.toolkit as toolkit
from ckanext.unhcr.utils import require_editor_user
from ckanext.unhcr.jobs import update_pkg_kobo_resources
from ckanext.unhcr.kobo.api import KoBoAPI, KoBoSurvey
from ckanext.unhcr.kobo.exceptions import KoboApiError, KoboMissingAssetIdError
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
            # check if there are new submissions
            old_submission_count = kd.get_submission_count()
            new_submission_count = survey['deployment__submission_count']
            survey['new_submissions'] = new_submission_count - old_submission_count
            download_statuses = [res.get('kobo_details', {}).get('kobo_download_status') for res in pkg['resources']]
            survey['update_is_running'] = 'pending' in download_statuses

    extra_vars = {
        'surveys': surveys,
    }
    return toolkit.render('kobo/surveys.html', extra_vars)


@require_editor_user
def enqueue_survey_update():
    """ Check for updates and if new submissions were found, starts a job to update.
        Return an API dict response """
    user_obj = toolkit.c.userobj

    kobo_asset_id = toolkit.request.form.get('kobo_asset_id')
    force = toolkit.asbool(toolkit.request.form.get('force', False))

    if not kobo_asset_id:
        message = 'Missing KoBoToolbox asset ID.'
        return _make_json_response(status_int=404, error_msg=message)

    kd = KoboDataset(kobo_asset_id)
    try:
        old_submission_count = kd.get_submission_count()
    except KoboMissingAssetIdError:
        message = 'Dataset not found for this KoBoToolbox asset ID.'
        return _make_json_response(status_int=404, error_msg=message)

    # check if an update is pending
    download_statuses = [res.get('kobo_details', {}).get('kobo_download_status') for res in kd.package_dict['resources']]
    if 'pending' in download_statuses:
        message = 'There is a pending update for this survey.'
        return _make_json_response(status_int=400, error_msg=message)

    if force:
        extra_data = {'forced': True}
        run_job = True
    else:
        # check if there are new submissions
        kobo_api = kd.get_kobo_api(user_obj)
        survey = KoBoSurvey(kobo_asset_id, kobo_api)

        new_submission_count = survey.get_total_submissions()
        new_submissions = new_submission_count - old_submission_count

        extra_data = {'new_submissions': new_submissions, 'forced': False}
        run_job = new_submissions > 0
        if new_submissions == 0:
            message = "There are no new submissions"

    if run_job:
        job = toolkit.enqueue_job(update_pkg_kobo_resources, [kobo_asset_id, user_obj.id], title='Enqueue survey update')
        message = "Job started {}".format(job.id),

    return _make_json_response(msg=message, extra_data=extra_data)


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
    rule=u'/enqueue-survey-update',
    view_func=enqueue_survey_update,
    methods=['POST'],
    strict_slashes=False,
)
