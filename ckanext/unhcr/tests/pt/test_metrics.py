import json
import pytest
from pathlib import Path
from ckantoolkit.tests import factories as core_factories
from ckanext.unhcr.tests import factories
from ckanext.unhcr.activity import create_download_activity
import ckanext.unhcr.metrics as metrics


def _load_keywords():
    schema_path = Path(__file__).parent.parent.parent / 'schemas' / 'dataset.json'
    with open(schema_path) as f:
        schema = json.load(f)
    choices = [
        field for field in schema['dataset_fields']
        if field['field_name'] == 'keywords'
    ][0]['choices']
    return {choice['label']: choice['value'] for choice in choices}

KEYWORDS = _load_keywords()


@pytest.mark.usefixtures('clean_db', 'clean_index', 'unhcr_migrate')
class TestMetrics:
    def setup(self):
        self.target = factories.DataContainer(id='data-target', title='Target')
        self.deposit_container = factories.DataContainer(
            id='data-deposit',
            name='data-deposit',
        )
        self.deposit_dataset = factories.DepositedDataset(
            owner_org='data-deposit',
            owner_org_dest=self.target['id'],
            title='deposit',
            tags=[{'name': 'foobar'}],
            keywords=[KEYWORDS['Water Sanitation Hygiene']],
        )
        self.deposit_resource = factories.Resource(
            package_id=self.deposit_dataset['id'],
            url_type='upload',
        )

        self.sysadmin = core_factories.Sysadmin()
        self.containers = [
            factories.DataContainer(title='Container1'),
            factories.DataContainer(title='Container1')
        ]
        self.users = [
            core_factories.User(fullname='User1'),
            core_factories.User(fullname='User2'),
        ]
        self.datasets = [
            factories.Dataset(
                user=self.sysadmin,
                tags=[{'name': 'economy'}, {'name': 'health'}, {'name': 'environment'}],
                keywords=[
                    KEYWORDS['Protection'],
                    KEYWORDS['Food Security'],
                    KEYWORDS['Emergency Shelter and NFI']
                ],
                owner_org=self.containers[0]['id'],
            ),
            factories.Dataset(
                user=self.users[0],
                tags=[{'name': 'health'}, {'name': 'environment'}],
                keywords=[KEYWORDS['Food Security'], KEYWORDS['Emergency Shelter and NFI']],
                owner_org=self.containers[0]['id'],
            ),
            factories.Dataset(
                user=self.users[0],
                tags=[{'name': 'health'}],
                keywords=[KEYWORDS['Food Security']],
                owner_org=self.containers[0]['id'],
            ),
            factories.Dataset(
                user=self.users[0],
                keywords=[KEYWORDS['Food Security']],
                owner_org=self.containers[1]['id'],
            ),
        ]
        self.resources = [
            factories.Resource(package_id=self.datasets[0]['id'], url_type='upload'),
            factories.Resource(package_id=self.datasets[0]['id'], url_type='upload'),

            factories.Resource(package_id=self.datasets[1]['id'], url_type='upload'),

            factories.Resource(package_id=self.datasets[2]['id'], url_type='upload'),
        ]

        create_download_activity({'user': self.sysadmin['name']}, self.resources[0]['id'])
        create_download_activity({'user': self.users[0]['name']}, self.resources[1]['id'])

        create_download_activity({'user': self.sysadmin['name']}, self.resources[2]['id'])
        create_download_activity({'user': self.users[0]['name']}, self.resources[2]['id'])
        create_download_activity({'user': self.users[0]['name']}, self.resources[2]['id'])

        create_download_activity({'user': self.sysadmin['name']}, self.deposit_resource['id'])


    def test_get_containers(self):
        table = metrics.get_containers({'user': self.sysadmin['name']})

        assert table['type'] == 'freq_table'
        assert table['title'] == 'Data Containers'
        assert table['id'] == 'data-containers'
        assert table['headers'] == ['Data Container', 'Datasets']

        assert len(table['data']) == 2
        assert table['data'][0]['display_name'] == self.containers[0]['title']
        assert table['data'][0]['count'] == 3
        assert table['data'][1]['display_name'] == self.containers[1]['title']
        assert table['data'][1]['count'] == 1
        assert (
            self.deposit_dataset['title'] not in
            [row['display_name'] for row in table['data']]
        )
        assert (
            self.target['title'] not in
            [row['display_name'] for row in table['data']]
        )

    def test_get_datasets_by_downloads(self):
        table = metrics.get_datasets_by_downloads({'user': self.sysadmin['name']})

        assert table['type'] == 'freq_table'
        assert table['title'] == 'Datasets (by downloads)'
        assert table['id'] == 'datasets-by-downloads'
        assert table['headers'] == ['Dataset', 'Downloads']

        assert len(table['data']) == 2
        assert table['data'][0]['display_name'] == self.datasets[0]['title']
        assert table['data'][0]['count'] == 3
        assert table['data'][1]['display_name'] == self.datasets[1]['title']
        assert table['data'][1]['count'] == 2
        assert (
            self.deposit_dataset['title'] not in
            [row['display_name'] for row in table['data']]
        )

    def test_get_tags(self):
        table = metrics.get_tags({'user': self.sysadmin['name']})

        assert table['type'] == 'freq_table'
        assert table['title'] == 'Tags'
        assert table['id'] == 'tags'
        assert table['headers'] == ['Tag', 'Datasets']

        assert len(table['data']) == 3
        assert table['data'][0]['display_name'] == 'health'
        assert table['data'][0]['count'] == 3
        assert table['data'][1]['display_name'] == 'environment'
        assert table['data'][1]['count'] == 2
        assert table['data'][2]['display_name'] == 'economy'
        assert table['data'][2]['count'] == 1
        assert(
            'foobar' not in
            [row['display_name'] for row in table['data']]
        )

    def test_get_keywords(self):
        table = metrics.get_keywords({'user': self.sysadmin['name']})

        assert table['type'] == 'freq_table'
        assert table['title'] == 'Keywords'
        assert table['id'] == 'keywords'
        assert table['headers'] == ['Keyword', 'Datasets']

        assert len(table['data']) == 3
        assert table['data'][0]['display_name'] == 'Food Security'
        assert table['data'][0]['count'] == 4
        assert table['data'][1]['display_name'] == 'Emergency Shelter and NFI'
        assert table['data'][1]['count'] == 2
        assert table['data'][2]['display_name'] == 'Protection'
        assert table['data'][2]['count'] == 1
        assert (
            'Water Sanitation Hygiene' not in
            [row['display_name'] for row in table['data']]
        )

    def test_get_users_by_datasets(self):
        table = metrics.get_users_by_datasets({'user': self.sysadmin['name']})

        assert table['type'] == 'freq_table'
        assert table['title'] == 'Users (by datasets created)'
        assert table['id'] == 'users-by-datasets-created'
        assert table['headers'] == ['User', 'Datasets Created']

        assert len(table['data']) == 2
        assert table['data'][0]['display_name'] == self.users[0]['fullname']
        assert table['data'][0]['count'] == 3
        assert table['data'][1]['display_name'] == self.sysadmin['fullname']
        assert table['data'][1]['count'] == 1
        assert(
            self.users[1]['fullname'] not in
            [row['display_name'] for row in table['data']]
        )

    def test_get_users_by_downloads(self):
        table = metrics.get_users_by_downloads({'user': self.sysadmin['name']})

        assert table['type'] == 'freq_table'
        assert table['title'] == 'Users (by downloads)'
        assert table['id'] == 'users-by-downloads'
        assert table['headers'] == ['User', 'Downloads']

        assert len(table['data']) == 2
        assert table['data'][0]['display_name'] == self.users[0]['fullname']
        assert table['data'][0]['count'] == 3
        assert table['data'][1]['display_name'] == self.sysadmin['fullname']
        assert table['data'][1]['count'] == 2
        assert(
            self.users[1]['fullname'] not in
            [row['display_name'] for row in table['data']]
        )
