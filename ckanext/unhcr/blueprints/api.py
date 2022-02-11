from flask import Blueprint
import ckan.plugins.toolkit as toolkit
from ckan.views.api import _finish, _finish_ok, API_REST_DEFAULT_VERSION


unhcr_api_blueprint = Blueprint('unhcr_api', __name__, url_prefix='/api')


def geography_autocomplete(ver=API_REST_DEFAULT_VERSION):
    if (not hasattr(toolkit.c, "user") or not toolkit.c.user):
        error = {
            "error": {
                "__type": "Authorization Error",
                "message": "Access denied: geography_autocomplete requires an authenticated user"
            },
            "success": False
        }
        return _finish(403, error, 'json')

    q = toolkit.request.args.get('q', '')
    limit = toolkit.request.args.get('limit', 100)

    geography_dicts = []
    if q:
        context = {'user': toolkit.c.user}
        data_dict = {'q': q, 'limit': limit}
        action = toolkit.get_action('geography_autocomplete')
        geography_dicts = action(context, data_dict)

    results = {
        'count': geography_dicts['count'],
        'ResultSet': {
            'Result': geography_dicts['results']
            }
        }
    return _finish_ok(results)


version_rule = '/<int(min=1, max=2):ver>'
unhcr_api_blueprint.add_url_rule(
    rule='/util/geography/autocomplete',
    view_func=geography_autocomplete,
    methods=['GET'],
)
unhcr_api_blueprint.add_url_rule(
    rule=version_rule + '/util/geography/autocomplete',
    view_func=geography_autocomplete,
    methods=['GET'],
)
