"""
Utility functions for VOD proxy operations.
"""

import logging

logger = logging.getLogger(__name__)


def get_client_info(request):
    """
    Extract client IP and User-Agent from request.

    Args:
        request: Django HttpRequest object

    Returns:
        tuple: (client_ip, user_agent)
    """
    # Get client IP, checking for proxy headers
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR')
    if client_ip:
        # Take the first IP if there are multiple (comma-separated)
        client_ip = client_ip.split(',')[0].strip()
    else:
        client_ip = request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR', 'unknown')

    # Get User-Agent
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')

    return client_ip, user_agent
