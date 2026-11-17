from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "status": "success",
        "message": "Backend API is running",
        "project": "Electricity Consumption Analytics"
    }