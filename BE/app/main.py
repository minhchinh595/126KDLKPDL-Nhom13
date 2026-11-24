from fastapi import FastAPI
import os
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, clustering, health, electricity, prediction, classification, auth, users, datasets, dashboard, model_runs, reports
app = FastAPI(
    title="Electricity Consumption Analytics",
    description="Electricity consumption analysis and prediction system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys([
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *[origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()],
    ])),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    health.router,
    prefix="/api",
    tags=["Health"]
)

app.include_router(electricity.router, prefix="/api", tags=["Electricity"])
app.include_router(analysis.router, prefix="/api", tags=["Analysis"])
app.include_router(clustering.router, prefix="/api", tags=["Clustering"])
app.include_router(prediction.router, prefix="/api", tags=["Prediction"])
app.include_router(classification.router, prefix="/api", tags=["Classification"],)
app.include_router(auth.router, prefix="/api", tags=["Authentication"])
app.include_router(users.router, prefix="/api", tags=["User Management"])
app.include_router(datasets.router, prefix="/api", tags=["Dataset Management"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(model_runs.router, prefix="/api", tags=["Model Runs"])
app.include_router(reports.router, prefix="/api", tags=["Reports"])

@app.get("/")
def root():
    return {
        "message": "Welcome to Electricity Consumption Analytics API"
    }
