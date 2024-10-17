#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# Learn more at: https://juju.is/docs/sdk

"""Cloudflared charm service."""

import json
import logging
import typing

import ops
from charms.cloudflare_configurator.v0.cloudflared_route import CloudflaredRouteProvider
from charms.traefik_k8s.v2.ingress import IngressPerAppProvider

logger = logging.getLogger(__name__)


class InvalidConfig(ValueError):
    """Raised when charm config is invalid."""


class CloudflareConfiguratorCharm(ops.CharmBase):
    """Cloudflare configurator charm service."""

    def __init__(self, *args: typing.Any):
        """Construct.

        Args:
            args: Arguments passed to the CharmBase parent constructor.
        """
        super().__init__(*args)
        self._cloudflare_route = CloudflaredRouteProvider(charm=self)
        self._ingress = IngressPerAppProvider(charm=self)
        self.framework.observe(self.on.config_changed, self._reconcile)
        self.framework.observe(self.on.secret_changed, self._reconcile)
        self.framework.observe(self._ingress.on.data_provided, self._reconcile)
        self.framework.observe(self.on["cloudflared-route"].relation_changed, self._reconcile)
        self.framework.observe(self.on.get_ingress_data_action, self._on_get_ingress_data_action)

    def _reconcile(self, _: ops.EventBase) -> None:
        """Handle changed configuration."""
        if not self.unit.is_leader():
            self.unit.status = ops.BlockedStatus(
                "this charm only supports a single unit, please remove the additional units "
                f"using `juju scale-application {self.app.name} 1`"
            )
            return
        self.unit.status = ops.ActiveStatus()
        domain = self.config.get("domain")
        try:
            tunnel_token = self._get_tunnel_tokens()
        except InvalidConfig as exc:
            self.unit.status = ops.BlockedStatus(str(exc))
            return
        if not (domain and tunnel_token):
            missing = []
            if not domain:
                missing.append("domain")
            if not tunnel_token:
                missing.append("tunnel-token")
            self.unit.status = ops.BlockedStatus(f"waiting for {', '.join(missing)} configuration")
            self._unpublish_ingress_url()
            return
        if relation := self.model.get_relation("cloudflared-route"):
            self._cloudflare_route.set_tunnel_token(tunnel_token, relation=relation)
            self._cloudflare_route.set_nameserver(self.config.get("nameserver"), relation=relation)
            if self._ingress.relations:
                self._ingress.publish_url(self._ingress.relations[0], f"https://{domain}")
        else:
            self._unpublish_ingress_url()

    def _unpublish_ingress_url(self) -> None:
        """Unpublish ingress url."""
        if self._ingress.relations:
            self._ingress.wipe_ingress_data(self._ingress.relations[0])

    def _get_tunnel_tokens(self) -> str | None:
        """Receive tunnel tokens from charm configuration.

        Returns:
            Cloudflared tunnel token.

        Raises:
            InvalidConfig: If tunnel-token config is invalid.
        """
        secret_id = typing.cast(str, self.config.get("tunnel-token"))
        if secret_id:
            secret = self.model.get_secret(id=secret_id)
            secret_value = secret.get_content(refresh=True).get("tunnel-token")
            if secret_value is None:
                raise InvalidConfig(f"missing 'tunnel-token' in juju secret: {secret_id}")
            return secret_value
        return None

    def _on_get_ingress_data_action(self, event: ops.ActionEvent) -> None:
        """Handle get-ingress-data action.

        Args:
            event: Action event.
        """
        if not self._ingress.relations:
            event.fail("no ingress relation")
            return
        relation = self._ingress.relations[0]
        data = self._ingress.get_data(relation)
        event.set_results(
            {
                "ingress": json.dumps(
                    {
                        "application-data": data.app.model_dump(),
                        "unit-data": sorted(
                            [unit.model_dump() for unit in data.units],
                            key=lambda unit: unit["host"],
                        ),
                    }
                )
            }
        )


if __name__ == "__main__":  # pragma: nocover
    ops.main.main(CloudflareConfiguratorCharm)
