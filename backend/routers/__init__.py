"""Connect HTTP adapters to their feature implementations."""


def register_routers(app):
    from backend.profiles import storage, upload, service as profiles_service
    from backend.search import service as search_service
    from backend import configuration, pages as page_service
    from . import (
        uploads,
        searches,
        configuration as config_routes,
        pages,
        profile_searches,
    )

    from .experiments import router as experiments_router

    from .review_datasets import router as review_router

    app.include_router(review_router)
    app.include_router(experiments_router)
    app.include_router(storage.router)
    for router, service in (
        (uploads, upload),
        (profile_searches, profiles_service),
        (searches, search_service),
        (config_routes, configuration),
        (pages, page_service),
    ):
        app.include_router(router.build_router(service))
