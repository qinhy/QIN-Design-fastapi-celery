@REM python -m celery -A tasks.celery_app worker -l info --concurrency=1 -P threads
python -m celery -A tasksNew.celery_app worker -l info --concurrency=1 -P threads