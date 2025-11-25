# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for charm integration tests."""

import json
import pathlib
import textwrap

import juju.application
import juju.model
import pytest
import pytest_asyncio
from pytest_operator.plugin import OpsTest

PROJECT_BASE = pathlib.Path(__file__).parent.parent.parent.resolve()


@pytest.fixture(scope="module")
def model(ops_test) -> juju.model.Model:
    """Testing juju model."""
    assert ops_test.model
    return ops_test.model


@pytest_asyncio.fixture(scope="module")
async def cloudflare_configurator(
    ops_test: OpsTest, pytestconfig: pytest.Config
) -> juju.application.Application:
    """Deploy the charm together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # Deploy the charm and wait for active/idle status
    charm = pytestconfig.getoption("--charm-file")
    assert ops_test.model
    return await ops_test.model.deploy(f"./{charm}")


@pytest_asyncio.fixture(scope="module")
async def ingress_requirer(ops_test: OpsTest) -> juju.application.Application:
    """Deploy an ingress requirer using any-charm"""
    ingress_requirer_src = textwrap.dedent(
        """\
        import ops
        from ingress import IngressPerAppRequirer
        from any_charm_base import AnyCharmBase

        class AnyCharm(AnyCharmBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.ingress = IngressPerAppRequirer(self, port=8080)
                self.unit.status = ops.ActiveStatus()
        """
    )
    return await ops_test.model.deploy(
        "any-charm",
        "ingress-requirer",
        config={
            "src-overwrite": json.dumps(
                {
                    "any_charm.py": ingress_requirer_src,
                    "ingress.py": (
                        PROJECT_BASE / "lib/charms/traefik_k8s/v2/ingress.py"
                    ).read_text(),
                }
            ),
            "python-packages": "pydantic",
        },
        num_units=2,
        channel="latest/edge",
    )


@pytest_asyncio.fixture(scope="module")
async def cloudflared_route_requirer(ops_test: OpsTest) -> juju.application.Application:
    """Deploy a cloudflared-route requirer using any-charm."""
    src = textwrap.dedent(
        """\
        import ops
        from cloudflared_route import CloudflaredRouteRequirer
        from any_charm_base import AnyCharmBase

        class AnyCharm(AnyCharmBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.cloudflared_route = CloudflaredRouteRequirer(
                    charm=self,
                    relation_name="require-cloudflared-route"
                )
                self.unit.status = ops.ActiveStatus()

            def get_tunnel_tokens(self):
                return [
                    self.cloudflared_route.get_tunnel_token(relation)
                    for relation in self.model.relations["require-cloudflared-route"]
                ]
        """
    )
    return await ops_test.model.deploy(
        "any-charm",
        "cloudflared-route-requirer",
        config={
            "src-overwrite": json.dumps(
                {
                    "any_charm.py": src,
                    "cloudflared_route.py": (
                        PROJECT_BASE / "lib/charms/cloudflare_configurator/v0/cloudflared_route.py"
                    ).read_text(),
                }
            ),
        },
        num_units=2,
        channel="latest/edge",
    )
