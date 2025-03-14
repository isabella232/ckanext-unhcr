# -*- coding: utf-8 -*-

import click

from ckan.plugins import toolkit
import ckan.model as model

from ckanext.unhcr.commands import expired_users_list, request_renewal
from ckanext.unhcr.activity import create_system_activity
from ckanext.unhcr.arcgis import import_geographies as arcgis_import_geographies
from ckanext.unhcr.models import create_tables, TimeSeriesMetric
from ckanext.unhcr.mailer import (
    compose_summary_email_body,
    get_summary_email_recipients,
    mail_user_by_id
)


@click.group(short_help=u'UNHCR plugin management commands')
def unhcr():
    pass


@unhcr.command(
    u'init-db',
    short_help=u'Create UNHCR DB tables'
)
def init_db():
    create_tables()
    click.echo(u'UNHCR tables initialized')


@unhcr.command(
    u'import-geographies',
    short_help=u'Import geographies from UNHCR GeoPortal'
)
@click.option('--where', '-w', 'where_list', multiple=True, help='Where clause for query')
@click.option('-v', '--verbose', is_flag=True)
def import_geographies(where_list, verbose):
    data = {}
    # If available, "where" it's a list and we need string
    where = ' AND '.join(where_list) if where_list else 'gis_name IS NOT NULL'

    try:  # we want to capture a system activity for each execution
        arcgis_import_geographies(data, where=where, verbose=verbose)
    except Exception as e:
        data['error'] = str(e)
        click.echo(' - Error: {} {}'.format(type(e), str(e)), err=True)
        description = 'Error! '
    else:
        if data.get('finished'):
            description = 'Finished OK. '
        else:
            description = 'Process not finished. '

    description += '{} geographies imported'.format(data.get('imported_geos', 0))
    click.echo(description)
    create_system_activity(title='import-geographies', description=description, extra_data=data)

@unhcr.command(
    u'snapshot-metrics',
    short_help=u'Take a snapshot of time-series metrics'
)
def snapshot_metrics():
    context = { 'ignore_auth': True }

    data_dict = {
        'q': '*:*',
        'rows': 0,
        'include_private': True,
    }
    packages = toolkit.get_action('package_search')(
        context, dict(data_dict, fq='-type:deposited-dataset'))
    deposits = toolkit.get_action('package_search')(
        context, dict(data_dict, fq='type:deposited-dataset'))
    organizations = toolkit.get_action('organization_list')(
        context,
        { 'type': 'data-container' },
    )

    rec = TimeSeriesMetric(
        datasets_count=packages['count'],
        deposits_count=deposits['count'],
        containers_count=len(organizations),
    )
    model.Session.add(rec)
    model.Session.commit()
    model.Session.refresh(rec)
    click.echo('Snapshot saved at {}'.format(rec.timestamp))


@unhcr.command(
    u'send-summary-emails',
    short_help=u'Send a summary of activity over the last 7 days\nto sysadmins and curators'
)
@click.option('-v', '--verbose', count=True)
def send_summary_emails(verbose):
    if not toolkit.asbool(toolkit.config.get('ckanext.unhcr.send_summary_emails', False)):
        click.echo('ckanext.unhcr.send_summary_emails is False. Not sending anything.')
        return

    recipients = get_summary_email_recipients()
    subject = '[UNHCR RIDL] Weekly Summary'

    for recipient in recipients:
        if recipient['email']:
            email = compose_summary_email_body(recipient)

            if email['total_events'] == 0:
                click.echo('SKIPPING summary email to: {}'.format(recipient['email']))
                continue

            click.echo('SENDING summary email to: {}'.format(recipient['email']))
            if verbose > 0:
                click.echo(email['body'])
                click.echo('')

            mail_user_by_id(recipient['id'], subject, email['body'])

    click.echo('Sent weekly summary emails.')


@unhcr.command(
    u'expire-users',
    short_help=u'Expire users'
)
@click.option('-v', '--verbose', count=True)
def expire_users(verbose):
    """ Check user expired and about to expire users and:
           - delete users who reach their "expiry_date"
           - notify admins about the users about to expire to allow to renewal those accounts """

    ignored = 0  # User is about to expire but doesn't have any relevant activity or already requested
    renewal = 0  # User is about to expire and have some relevant activity. Renewal is requested
    deleted = 0  # User expired and was inactivated/deleted
    # Extra data for logging this activity
    data = {
        'users_about_to_expire': [],
        'expired_users': [],
        'renewal_access_requests': [],
        'renewal_access_ignored': [],
    }  

    before_expire_days = toolkit.config.get('ckanext.unhcr.external_accounts_notify_delta', 30)
    about_to_expire_users = expired_users_list(before_expire_days=before_expire_days, include_activities=True)
    data['users_about_to_expire'] = about_to_expire_users
    if len(about_to_expire_users) == 0:
        click.echo('There are no users about to expire')

    for about_to_expire_user in about_to_expire_users:
        click.echo('User {} will expire at {}'.format(about_to_expire_user['name'], about_to_expire_user['expiry_date']))
        activities = about_to_expire_user.get('activities', [])
        last_activity = {} if len(activities) == 0 else activities[0]

        if verbose:
            click.echo(' - Last activity: "{}"'.format(last_activity['activity_type']))

        if last_activity.get('activity_type', 'new user') == 'new user':
            if verbose:
                click.echo(' - No relevant activities: {} ignored'.format(about_to_expire_user['name']))
            ignored += 1
            data['renewal_access_ignored'].append(about_to_expire_user)
            continue

        created, reason = request_renewal(about_to_expire_user, last_activity)
        if created:
            click.secho(
                ' - Renewal access requested for {}'.format(
                    about_to_expire_user['name']
                ),
                bold=True
            )
            renewal += 1
            data['renewal_access_requests'].append(about_to_expire_user)
        else:
            click.echo(' - Renewal access not created for user {}: {}'.format(about_to_expire_user['name'], reason))
            ignored += 1
            data['renewal_access_ignored'].append(about_to_expire_user)

    expired_users = expired_users_list()
    if len(expired_users) == 0:
        click.secho('There are no expired users', bold=True)

    for expired_user in expired_users:
        # this user has expired. Renewal was requested but no one approved it.
        click.secho(
            'User {} expired on {}'.format(
                expired_user['name'], expired_user['expiry_date']
            ),
            bold=True,
            fg='red',
            bg='white'
        )
        toolkit.get_action('user_delete')(
            {'ignore_auth': True},
            {'id': expired_user['id']}
        )
        data['expired_users'].append(expired_user)
        click.secho(' - Deleted', bold=True, fg='red', bg='white')
        deleted += 1

    result = '{} deleted, {} renewal, {} ignored'.format(deleted, renewal, ignored)
    click.secho('Expire users command finished. {}'.format(result), bold=True)
    create_system_activity(title='expire-users', description=result, extra_data=data)
