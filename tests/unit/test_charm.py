# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=duplicate-code,missing-function-docstring

"""Unit tests."""

import json

import ops
import ops.testing
import pytest

from src.charm import CloudflareConfiguratorCharm


def test_cloudflared_route_tunnel_token():
    """
    arrange: create a scenario with proper config and an integration with a cloudflared-route
        requirer.
    act: run the config-changed event
    assert: tunnel-token should be passed to the cloudflared-route requirer correctly.
    """
    context = ops.testing.Context(CloudflareConfiguratorCharm)
    cloudflared_route_relation = ops.testing.Relation(endpoint="cloudflared-route")
    secret = ops.testing.Secret(tracked_content={"tunnel-token": "foobar"})

    out = context.run(
        context.on.config_changed(),
        ops.testing.State(
            leader=True,
            config={"domain": "example.com", "tunnel-token": secret.id},
            relations=[cloudflared_route_relation],
            secrets=[secret],
        ),
    )

    local_app_data = out.get_relation(cloudflared_route_relation.id).local_app_data
    assert (
        out.get_secret(id=local_app_data["tunnel_token_secret_id"]).tracked_content["tunnel-token"]
        == "foobar"
    )


def test_publish_ingress_url():
    """
    arrange: create a scenario with proper config and an integration with a ingress requirer.
    act: run the config-changed event
    assert: ingress url should be set in the ingress integration.
    """
    context = ops.testing.Context(CloudflareConfiguratorCharm)
    ingress_relation = ops.testing.Relation(endpoint="ingress")
    cloudflared_route_relation = ops.testing.Relation(endpoint="cloudflared-route")
    secret = ops.testing.Secret(tracked_content={"tunnel-token": "foobar"})

    out = context.run(
        context.on.config_changed(),
        ops.testing.State(
            leader=True,
            config={"domain": "example.com", "tunnel-token": secret.id},
            relations=[ingress_relation, cloudflared_route_relation],
            secrets=[secret],
        ),
    )

    assert (
        out.get_relation(ingress_relation.id).local_app_data["ingress"]
        == '{"url": "https://example.com/"}'
    )


def test_get_ingress_data_action():
    """
    arrange: create a scenario with proper config and an integration with a ingress requirer.
    act: run the get-ingress-data action
    assert: get-ingress-data action should dump all ingress integration data.
    """
    context = ops.testing.Context(CloudflareConfiguratorCharm)
    ingress_relation = ops.testing.Relation(
        endpoint="ingress",
        remote_app_data={
            "name": json.dumps("example"),
            "model": json.dumps("example-model"),
            "port": json.dumps(8080),
        },
        remote_units_data={
            0: {"host": json.dumps("example-host-0"), "ip": json.dumps("10.0.0.1")},
            1: {"host": json.dumps("example-host-1"), "ip": json.dumps("10.0.0.2")},
        },
    )

    context.run(
        context.on.action("get-ingress-data"), ops.testing.State(relations=[ingress_relation])
    )

    assert json.loads(context.action_results.get("ingress")) == {
        "application-data": {
            "model": "example-model",
            "name": "example",
            "port": 8080,
            "redirect_https": False,
            "scheme": "http",
            "strip_prefix": False,
        },
        "unit-data": [
            {"host": "example-host-0", "ip": "10.0.0.1"},
            {"host": "example-host-1", "ip": "10.0.0.2"},
        ],
    }


def test_get_ingress_data_action_no_ingress():
    """
    arrange: create a scenario without integration with ingress requirer.
    act: run the get-ingress-data action
    assert: get-ingress-data action should fail.
    """
    context = ops.testing.Context(CloudflareConfiguratorCharm)

    with pytest.raises(ops.testing.ActionFailed):
        context.run(context.on.action("get-ingress-data"), ops.testing.State())


def test_non_leader():
    """
    arrange: create a scenario where the charm unit is not the leader.
    act: run the config-changed event
    assert: charm should enter the blocked state.
    """
    context = ops.testing.Context(CloudflareConfiguratorCharm)

    out = context.run(context.on.config_changed(), ops.testing.State(leader=False))

    assert out.unit_status == ops.testing.BlockedStatus(
        "this charm only supports a single unit, please remove the additional units using "
        "`juju scale-application cloudflare-configurator 1`"
    )


def test_no_domain_config():
    """
    arrange: create a scenario without the `domain` charm config.
    act: run the config-changed event
    assert: charm should enter the blocked state.
    """
    context = ops.testing.Context(CloudflareConfiguratorCharm)
    cloudflared_route_relation = ops.testing.Relation(endpoint="cloudflared-route")
    secret = ops.testing.Secret(tracked_content={"tunnel-token": "foobar"})
    config = {"tunnel-token": secret.id}

    out = context.run(
        context.on.config_changed(),
        ops.testing.State(
            leader=True,
            config=config,
            relations=[cloudflared_route_relation],
            secrets=[secret],
        ),
    )

    assert out.unit_status == ops.testing.BlockedStatus("waiting for domain configuration")


def test_no_tunnel_token_config():
    """
    arrange: create a scenario without the `tunnel-token` charm config.
    act: run the config-changed event
    assert: charm should enter the blocked state.
    """
    context = ops.testing.Context(CloudflareConfiguratorCharm)
    cloudflared_route_relation = ops.testing.Relation(endpoint="cloudflared-route")
    config = {"domain": "example.com"}

    out = context.run(
        context.on.config_changed(),
        ops.testing.State(
            leader=True,
            config=config,
            relations=[cloudflared_route_relation],
        ),
    )

    assert out.unit_status == ops.testing.BlockedStatus("waiting for tunnel-token configuration")


def test_unpublish_ingress_url():
    """
    arrange: create a scenario without the integration with cloudflared-route requirer.
    act: run the config-changed event
    assert: ingress url should be removed from the ingress integration.
    """
    context = ops.testing.Context(CloudflareConfiguratorCharm)
    secret = ops.testing.Secret(tracked_content={"tunnel-token": "foobar"})
    config = {"domain": "example.com", "tunnel-token": secret.id}
    ingress_relation = ops.testing.Relation(
        endpoint="ingress", local_app_data={"ingress": '{"url": "https://example.com/"}'}
    )

    out = context.run(
        context.on.config_changed(),
        ops.testing.State(
            leader=True,
            config=config,
            secrets=[secret],
            relations=[ingress_relation],
        ),
    )

    assert not out.get_relation(ingress_relation.id).local_app_data.get("ingress")


def test_invalid_tunnel_token_config():
    """
    arrange: create a scenario with an invalid tunnel-token configuration.
    act: run the config-changed event
    assert: charm should enter the blocked state.
    """
    context = ops.testing.Context(CloudflareConfiguratorCharm)
    cloudflared_route_relation = ops.testing.Relation(endpoint="cloudflared-route")
    secret = ops.testing.Secret(tracked_content={"foobar": "foobar"})
    config = {"domain": "example.com", "tunnel-token": secret.id}

    out = context.run(
        context.on.config_changed(),
        ops.testing.State(
            leader=True,
            config=config,
            secrets=[secret],
            relations=[cloudflared_route_relation],
        ),
    )

    assert out.unit_status == ops.testing.BlockedStatus(
        f"missing 'tunnel-token' in juju secret: {secret.id}"
    )
