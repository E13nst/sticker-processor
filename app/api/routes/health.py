"""Health check routes."""
from datetime import datetime
from fastapi import APIRouter

router = APIRouter()


@router.get(
    "/health",
    summary="Health Check",
    description="Check if the service is running and healthy",
    tags=["System"]
)
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

