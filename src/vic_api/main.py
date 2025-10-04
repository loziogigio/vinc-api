from .app import create_app

# Uvicorn entrypoint: `uvicorn vic_api.main:app --reload`
app = create_app()
