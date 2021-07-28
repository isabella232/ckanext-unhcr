import datetime
import pytest
from ckan.plugins import toolkit
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.models import USER_REQUEST_TYPE_RENEWAL
from ckanext.unhcr.tests import factories
from ckan.cli.cli import ckan


@pytest.mark.usefixtures('clean_db', 'unhcr_migrate')
def test_expired_user_command(cli):
    not_expired_date = datetime.date.today() + datetime.timedelta(days=35)
    expired_date = datetime.date.today() - datetime.timedelta(days=5)
    about_to_expire_date = datetime.date.today() + datetime.timedelta(days=25)

    # Internal User: nevwe expired
    internal_user = core_factories.User(name='internal-user')

    # Not expired user
    user1 = factories.ExternalUser(
        name='not-expired-user',
        email='one@external.org',
        expiry_date=not_expired_date
    )

    # User expired
    user2 = factories.ExternalUser(
        name='expired-user',
        email='two@external.org',
        expiry_date=expired_date
    )

    # About to expire user (with activities)
    user3 = factories.ExternalUser(
        name='about-expire-with-activity-user',
        email='three@external.org',
        expiry_date=about_to_expire_date
    )
    dataset = factories.Dataset()
    activity = core_factories.Activity(
        user_id=user3["id"],
        object_id=dataset["id"],
        activity_type="new package",
        data={"package": dataset, "actor": "Mr Someone"},
    )

    # About to expire user (without relevant activities)
    user4 = factories.ExternalUser(
        name='about-expire-no-activity-user',
        email='four@external.org',
        expiry_date=about_to_expire_date
    )

    # About to expire user (with activities and already renewal requested)
    user5 = factories.ExternalUser(
        name='about-expire-renewal-requested-user',
        email='five@external.org',
        expiry_date=about_to_expire_date
    )
    dataset2 = factories.Dataset()
    activity = core_factories.Activity(
        user_id=user5["id"],
        object_id=dataset2["id"],
        activity_type="new package",
        data={"package": dataset2, "actor": "Mr Someone"},
    )
    toolkit.get_action('access_request_create')(
        {'ignore_auth': True, 'user': user5['id']},
        {
            'object_id': user5['id'],
            'object_type': 'user',
            'message': 'testing request renewal',
            'role': 'member',  # TODO this is only required to fit the schema
            'data': {
                'user_request_type': USER_REQUEST_TYPE_RENEWAL
            }
        }
    )

    result = cli.invoke(ckan, [u'unhcr', u'expire-users', u'--verbose'])
    if result.exit_code != 0:
        print('COMMAND Error: {}\n{}'.format(result.exception, result.output))
    assert result.exit_code == 0

    assert internal_user['name'] not in result.output

    assert 'Renewal access requested' in result.output

    # User1 is not expired and is not about to expire
    assert user1['name'] not in result.output

    # User2 is expired and deleted
    assert 'User %s expired on' % user2['name'] in result.output

    # User3 is about to expire
    assert 'User %s will expire at' % user3['name'] in result.output
    assert 'Last activity: "%s"' % activity['activity_type'] in result.output
    assert 'Renewal access requested for %s' % user3['name'] in result.output

    # User4 is about to expire but ignored
    assert 'User %s will expire at' % user4['name'] in result.output
    assert 'No relevant activities: %s ignored' % user4['name'] in result.output

    # User5 already requested for renewal
    assert 'Renewal access not created for user %s' % user5['name'] in result.output

    assert '1 deleted' in result.output
    assert '1 renewal' in result.output
    assert '2 ignored' in result.output
