"""Bounded regional model inventory; listing does not establish inference access."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re

from .project import FlowError, load_project, redact
from .remote import signer_for


_MAX_PAGES = 20
_MAX_ITEMS = 2000


def _metadata(model):
    result = {}
    for field, wire in (("id", "id"), ("display_name", "displayName"), ("vendor", "vendor"),
                        ("version", "version"), ("lifecycle_state", "lifecycleState"), ("type", "type")):
        value = getattr(model, field, None)
        if value is not None:
            if not isinstance(value, str) or len(value) > 4096:
                raise FlowError("Model inventory returned invalid metadata")
            result[wire] = value
    if not result.get("id") or not result.get("lifecycleState"):
        raise FlowError("Model inventory returned incomplete model identity or lifecycle")
    capabilities = getattr(model, "capabilities", None)
    if capabilities is not None:
        if (not isinstance(capabilities, list) or len(capabilities) > 100
                or any(not isinstance(value, str) or len(value) > 255 for value in capabilities)):
            raise FlowError("Model inventory returned invalid capabilities")
        result["capabilities"] = capabilities
    for field, wire in (("time_deprecated", "timeDeprecated"),
                        ("time_on_demand_retired", "timeOnDemandRetired"),
                        ("time_dedicated_retired", "timeDedicatedRetired")):
        value = getattr(model, field, None)
        if value is not None:
            if not isinstance(value, (date, datetime)):
                raise FlowError("Model inventory returned an invalid retirement date")
            result[wire] = value.isoformat()
    for field, wire in (("model_deprecated", "modelDeprecated"),
                        ("is_long_term_supported", "isLongTermSupported")):
        value = getattr(model, field, None)
        if value is not None:
            if not isinstance(value, bool):
                raise FlowError("Model inventory returned invalid lifecycle metadata")
            result[wire] = value
    return redact(result)


def _model_pages(client, compartment, region, limit, retry):
    items, page, visited, identities = [], None, set(), set()
    for page_count in range(1, _MAX_PAGES + 1):
        options = {"limit": limit, "retry_strategy": retry}
        if page is not None:
            options["page"] = page
        response = client.list_models(compartment, **options)
        batch = getattr(response.data, "items", None)
        if not isinstance(batch, list) or len(batch) > limit or len(items) + len(batch) > _MAX_ITEMS:
            raise FlowError("Model inventory exceeded its bounded size or returned an invalid page")
        for model in batch:
            item = _metadata(model)
            if item["id"] in identities:
                raise FlowError("Model inventory repeated a model identity; repeat the bounded read")
            identities.add(item["id"])
            items.append(item)
        headers = {str(key).lower(): value for key, value in response.headers.items()}
        page = headers.get("opc-next-page")
        if page is None or page == "":
            return {"region": region, "items": items, "complete": True, "pageCount": page_count,
                    "inference_checked": False, "model_selected": False, "configuration_changed": False}
        if not isinstance(page, str) or len(page) > 1024 or page in visited:
            raise FlowError("Model inventory returned invalid or repeated pagination state")
        visited.add(page)
    raise FlowError("Model inventory exceeded its page bound; listing is incomplete")


def list_models(root, limit=100):
    """Read all bounded pages; never select, invoke or change a model.

    ``limit`` is the page size. Incomplete listings fail instead of hiding rows.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise FlowError("Model page size must be an integer from 1 to 1000")
    root, project = load_project(root)
    settings, auth = project.get("model", {}), project.get("oci", {})
    region, compartment = settings.get("region", ""), settings.get("compartment_id", "")
    if not isinstance(region, str) or not re.fullmatch(r"[a-z]+(?:-[a-z]+)+-\d+", region):
        raise FlowError("Select the model's OCI region before listing models")
    if (not isinstance(compartment, str) or not compartment or len(compartment) > 500
            or any(character.isspace() for character in compartment)):
        raise FlowError("Select the OCI compartment before listing models")
    config_file = Path(auth.get("config_file", ".oci/config")).expanduser()
    if not config_file.is_absolute():
        config_file = root / config_file
    client = None
    try:
        import oci

        config = oci.config.from_file(str(config_file), auth.get("profile", "DEFAULT"))
        retry = oci.retry.NoneRetryStrategy()
        client = oci.generative_ai.GenerativeAiClient(
            {**config, "region": region}, signer=signer_for(config),
            retry_strategy=retry, timeout=(5, 60))
        return _model_pages(client, compartment, region, limit, retry)
    except FlowError:
        raise
    except Exception:
        raise FlowError("OCI model inventory failed; verify the selected profile, region and compartment access") from None
    finally:
        if client is not None:
            client.base_client.session.close()
