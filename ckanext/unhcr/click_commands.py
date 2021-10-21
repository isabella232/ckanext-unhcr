# -*- coding: utf-8 -*-

import click

from ckan.plugins import toolkit
import ckan.model as model

from ckanext.unhcr.commands import expired_users_list, request_renewal
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
    print(u'UNHCR tables initialized')


@unhcr.command(
    u'import-geographies',
    short_help=u'Import geographies from UNHCR GeoPortal'
)
def import_geographies():
    arcgis_import_geographies()


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
    print('Snapshot saved at {}'.format(rec.timestamp))


@unhcr.command(
    u'send-summary-emails',
    short_help=u'Send a summary of activity over the last 7 days\nto sysadmins and curators'
)
@click.option('-v', '--verbose', count=True)
def send_summary_emails(verbose):
    if not toolkit.asbool(toolkit.config.get('ckanext.unhcr.send_summary_emails', False)):
        print('ckanext.unhcr.send_summary_emails is False. Not sending anything.')
        return

    recipients = get_summary_email_recipients()
    subject = '[UNHCR RIDL] Weekly Summary'

    for recipient in recipients:
        if recipient['email']:
            email = compose_summary_email_body(recipient)

            if email['total_events'] == 0:
                print('SKIPPING summary email to: {}'.format(recipient['email']))
                continue

            print('SENDING summary email to: {}'.format(recipient['email']))
            if verbose > 0:
                print(email['body'])
                print('')

            mail_user_by_id(recipient['id'], subject, email['body'])

    print('Sent weekly summary emails.')


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

    before_expire_days = toolkit.config.get('ckanext.unhcr.external_accounts_notify_delta', 30)
    about_to_expire_users = expired_users_list(before_expire_days=before_expire_days, include_activities=True)
    if len(about_to_expire_users) == 0:
        print('There are no users about to expire')

    for about_to_expire_user in about_to_expire_users:
        print('User {} will expire at {}'.format(about_to_expire_user['name'], about_to_expire_user['expiry_date']))
        activities = about_to_expire_user.get('activities', [])
        last_activity = {} if len(activities) == 0 else activities[0]

        if verbose:
            print(' - Last activity: "{}"'.format(last_activity['activity_type']))

        if last_activity.get('activity_type', 'new user') == 'new user':
            if verbose:
                print(' - No relevant activities: {} ignored'.format(about_to_expire_user['name']))
            ignored += 1
            continue

        created, reason = request_renewal(about_to_expire_user, last_activity)
        if created:
            print(' - Renewal access requested for {}'.format(about_to_expire_user['name']))
            renewal += 1
        else:
            print(' - Renewal access not created for user {}: {}'.format(about_to_expire_user['name'], reason))
            ignored += 1

    expired_users = expired_users_list()
    if len(expired_users) == 0:
        print('There are no expired users')

    for expired_user in expired_users:
        # this user has expired. Renewal was requested but no one approved it.
        print('User {} expired on {}'.format(expired_user['name'], expired_user['expiry_date']))
        toolkit.get_action('user_delete')(
            {'ignore_auth': True},
            {'id': expired_user['id']}
        )

        print(' - Deleted')
        deleted += 1

    print('Expire users command finished. {} deleted, {} renewal, {} ignored'.format(deleted, renewal, ignored))
