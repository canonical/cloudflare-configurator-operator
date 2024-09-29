#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests."""
import json
import logging

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(
    model, cloudflare_configurator, ingress_requirer, cloudflared_route_requirer
):
    """
    arrange: deploy the cloudflare-configurator charm with related charms.
    act: relate the cloudflare-configurator charm with related charms.
    assert: no error happens.
    """
    await model.integrate(f"{cloudflare_configurator.name}:ingress", ingress_requirer.name)
    await model.integrate(
        f"{cloudflare_configurator.name}:cloudflared-route", cloudflared_route_requirer.name
    )
    await model.wait_for_idle(
        apps=[
            cloudflare_configurator.name,
            ingress_requirer.name,
            cloudflared_route_requirer.name,
        ],
    )


async def test_set_tunnel_token(model, cloudflare_configurator, cloudflared_route_requirer):
    """
    arrange: deploy the cloudflare-configurator charm with related charms.
    act: set tunnel-token charm configuration of the cloudflare-configurator charm.
    assert: cloudflare-configurator charm pass the tunnel-token to cloudflared-route requirers.
    """
    secret_id = await model.add_secret(name="tunnel-token", data_args=["tunnel-token=foobar"])
    secret_id = secret_id.strip()
    await model.grant_secret("tunnel-token", cloudflare_configurator.name)
    await cloudflare_configurator.set_config({"domain": "example.com", "tunnel-token": secret_id})
    await model.wait_for_idle(status="active")
    action = await cloudflared_route_requirer.units[0].run_action(
        "rpc", method="get_tunnel_tokens"
    )
    await action.wait()
    assert json.loads(action.results["return"]) == ["foobar"]


async def test_get_ingress_data(model, cloudflare_configurator, ingress_requirer):
    """
    arrange: deploy the cloudflare-configurator charm with related charms.
    act: run get-ingress-data charm action.
    assert: get-ingress-data charm action dumps ingress integration data.
    """
    action = await cloudflare_configurator.units[0].run_action("get-ingress-data")
    await action.wait()
    ingress_data = json.loads(action.results["ingress"])
    assert ingress_data["application-data"]["model"] == model.name
    assert ingress_data["application-data"]["name"] == ingress_requirer.name
    assert len(ingress_data["unit-data"]) == len(ingress_requirer.units)
