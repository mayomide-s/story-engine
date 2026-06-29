from app.db.session import SessionLocal
from app.services.pipeline_service import process_resume_pipeline
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.jobs.resume_pipeline_task")
def resume_pipeline_task(run_id: str):
    db = SessionLocal()
    try:
        process_resume_pipeline(db, run_id)
    finally:
        db.close()
