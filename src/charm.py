#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# Learn more at: https://juju.is/docs/sdk

"""Cloudflared charm service."""

import json
import logging
import socket
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
        domain = self.config.get("domain")
        try:
            tunnel_token = self._get_tunnel_tokens()
        except InvalidConfig as exc:
            self.unit.status = ops.BlockedStatus(str(exc))
            self._cleanup()
            return
        if not (domain and tunnel_token):
            missing = []
            if not domain:
                missing.append("domain")
            if not tunnel_token:
                missing.append("tunnel-token")
            self.unit.status = ops.WaitingStatus(f"waiting for {', '.join(missing)} configuration")
            self._cleanup()
            return
        if not self._cloudflare_route.relation:
            self.unit.status = ops.WaitingStatus("waiting for cloudflared-route integration")
            self._cleanup()
            return
        self._cloudflare_route.set_tunnel_token(tunnel_token)
        self._cloudflare_route.set_nameserver(self.config.get("nameserver") or self._get_k8s_dns())
        if self._ingress.relations:
            self._ingress.publish_url(self._ingress.relations[0], f"https://{domain}")
        self.unit.status = ops.ActiveStatus()

    def _cleanup(self):
        if self._cloudflare_route.relation:
            self._cloudflare_route.set_nameserver(nameserver=None)
            self._cloudflare_route.set_tunnel_token(tunnel_token=None)
        self._unpublish_ingress_url()

    def _get_k8s_dns(self) -> str | None:
        """Retrieve the current k8s dns address being used.

        Returns:
            The address of the k8s dns.
        """
        try:
            return socket.gethostbyname("kube-dns.kube-system.svc")
        except socket.error:
            return None

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
