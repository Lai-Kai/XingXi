"""Background execution for uploaded historical-source ingestion jobs."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from wu_culture import (
    AuthorizedUse,
    DocumentParseError,
    DocumentParseRequest,
    ParsedDocument,
    SourceFile,
    parse_document,
)
from wu_culture.chunking import ChunkingPolicy, ChunkSet, ChunkSourcePage, chunk_cleaned_pages
from wu_culture.cleaning import CleanedOcrPage, RawOcrPage, TextCleaningPolicy, clean_ocr_pages
from wu_culture.ingestion import (
    IngestionConcurrencyError,
    IngestionJob,
    IngestionJobRepository,
    IngestionJobStatus,
    IngestionStepName,
    complete_step,
    create_ingestion_job,
    fail_step,
)
from wu_culture.ocr import OcrPageAttempt, OcrPageStatus, OcrService, render_ocr_pages
from wu_culture.releases import (
    ActivateReleaseRequest,
    KnowledgeReleaseGateError,
    PublishReleaseRequest,
    ReleaseStatus,
)
from wu_culture.storage import ObjectKind, ObjectMetadataRepository, ObjectStorage, PutObjectRequest

logger = logging.getLogger(__name__)


class IngestionWorker:
    """Claim and execute pending ingestion steps using the domain state machine."""

    def __init__(
        self,
        *,
        job_repository: IngestionJobRepository,
        source_file_repository: Any,
        source_document_repository: Any | None = None,
        parsed_repository: Any,
        ocr_repository: Any,
        cleaning_repository: Any,
        chunk_repository: Any,
        evidence_repository: Any | None,
        graph_repository: Any | None,
        object_storage: ObjectStorage,
        object_metadata_repository: ObjectMetadataRepository | None,
        corpus_config: Any | None,
        app_config: Any,
        ocr_service_factory: Callable[[], OcrService] | None = None,
        worker_id: str = "gateway-ingestion-worker",
    ) -> None:
        self._jobs = job_repository
        self._files = source_file_repository
        self._source_documents = source_document_repository
        self._parsed = parsed_repository
        self._ocr = ocr_repository
        self._cleaning = cleaning_repository
        self._chunks = chunk_repository
        self._evidence = evidence_repository
        self._graph = graph_repository
        self._storage = object_storage
        self._object_metadata = object_metadata_repository
        self._corpus_config = corpus_config
        self._config = app_config
        self._ocr_service_factory = ocr_service_factory
        self._worker_id = worker_id

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        poll_seconds = 1.0
        while not stop_event.is_set():
            try:
                processed = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Ingestion worker loop failed")
                processed = False
            if processed:
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass

    async def run_once(self) -> bool:
        """Claim and process at most one pending step."""
        if await self._claim_and_execute_pending_step():
            return True
        await self._backfill_missing_jobs()
        if await self._claim_and_execute_pending_step():
            return True
        return False

    async def _claim_and_execute_pending_step(self) -> bool:
        rows = await self._jobs.list_recent(
            limit=100,
            statuses={IngestionJobStatus.PENDING},
        )
        for job, _title, _filename in rows:
            if job.current_step is None:
                continue
            claimed = await self._jobs.try_start_step(
                job.id,
                step_name=job.current_step,
                worker_id=self._worker_id,
                max_concurrent_jobs=self._config.ingestion.max_concurrent_jobs,
                lease_seconds=self._config.ingestion.lease_seconds,
                now=datetime.now(UTC),
            )
            if claimed is None:
                continue
            await self._execute(claimed)
            return True
        return False

    async def _backfill_missing_jobs(self) -> None:
        """Create jobs for source files uploaded before the durable worker existed."""
        if self._source_documents is None or not hasattr(self._files, "list_all"):
            return
        documents = await self._source_documents.list()
        document_ids = {document.id for document in documents}
        files = [source_file for source_file in await self._files.list_all() if source_file.document_id in document_ids]
        for source_file in files:
            if await self._jobs.list_for_source_file(source_file.id):
                continue
            job, event = create_ingestion_job(
                job_id=f"ingestion-job-{hashlib.sha256(source_file.id.encode('utf-8')).hexdigest()}",
                document_id=source_file.document_id,
                source_file_id=source_file.id,
                idempotency_key=f"source-file:{source_file.id}",
                created_by=source_file.uploaded_by,
                now=datetime.now(UTC),
            )
            try:
                await self._jobs.create(job, event)
            except Exception:
                logger.exception("Failed to backfill ingestion job for source file %s", source_file.id)

    async def _execute(self, claimed: IngestionJob) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(claimed.id), name=f"ingestion-heartbeat-{claimed.id}")
        try:
            output_ref = await self._process_step(claimed)
            current = await self._jobs.get(claimed.id)
            if current is None or current.status is not IngestionJobStatus.RUNNING:
                return
            updated, event = complete_step(
                current,
                step_name=claimed.current_step,  # type: ignore[arg-type]
                output_ref=output_ref,
                now=datetime.now(UTC),
            )
            await self._jobs.save(updated, event, expected_version=current.version)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Ingestion step failed: job=%s step=%s", claimed.id, claimed.current_step)
            current = await self._jobs.get(claimed.id)
            if current is None or current.status is not IngestionJobStatus.RUNNING or current.current_step is None:
                return
            code = str(getattr(exc, "code", "ingestion_step_failed"))
            message = str(getattr(exc, "message", str(exc)))[:4000] or "Ingestion step failed"
            updated, event = fail_step(
                current,
                step_name=current.current_step,
                error_code=code,
                error_message=message,
                retryable=code not in {"invalid_pdf", "invalid_docx", "unsupported_document_type", "text_encoding_unknown"},
                now=datetime.now(UTC),
            )
            try:
                await self._jobs.save(updated, event, expected_version=current.version)
            except IngestionConcurrencyError:
                logger.warning("Ingestion failure transition lost a race: job=%s", claimed.id)
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def _heartbeat(self, job_id: str) -> None:
        interval = max(1.0, self._config.ingestion.lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            renewed = await self._jobs.renew_lease(
                job_id,
                worker_id=self._worker_id,
                lease_seconds=self._config.ingestion.lease_seconds,
                now=datetime.now(UTC),
            )
            if renewed is None:
                return

    async def _process_step(self, job: IngestionJob) -> str:
        if job.current_step is IngestionStepName.PARSE:
            return await self._process_parse(job)
        if job.current_step is IngestionStepName.OCR:
            return await self._process_ocr(job)
        if job.current_step is IngestionStepName.CLEAN:
            return await self._process_clean(job)
        if job.current_step is IngestionStepName.CHUNK:
            return await self._process_chunk(job)
        raise RuntimeError(f"worker cannot automatically execute {job.current_step.value if job.current_step else 'none'}")

    async def _source_file(self, job: IngestionJob) -> SourceFile:
        source_file = await self._files.get(job.source_file_id)
        if source_file is None:
            raise ValueError(f"source file {job.source_file_id!r} was not found")
        while source_file.duplicate_of_file_id:
            canonical = await self._files.get(source_file.duplicate_of_file_id)
            if canonical is None:
                raise ValueError(f"canonical source file for {source_file.id!r} was not found")
            source_file = canonical
        return source_file

    async def _read_source_content(self, source_file: SourceFile) -> bytes:
        if self._object_metadata is not None:
            metadata = await self._object_metadata.get(owner_id=source_file.document_id, object_key=source_file.object_key)
            if metadata is not None and metadata.backend == "mounted":
                if self._corpus_config is None:
                    raise ValueError("mounted source requires corpus import configuration")
                path = self._corpus_config.resolve_storage_uri(metadata.storage_uri)
                return await asyncio.to_thread(path.read_bytes)
        stored = await self._storage.get(owner_id=source_file.document_id, object_key=source_file.object_key)
        return stored.content

    async def _process_parse(self, job: IngestionJob) -> str:
        source_file = await self._source_file(job)
        existing = await self._parsed.get_by_source_file_id(source_file.id)
        if existing is not None:
            return f"parsed:{existing.id}"
        content = await self._read_source_content(source_file)
        try:
            parsed_content = await asyncio.to_thread(
                parse_document,
                DocumentParseRequest(
                    filename=source_file.original_filename,
                    mime_type=source_file.mime_type,
                    content=content,
                ),
            )
        except DocumentParseError as exc:
            if exc.code == "no_extractable_text":
                return "ocr-required:no-text-layer"
            raise
        parsed = ParsedDocument(
            id=f"parsed-{source_file.id}",
            source_file_id=source_file.id,
            mime_type=source_file.mime_type,
            parsed_at=datetime.now(UTC),
            **parsed_content.model_dump(),
        )
        try:
            await self._parsed.save(parsed)
        except Exception:
            concurrent = await self._parsed.get_by_source_file_id(source_file.id)
            if concurrent is None:
                raise
            return f"parsed:{concurrent.id}"
        return f"parsed:{parsed.id}"

    async def _process_ocr(self, job: IngestionJob) -> str:
        source_file = await self._source_file(job)
        existing = await self._ocr.list_latest(source_file.id)
        if existing:
            return f"ocr-pages:{len(existing)}"
        parsed = await self._parsed.get_by_source_file_id(source_file.id)
        if parsed is not None:
            by_page: dict[int, list[str]] = defaultdict(list)
            for block in parsed.blocks:
                by_page[block.page_number].append(block.text)
            attempts = tuple(
                OcrPageAttempt(
                    id=f"ocr-{source_file.id}-p{page_number}-digital-v1",
                    source_file_id=source_file.id,
                    page_number=page_number,
                    attempt_number=1,
                    provider_name="digital-parser",
                    model_name=parsed.parser_name,
                    languages=("zh-Hans", "zh-Hant"),
                    status=OcrPageStatus.COMPLETED,
                    raw_text="\n".join(by_page[page_number]).strip(),
                    mean_confidence=1.0,
                    created_at=datetime.now(UTC),
                )
                for page_number in sorted(by_page)
                if "\n".join(by_page[page_number]).strip()
            )
            if not attempts:
                raise ValueError("digital document contains no text pages")
            await self._save_ocr_attempts_idempotently(source_file.id, attempts)
            return f"ocr-pages:{len(attempts)}"

        if self._ocr_service_factory is None:
            raise RuntimeError("no extractable text layer and OCR service is not configured")
        content = await self._read_source_content(source_file)
        ocr_config = self._config.ocr
        pages = await asyncio.to_thread(
            render_ocr_pages,
            filename=source_file.original_filename,
            mime_type=source_file.mime_type,
            content=content,
            dpi=ocr_config.render_dpi,
        )
        if len(pages) > ocr_config.max_pages_per_batch:
            raise ValueError(f"OCR batch accepts at most {ocr_config.max_pages_per_batch} pages")
        stored_pages = []
        for page in pages:
            metadata = await self._storage.put(
                PutObjectRequest(
                    owner_id=source_file.document_id,
                    kind=ObjectKind.PAGE_IMAGE,
                    content=page.content,
                    mime_type="image/png",
                    original_filename=f"{source_file.id}-page-{page.page_number}.png",
                )
            )
            if self._object_metadata is not None:
                await self._object_metadata.save(metadata)
            stored_pages.append(page.model_copy(update={"object_key": metadata.object_key}))
        attempts = await self._ocr_service_factory().recognize_pages(
            source_file_id=source_file.id,
            pages=tuple(stored_pages),
        )
        await self._save_ocr_attempts_idempotently(source_file.id, attempts)
        failed = [attempt for attempt in attempts if attempt.status is OcrPageStatus.FAILED]
        if failed:
            raise RuntimeError(f"OCR failed for {len(failed)} page(s)")
        return f"ocr-pages:{len(attempts)}"

    async def _save_ocr_attempts_idempotently(self, source_file_id: str, attempts: tuple[OcrPageAttempt, ...]) -> None:
        try:
            await self._ocr.save_attempts(attempts)
        except Exception:
            existing = await self._ocr.list_latest(source_file_id)
            if not existing:
                raise

    async def _process_clean(self, job: IngestionJob) -> str:
        source_file = await self._source_file(job)
        attempts = [attempt for attempt in await self._ocr.list_latest(source_file.id) if attempt.raw_text]
        if not attempts:
            raise ValueError("OCR produced no text pages")
        policy = TextCleaningPolicy(rule_version="xingxi-clean-v1")
        previous = {page.page_number: page for page in await self._cleaning.list_latest(source_file.id)}
        if all(
            attempt.page_number in previous
            and previous[attempt.page_number].ocr_attempt_id == attempt.id
            and previous[attempt.page_number].policy == policy
            for attempt in attempts
        ):
            return f"clean-pages:{len(previous)}"
        contents = await asyncio.to_thread(
            clean_ocr_pages,
            tuple(
                RawOcrPage(
                    source_file_id=source_file.id,
                    ocr_attempt_id=attempt.id,
                    page_number=attempt.page_number,
                    raw_text=attempt.raw_text,
                )
                for attempt in attempts
            ),
            policy=policy,
        )
        generated_at = datetime.now(UTC)
        pages = tuple(
            CleanedOcrPage(
                id=f"cleaned-{source_file.id}-p{content.page_number}-g{previous.get(content.page_number).generation_number + 1 if content.page_number in previous else 1}",
                generation_number=previous.get(content.page_number).generation_number + 1 if content.page_number in previous else 1,
                policy=policy,
                generated_by=job.created_by,
                generated_at=generated_at,
                **content.model_dump(),
            )
            for content in contents
        )
        try:
            await self._cleaning.save_many(pages)
        except Exception:
            concurrent = await self._cleaning.list_latest(source_file.id)
            if not concurrent:
                raise
            return f"clean-pages:{len(concurrent)}"
        return f"clean-pages:{len(pages)}"

    async def _process_chunk(self, job: IngestionJob) -> str:
        source_file = await self._source_file(job)
        cleaned_pages = await self._cleaning.list_latest(source_file.id)
        if not cleaned_pages:
            raise ValueError("cleaned page text is unavailable")
        policy = ChunkingPolicy(
            split_version="xingxi-structure-v1",
            max_characters=1000,
            overlap_characters=100,
        )
        input_identity = "\x1f".join(f"{page.id}:{page.raw_sha256}:{page.clean_sha256}" for page in sorted(cleaned_pages, key=lambda value: value.page_number))
        input_sha256 = hashlib.sha256(input_identity.encode("utf-8")).hexdigest()
        existing = await self._chunks.get(source_file.id, policy.split_version)
        if existing is not None:
            if existing.input_sha256 != input_sha256 or existing.policy != policy:
                raise ValueError("existing chunk version refers to different clean input")
            chunk_set = existing
        else:
            result = await asyncio.to_thread(
                chunk_cleaned_pages,
                document_id=source_file.document_id,
                source_file_id=source_file.id,
                pages=tuple(
                    ChunkSourcePage(
                        cleaned_page_id=page.id,
                        page_number=page.page_number,
                        raw_text=page.raw_text,
                        clean_text=page.clean_text,
                    )
                    for page in cleaned_pages
                    if page.clean_text.strip()
                ),
                policy=policy,
            )
            if not result.chunks:
                raise ValueError("cleaned pages contain no paragraph text")
            chunk_set = ChunkSet(
                id=f"chunk-set-{hashlib.sha256(f'{source_file.id}:{policy.split_version}'.encode()).hexdigest()}",
                input_sha256=input_sha256,
                generated_by=job.created_by,
                generated_at=datetime.now(UTC),
                **result.model_dump(),
            )
            try:
                await self._chunks.save(chunk_set)
            except Exception:
                concurrent = await self._chunks.get(source_file.id, policy.split_version)
                if concurrent is None:
                    raise
                chunk_set = concurrent

        evidence_count = await self._ensure_evidence(chunk_set)
        graph_count = await self._extract_graph(chunk_set)
        await self._publish_internal_working_release()
        return f"chunk-set:{chunk_set.id};chunks:{len(chunk_set.chunks)};evidence:{evidence_count};graph:{graph_count}"

    async def _ensure_evidence(self, chunk_set: ChunkSet) -> int:
        if self._evidence is None:
            return 0
        ensure = getattr(self._evidence, "ensure_chunk_evidence", None)
        if not callable(ensure):
            return 0
        return int(await ensure(chunk_set_id=chunk_set.id))

    async def _extract_graph(self, chunk_set: ChunkSet) -> int:
        if self._graph is None:
            return 0
        ingest = getattr(self._graph, "ingest_chunk", None)
        if not callable(ingest):
            return 0
        count = 0
        for chunk in chunk_set.chunks:
            count += int(
                await ingest(
                    document_id=chunk.document_id,
                    source_file_id=chunk.source_file_id,
                    chunk_id=chunk.id,
                    text=chunk.clean_text,
                )
            )
        return count

    async def _publish_internal_working_release(self) -> None:
        if not getattr(self._config.ingestion, "auto_publish_internal_release", True):
            return
        from deerflow.persistence import engine as persistence_engine
        from deerflow.persistence.wu_culture import SqlFullTextRepository, SqlKnowledgeReleaseRepository

        session_factory = persistence_engine.get_session_factory()
        if session_factory is None:
            return
        chunk_sets = await self._chunks.list_all() if hasattr(self._chunks, "list_all") else []
        if not chunk_sets:
            return
        from wu_culture.authorization import evaluate_source_access

        from deerflow.persistence.wu_culture import SqlSourceDocumentRepository

        sources = SqlSourceDocumentRepository(session_factory)
        allowed_sets = []
        for chunk_set in chunk_sets:
            document = await sources.get(chunk_set.document_id)
            if document is not None and evaluate_source_access(document, use=AuthorizedUse.INTERNAL_PROCESSING).allowed:
                allowed_sets.append(chunk_set)
        if not allowed_sets:
            return
        release_repo = SqlKnowledgeReleaseRepository(
            session_factory,
            publication_indexer=SqlFullTextRepository(session_factory),
        )
        requested = {chunk_set.id for chunk_set in allowed_sets}
        existing = next(
            (release for release in await release_repo.list_releases() if release.scope == "internal" and release.status in {ReleaseStatus.ACTIVE, ReleaseStatus.READY} and {item.chunk_set_id for item in release.items} == requested),
            None,
        )
        state = await release_repo.get_state()
        if existing is not None:
            if state.active_release_id != existing.id:
                await release_repo.activate(
                    ActivateReleaseRequest(
                        release_id=existing.id,
                        expected_state_version=state.state_version,
                        reason="Activate the complete internal uploaded-source working corpus",
                    ),
                    actor_id="gateway-ingestion-worker",
                    changed_at=datetime.now(UTC),
                )
            return
        try:
            await release_repo.publish(
                PublishReleaseRequest(
                    chunk_set_ids=tuple(chunk_set.id for chunk_set in allowed_sets),
                    release_notes="上传文献全量内部工作版本；内容与来源等级待人工复核，不可公开引用",
                    expected_state_version=state.state_version,
                    activate=True,
                    scope="internal",
                ),
                actor_id="gateway-ingestion-worker",
                created_at=datetime.now(UTC),
            )
        except KnowledgeReleaseGateError:
            logger.info("Internal working release is waiting for source authorization")
