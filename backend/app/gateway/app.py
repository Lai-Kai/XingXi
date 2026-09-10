import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.gateway.auth_disabled import warn_if_auth_disabled_enabled
from app.gateway.auth_middleware import AuthMiddleware
from app.gateway.config import get_gateway_config
from app.gateway.csrf_middleware import CSRFMiddleware, get_configured_cors_origins
from app.gateway.deps import langgraph_runtime
from app.gateway.errors import gateway_error_response
from app.gateway.routers import (
    artifacts,
    assistants_compat,
    auth,
    channel_connections,
    channels,
    console,
    corpus_imports,
    entities,  # noqa: F401
    features,
    feedback,
    github_webhooks,
    input_polish,
    knowledge_graph,
    knowledge_releases,
    knowledge_search,
    map_points,  # noqa: F401
    mcp,
    memory,
    models,
    operations,
    public_knowledge,
    research_feed,
    research_projects,
    runs,
    scheduled_tasks,
    source_documents,
    suggestions,
    thread_runs,
    threads,
    uploads,
)
from app.gateway.trace_middleware import TraceMiddleware, resolve_trace_enabled
from deerflow.config import app_config as deerflow_app_config
from deerflow.logging_config import DEFAULT_LOG_DATE_FORMAT, DEFAULT_LOG_FORMAT, configure_logging
from deerflow.tracing.monocle import setup_monocle_tracing_if_enabled
from deerflow.uploads.manager import cleanup_stale_upload_staging_files

AppConfig = deerflow_app_config.AppConfig
get_app_config = deerflow_app_config.get_app_config

# Default logging; lifespan overrides from config.yaml log_level.
logging.basicConfig(
    level=logging.INFO,
    format=DEFAULT_LOG_FORMAT,
    datefmt=DEFAULT_LOG_DATE_FORMAT,
)

logger = logging.getLogger(__name__)

# Upper bound (seconds) each lifespan shutdown hook is allowed to run.
# Bounds worker exit time so uvicorn's reload supervisor does not keep
# firing signals into a worker that is stuck waiting for shutdown cleanup.
_SHUTDOWN_HOOK_TIMEOUT_SECONDS = 5.0


async def _ensure_admin_user(app: FastAPI) -> None:
    """Startup hook: handle first boot and migrate orphan threads otherwise.

    After admin creation, migrate orphan threads from the LangGraph
    store (metadata.user_id unset) to the admin account. This is the
    "no-auth → with-auth" upgrade path: users who ran DeerFlow without
    authentication have existing LangGraph thread data that needs an
    owner assigned.
        First boot (no admin exists):
            - Does NOT create any user accounts automatically.
            - The operator must visit ``/setup`` to create the first admin.

    Subsequent boots (admin already exists):
      - Runs the one-time "no-auth → with-auth" orphan thread migration for
        existing LangGraph thread metadata that has no user_id.

    No SQL persistence migration is needed: the four user_id columns
    (threads_meta, runs, run_events, feedback) only come into existence
    alongside the auth module via create_all, so freshly created tables
    never contain NULL-owner rows.
    """
    from sqlalchemy import select

    from app.gateway.deps import get_local_provider
    from deerflow.persistence.engine import get_session_factory
    from deerflow.persistence.user.model import UserRow

    try:
        provider = get_local_provider()
    except RuntimeError:
        # Auth persistence may not be initialized in some test/boot paths.
        # Skip admin migration work rather than failing gateway startup.
        logger.warning("Auth persistence not ready; skipping admin bootstrap check")
        return

    sf = get_session_factory()
    if sf is None:
        return

    admin_count = await provider.count_admin_users()

    if admin_count == 0:
        logger.info("=" * 60)
        logger.info("  First boot detected — no admin account exists.")
        logger.info("  Visit /setup to complete admin account creation.")
        logger.info("=" * 60)
        return

    # Admin already exists — run orphan thread migration for any
    # LangGraph thread metadata that pre-dates the auth module.
    async with sf() as session:
        stmt = select(UserRow).where(UserRow.system_role == "admin").limit(1)
        row = (await session.execute(stmt)).scalar_one_or_none()

    if row is None:
        return  # Should not happen (admin_count > 0 above), but be safe.

    admin_id = str(row.id)

    # LangGraph store orphan migration — non-fatal.
    # This covers the "no-auth → with-auth" upgrade path for users
    # whose existing LangGraph thread metadata has no user_id set.
    store = getattr(app.state, "store", None)
    if store is not None:
        try:
            migrated = await _migrate_orphaned_threads(store, admin_id)
            if migrated:
                logger.info("Migrated %d orphan LangGraph thread(s) to admin", migrated)
        except Exception:
            logger.exception("LangGraph thread migration failed (non-fatal)")


async def _iter_store_items(store, namespace, *, page_size: int = 500):
    """Paginated async iterator over a LangGraph store namespace.

    Replaces the old hardcoded ``limit=1000`` call with a cursor-style
    loop so that environments with more than one page of orphans do
    not silently lose data. Terminates when a page is empty OR when a
    short page arrives (indicating the last page).
    """
    offset = 0
    while True:
        batch = await store.asearch(namespace, limit=page_size, offset=offset)
        if not batch:
            return
        for item in batch:
            yield item
        if len(batch) < page_size:
            return
        offset += page_size


async def _migrate_orphaned_threads(store, admin_user_id: str) -> int:
    """Migrate LangGraph store threads with no user_id to the given admin.

    Uses cursor pagination so all orphans are migrated regardless of
    count. Returns the number of rows migrated.
    """
    migrated = 0
    async for item in _iter_store_items(store, ("threads",)):
        metadata = item.value.get("metadata", {})
        if not metadata.get("user_id"):
            metadata["user_id"] = admin_user_id
            item.value["metadata"] = metadata
            await store.aput(("threads",), item.key, item.value)
            migrated += 1
    return migrated


async def _recover_interrupted_ingestion_jobs(*, grace_seconds: int) -> int:
    """Requeue steps left running by an earlier Gateway process."""

    from deerflow.persistence.engine import get_session_factory
    from deerflow.persistence.wu_culture import SqlIngestionJobRepository

    session_factory = get_session_factory()
    if session_factory is None:
        return 0
    recovered = await SqlIngestionJobRepository(session_factory).recover_interrupted(
        now=datetime.now(UTC),
        grace_seconds=grace_seconds,
    )
    if recovered:
        logger.info("Recovered %d interrupted ingestion job(s)", len(recovered))
    return len(recovered)


async def _start_ingestion_worker(app: FastAPI, startup_config: AppConfig) -> None:
    """Start the durable source-ingestion worker after SQL bootstrap is ready."""
    from deerflow.persistence.engine import get_session_factory

    session_factory = get_session_factory()
    if session_factory is None:
        logger.info("Ingestion worker disabled because database backend is memory")
        return

    from app.gateway.ingestion_worker import IngestionWorker
    from deerflow.object_storage import create_object_storage
    from deerflow.persistence.object_storage import SqlObjectMetadataRepository
    from deerflow.persistence.wu_culture import (
        SqlEvidenceRepository,
        SqlIngestionJobRepository,
        SqlKnowledgeGraphRepository,
        SqlOcrRepository,
        SqlParsedDocumentRepository,
        SqlSourceDocumentRepository,
        SqlSourceFileRepository,
        SqlStructuredChunkRepository,
        SqlTextCleaningRepository,
    )

    stop_event = asyncio.Event()
    worker = IngestionWorker(
        job_repository=SqlIngestionJobRepository(session_factory),
        source_file_repository=SqlSourceFileRepository(session_factory),
        source_document_repository=SqlSourceDocumentRepository(session_factory),
        parsed_repository=SqlParsedDocumentRepository(session_factory),
        ocr_repository=SqlOcrRepository(session_factory),
        cleaning_repository=SqlTextCleaningRepository(session_factory),
        chunk_repository=SqlStructuredChunkRepository(session_factory),
        evidence_repository=SqlEvidenceRepository(session_factory),
        graph_repository=SqlKnowledgeGraphRepository(session_factory),
        object_storage=create_object_storage(startup_config.object_storage),
        object_metadata_repository=SqlObjectMetadataRepository(session_factory),
        corpus_config=startup_config.corpus_import,
        app_config=startup_config,
        ocr_service_factory=source_documents.get_ocr_service,
    )
    task = asyncio.create_task(worker.run_forever(stop_event), name="xingxi-ingestion-worker")
    app.state.ingestion_worker = worker
    app.state.ingestion_worker_stop = stop_event
    app.state.ingestion_worker_task = task
    logger.info("Historical-source ingestion worker started")


async def _stop_ingestion_worker(app: FastAPI) -> None:
    task = getattr(app.state, "ingestion_worker_task", None)
    stop_event = getattr(app.state, "ingestion_worker_stop", None)
    if task is None or stop_event is None:
        return
    stop_event.set()
    try:
        await asyncio.wait_for(task, timeout=_SHUTDOWN_HOOK_TIMEOUT_SECONDS)
    except TimeoutError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.warning("Ingestion worker shutdown exceeded %.1fs", _SHUTDOWN_HOOK_TIMEOUT_SECONDS)
    except Exception:
        logger.exception("Ingestion worker stopped with an error")
    finally:
        app.state.ingestion_worker_task = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""

    # Load config and check necessary environment variables at startup.
    # `startup_config` is a local snapshot used only for one-shot bootstrap
    # work (logging level, langgraph_runtime engines, channels). Request-time
    # config resolution always routes through `get_app_config()` in
    # `app/gateway/deps.py::get_config()` so `config.yaml` edits become
    # visible without a process restart. We deliberately do NOT cache this
    # snapshot on `app.state` to keep that contract enforceable.
    try:
        startup_config = get_app_config()
        configure_logging(startup_config)
        logger.info("Configuration loaded successfully")
        warn_if_auth_disabled_enabled()
    except Exception as e:
        error_msg = f"Failed to load configuration during gateway startup: {e}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg) from e
    config = get_gateway_config()
    logger.info(f"Starting API Gateway on {config.host}:{config.port}")

    # Agent observability (Monocle). Off by default; enabled with
    # MONOCLE_TRACING. Initialized here at startup — not at import time — so a
    # plain `import deerflow.agents` never installs a process-global tracer.
    # Unlike LangSmith/Langfuse, whose validation failures abort the agent run,
    # a bad Monocle config only logs: the Gateway keeps serving without tracing.
    try:
        setup_monocle_tracing_if_enabled()
    except Exception:  # observability must never break startup
        logger.exception("Monocle tracing setup failed; continuing without it")

    # Pre-warm tiktoken encoding cache so the first memory-injection request
    # never blocks on the BPE data download (which hits an OpenAI/Azure URL
    # that may be unreachable in restricted networks — see issue #3402).
    # Warm-up runs via the manager's `warm` capability (getattr-probed, so
    # non-DeerMem backends skip it). DeerMem.warm re-checks token_counting==
    # "char" and returns early, so char-mode backends never touch tiktoken
    # (avoids even the 5s probe in
    # network-restricted deployments — see issue #3429).
    try:
        from deerflow.agents.memory import get_memory_manager

        manager = get_memory_manager()
        warm = getattr(manager, "warm", None)
        if not callable(warm):
            logger.info("Memory backend %s has no warm-up hook; skipping tiktoken warm-up", type(manager).__name__)
        else:
            warmed = await asyncio.wait_for(
                asyncio.to_thread(warm),
                timeout=5,
            )
            if warmed:
                logger.info("tiktoken encoding cache warmed successfully")
            else:
                logger.warning("tiktoken encoding cache warm-up failed; token counting will use character-based fallback until tiktoken loads successfully")
    except TimeoutError:
        logger.warning("tiktoken encoding cache warm-up timed out; token counting will use character-based fallback until tiktoken loads successfully")
    except Exception:
        logger.warning("tiktoken warm-up skipped", exc_info=True)

    try:
        removed_upload_staging_files = await asyncio.to_thread(cleanup_stale_upload_staging_files)
        if removed_upload_staging_files:
            logger.info("Removed %d stale upload staging file(s)", removed_upload_staging_files)
    except Exception:
        logger.warning("Upload staging file cleanup skipped", exc_info=True)

    # Initialize LangGraph runtime components (StreamBridge, RunManager, checkpointer, store)
    async with langgraph_runtime(app, startup_config):
        logger.info("LangGraph runtime initialised")

        # Check admin bootstrap state and migrate orphan threads after admin exists.
        # Must run AFTER langgraph_runtime so app.state.store is available for thread migration
        await _ensure_admin_user(app)

        try:
            await _recover_interrupted_ingestion_jobs(
                grace_seconds=startup_config.ingestion.recovery_grace_seconds,
            )
        except Exception:
            logger.exception("Failed to recover interrupted ingestion jobs")

        try:
            await _start_ingestion_worker(app, startup_config)
        except Exception:
            logger.exception("Failed to start historical-source ingestion worker")

        # Start IM channel service if any channels are configured
        try:
            from app.channels.service import start_channel_service

            channel_service = await start_channel_service(startup_config)
            logger.info("Channel service started: %s", channel_service.get_status())
        except Exception:
            logger.exception("No IM channels configured or channel service failed to start")

        try:
            from app.gateway.services import launch_scheduled_thread_run
            from app.scheduler import ScheduledTaskService

            if getattr(app.state, "scheduled_task_repo", None) is not None and getattr(app.state, "scheduled_task_run_repo", None) is not None:
                scheduled_task_service = ScheduledTaskService(
                    task_repo=app.state.scheduled_task_repo,
                    task_run_repo=app.state.scheduled_task_run_repo,
                    launch_run=lambda **kwargs: launch_scheduled_thread_run(app=app, **kwargs),
                    poll_interval_seconds=startup_config.scheduler.poll_interval_seconds,
                    lease_seconds=startup_config.scheduler.lease_seconds,
                    max_concurrent_runs=startup_config.scheduler.max_concurrent_runs,
                )
                app.state.scheduled_task_service = scheduled_task_service
                if startup_config.scheduler.enabled:
                    await scheduled_task_service.start()
        except Exception:
            logger.exception("Failed to initialize scheduled task service")

        # Prime the evidence-bound daily feed before the first browser request.
        # The service returns its verified seed selection first and performs
        # popularity/RAG refresh work in its own bounded background task.
        research_feed_service = research_feed.get_research_feed_service()
        app.state.research_feed_warm_task = asyncio.create_task(
            research_feed_service.build_feed(research_feed._now_shanghai().date()),
            name="research-feed-startup-warm",
        )

        yield

        try:
            await asyncio.wait_for(
                app.state.research_feed_warm_task,
                timeout=_SHUTDOWN_HOOK_TIMEOUT_SECONDS,
            )
            await asyncio.wait_for(
                research_feed_service.wait_for_refreshes(),
                timeout=_SHUTDOWN_HOOK_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            app.state.research_feed_warm_task.cancel()
            logger.warning("Research feed warm-up did not finish before shutdown")
        except Exception:
            logger.exception("Research feed warm-up stopped with an error")

        await _stop_ingestion_worker(app)

        try:
            await auth.close_oidc_service()
        except Exception:
            logger.exception("Failed to close OIDC service")

        # Stop channel service on shutdown (bounded to prevent worker hang)
        try:
            from app.channels.service import stop_channel_service

            await asyncio.wait_for(
                stop_channel_service(),
                timeout=_SHUTDOWN_HOOK_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning(
                "Channel service shutdown exceeded %.1fs; proceeding with worker exit.",
                _SHUTDOWN_HOOK_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.exception("Failed to stop channel service")

        if getattr(app.state, "scheduled_task_service", None) is not None:
            try:
                await app.state.scheduled_task_service.stop()
            except Exception:
                logger.exception("Failed to stop scheduled task service")

        # Drain the memory backend's pending-update buffer before the worker
        # exits (best-effort, bounded). IM channels and the scheduler are
        # already stopped above, so no new IM/scheduler updates arrive during
        # the drain; the LangGraph runtime / in-flight HTTP requests can still
        # complete memory enqueues in a narrow window, but anything added after
        # the drain copies the buffer only resets the debounce Timer
        # (best-effort, same as today).
        #
        # No host-level pending/processing guard: ``shutdown_flush``
        # short-circuits on a truly idle buffer (returns True immediately), so
        # calling it unconditionally is cheap and keeps the in-flight-worker
        # race entirely inside the backend (where the buffer lives) -- the host
        # cannot "forget" that case the way a ``pending_count > 0``-only guard
        # would (review #6 on the original PR).
        #
        # K8s caveat: ``shutdown_flush_timeout_seconds`` must fit inside the
        # pod's ``terminationGracePeriodSeconds`` (channel stop + this drain +
        # buffer), set on the gateway Helm deployment -- or K8s SIGKILLs the
        # drain mid-flight and the loss this is fixing is silently re-introduced.
        try:
            app_cfg = get_app_config()
            if app_cfg.memory.enabled:
                from deerflow.agents.memory import get_memory_manager

                manager = get_memory_manager()
                flush_timeout = app_cfg.memory.shutdown_flush_timeout_seconds
                completed = await asyncio.to_thread(manager.shutdown_flush, flush_timeout)
                if completed:
                    logger.info("Memory queue flush completed within %.1fs", flush_timeout)
                else:
                    logger.warning(
                        "Memory queue flush did not finish within %.1fs; remaining updates may be lost",
                        flush_timeout,
                    )
        except Exception:
            logger.exception("Failed to flush memory queue on shutdown")

    logger.info("Shutting down API Gateway")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    config = get_gateway_config()
    docs_url = "/docs" if config.enable_docs else None
    redoc_url = "/redoc" if config.enable_docs else None
    openapi_url = "/openapi.json" if config.enable_docs else None

    app = FastAPI(
        title="Xingxi API Gateway",
        description="""
## Xingxi API Gateway

API Gateway for 星羲弦沚, a traceable Wu-culture and Mudu regional-history agent.

### Features

- **Models Management**: Query and retrieve available AI models
- **MCP Configuration**: Manage Model Context Protocol (MCP) server configurations
- **Memory Management**: Access and manage global memory data for personalized conversations
- **Artifacts**: Access thread artifacts and generated files
- **Health Monitoring**: System health check endpoints

### Architecture

LangGraph-compatible requests are routed through nginx to this gateway.
This gateway provides Xingxi runtime endpoints plus supporting model, MCP, memory, and artifact APIs.
        """,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        openapi_tags=[
            {
                "name": "models",
                "description": "Operations for querying available AI models and their configurations",
            },
            {
                "name": "mcp",
                "description": "Manage Model Context Protocol (MCP) server configurations",
            },
            {
                "name": "memory",
                "description": "Access and manage global memory data for personalized conversations",
            },
            {
                "name": "skills",
                "description": "Manage skills and their configurations",
            },
            {
                "name": "artifacts",
                "description": "Access and download thread artifacts and generated files",
            },
            {
                "name": "uploads",
                "description": "Upload and manage user files for threads",
            },
            {
                "name": "source-documents",
                "description": "Register and maintain historical-source metadata",
            },
            {
                "name": "threads",
                "description": "Manage DeerFlow thread-local filesystem data",
            },
            {
                "name": "agents",
                "description": "Create and manage custom agents with per-agent config and prompts",
            },
            {
                "name": "suggestions",
                "description": "Generate follow-up question suggestions for conversations",
            },
            {
                "name": "input-polish",
                "description": "Polish composer draft input before sending",
            },
            {
                "name": "channels",
                "description": "Manage IM channel integrations (Feishu, Slack, Telegram)",
            },
            {
                "name": "assistants-compat",
                "description": "LangGraph Platform-compatible assistants API (stub)",
            },
            {
                "name": "runs",
                "description": "LangGraph Platform-compatible runs lifecycle (create, stream, cancel)",
            },
            {
                "name": "health",
                "description": "Health check and system status endpoints",
            },
        ],
    )

    @app.exception_handler(HTTPException)
    async def handle_http_error(_request: Request, exc: HTTPException):
        return gateway_error_response(exc.status_code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError):
        return gateway_error_response(422, exc.errors())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception):
        logger.exception("Unhandled Gateway error", exc_info=exc)
        return gateway_error_response(500, "The Gateway could not complete the request", retryable=True)

    # Auth: reject unauthenticated requests to non-public paths (fail-closed safety net)
    app.add_middleware(AuthMiddleware)

    # CSRF: Double Submit Cookie pattern for state-changing requests
    app.add_middleware(CSRFMiddleware)

    # CORS: the unified nginx endpoint is same-origin by default. Split-origin
    # browser clients must opt in with this explicit Gateway allowlist so CORS
    # and CSRF origin checks share the same source of truth.
    cors_origins = sorted(get_configured_cors_origins())
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Request trace correlation: when logging.enhance.enabled=true, bind one
    # trace id per Gateway HTTP request and write it to response start headers.
    # `logging` is registered as restart-required (see reload_boundary.py) so we
    # snapshot the flag from the startup AppConfig instead of reading live; a
    # runtime toggle would otherwise leave the log formatter (installed once by
    # configure_logging() at lifespan startup) out of sync with the middleware.
    app.add_middleware(TraceMiddleware, enabled=_resolve_trace_enabled_for_app_construction())

    # Include routers
    # Models API is mounted at /api/models
    app.include_router(models.router)

    # Features API is mounted at /api/features
    app.include_router(features.router)

    # Console API (cross-thread observability) is mounted at /api/console
    app.include_router(console.router)

    # MCP API is mounted at /api/mcp
    app.include_router(mcp.router)

    # Memory API is mounted at /api/memory
    app.include_router(memory.router)

    # Artifacts API is mounted at /api/threads/{thread_id}/artifacts
    app.include_router(artifacts.router)

    # Uploads API is mounted at /api/threads/{thread_id}/uploads
    app.include_router(uploads.router)

    # Thread cleanup API is mounted at /api/threads/{thread_id}
    app.include_router(threads.router)

    # Scheduled tasks API is mounted at /api/scheduled-tasks
    app.include_router(scheduled_tasks.router)

    # Historical-source registration API is mounted at /api/source-documents
    app.include_router(source_documents.router)
    app.include_router(source_documents.public_router)
    app.include_router(corpus_imports.router)

    app.include_router(knowledge_releases.router)
    app.include_router(knowledge_graph.router)
    app.include_router(entities.router)
    app.include_router(map_points.router)
    app.include_router(operations.router)
    app.include_router(public_knowledge.router)
    app.include_router(research_feed.router)
    app.include_router(research_projects.router)
    app.include_router(knowledge_search.router)

    # Suggestions API is mounted at /api/threads/{thread_id}/suggestions
    app.include_router(suggestions.router)

    # Input polishing API is mounted at /api/input-polish
    app.include_router(input_polish.router)

    # User-facing IM channel connection API is mounted at /api/channels
    app.include_router(channel_connections.router)

    # Channels API is mounted at /api/channels
    app.include_router(channels.router)

    # Assistants compatibility API (LangGraph Platform stub)
    app.include_router(assistants_compat.router)

    # Auth API is mounted at /api/v1/auth
    app.include_router(auth.router)

    # Feedback API is mounted at /api/threads/{thread_id}/runs/{run_id}/feedback
    app.include_router(feedback.router)

    # Thread Runs API (LangGraph Platform-compatible runs lifecycle)
    app.include_router(thread_runs.router)

    # Stateless Runs API (stream/wait without a pre-existing thread)
    app.include_router(runs.router)

    # GitHub webhooks API is mounted at /api/webhooks/github
    # Exempt from auth and CSRF middleware (see auth_middleware._PUBLIC_PATH_PREFIXES
    # and csrf_middleware.should_check_csrf); authenticity is enforced via the
    # X-Hub-Signature-256 HMAC against GITHUB_WEBHOOK_SECRET.
    # Including this router transitively imports app.gateway.github, which
    # registers the GitHub channel's ChannelRunPolicy as an import side-effect.
    #
    # Fail-closed: only mount the route when a webhook secret is configured
    # (or when the explicit DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS=1
    # dev opt-in is set). A misconfigured deployment without a secret cannot
    # serve forged deliveries because the URL responds 404 — there is no
    # handler to reach.
    if github_webhooks.is_route_enabled():
        app.include_router(github_webhooks.router)
        logger.info("GitHub webhooks route mounted at /api/webhooks/github")
    else:
        logger.warning("GitHub webhooks route NOT mounted: GITHUB_WEBHOOK_SECRET unset and DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS not set. /api/webhooks/github will respond 404. Configure either env var to enable the route.")

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Service health status information.
        """
        return {"status": "healthy", "service": "xingxi-gateway"}

    return app


def _resolve_trace_enabled_for_app_construction() -> bool:
    """Resolve the trace middleware flag without making imports require config.yaml."""
    try:
        return resolve_trace_enabled(get_app_config())
    except FileNotFoundError:
        # Startup lifespan still performs strict config loading before serving.
        logger.debug("config.yaml not found while constructing Gateway app; TraceMiddleware disabled for this app instance")
        return False


# Create app instance for uvicorn
app = create_app()
