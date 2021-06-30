# -*- coding: utf-8 -*-

from operator import itemgetter
from slugify import slugify
from sqlalchemy import and_, desc, func, select
import ckan.model as model
import ckan.plugins.toolkit as toolkit
from ckanext.unhcr.models import TimeSeriesMetric


def _get_timeseries_metric(field):
    sql = select([
        func.date(TimeSeriesMetric.timestamp).label('date'),
        getattr(TimeSeriesMetric, field)
    ]).order_by(
        TimeSeriesMetric.timestamp
    )
    result = model.Session.execute(sql).fetchall()
    dates = {}
    for row in result:
        # De-dupe on date. As long as we've ordered our query by timestamp,
        # we'll take the last value recorded on each date
        dates[row['date']] = row[field]
    return dates

def _get_facet_table(facet, context):
    data_dict = {
        'q': '*:*',
        'fq': "-type:deposited-dataset",
        'rows': 0,
        'facet.field': [facet],
        'facet.limit': 10,
        'include_private': True,
    }
    packages = toolkit.get_action('package_search')(context, data_dict)

    return sorted(
        packages['search_facets'][facet]['items'],
        key=itemgetter('count'),
        reverse=True,
    )


def get_datasets_by_date(context):
    title = 'Total number of Datasets'
    data_dict = {
        'q': '*:*',
        'rows': 0,
        'include_private': True,
    }
    datasets_total = toolkit.get_action('package_search')(
        context, dict(data_dict, fq='-type:deposited-dataset')
    )
    deposits_total = toolkit.get_action('package_search')(
        context, dict(data_dict, fq='type:deposited-dataset')
    )
    datasets = _get_timeseries_metric('datasets_count')
    deposits = _get_timeseries_metric('deposits_count')

    return {
        'type': 'timeseries_graph',
        'short_title': 'Datasets',
        'title': title,
        'id': slugify(title),
        'total': "{datasets} datasets / {deposits} deposits".format(
            datasets=datasets_total['count'],
            deposits=deposits_total['count']
        ),
        'data': [
            ['x'] + [str(date) for date in datasets.keys()],
            ['Datasets'] + [count for count in datasets.values()],
            ['Deposits'] + [count for count in deposits.values()],
        ],
    }

def get_datasets_by_downloads(context):
    activity_table = model.meta.metadata.tables['activity']
    package_table = model.meta.metadata.tables['package']
    join_obj = activity_table.join(
        package_table, package_table.c.id==activity_table.c.object_id
    )
    select_cols = (
        [c for c in package_table.columns] +
        [func.count(package_table.c.id).label('count')]
    )

    sql = select(
        select_cols
    ).select_from(
        join_obj
    ).where(
        and_(
            package_table.c.state == 'active',
            package_table.c.type != 'deposited-dataset',
            activity_table.c.activity_type == 'download resource',
        )
    ).group_by(
        package_table.c.id
    ).order_by(
        desc('count')
    ).limit(10)

    result = model.Session.execute(sql).fetchall()

    data = []
    for row in result:
        data.append({
            'display_name': row['title'],
            'link': toolkit.url_for('dataset.read', id=row['name']),
            'count': row['count'],
        })

    title = 'Datasets (by downloads)'
    return {
        'type': 'freq_table',
        'title': title,
        'id': slugify(title),
        'headers': ['Dataset', 'Downloads'],
        'data': data,
    }

def get_containers(context):
    data = _get_facet_table('organization', context)
    for row in data:
        row['link'] = toolkit.url_for('data-container.read', id=row['name'])

    title = 'Data Containers'
    return {
        'type': 'freq_table',
        'title': title,
        'id': slugify(title),
        'headers': ['Data Container', 'Datasets'],
        'data': data,
    }

def get_containers_by_date(context):
    title = 'Total number of Containers'
    dates = _get_timeseries_metric('containers_count')

    return {
        'type': 'timeseries_graph',
        'short_title': 'Containers',
        'title': title,
        'total': list(dates.values())[-1] if len(dates.values()) > 0 else None,
        'id': slugify(title),
        'data': [
            ['x'] + [str(date) for date in dates.keys()],
            ['Containers'] + [count for count in dates.values()],
        ],
    }

def get_tags(context):
    data = _get_facet_table('tags', context)
    for row in data:
        row['link'] = toolkit.url_for('dataset', tags=row['name'])

    title = 'Tags'
    return {
        'type': 'freq_table',
        'title': title,
        'id': slugify(title),
        'headers': ['Tag', 'Datasets'],
        'data': data,
    }

def get_keywords(context):
    data = _get_facet_table('vocab_keywords', context)
    for row in data:
        row['link'] = toolkit.url_for('dataset', vocab_keywords=row['name'])

    title = 'Keywords'
    return {
        'type': 'freq_table',
        'title': title,
        'id': slugify(title),
        'headers': ['Keyword', 'Datasets'],
        'data': data,
    }

def get_users_by_datasets(context):
    all_users = toolkit.get_action('user_list')(context, {})
    default_user = toolkit.get_action('get_site_user')({ 'ignore_auth': True })

    package_table = model.meta.metadata.tables['package']
    user_table = model.meta.metadata.tables['user']
    join_obj = user_table.join(
        package_table, package_table.c.creator_user_id == user_table.c.id
    )
    select_cols = (
        [c for c in user_table.columns] +
        [func.count(package_table.c.id).label('number_created_packages')]
    )

    sql = select(
        select_cols
    ).select_from(
        join_obj
    ).where(
        and_(
            package_table.c.state == 'active',
            package_table.c.type != 'deposited-dataset',
            user_table.c.name != default_user['name'],
        )
    ).group_by(
        user_table.c.id
    ).order_by(
        desc('number_created_packages')
    ).limit(10)

    result = model.Session.execute(sql).fetchall()

    data = []
    for row in result:
        data.append({
            'display_name': row['fullname'] if row['fullname'] else row['name'],
            'count': row['number_created_packages'],
            'link': toolkit.url_for('user.read', id=row['id']),
        })

    title = 'Users (by datasets created)'
    return {
        'type': 'freq_table',
        'short_title': 'Users',
        'title': title,
        'id': slugify(title),
        'total': len(all_users),
        'headers': ['User', 'Datasets Created'],
        'data': data,
    }

def get_users_by_downloads(context):
    default_user = toolkit.get_action('get_site_user')({ 'ignore_auth': True })
    activity_table = model.meta.metadata.tables['activity']
    package_table = model.meta.metadata.tables['package']
    user_table = model.meta.metadata.tables['user']
    join_obj = activity_table.join(
        package_table, package_table.c.id==activity_table.c.object_id
    ).join(
        user_table, user_table.c.id==activity_table.c.user_id
    )
    select_cols = (
        [c for c in user_table.columns] +
        [func.count(user_table.c.id).label('count')]
    )

    sql = select(
        select_cols
    ).select_from(
        join_obj
    ).where(
        and_(
            package_table.c.state == 'active',
            package_table.c.type != 'deposited-dataset',
            activity_table.c.activity_type == 'download resource',
            user_table.c.name != default_user['name'],
        )
    ).group_by(
        user_table.c.id
    ).order_by(
        desc('count')
    ).limit(10)

    result = model.Session.execute(sql).fetchall()

    data = []
    for row in result:
        data.append({
            'display_name': row['fullname'] if row['fullname'] else row['name'],
            'count': row['count'],
            'link': toolkit.url_for('user.read', id=row['id']),
        })

    title = 'Users (by downloads)'
    return {
        'type': 'freq_table',
        'title': title,
        'id': slugify(title),
        'headers': ['User', 'Downloads'],
        'data': data,
    }
