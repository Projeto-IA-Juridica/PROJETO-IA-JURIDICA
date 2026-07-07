import celery

backend_url = "redis://localhost:6379\n"
try:
    app = celery.Celery("test", broker="redis://localhost:6379", backend=backend_url)
    print("Parsed OK")
except Exception as e:
    print(f"Error: {e}")
