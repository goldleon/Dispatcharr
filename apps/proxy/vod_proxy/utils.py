"""
Utility functions for VOD proxy operations.
"""

import logging

from dispatcharr.utils import get_client_ip

logger = logging.getLogger(__name__)


def get_client_info(request):
    """
    Extract client IP and User-Agent from request.

    Args:
        request: Django HttpRequest object

    Returns:
        tuple: (client_ip, user_agent)
    """
    client_ip = get_client_ip(request) or "unknown"
    user_agent = request.META.get("HTTP_USER_AGENT", "unknown")

    return client_ip, user_agent
