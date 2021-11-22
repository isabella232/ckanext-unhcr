import uuid
import factory
from ckan import model
from ckantoolkit.tests import factories
from ckanext.unhcr.utils import get_internal_domains
from ckanext.unhcr.models import Geography


def _generate_email(user):
    return "{0}@externaluser.com".format(user.name).lower()


class Geography(factory.Factory):
    class Meta:
        model = Geography

    globalid = factory.LazyAttribute(lambda obj: str(uuid.uuid1()).upper())
    pcode = 'BIHr000000043'
    iso3 = 'BIH'
    gis_name = 'Sarajevo'
    gis_status = 'active'
    layer = 'wrl_prp_p_unhcr_ALL'
    hierarchy_pcode = '20BIH002006004'

    @classmethod
    def _create(cls, target_class, *args, **kwargs):
        if args:
            assert False, "Positional args aren't supported, use keyword args."

        geog = target_class(**kwargs)
        model.Session.add(geog)
        model.Session.commit()
        model.Session.remove()
        return geog


class DataContainer(factories.Organization):

    type = 'data-container'
    country = ['SVN']
    geographic_area = 'southern_africa'
    visible_external = True


class Dataset(factories.Dataset):

    unit_of_measurement = 'individual'
    keywords = ['3', '4']
    archived = 'False'
    data_collector = 'ACF,UNHCR'
    data_collection_technique = 'f2f'
    sampling_procedure = 'nonprobability'
    operational_purpose_of_data = 'cartography'
    visibility = 'public'
    external_access_level = 'open_access'


class Resource(factories.Resource):

    type = 'data'
    file_type = 'microdata'
    identifiability = 'anonymized_public'
    date_range_start = '2018-01-01'
    date_range_end = '2019-01-01'
    process_status = 'anonymized'
    version = '1'
    visibility = 'public'


class DepositedDataset(factories.Dataset):

    type = 'deposited-dataset'
    owner_org = 'id-data-deposit'
    owner_org_dest = 'id-data-target'
    visibility = 'public'


class ExternalUser(factories.User):

    email = factory.LazyAttribute(_generate_email)
    focal_point = 'focal-point'
    default_containers = []


def _generate_internal_email(user):
    """Return an email address for the given User factory stub object."""

    internal_domain = get_internal_domains()[0]
    return "{0}@{1}".format(user.name, internal_domain).lower()


def _generate_plugin_extras(user):

    plugin_extras = {
        'saml2auth': {
            'saml_id': "saml_id_{}".format(user.name)
        }
    }

    return plugin_extras


def _generate_kobo_extras(user):

    plugin_extras = _generate_plugin_extras(user)
    plugin_extras.update({
        'unhcr': {
            'kobo_token': "test_kobo_token_{}".format(user.name)
        }
    })

    return plugin_extras


class InternalUser(factories.User):

    email = factory.LazyAttribute(_generate_internal_email)
    plugin_extras = factory.LazyAttribute(_generate_plugin_extras)


class InternalKoBoUser(InternalUser):

    plugin_extras = factory.LazyAttribute(_generate_kobo_extras)
