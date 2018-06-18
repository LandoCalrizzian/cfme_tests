import pytest

from cfme.containers.provider import ContainersProvider, ContainersTestItem
from cfme.containers.node import Node, NodeCollection
from cfme.markers.env_markers.provider import providers
from cfme.utils.appliance.implementations.ui import navigate_to
from cfme.utils.providers import ProviderFilter
from cfme.utils.version import current_version

pytestmark = [
    pytest.mark.uncollectif(lambda provider: current_version() < "5.8"),
    pytest.mark.usefixtures('setup_provider'),
    pytest.mark.tier(1),
    pytest.mark.provider(gen_func=providers,
                         filters=[ProviderFilter(classes=[ContainersProvider],
                                                 required_flags=['cmqe_logging'])],
                         scope='function')]

TEST_ITEMS = [
    pytest.mark.polarion('CMP-10634')(ContainersTestItem(
        ContainersProvider, 'CMP-10634', collection_obj=None)),
    pytest.mark.polarion('CMP-10635')(ContainersTestItem(
        Node, 'CMP-10635', collection_obj=NodeCollection))
]

NUM_OF_DEFAULT_LOG_ROUTES = 2


@pytest.fixture(scope="function")
def kibana_logging_url(provider):
    """ This fixture verifies the correct setup of the Kibana logging namespace and returns
    the Kibana logging router url """

    # Get the Namespace of the Kibana project
    ose_pods = provider.mgmt.list_pods()
    for pod in ose_pods:
        if 'kibana' in pod.metadata.name:
            logging_project = pod.metadata.namespace
            break
        else:
            continue

    # Verify Pods are in the "Ready state"
    logging_pods = provider.mgmt.list_pods(namespace=logging_project)
    for logging_pod in logging_pods:
        if all(status.ready is True for status in logging_pod.status.container_statuses):
            continue
        else:
            pytest.skip("Logging pods are not in the 'Ready' state for provider {}".format(
                provider.name))

    all_logging_routes = provider.mgmt.list_route(namespace=logging_project)

    # To work correctly, two routes should be deployed, kibana and kibana-ops
    if len(all_logging_routes) >= NUM_OF_DEFAULT_LOG_ROUTES:
        pass
    else:
        pytest.skip("Missing logging routes for {}".format(provider.name))

    for route in all_logging_routes:
        # Kibana-ops router is what will be redirected to from the CFME appliance
        # In 3.5, only 'ops' is in the route, so check just for 'ops' not 'kibana-ops'
        if 'ops' in route.spec.host:
            kibana_router = route.spec.host
            break
    else:
        pytest.skip("Could not determine Kibana Router for provider {}".format(provider.name))

    return kibana_router


@pytest.mark.parametrize('test_item', TEST_ITEMS,
                         ids=[ContainersTestItem.get_pretty_id(ti) for ti in TEST_ITEMS])
def test_external_logging_activated(provider, appliance, test_item, kibana_logging_url):

    test_collection = ([provider] if test_item.obj is ContainersProvider
                       else test_item.collection_obj(appliance).all())

    for test_obj in test_collection:
        if not test_obj.exists:
            continue
        view = navigate_to(test_obj, 'Details')
        assert view.toolbar.monitoring.item_enabled('External Logging'), (
            "Monitoring --> External Logging not activated")
        view.toolbar.monitoring.item_select('External Logging')
        kibana_console = test_obj.vm_console
        kibana_console.switch_to_console()
        assert not view.is_displayed
        assert kibana_logging_url in appliance.server.browser.url
        kibana_console.close_console_window()
        assert view.is_displayed
        view.flash.assert_no_error()
