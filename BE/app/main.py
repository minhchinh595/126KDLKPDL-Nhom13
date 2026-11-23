from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, clustering, health, electricity, prediction, classification
app = FastAPI(
    title="Electricity Consumption Analytics",
    description="Electricity consumption analysis and prediction system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
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

@app.get("/")
def root():
    return {
        "message": "Welcome to Electricity Consumption Analytics API"
    }
