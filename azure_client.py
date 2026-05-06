"""Azure SDK client helpers for ThumbTack RI Coverage page.

Reads credentials from a local ``.env`` file and exposes async functions
that return plain Python dicts / lists.  All sync Azure SDK calls are run
through ``asyncio.to_thread`` so the helpers are safe to use in an async
application.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

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


# ------------------------------------------------------------------------------
# 3. Cost Management — Top Spenders
# ------------------------------------------------------------------------------
@_graceful("get_top_spenders")
def _sync_get_top_spenders(
    subscription_id: str, lookback_days: int = 30, top_n: int = 50
) -> dict:
    """Query Azure Cost Management API for top spenders by resource group and service."""
    credential = _build_credential()
    token = credential.get_token("https://management.azure.com/.default")
    headers = {
        "Authorization": f"Bearer {token.token}",
        "Content-Type": "application/json",
    }
    end = datetime.date.today()
    start = end - datetime.timedelta(days=lookback_days)
    base_url = f"https://management.azure.com/subscriptions/{subscription_id}"

    def _fetch(dimension_name: str) -> list[dict]:
        body = {
            "type": "Usage",
            "timeframe": "Custom",
            "timePeriod": {"from": start.isoformat(), "to": end.isoformat()},
            "dataset": {
                "granularity": "None",
                "aggregation": {
                    "totalCost": {"name": "PreTaxCost", "function": "Sum"}
                },
                "grouping": [{"type": "Dimension", "name": dimension_name}],
                "sorting": [{"direction": "descending", "name": "PreTaxCost"}],
            },
        }
        url = f"{base_url}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
        rsp = requests.post(url, headers=headers, json=body, timeout=60)
        rsp.raise_for_status()
        data = rsp.json()
        props = data.get("properties", {})
        cols = [c.get("name") for c in props.get("columns", [])]
        rows = props.get("rows", [])
        name_idx = next((i for i, n in enumerate(cols) if n == dimension_name), 0)
        cost_idx = next((i for i, n in enumerate(cols) if n == "PreTaxCost"), 1)
        out: list[dict] = []
        for row in rows:
            try:
                name = row[name_idx] or "Uncategorized"
                cost_val = row[cost_idx]
                cost = float(cost_val) if cost_val is not None else 0.0
            except (IndexError, TypeError, ValueError):
                continue
            out.append({"name": name, "cost": round(cost, 2)})
        return out

    return {
        "by_resource_group": _fetch("ResourceGroup")[:top_n],
        "by_service": _fetch("MeterCategory")[:top_n],
    }


async def get_top_spenders(
    subscription_id: str, *, lookback_days: int = 30, top_n: int = 50
) -> dict:
    return await _sync_get_top_spenders(subscription_id, lookback_days, top_n)
