import ast
import logging
from ckan.plugins import toolkit


logger = logging.getLogger(__name__)


def process_pkg_kobo_filters(kobo_filters):
    """ Check pkg KoBo filters.
        Just for new packages from KoBo """
    logger.info('Processing kobo filters for new pkg {}'.format(kobo_filters))
    include_questionnaire = kobo_filters.get('kobo_filter_include_questionnaire', 'true')
    fields_from_all_versions = kobo_filters.get('kobo_filter_fields_from_all_versions', 'true')
    group_sep = kobo_filters.get('kobo_filter_group_sep', '/')
    hierarchy_in_labels = kobo_filters.get('kobo_filter_hierarchy_in_labels', 'true')
    multiple_select = kobo_filters.get('kobo_filter_multiple_select', 'both')
    field_list = kobo_filters.get('kobo_filter_fields', [])
    format_list = kobo_filters.get('kobo_filter_formats', ['csv'])

    query = kobo_filters.get('kobo_filter_query')
    if not query:
        query = None
    else:
        # we need a dict no mater if uses single or double quotes
        query = ast.literal_eval(query)

    return dict(
        include_questionnaire=toolkit.asbool(include_questionnaire),
        fields_from_all_versions=toolkit.asbool(fields_from_all_versions),
        group_sep=group_sep,
        hierarchy_in_labels=toolkit.asbool(hierarchy_in_labels),
        multiple_select=multiple_select,
        fields=field_list,
        formats=format_list,
        query=query
    )


def process_resource_kobo_filters(kobo_details):
    """ Get resource details (already parsed) and return final KoBo filters """
    logger.info('Processing kobo filters for resource {}'.format(kobo_details))

    return dict(
        fields_from_all_versions=kobo_details.get('kobo_filter_fields_from_all_versions', True),
        group_sep=kobo_details.get('kobo_filter_group_sep', '/'),
        hierarchy_in_labels=kobo_details.get('kobo_filter_hierarchy_in_labels', True),
        multiple_select=kobo_details.get('kobo_filter_multiple_select', 'both'),
        fields=kobo_details.get('kobo_filter_fields', []),
        query=kobo_details.get('kobo_filter_query'),
    )
