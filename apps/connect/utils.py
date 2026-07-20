# connect/utils.py
import logging
import string
from .models import EventSubscription, DeliveryLog, SUPPORTED_EVENTS
from .handlers.webhook import WebhookHandler
from .handlers.script import ScriptHandler
from apps.plugins.loader import PluginManager

logger = logging.getLogger(__name__)

HANDLERS = {
    "webhook": WebhookHandler,
    "script": ScriptHandler,
}


def _safe_render_template(template_str, payload):
    """Render a payload template using Python's string.Template (safe_substitute).

    This deliberately avoids Django's Template engine which exposes settings,
    model methods, and ORM traversal via {{ }} tags — a Server-Side Template
    Injection (SSTI) vector.

    string.Template only supports $variable and ${variable} substitution with
    no attribute access, method calls, or tag loading. safe_substitute() leaves
    unresolved placeholders intact instead of raising errors.
    """
    flat_payload = {}
    for k, v in (payload or {}).items():
        # Only expose scalar values; skip nested dicts/lists to prevent
        # accidental information leakage of complex objects.
        if isinstance(v, (str, int, float, bool)):
            flat_payload[str(k)] = str(v)
        elif v is None:
            flat_payload[str(k)] = ""
    tmpl = string.Template(template_str)
    return tmpl.safe_substitute(flat_payload)


def trigger_event(event_name, payload):
    if event_name not in SUPPORTED_EVENTS:
        logger.debug(f"Unsupported event '{event_name}' - skipping")
        return

    logger.debug(
        f"Triggering connect event: {event_name} payload_keys={list((payload or {}).keys())}"
    )
    subscriptions = EventSubscription.objects.filter(
        event=event_name, enabled=True
    ).select_related("integration")

    count = subscriptions.count()
    logger.info(f"Found {count} connect subscription(s) for event '{event_name}'")

    # First, fetch all subscriptions and trigger
    for sub in subscriptions:
        integration = sub.integration
        if not integration.enabled:
            logger.debug(
                f"Skipping disabled integration id={integration.id} name={integration.name}"
            )
            continue

        # apply optional payload template (only for webhook integrations)
        # Uses safe string.Template substitution — NOT Django's Template engine
        # which would allow SSTI via {{ settings.SECRET_KEY }} etc.
        final_payload = payload
        if integration.type == 'webhook' and sub.payload_template:
            try:
                final_payload = _safe_render_template(
                    sub.payload_template, payload
                )
            except Exception as e:
                logger.error(
                    f"Payload template render failed for subscription id={sub.id}: {e}"
                )
                final_payload = payload

        handler_cls = HANDLERS.get(integration.type)
        if not handler_cls:
            DeliveryLog.objects.create(
                subscription=sub,
                status="failed",
                request_payload=final_payload,
                error_message=f"No handler for integration type '{integration.type}'",
            )
            logger.error(
                f"No handler for integration type '{integration.type}' (integration id={integration.id})"
            )
            continue

        handler = handler_cls(integration, sub, final_payload)
        logger.debug(
            f"Executing handler type={integration.type} integration_id={integration.id} subscription_id={sub.id}"
        )

        try:
            result = handler.execute()
            DeliveryLog.objects.create(
                subscription=sub,
                status="success" if result.get("success") else "failed",
                request_payload=final_payload,
                response_payload=result,
            )
            logger.info(
                f"Connect delivery succeeded for subscription id={sub.id} integration '{integration.name}'"
            )
        except Exception as e:
            DeliveryLog.objects.create(
                subscription=sub,
                status="failed",
                request_payload=final_payload,
                error_message=str(e),
            )
            logger.error(
                f"Connect delivery failed for subscription id={sub.id} integration '{integration.name}': {e}"
            )

    pm = PluginManager.get()
    pm.discover_plugins(sync_db=False, use_cache=True, release_connections=False)
    handlers = list(pm.iter_actions_for_event(event_name))
    if not handlers:
        return

    from apps.plugins.models import PluginConfig

    handler_keys = {key for key, _ in handlers}
    enabled_keys = set(
        PluginConfig.objects.filter(enabled=True, key__in=handler_keys).values_list(
            "key", flat=True
        )
    )

    logger.debug(
        "Dispatching event '%s' to %d plugin action(s) (%d enabled)",
        event_name,
        len(handlers),
        len(enabled_keys),
    )
    params = {"event": event_name, "payload": payload}
    for key, action_id in handlers:
        if key not in enabled_keys:
            logger.debug(
                "Skipping disabled plugin id=%s for event '%s'", key, event_name
            )
            continue
        logger.debug(
            "Triggering plugin action for event '%s' on plugin id=%s action=%s",
            event_name,
            key,
            action_id,
        )
        try:
            pm.run_action(key, action_id, params)
        except Exception:
            logger.exception(
                "Plugin action failed for event '%s' on plugin id=%s action=%s",
                event_name,
                key,
                action_id,
            )
