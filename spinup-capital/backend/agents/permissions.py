"""
PERMISSION ENFORCEMENT — the architectural guarantee, made real.

Previously, agent permissions (e.g. ["market_data", "options_data",
"trading:propose"]) existed only as descriptive strings sitting on an
AgentSpec — nothing ever actually checked them. This module turns that
into a hard runtime gate: every role in the firm has an explicit, named
scope, and any attempt to exercise a scope the caller doesn't hold raises
PermissionDenied instead of silently proceeding.

This is what lets us say, concretely rather than narratively: "the Bull/
Bear desk and the Risk Governor literally cannot place a trade" — because
if anything ever tried to route a trade through their role, this module
refuses it before it reaches the broker.
"""
from __future__ import annotations
from typing import Iterable, Optional

# The firm's access-control matrix (spec section 10), made literal instead
# of a table in a document. `execution_gateway` is the ONLY role that ever
# holds `trading:execute` — no specialist template grants it, by design.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "managing_partner":  {"market_data", "options_data", "account:read"},
    "specialist":        {"market_data", "options_data", "trading:propose"},
    "bull_bear":         {"market_data", "options_data"},
    "risk_governor":     {"market_data", "options_data", "account:read"},
    "execution_gateway": {"market_data", "options_data", "trading:execute", "account:read", "account:write"},
    "talent_agent":      {"account:read"},
}


class PermissionDenied(PermissionError):
    def __init__(self, role: str, permission: str, held: Optional[set[str]] = None):
        scope = sorted(held if held is not None else ROLE_PERMISSIONS.get(role, set()))
        super().__init__(
            f"'{role}' does not hold the '{permission}' permission — request refused. "
            f"Held permissions: {scope}"
        )
        self.role = role
        self.permission = permission
        self.held = sorted(held if held is not None else ROLE_PERMISSIONS.get(role, set()))


def require(role: str, permission: str, held: Optional[Iterable[str]] = None) -> None:
    """
    Raise PermissionDenied unless `role` holds `permission`.

    Pass `held` when checking an actual agent *instance's* stored
    permission list (e.g. from the database) rather than the role's
    default template scope — this is what lets a probation agent with a
    narrower grant fail a check that a senior agent of the same role
    would pass.
    """
    scope = set(held) if held is not None else ROLE_PERMISSIONS.get(role, set())
    if permission not in scope:
        raise PermissionDenied(role, permission, scope)


def can(role: str, permission: str, held: Optional[Iterable[str]] = None) -> bool:
    try:
        require(role, permission, held)
        return True
    except PermissionDenied:
        return False


def matrix() -> dict:
    """Serializable view of the access-control matrix for the dashboard."""
    all_perms = sorted({p for scope in ROLE_PERMISSIONS.values() for p in scope})
    return {
        "permissions": all_perms,
        "roles": [
            {"role": role, "granted": sorted(scope)}
            for role, scope in ROLE_PERMISSIONS.items()
        ],
    }
