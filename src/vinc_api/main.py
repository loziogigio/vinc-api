from .app import create_app

# Uvicorn entrypoint: `uvicorn vinc_api.main:app --reload`
app = create_app()
