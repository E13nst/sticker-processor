"""Webhook models for Snapstix callbacks."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SnapstixWebhookRequest(BaseModel):
    """Request model for Snapstix webhook callback."""
    
    status: str = Field(..., description="Status of the job (e.g., 'SUCCESS')")
    chat_id: str = Field(..., description="Chat ID")
    style_id: str = Field(..., description="Style ID")
    style_hash: str = Field(..., description="Style hash")
    job_id: str = Field(..., description="Job ID")
    original_message_id: str = Field(..., description="Original message ID")
    processing_job_id: str = Field(..., description="Processing job ID")
    img_url: Optional[str] = Field(default=None, description="Image URL")
    sticker_url: Optional[str] = Field(default=None, description="Sticker URL")
    error_data: Optional[dict] = Field(default=None, description="Error data if any")
    
    class Config:
        # Allow extra fields to be ignored (in case Snapstix sends additional data)
        extra = "ignore"


class WebhookRecord(BaseModel):
    """Model for webhook record in database."""
    
    id: Optional[int] = None
    status: str
    chat_id: str
    style_id: str
    style_hash: str
    job_id: str
    original_message_id: str
    processing_job_id: str
    img_url: Optional[str] = None
    sticker_url: Optional[str] = None
    error_data: Optional[str] = None  # JSON string
    created_at: Optional[datetime] = None

