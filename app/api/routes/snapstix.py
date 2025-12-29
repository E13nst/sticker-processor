"""Snapstix webhook routes."""
import logging
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pathlib import Path

from app.models.webhook import SnapstixWebhookRequest
from app.services.webhook_db import WebhookDBService

logger = logging.getLogger(__name__)

# Initialize templates
templates_dir = Path(__file__).parent.parent.parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))


def create_snapstix_router(webhook_db: WebhookDBService) -> APIRouter:
    """Create snapstix router with webhook_db dependency."""
    router = APIRouter(prefix="/snapstix")


    @router.post(
        "/webhook",
        summary="Snapstix Webhook",
        description="Receive webhook callbacks from Snapstix service",
        tags=["Snapstix"],
        status_code=200
    )
    async def receive_snapstix_webhook(webhook_data: SnapstixWebhookRequest):
        """Receive and save webhook data from Snapstix."""
        try:
            # Log incoming request for debugging
            logger.info(f"Webhook received - job_id: {webhook_data.job_id}, status: {webhook_data.status}")
            logger.debug(f"Webhook payload: {webhook_data.model_dump_json(indent=2)}")
            
            # Convert Pydantic model to dict
            data_dict = webhook_data.model_dump()
            
            # Save to database
            record_id = await webhook_db.save_webhook(data_dict)
            
            logger.info(f"Webhook received and saved: job_id={webhook_data.job_id}, record_id={record_id}")
            
            return {
                "status": "success",
                "message": "Webhook received and saved",
                "record_id": record_id
            }
        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error processing webhook: {str(e)}")


    @router.get(
        "/view",
        response_class=HTMLResponse,
        summary="View Webhook Records",
        description="Display webhook records in a simple HTML table",
        tags=["Snapstix"]
    )
    async def view_webhooks(request: Request, limit: int = 100, offset: int = 0):
        """Display webhook records in HTML table."""
        try:
            records = await webhook_db.get_all_records(limit=limit, offset=offset)
            total_count = await webhook_db.get_count()
            
            return templates.TemplateResponse(
                "webhooks.html",
                {
                    "request": request,
                    "records": records,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "has_next": len(records) == limit,
                    "has_prev": offset > 0
                }
            )
        except Exception as e:
            logger.error(f"Error displaying webhooks: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error displaying webhooks: {str(e)}")


    @router.get(
        "/list",
        summary="Get Webhook Records (JSON)",
        description="Get webhook records as JSON",
        tags=["Snapstix"]
    )
    async def get_webhooks_list(limit: int = 100, offset: int = 0):
        """Get webhook records as JSON."""
        try:
            records = await webhook_db.get_all_records(limit=limit, offset=offset)
            total_count = await webhook_db.get_count()
            
            return {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "records": [record.model_dump() for record in records]
            }
        except Exception as e:
            logger.error(f"Error fetching webhooks: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error fetching webhooks: {str(e)}")
    
    return router

