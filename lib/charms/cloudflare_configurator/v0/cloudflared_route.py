# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

r"""# Interface Library for cloudflared_route.

This library wraps relation endpoints using the `cloudflared_route` interface
and provides a Python API for both requesting and providing cloudflared-route
integrations.

To get started using the library, you just need to fetch the library using `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.cloudflare_configurator.v0.cloudflared_route
```

In the `metadata.yaml` of the charm, add the following:

```yaml
requires:
    cloudflared-route:
        interface: cloudflared_route
```
"""

import logging
import typing

import ops

# The unique Charmhub library identifier, never change it
LIBID = "8a2a38667ef342cc86db1852f6c6cbfe"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 3

_TUNNEL_TOKEN_SECRET_ID_FIELD = "tunnel_token_secret_id"
_TUNNEL_TOKEN_SECRET_VALUE_FIELD = "tunnel-token"
DEFAULT_CLOUDFLARED_ROUTE_RELATION = "cloudflared-route"

logger = logging.getLogger(__name__)


class InvalidIntegration(ValueError):
    """Charm received invalid integration data."""


class CloudflaredRouteProvider(ops.Object):
    """cloudflared-route provider."""

    def __init__(
        self, charm: ops.CharmBase, relation_name: str = DEFAULT_CLOUDFLARED_ROUTE_RELATION
    ):
        self._charm = charm
        super().__init__(self._charm, relation_name)
        self.relation = charm.model.get_relation(relation_name)
        self.framework.observe(
            self._charm.on[relation_name].relation_broken, self._on_relation_broken
        )

    def set_tunnel_token(self, tunnel_token: str | None) -> None:
        """Update the cloudflared tunnel token in the integration data,
            no-op if there's no integration.

        Args:
            tunnel_token: The tunnel token to set in the integration. If set to None, the tunnel
                token will be removed from the integration data.
        """
        relation_data = self.relation.data[self._charm.app]
        secret_id = relation_data.get(_TUNNEL_TOKEN_SECRET_ID_FIELD)
        if tunnel_token is None:
            if secret_id:
                self._charm.model.get_secret(id=secret_id).remove_all_revisions()
            del relation_data[_TUNNEL_TOKEN_SECRET_VALUE_FIELD]
            return
        if not secret_id:
            secret = self._charm.app.add_secret({_TUNNEL_TOKEN_SECRET_VALUE_FIELD: tunnel_token})
            secret.grant(self.relation)
            relation_data[_TUNNEL_TOKEN_SECRET_ID_FIELD] = secret.id
        else:
            secret = self._charm.model.get_secret(id=secret_id)
            content = {_TUNNEL_TOKEN_SECRET_VALUE_FIELD: tunnel_token}
            if secret.get_content(refresh=True) != content:
                secret.set_content(content)

    def set_nameserver(self, nameserver: str | None) -> None:
        """Update the nameserver setting in the integration data.

        Args:
            nameserver: The nameserver used by the Cloudflared tunnel. If set to None, the
                nameserver will be removed from the integration data.
        """
        data = self.relation.data[self._charm.app]
        if nameserver:
            data["nameserver"] = nameserver
        else:
            del data["nameserver"]

    def _on_relation_broken(self, _: ops.RelationBrokenEvent):
        """Handle the relation-broken event"""
        self.set_tunnel_token(tunnel_token=None)


class CloudflaredRouteRequirer(ops.Object):
    """cloudflared-route requirer."""

    @classmethod
    def get_all(
        cls,
        charm: ops.CharmBase,
        relation_name: str = DEFAULT_CLOUDFLARED_ROUTE_RELATION,
    ) -> list[typing.Self]:
        """Retrieve all CloudflaredRouteRequirer objects for the cloudflared-route integration.

        This method generates a list of CloudflaredRouteRequirer instances,
        each corresponding to a cloudflared-route integration available.

        Args:
            charm: The charm instance.
            relation_name: The name of the relation.

        Returns:
            A list of CloudflaredRouteRequirer objects for each integration.
        """
        relations = charm.model.relations[relation_name]
        return [cls(charm=charm, relation=relation) for relation in relations]

    def __init__(self, charm: ops.CharmBase, relation: ops.Relation):
        """Instantiate the cloudflared-route requirer."""
        super().__init__(charm, f"{relation.name}-{relation.id}")
        self._charm = charm
        self.relation = relation

    def get_tunnel_token(self) -> str | None:
        """Get cloudflared tunnel-token from the integration data.

        Returns:
            cloudflared tunnel-token.

        Raises:
            InvalidIntegration: integration contains invalid data
        """
        relation_data = self.relation.data[self.relation.app]
        secret_id = relation_data.get(_TUNNEL_TOKEN_SECRET_ID_FIELD)
        if not secret_id:
            return None
        secret = self._charm.model.get_secret(id=secret_id)
        try:
            return secret.get_content(refresh=True)[_TUNNEL_TOKEN_SECRET_VALUE_FIELD]
        except KeyError as exc:
            raise InvalidIntegration(
                f"secret doesn't have '{_TUNNEL_TOKEN_SECRET_VALUE_FIELD}' field"
            ) from exc

    def get_nameserver(self) -> str | None:
        """Get the nameserver setting from the integration data.

        Returns:
            the nameserver that should be used by the Cloudflared tunnel.
        """
        return self.relation.data[self.relation.app].get("nameserver")
