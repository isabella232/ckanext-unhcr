from ckan import model
from ckan.plugins import toolkit


def render_tree():
    '''Returns HTML for a hierarchy of all data containers'''
    context = {'model': model, 'session': model.Session}
    top_nodes = toolkit.get_action('group_tree')(
        context,
        data_dict={'type': 'data-container'})
    return _render_tree(top_nodes)


def _render_tree(top_nodes):
    html = '<ul class="hierarchy-tree-top">'
    for node in top_nodes:
        html += _render_tree_node(node)
    return html + '</ul>'


def _render_tree_node(node):
    html = '<a href="/data-container/{}">{}</a>'.format(
        node['name'], node['title'])
    if node['highlighted']:
        html = '<strong>{}</strong>'.format(html)
    if node['children']:
        html += '<ul class="hierarchy-tree">'
        for child in node['children']:
            html += _render_tree_node(child)
        html += '</ul>'
    html = '<li id="node_{}">{}</li>'.format(node['name'], html)
    return html
