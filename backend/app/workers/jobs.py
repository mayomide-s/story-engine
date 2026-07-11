from app.db.session import SessionLocal
from app.services.narration_service import process_narration_render
from app.services.pipeline_service import process_resume_pipeline
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
