from app.db.session import SessionLocal
from app.services.narration_service import process_narration_render
from app.services.pipeline_service import process_resume_pipeline
from app.services.publication_execution_service import (
    poll_youtube_publication_target,
    process_youtube_publication_target,
    scan_recoverable_publication_targets,
)
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.jobs.resume_pipeline_task")
def resume_pipeline_task(run_id: str):
    db = SessionLocal()
    try:
        process_resume_pipeline(db, run_id)
    finally:
        db.close()


@celery_app.task(name="app.workers.jobs.narration_render_task", bind=True)
def narration_render_task(self, render_id: str):
    db = SessionLocal()
    try:
        process_narration_render(db, render_id, mode="full", task_id=self.request.id)
    finally:
        db.close()


@celery_app.task(name="app.workers.jobs.narration_recompose_task", bind=True)
def narration_recompose_task(self, render_id: str):
    db = SessionLocal()
    try:
        process_narration_render(db, render_id, mode="recompose", task_id=self.request.id)
    finally:
        db.close()


@celery_app.task(name="app.workers.jobs.start_youtube_publication_target_task", bind=True)
def start_youtube_publication_target_task(self, target_id: str):
    db = SessionLocal()
    try:
        process_youtube_publication_target(db, target_id)
    finally:
        db.close()


@celery_app.task(name="app.workers.jobs.poll_youtube_publication_target_task", bind=True)
def poll_youtube_publication_target_task(self, target_id: str):
    db = SessionLocal()
    try:
        poll_youtube_publication_target(db, target_id)
    finally:
        db.close()


@celery_app.task(name="app.workers.jobs.recover_youtube_publication_targets_task")
def recover_youtube_publication_targets_task():
    db = SessionLocal()
    try:
        scan_recoverable_publication_targets(db)
    finally:
        db.close()
