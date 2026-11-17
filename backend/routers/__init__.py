"""Connect HTTP adapters to their feature implementations."""


def register_routers(app):
    from backend.profiles import storage, upload, service as profiles_service
    from backend.search import service as search_service
    from backend import configuration, pages as page_service, api_keys as key_service
    from . import (
        api_keys,
        uploads,
        searches,
        configuration as config_routes,
        pages,
        profile_searches,
    )

    from .playground import router as playground_router

    app.include_router(playground_router)
    app.include_router(storage.router)
    for router, service in (
        (uploads, upload),
        (profile_searches, profiles_service),
        (searches, search_service),
        (config_routes, configuration),
        (api_keys, key_service),
        (pages, page_service),
    ):
        app.include_router(router.build_router(service))
