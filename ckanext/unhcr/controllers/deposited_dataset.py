import logging
from ckan import model
import ckan.plugins.toolkit as toolkit
import ckan.lib.helpers as lib_helpers
from ckanext.unhcr import helpers
log = logging.getLogger(__name__)


# Module API

# TODO: extract duplication (get_curation/authorize) from methods
class DepositedDatasetController(toolkit.BaseController):

    def approve(self, dataset_id):
        user_id = getattr(toolkit.c.userobj, 'id', None)

        # Get curation data
        try:
            context, dataset, curation = _get_curation_data(dataset_id, user_id)
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            message = 'Not authorized to read dataset "%s"'
            return toolkit.abort(403, message % dataset_id)

        # Authorize context
        if 'approve' not in curation['actions']:
            message = 'Not authorized to approve dataset "%s"'
            return toolkit.abort(403, message % dataset_id)
        context['ignore_auth'] = True

        # Update dataset
        try:
            # We also set type in context to allow type switching by ckan patch
            dataset = helpers.convert_deposited_dataset_to_regular_dataset(dataset)
            dataset = toolkit.get_action('package_update')(
                    dict(context.items() + {'type': dataset['type']}.items()), dataset)
        except toolkit.ValidationError as error:
            message = 'Deposited dataset "%s" is invalid\n(validation error summary: %s)'
            return toolkit.abort(403, message % (id, error.error_summary))

        # Update activity stream
        #

        # Send notification email
        #

        # Show flash message and redirect
        message = 'Datasest "%s" approved and moved to the destination data container'
        toolkit.h.flash_success(message % dataset['title'])
        toolkit.redirect_to('deposited-dataset_read', id=dataset['name'])

    def assign(self, dataset_id):
        user_id = getattr(toolkit.c.userobj, 'id', None)

        # Get curation data
        try:
            context, dataset, curation = _get_curation_data(dataset_id, user_id)
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            message = 'Not authorized to read dataset "%s"'
            return toolkit.abort(403, message % dataset_id)

        # Authorize context
        if 'assign' not in curation['actions']:
            message = 'Not authorized to assign curator to dataset "%s"'
            return toolkit.abort(403, message % dataset_id)
        context['ignore_auth'] = True

        # Update dataset
        curator_id = toolkit.request.params.get('curator_id')
        if curator_id:
            dataset['curator_id'] = curator_id
        else:
            dataset.pop('curator_id', None)
        try:
            dataset = toolkit.get_action('package_update')(context, dataset)
        except toolkit.ValidationError:
            message = 'Curator is invalid'
            return toolkit.abort(403, message)

        # Update activity stream
        #

        # Send notification email
        #

        # Show flash message and redirect
        message = 'Datasest "%s" curator updated'
        toolkit.h.flash_error(message % dataset['title'])
        toolkit.redirect_to('deposited-dataset_read', id=dataset['name'])

    def request_changes(self, dataset_id):
        user_id = getattr(toolkit.c.userobj, 'id', None)

        # Get curation data
        try:
            context, dataset, curation = _get_curation_data(dataset_id, user_id)
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            message = 'Not authorized to read dataset "%s"'
            return toolkit.abort(403, message % dataset_id)

        # Authorize context
        if 'request_changes' not in curation['actions']:
            message = 'Not authorized to request changes of dataset "%s"'
            return toolkit.abort(403, message % dataset_id)
        context['ignore_auth'] = True

        # Update dataset
        if dataset['curation_state'] == 'review':
            dataset['curation_state'] = 'submitted'
        else:
            dataset['curation_state'] = 'draft'
        dataset = toolkit.get_action('package_update')(context, dataset)

        # Update activity stream
        #

        # Send notification email
        #

        # Show flash message and redirect
        message = 'Datasest "%s" changes requested'
        toolkit.h.flash_error(message % dataset['title'])
        toolkit.redirect_to('deposited-dataset_read', id=dataset['name'])

    def request_review(self, dataset_id):
        user_id = getattr(toolkit.c.userobj, 'id', None)

        # Get curation data
        try:
            context, dataset, curation = _get_curation_data(dataset_id, user_id)
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            message = 'Not authorized to read dataset "%s"'
            return toolkit.abort(403, message % dataset_id)

        # Authorize context
        if 'request_review' not in curation['actions']:
            message = 'Not authorized to request review of dataset "%s"'
            return toolkit.abort(403, message % dataset_id)
        context['ignore_auth'] = True

        # Update dataset
        dataset['curation_state'] = 'review'
        dataset = toolkit.get_action('package_update')(context, dataset)

        # Update activity stream
        #

        # Send notification email
        #

        # Show flash message and redirect
        message = 'Datasest "%s" review requested'
        toolkit.h.flash_error(message % dataset['title'])
        toolkit.redirect_to('deposited-dataset_read', id=dataset['name'])

    def reject(self, dataset_id):
        user_id = getattr(toolkit.c.userobj, 'id', None)

        # Get curation data
        try:
            context, dataset, curation = _get_curation_data(dataset_id, user_id)
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            message = 'Not authorized to read dataset "%s"'
            return toolkit.abort(403, message % dataset_id)

        # Authorize context
        if 'reject' not in curation['actions']:
            message = 'Not authorized to reject dataset "%s"'
            return toolkit.abort(403, message % dataset_id)
        context['ignore_auth'] = True

        # Purge rejected dataset
        toolkit.get_action('dataset_purge')(context, {'id': dataset_id})

        # Update activity stream
        #

        # Send notification email
        #

        # Show flash message and redirect
        message = 'Datasest "%s" rejected'
        toolkit.h.flash_error(message % dataset['title'])
        toolkit.redirect_to('data-container_read', id='data-deposit')

    def submit(self, dataset_id):
        user_id = getattr(toolkit.c.userobj, 'id', None)

        # Get curation data
        try:
            context, dataset, curation = _get_curation_data(dataset_id, user_id)
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            message = 'Not authorized to read dataset "%s"'
            return toolkit.abort(403, message % dataset_id)

        # Authorize context
        if 'submit' not in curation['actions']:
            message = 'Not authorized to submit dataset "%s"'
            return toolkit.abort(403, message % dataset_id)
        context['ignore_auth'] = True

        # Update dataset
        dataset['curation_state'] = 'submitted'
        dataset = toolkit.get_action('package_update')(context, dataset)

        # Update activity stream
        #

        # Send notification email
        #

        # Show flash message and redirect
        message = 'Datasest "%s" submitted'
        toolkit.h.flash_error(message % dataset['title'])
        toolkit.redirect_to('deposited-dataset_read', id=dataset['name'])

    def withdraw(self, dataset_id):
        user_id = getattr(toolkit.c.userobj, 'id', None)

        # Get curation data
        try:
            context, dataset, curation = _get_curation_data(dataset_id, user_id)
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            message = 'Not authorized to read dataset "%s"'
            return toolkit.abort(403, message % dataset_id)

        # Authorize context
        if 'withdraw' not in curation['actions']:
            message = 'Not authorized to withdraw dataset "%s"'
            return toolkit.abort(403, message % dataset_id)
        context['ignore_auth'] = True

        # Purge withdrawn dataset
        toolkit.get_action('dataset_purge')(context, {'id': dataset_id})

        # Update activity stream
        #

        # Send notification email
        #

        # Show flash message and redirect
        message = 'Datasest "%s" withdrawn'
        toolkit.h.flash_error(message % dataset['title'])
        toolkit.redirect_to('data-container_read', id='data-deposit')


# Internal

def _get_curation_data(dataset_id, user_id):
    context = _get_context()
    dataset = _get_deposited_dataset(context, dataset_id)
    curation = helpers.get_deposited_dataset_user_curation_status(dataset, user_id)
    return context, dataset, curation


def _get_context(**patch):
    context = {'model': model, 'user': toolkit.c.user}
    context.update(patch)
    return context


def _get_deposited_dataset(context, dataset_id):
    deposit = helpers.get_data_deposit()
    dataset = toolkit.get_action('package_show')(context, {'id': dataset_id})
    if dataset.get('owner_org') != deposit['id']:
        message = 'Deposited dataset "%s" not found' % dataset_id
        raise toolkit.ObjectNotFound(message)
    return dataset
