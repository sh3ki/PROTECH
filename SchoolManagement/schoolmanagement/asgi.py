"""
ASGI config for schoolmanagement project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import school.routing  # Import WebSocket routes from your app

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'schoolmanagement.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),  # Handles HTTP requests
    "websocket": AuthMiddlewareStack(
        URLRouter(
            school.routing.websocket_urlpatterns  # WebSocket routes
        )
    ),
})
