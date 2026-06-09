import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.schemas.campaign import CampaignCreate, CampaignOut, CampaignUpdate
from app.tasks.celery_app import send_campaign_task

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(data: CampaignCreate, db: AsyncSession = Depends(get_db)):
    campaign = Campaign(
        name=data.name,
        template_name=data.template_name,
        template_params=data.template_params,
        audience_tags=data.audience_tags,
        scheduled_at=data.scheduled_at,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    send_campaign_task.apply_async(args=[str(campaign.id)], queue="default")
    return campaign


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(Campaign).order_by(Campaign.created_at.desc()))
    return result.scalars().all()


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(campaign_id: uuid.UUID, data: CampaignUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in (CampaignStatus.draft, CampaignStatus.scheduled):
        raise HTTPException(status_code=409, detail="Only draft or scheduled campaigns can be edited")
    if data.name is not None:
        campaign.name = data.name
    if data.template_name is not None:
        campaign.template_name = data.template_name
    if data.template_params is not None:
        campaign.template_params = data.template_params
    if data.audience_tags is not None:
        campaign.audience_tags = data.audience_tags
    if data.scheduled_at is not None:
        campaign.scheduled_at = data.scheduled_at
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.delete(campaign)
    await db.commit()
