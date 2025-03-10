# encoding: utf-8
import json
import logging
from ckan import model
import ckan.lib.helpers as core_helpers
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckan.lib.plugins import DefaultTranslation
from ckan.lib.plugins import DefaultPermissionLabels

# 🙈
import ckan.authz as authz

from ckanext.unhcr import actions, auth, click_commands, blueprints, helpers, jobs, utils, validators
from ckanext.unhcr.activity import create_curation_activity
from ckanext.unhcr.models import Geography
from ckanext.scheming.helpers import scheming_get_dataset_schema
from ckanext.hierarchy.helpers import group_tree_section

log = logging.getLogger(__name__)

_ = toolkit._


ALLOWED_ACTIONS = [
    'datastore_create',
    'datastore_delete',
    'datastore_upsert',
    'datastore_info',
    'datastore_search',
    'format_autocomplete',
    'geography_autocomplete',
    'geography_show',
    'group_list_authz',
    'group_show',
    'organization_list_for_user',
    'organization_show',
    'package_create',
    'package_delete',
    'package_patch',
    'package_resource_reorder',
    'package_search',
    'package_show',
    'package_update',
    'resource_create',
    'resource_delete',
    'resource_download',
    'resource_patch',
    'resource_show',
    'resource_update',
    'resource_view',
    'resource_view_show',
    'resource_view_list',
    'scan_submit',
    'site_read',
    'tag_autocomplete',
    'tag_list',
    'task_status_show',
    'user_show',
    'user_update',
    'user_generate_apikey',
]


def restrict_external(func):
    '''
    Decorator function to restrict external users to a small number of allowed_actions
    '''
    def unhcr_auth_wrapper(action, context, data_dict=None):
        user = model.User.by_name(context.get('user'))
        if not user:
            return func(action, context, data_dict)
        if user.sysadmin:
            return func(action, context, data_dict)
        if context.get('ignore_auth'):
            return func(action, context, data_dict)
        if user.external and action not in ALLOWED_ACTIONS:
            return {'success': False, 'msg': 'Not allowed to perform this action'}
        return func(action, context, data_dict)
    return unhcr_auth_wrapper


_url_for = core_helpers.url_for


def url_for(*args, **kw):
    url = _url_for(*args, **kw)

    try:
        if (
            getattr(toolkit.c, "userobj", None)
            and getattr(toolkit.c.userobj, "external", None)
            and "/dataset/" in url
        ):
            url = url.replace('/dataset/', '/deposited-dataset/')
    except (TypeError, RuntimeError):
        pass

    return url


class UnhcrPlugin(
        plugins.SingletonPlugin, DefaultTranslation, DefaultPermissionLabels):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IResourceController, inherit=True)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.IPermissionLabels)
    plugins.implements(plugins.IBlueprint)

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('fanstatic', 'unhcr')
        toolkit.add_ckan_admin_tab(config_, 'unhcr_search_index.index', 'Search Index', icon='hdd-o')
        toolkit.add_ckan_admin_tab(config_, 'unhcr_system_activities.index', 'System activities', icon='history')

        model.User.external = property(utils.user_is_external)
        if (authz.is_authorized.__name__ != 'unhcr_auth_wrapper'):
            authz.is_authorized = restrict_external(authz.is_authorized)
        core_helpers.url_for = url_for

    def update_config_schema(self, schema):
        schema.update({
            'ckanext.unhcr.microdata_api_key': [
                toolkit.get_validator('ignore_missing'),
            ],
        })

        return schema

    # IClick

    def get_commands(self):
        return [click_commands.unhcr]

    # IFacets

    def _facets(self, facets_dict):
        if 'groups' in facets_dict:
            del facets_dict['groups']

        facets_dict['vocab_data_collector'] = _('Data Collector')
        facets_dict['vocab_keywords'] = _('Keywords')
        facets_dict['vocab_geo_name'] = _('Geographic coverage')
        facets_dict['vocab_sampling_procedure'] = _('Sampling Procedure')
        facets_dict['vocab_operational_purpose_of_data'] = _(
            'Operational purpose of data')
        facets_dict['vocab_process_status'] = _('Process Status')
        facets_dict['vocab_identifiability'] = _('Identifiability')
        facets_dict['vocab_data_collection_technique'] = _(
            'Data Collection Technique')

        return facets_dict

    def dataset_facets(self, facets_dict, package_type):
        return self._facets(facets_dict)

    def group_facets(self, facets_dict, group_type, package_type):
        return self._facets(facets_dict)

    def organization_facets(self, facets_dict, organization_type, package_type):
        # TODO: optimize data deposit calls
        deposit = helpers.get_data_deposit()
        if deposit['id'] == getattr(toolkit.c.group, 'id', None):
            facets_dict.clear()
            facets_dict['curation_state'] = _('State')
            facets_dict['curator_display_name'] = _('Curator')
            facets_dict['depositor_display_name'] = _('Depositor')
            facets_dict['owner_org_dest_display_name'] = _('Data Container')
            return facets_dict
        else:
            return self._facets(facets_dict)

    # ITemplateHelpers

    def get_helpers(self):
        return {
            # Core overrides
            'new_activities': helpers.new_activities,
            'dashboard_activity_stream': helpers.dashboard_activity_stream,
            # General
            'get_data_container': helpers.get_data_container,
            'get_all_data_containers': helpers.get_all_data_containers,
            'get_dataset_count': helpers.get_dataset_count,
            # Hierarchy
            'get_allowable_parent_groups': helpers.get_allowable_parent_groups,
            'render_tree': helpers.render_tree,
            # Access restriction
            'page_authorized': helpers.page_authorized,
            'get_came_from_param': helpers.get_came_from_param,
            'user_is_curator': helpers.user_is_curator,
            'user_is_editor': helpers.user_is_editor,
            'user_is_container_admin': helpers.user_is_container_admin,
            'user_orgs': helpers.user_orgs,
            # Linked datasets
            'get_linked_datasets_for_form': helpers.get_linked_datasets_for_form,
            'get_linked_datasets_for_display': helpers.get_linked_datasets_for_display,
            # Geography
            'get_geographies_for_display': helpers.get_geographies_for_display,
            'get_default_geography': helpers.get_default_geography,
            # Access requests
            'get_pending_requests_total': helpers.get_pending_requests_total,
            'get_existing_access_request': helpers.get_existing_access_request,
            'get_access_request_for_user': helpers.get_access_request_for_user,
            # Activities
            'curation_activity_message': helpers.curation_activity_message,
            # Deposited datasets
            'get_data_deposit': helpers.get_data_deposit,
            'get_data_curation_users': helpers.get_data_curation_users,
            'get_deposited_dataset_user_curation_status': helpers.get_deposited_dataset_user_curation_status,
            'get_deposited_dataset_user_curation_role': helpers.get_deposited_dataset_user_curation_role,
            'get_dataset_validation_report': helpers.get_dataset_validation_report,
            'get_user_deposited_drafts': helpers.get_user_deposited_drafts,
            'get_default_container_for_user': helpers.get_default_container_for_user,
            # Microdata
            'get_microdata_collections': helpers.get_microdata_collections,
            # KoBo
            'get_kobo_token': helpers.get_kobo_token,
            'get_kobo_url': helpers.get_kobo_url,
            'get_kobo_import_limit': helpers.get_kobo_import_limit,
            'get_kobo_initial_dataset': helpers.get_kobo_initial_dataset,
            'get_kobo_survey': helpers.get_kobo_survey,
            'get_kobo_all_formats': helpers.get_kobo_all_formats,
            'get_kobo_fixed_fields_export': helpers.get_kobo_fixed_fields_export,
            # Misc
            'current_path': helpers.current_path,
            'normalize_list': helpers.normalize_list,
            'get_field_label': helpers.get_field_label,
            'can_download': helpers.can_download,
            'can_request_access': helpers.can_request_access,
            'get_choice_label': helpers.get_choice_label,
            'get_data_container_choice_label': helpers.get_data_container_choice_label,
            'get_ridl_version': helpers.get_ridl_version,
            'get_envname': helpers.get_envname,
            'get_max_resource_size': helpers.get_max_resource_size,
            'get_google_analytics_id': helpers.get_google_analytics_id,
            'nl_to_br': helpers.nl_to_br,
            'is_plugin_loaded': helpers.is_plugin_loaded,
            'get_resource_value_label': helpers.get_resource_value_label,
            'get_kobo_import_process_real_status': helpers.get_kobo_import_process_real_status,
            'get_system_activities': helpers.get_system_activities,
            'get_bool_arg_value': helpers.get_bool_arg_value,
        }

    # IPackageController

    def before_index(self, pkg_dict):

        # Remove internal non-indexable fields

        # admin_notes
        pkg_dict.pop('admin_notes', None)
        pkg_dict.pop('extras_admin_notes', None)

        # sampling_procedure_notes
        pkg_dict.pop('sampling_procedure_notes', None)
        pkg_dict.pop('extras_sampling_procedure_notes', None)

        # response_rate_notes
        pkg_dict.pop('response_rate_notes', None)
        pkg_dict.pop('extras_response_rate_notes', None)

        # data_collection_notes
        pkg_dict.pop('data_collection_notes', None)
        pkg_dict.pop('extras_data_collection_notes', None)

        # weight_notes
        pkg_dict.pop('weight_notes', None)
        pkg_dict.pop('extras_weight_notes', None)

        # clean_ops_notes
        pkg_dict.pop('clean_ops_notes', None)
        pkg_dict.pop('extras_clean_ops_notes', None)

        # data_accs_notes
        pkg_dict.pop('data_accs_notes', None)
        pkg_dict.pop('extras_data_accs_notes', None)

        # Index labels on selected fields

        schema = scheming_get_dataset_schema('dataset')
        fields = ['data_collector', 'keywords', 'sampling_procedure',
                  'operational_purpose_of_data',  'data_collection_technique',
                  'process_status', 'identifiability', 'geographies']
        for field in fields:
            if pkg_dict.get(field):
                value = pkg_dict[field]

                # Free text values: value1,value2
                if field == 'data_collector':
                    pkg_dict['vocab_' + field] = helpers.normalize_list(value)
                # Index geo info (names and pcodes)
                elif field == 'geographies':
                    if pkg_dict.get('geographies'):
                        vocab_geo_names = []
                        vocab_geo_pcodes = []
                        ids = helpers.normalize_list(pkg_dict['geographies'])
                        for id_ in ids:
                            geog = model.Session.query(Geography).get(id_)
                            if geog:
                                vocab_geo_names.append(geog.gis_name)
                                vocab_geo_pcodes.append(geog.pcode)

                                for parent in geog.parents:
                                    vocab_geo_names.append(parent.gis_name)
                                    vocab_geo_pcodes.append(parent.pcode)

                        pkg_dict['vocab_geo_name'] = vocab_geo_names
                        pkg_dict['vocab_geo_pcodes'] = vocab_geo_pcodes

                # Select values: ["value1","value2"]
                else:
                    try:
                        values = json.loads(pkg_dict[field])
                    except ValueError:
                        values = [value]
                    out = []
                    for schema_field in schema['dataset_fields']:
                        if schema_field['field_name'] == field:
                            for item in values:
                                for choice in schema_field['choices']:
                                    if choice['value'] == item:
                                        out.append(choice['label'])
                    pkg_dict['vocab_' + field] = out

        # Index additional data for deposited dataset

        if pkg_dict.get('type') == 'deposited-dataset':
            # curator
            curator_id = pkg_dict.get('curator_id')
            if curator_id:
                try:
                    curator = toolkit.get_action('user_show')(
                        {'ignore_auth': True}, {'id': curator_id})
                    pkg_dict['curator_display_name'] = curator.get('display_name')
                except toolkit.ObjectNotFound:
                    pass
            # depositor
            depositor_id = pkg_dict.get('creator_user_id')
            if depositor_id:
                try:
                    depositor = toolkit.get_action('user_show')(
                        {'ignore_auth': True}, {'id': depositor_id})
                    pkg_dict['depositor_display_name'] = depositor.get('display_name')
                except toolkit.ObjectNotFound:
                    pass
            # data-container
            owner_org_dest_id = pkg_dict.get('owner_org_dest')
            if owner_org_dest_id:
                try:
                    owner_org_dest = toolkit.get_action('organization_show')(
                        {'ignore_auth': True}, {'id': owner_org_dest_id})
                    pkg_dict['owner_org_dest_display_name'] = owner_org_dest.get('display_name')
                except toolkit.ObjectNotFound:
                    pass

        return pkg_dict

    def before_search(self, search_params):
        try:
            blueprint, view = toolkit.get_endpoint()
        except (TypeError, RuntimeError):
            return search_params

        if blueprint in ['dataset', 'package']:
            search_extras = search_params.get('extras', {})
            ext_include_deleted = search_extras.pop('ext_include_deleted', None)
            include_deleted = toolkit.asbool(ext_include_deleted)    
            if include_deleted:
                search_params['include_deleted'] = True

        elif blueprint in ['organization', 'data-container'] and view != 'edit':
            # Always include sub-containers to container_read search
            toolkit.c.include_children_selected = True

            # helper function
            def _children_name_list(children):
                name_list = []
                for child in children:
                    name = child.get('name', "")
                    name_list += [name] + _children_name_list(child.get('children', []))
                return name_list

            # update filter query
            if getattr(toolkit.c, "group", None):
                children = _children_name_list(
                    group_tree_section(
                        toolkit.c.group.name,
                        type_='data-container',
                        include_parents=False,
                        include_siblings=False
                    ).get('children',[])
                )
                if children:
                    search_params['fq'] = 'organization:%s' % toolkit.c.group.name
                    for name in children:
                        if name:
                            search_params['fq'] += ' OR organization:%s' %  name
                    search_params['fq'] = '({})'.format(search_params['fq'])
        return search_params

    # IPackageController, IResourceController
    # note: if we add more hooks that are in the interface for both
    # IPackageController and IResourceController (e.g: before_update)
    # we need to account for the fact that data_dict might be a package
    # and might be a resource.
    # Refs https://github.com/okfn/ckanext-unhcr/pull/459

    def after_create(self, context, data_dict):
        if 'owner_org' in data_dict and 'package_id' not in data_dict:
            self._package_after_create(context, data_dict)

        if 'resource_type' in data_dict and 'package_id' in data_dict:
            self._resource_after_create(context, data_dict)

    def _package_after_create(self, context, pkg_dict):
        if not context.get('job') and not context.get('defer_commit'):
            if self._package_is_active(context, pkg_dict):
                toolkit.enqueue_job(
                    jobs.process_dataset_on_create,
                    [pkg_dict['id']],
                    title="_package_after_create {}".format(pkg_dict['name'])
                )

        if pkg_dict.get('type') == 'deposited-dataset':
            user_id = None
            if context.get('auth_user_obj'):
                user_id = context['auth_user_obj'].id
            elif context.get('user'):
                user = toolkit.get_action('user_show')(
                    {'ignore_auth': True}, {'id': context['user']})
                user_id = user['id']
            if user_id:
                create_curation_activity('dataset_deposited', pkg_dict['id'],
                    pkg_dict['name'], user_id)

    def _resource_after_create(self, context, res_dict):
        if not context.get('job'):
            if self._resource_is_active(context, res_dict):
                toolkit.enqueue_job(
                    jobs.process_dataset_on_update,
                    [res_dict['package_id']],
                    title="_resource_after_create {}".format(res_dict['id'])
                )

    def after_update(self, context, data_dict):
        if 'owner_org' in data_dict and 'package_id' not in data_dict:
            self._package_after_update(context, data_dict)

        if 'resource_type' in data_dict and 'package_id' in data_dict:
            self._resource_after_update(context, data_dict)

    def _package_after_update(self, context, pkg_dict):
        if not context.get('job') and not context.get('defer_commit'):
            if self._package_is_active(context, pkg_dict):
                toolkit.enqueue_job(
                    jobs.process_dataset_on_update,
                    [pkg_dict['id']],
                    title="_package_after_update {}".format(pkg_dict['name'])
                )

    def _resource_after_update(self, context, res_dict):
        if not context.get('job'):
            if self._resource_is_active(context, res_dict):
                toolkit.enqueue_job(
                    jobs.process_dataset_on_update,
                    [res_dict['package_id']],
                    title="_resource_after_update {}".format(res_dict['id'])
                )

    def after_delete(self, context, data_dict):
        if not context.get('job') and type(data_dict) == dict and data_dict.get('id'):
            toolkit.enqueue_job(
                jobs.process_dataset_on_delete,
                [data_dict['id']],
                title="_resource_after_update {}".format(data_dict['id'])
            )

    def _package_is_active(self, context, pkg_dict):
        if pkg_dict.get('state') == 'active':
            return True
        pkg = context.get('package')
        if pkg and pkg.state == 'active':
            return True
        return False

    def _resource_is_active(self, context, res_dict):
        if res_dict.get('state') == 'active':
            return True
        pkg = context.get('package')
        res_id = res_dict.get('id')
        if pkg and pkg.resources:
            if res_id in [r.id for r in pkg.resources if r.state == 'active']:
                return True
        return False


    # IAuthFunctions

    def get_auth_functions(self):
        functions = auth.restrict_access_to_get_auth_functions()
        functions['resource_download'] = auth.resource_download
        functions['datastore_info'] = auth.datastore_info
        functions['datastore_search'] = auth.datastore_search
        functions['datastore_search_sql'] = auth.datastore_search_sql
        functions['datasets_validation_report'] = auth.datasets_validation_report
        functions['organization_create'] = auth.organization_create
        functions['organization_show'] = auth.organization_show
        functions['organization_list_all_fields'] = auth.organization_list_all_fields
        functions['group_list_authz'] = auth.group_list_authz
        functions['package_internal_activity_list'] = auth.package_internal_activity_list
        functions['package_create'] = auth.package_create
        functions['package_collaborator_create'] = auth.package_collaborator_create
        functions['package_update'] = auth.package_update
        functions['scan_hook'] = auth.scan_hook
        functions['scan_submit'] = auth.scan_submit
        functions['access_request_list_for_user'] = auth.access_request_list_for_user
        functions['access_request_create'] = auth.access_request_create
        functions['access_request_update'] = auth.access_request_update
        functions['user_update_sysadmin'] = auth.user_update_sysadmin
        functions['external_user_update_state'] = auth.external_user_update_state
        functions['search_index_rebuild'] = auth.search_index_rebuild
        functions['geography_autocomplete'] = auth.geography_autocomplete
        functions['geography_show'] = auth.geography_show
        functions['user_show'] = auth.user_show
        functions['user_reset'] = auth.user_reset
        functions['request_reset'] = auth.request_reset
        functions['package_kobo_update'] = auth.package_kobo_update
        return functions

    # IActions

    def get_actions(self):
        functions = {
            'access_request_list_for_user': actions.access_request_list_for_user,
            'access_request_update': actions.access_request_update,
            'access_request_create': actions.access_request_create,
            'package_update': actions.package_update,
            'package_create': actions.package_create,
            'package_publish_microdata': actions.package_publish_microdata,
            'package_get_microdata_collections': actions.package_get_microdata_collections,
            'package_collaborator_create': actions.package_collaborator_create,
            'package_collaborator_delete': actions.package_collaborator_delete,
            'organization_create': actions.organization_create,
            'organization_member_create': actions.organization_member_create,
            'organization_member_delete': actions.organization_member_delete,
            'organization_list_all_fields': actions.organization_list_all_fields,
            'package_internal_activity_list': actions.package_internal_activity_list,
            'container_request_list': actions.container_request_list,
            'package_activity_list': actions.package_activity_list,
            'dashboard_activity_list': actions.dashboard_activity_list,
            'user_activity_list': actions.user_activity_list,
            'group_activity_list': actions.group_activity_list,
            'organization_activity_list': actions.organization_activity_list,
            'datasets_validation_report': actions.datasets_validation_report,
            'scan_hook': actions.scan_hook,
            'scan_submit': actions.scan_submit,
            'resource_create': actions.resource_create,
            'resource_update': actions.resource_update,
            'user_update_sysadmin': actions.user_update_sysadmin,
            'external_user_update_state': actions.external_user_update_state,
            'search_index_rebuild': actions.search_index_rebuild,
            'user_autocomplete': actions.user_autocomplete,
            'geography_autocomplete': actions.geography_autocomplete,
            'geography_show': actions.geography_show,
            'user_list': actions.user_list,
            'user_show': actions.user_show,
            'user_create': actions.user_create,
            'user_update': actions.user_update,
            'user_delete': actions.user_delete,
            'datastore_create': actions.datastore_create,
        }
        return functions

    # IValidators

    def get_validators(self):
        return {
            'ignore_if_attachment': validators.ignore_if_attachment,
            'linked_datasets_validator': validators.linked_datasets,
            'geographies_validator': validators.geographies,
            'unhcr_choices': validators.unhcr_choices,
            'deposited_dataset_owner_org': validators.deposited_dataset_owner_org,
            'deposited_dataset_owner_org_dest': validators.deposited_dataset_owner_org_dest,
            'deposited_dataset_curation_state': validators.deposited_dataset_curation_state,
            'deposited_dataset_curator_id': validators.deposited_dataset_curator_id,
            'always_false_if_not_sysadmin': validators.always_false_if_not_sysadmin,
            'visibility_validator': validators.visibility_validator,
            'visibility_validator_resource': validators.visibility_validator_resource,
            'file_type_validator': validators.file_type_validator,
            'upload_not_empty': validators.upload_not_empty,
            'object_id_validator': validators.object_id_validator,
            'activity_type_exists': validators.activity_type_exists,
            'output_list': validators.output_list,
        }

    # IPermissionLabels

    def get_dataset_labels(self, dataset_obj):
        # https://github.com/ckan/ckan/blob/master/ckanext/example_ipermissionlabels/plugin.py

        # For deposited datasets
        if dataset_obj.type == 'deposited-dataset':
            context = {'ignore_auth': True}
            dataset = toolkit.get_action('package_show')(
                context,
                {'id': dataset_obj.id}
            )
            deposit = helpers.get_data_deposit()

            labels = [
                'deposited-dataset',
                'creator-%s' % dataset_obj.creator_user_id,
            ]
            if dataset['owner_org_dest'] not in [deposit['id'], 'unknown']:
                labels.append(
                    'deposited-dataset-{}'.format(dataset['owner_org_dest'])
                )

        # For normal datasets
        else:
            labels = super(UnhcrPlugin, self).get_dataset_labels(dataset_obj)

        return labels

    def get_user_dataset_labels(self, user_obj):
        # https://github.com/ckan/ckan/blob/master/ckanext/example_ipermissionlabels/plugin.py

        # For normal users
        # The label "creator-%s" is here for a package creator
        labels = super(UnhcrPlugin, self).get_user_dataset_labels(user_obj)

        # For curating users
        # Adding "deposited-dataset" label for data curators
        if user_obj:

            if user_obj.external:
                return ['creator-%s' % user_obj.id]

            context = {u'user': user_obj.id}
            deposit = helpers.get_data_deposit()
            orgs = toolkit.get_action('organization_list_for_user')(context, {})
            for org in orgs:
                if deposit['id'] == org['id']:
                    labels.append('deposited-dataset')
                    continue
                if org['capacity'] == 'admin':
                    labels.append(
                        'deposited-dataset-{}'.format(org['id'])
                    )

        return labels

    # IBlueprint

    def get_blueprint(self):
        return [
            blueprints.unhcr_access_requests_blueprint,
            blueprints.unhcr_admin_blueprint,
            blueprints.unhcr_api_blueprint,
            blueprints.unhcr_dashboard_blueprint,
            blueprints.unhcr_dataset_blueprint,
            blueprints.unhcr_data_container_blueprint,
            blueprints.unhcr_deposited_dataset_blueprint,
            blueprints.unhcr_metrics_blueprint,
            blueprints.unhcr_resource_blueprint,
            blueprints.unhcr_search_index_blueprint,
            blueprints.unhcr_system_activities_blueprint,
            blueprints.unhcr_user_blueprint,
            blueprints.unhcr_kobo_blueprint,
        ]
