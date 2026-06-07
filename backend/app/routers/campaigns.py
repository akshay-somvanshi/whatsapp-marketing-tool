import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.schemas.campaign import CampaignCreate, CampaignOut

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
