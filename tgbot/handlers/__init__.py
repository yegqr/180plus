"""Import all routers and add them to routers_list."""
from .admin import admin_router
from .admin import admin_router
from .user import user_router
from .join_request import join_router
from .error import error_router

routers_list = [
    admin_router,
    user_router,
    join_router,
    error_router,
]

__all__ = [
    "routers_list",
]
