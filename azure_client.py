"""Azure SDK client helpers for ThumbTack RI Coverage page.

Reads credentials from a local ``.env`` file and exposes async functions
that return plain Python dicts / lists.  All sync Azure SDK calls are run
through ``asyncio.to_thread`` so the helpers are safe to use in an async
application.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.reservations import AzureReservationAPI
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from msrest.exceptions import ClientException

# ------------------------------------------------------------------------------
# Env bootstrap
# ------------------------------------------------------------------------------
ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

logger = logging.getLogger("azure_client")

# ------------------------------------------------------------------------------
# Credential helpers
# ------------------------------------------------------------------------------
def _get_required_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


def _build_credential() -> ClientSecretCredential:
    """Return a ClientSecretCredential from environment variables."""
    return ClientSecretCredential(
        tenant_id=_get_required_env("AZURE_TENANT_ID"),
        client_id=_get_required_env("AZURE_CLIENT_ID"),
        client_secret=_get_required_env("AZURE_CLIENT_SECRET"),
    )


# ------------------------------------------------------------------------------
# Error handling decorator
# ------------------------------------------------------------------------------
def _graceful(msg: str):
    """Decorator that wraps sync Azure calls so auth / API errors are returned
    as dicts with an ``error`` key instead of raising and crashing the app."""

    def decorator(fn):
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await asyncio.to_thread(fn, *args, **kwargs)
            except ClientAuthenticationError as exc:
                logger.error("Azure auth error in %s: %s", fn.__name__, exc)
                return {"error": f"Azure authentication failed: {exc}"}
            except HttpResponseError as exc:
                logger.error("Azure API error in %s: %s", fn.__name__, exc)
                return {"error": f"Azure API error: {exc.message or str(exc)}"}
            except ClientException as exc:
                logger.error("Azure client error in %s: %s", fn.__name__, exc)
                return {"error": f"Azure client error: {exc}"}
            except Exception as exc:
                logger.error("Unexpected error in %s: %s", fn.__name__, exc)
                return {"error": f"Unexpected error: {exc}"}

        return wrapper

    return decorator


def _sub_from_id(resource_id: str | None) -> str | None:
    """Extract the subscription UUID from an Azure resource id."""
    if not resource_id:
        return None
    parts = resource_id.split("/")
    try:
        idx = parts.index("subscriptions")
        return parts[idx + 1] if idx + 1 < len(parts) else None
    except (ValueError, IndexError):
        return None


def _rg_from_id(resource_id: str | None) -> str | None:
    """Extract the resource group name from an Azure resource id."""
    if not resource_id:
        return None
    parts = resource_id.split("/")
    try:
        rg_index = parts.index("resourceGroups")
        return parts[rg_index + 1]
    except (ValueError, IndexError):
        return None


# ------------------------------------------------------------------------------
# 1. Reserved Instances
# ------------------------------------------------------------------------------
@_graceful("get_reserved_instances")
def _sync_get_reserved_instances(subscription_id: str) -> list[dict]:
    """Return active Reserved Instances with region, SKU, quantity, expiry date."""
    credential = _build_credential()
    client = AzureReservationAPI(credential=credential)

    items = client.reservation.list_all(selected_state="Active")
    out = []
    for res in items:
        props = res.properties
        if not props:
            continue
        # Filter by subscription if the reservation is scoped to one
        res_sub = _sub_from_id(res.id)
        applied = props.applied_scopes or []
        if subscription_id and res_sub != subscription_id and subscription_id not in applied:
            # Skip reservations not relevant to this subscription
            continue

        expiry = props.expiry_date
        expiry_str = expiry.isoformat() if expiry else None
        out.append(
            {
                "reservation_id": res.id or None,
                "subscription_id": res_sub or subscription_id or None,
                "name": res.display_name or props.display_name or None,
                "sku": res.sku.name if res.sku else None,
                "region": res.location or (applied[0] if applied else None),
                "quantity": props.quantity or 1,
                "expiry_date": expiry_str,
                "state": props.provisioning_state,
            }
        )
    return out


async def get_reserved_instances(subscription_id: str) -> list[dict]:
    return await _sync_get_reserved_instances(subscription_id)


# ------------------------------------------------------------------------------
# 2. Virtual Machines
# ------------------------------------------------------------------------------
@_graceful("get_virtual_machines")
def _sync_get_virtual_machines(subscription_id: str) -> list[dict]:
    """Return running VMs with name, region, size/SKU, resource group."""
    credential = _build_credential()
    client = ComputeManagementClient(credential=credential, subscription_id=subscription_id)

    out = []
    for vm in client.virtual_machines.list_all():
        # instance_view not populated by list_all; fetch per VM
        try:
            instance_view = client.virtual_machines.instance_view(
                resource_group_name=_rg_from_id(vm.id),
                vm_name=vm.name,
            )
            power_state = next(
                (
                    s.display_status
                    for s in instance_view.statuses
                    if s.code and s.code.startswith("PowerState/")
                ),
                None,
            )
        except Exception:
            power_state = None

        if power_state != "VM running":
            continue

        out.append(
            {
                "name": vm.name,
                "subscription_id": subscription_id,
                "region": vm.location,
                "size": vm.hardware_profile.vm_size if vm.hardware_profile else None,
                "resource_group": _rg_from_id(vm.id),
            }
        )
    return out


async def get_virtual_machines(subscription_id: str) -> list[dict]:
    return await _sync_get_virtual_machines(subscription_id)
