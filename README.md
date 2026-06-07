# WhatsApp Marketing Platform

A lightweight WhatsApp marketing tool for small businesses. Send broadcast campaigns, automate post-purchase review requests, and let an AI handle customer replies — all through WhatsApp.

---

## What It Does

- **Contacts** — Import your customer list (CSV or manual entry). Each contact has a name, phone number, and consent status.
- **Campaigns** — Pick a pre-approved WhatsApp template, choose your audience by tag, schedule or send immediately.
- **Inbox** — See every active WhatsApp conversation. Read replies, toggle AI auto-reply on or off per conversation.
- **Automation** — 3 days after a customer is tagged "purchased", they automatically receive a review request. No manual action needed.
- **AI replies** — When a customer replies to a message, an AI assistant (powered by Claude) responds naturally on your behalf. You can turn this off and take over any conversation manually.

---

## Prerequisites

Before you start, you need accounts and credentials for three services:

| Service | Why | Where to get it |
|---|---|---|
| Docker Desktop | Runs the entire platform locally | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Meta WhatsApp Business API | Sends and receives WhatsApp messages | [Meta Developer Console](https://developers.facebook.com/) |
| Anthropic API | Powers the AI auto-reply | [console.anthropic.com](https://console.anthropic.com/) |
| ngrok (for local dev) | Exposes your local server so Meta can send you webhook events | [ngrok.com](https://ngrok.com/) |

---

## Getting Your API Credentials

### WhatsApp (Meta)

1. Go to [developers.facebook.com](https://developers.facebook.com/) and create a new App.
2. Add the **WhatsApp** product to your app.
3. In **WhatsApp > API Setup**, find your:
   - **Phone Number ID** → this is `WHATSAPP_PHONE_NUMBER_ID`
   - **Temporary Access Token** (or generate a permanent System User token) → this is `WHATSAPP_API_TOKEN`
4. Under **WhatsApp > Configuration**, set your webhook URL to `https://<your-ngrok-url>/webhook` and enter the verify token you'll put in `.env` as `WEBHOOK_VERIFY_TOKEN`.
5. Subscribe to the `messages` webhook field.

> During development, Meta provides a sandbox with free test phone numbers. You don't need a real business account to start.

### Anthropic (Claude AI)

1. Go to [console.anthropic.com](https://console.anthropic.com/) and create an API key.
2. That key is `ANTHROPIC_API_KEY`.

---

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url>
cd whatsapp-marketing-tool
cp .env.example .env
```

Open `.env` and fill in your credentials:

```
WHATSAPP_API_TOKEN=your_meta_token_here
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here
WEBHOOK_VERIFY_TOKEN=pick_any_secret_string
ANTHROPIC_API_KEY=your_anthropic_key_here
MOCK_WHATSAPP=true        # Keep true until you're ready to send real messages
```

### 2. Start everything

```bash
docker compose up --build
```

This starts:
- **PostgreSQL** database (port 5432)
- **Redis** queue (port 6379)
- **FastAPI** backend (port 8000)
- **Celery** background worker
- **Next.js** frontend (port 3000)

Wait for the line `Application startup complete` before proceeding.

### 3. Open the app

Visit [http://localhost:3000](http://localhost:3000)

### 4. Expose your webhook (for real WhatsApp messages)

In a separate terminal:

```bash
ngrok http 8000
```

Copy the `https://....ngrok.io` URL and paste it into your Meta Developer Console as the webhook URL: `https://....ngrok.io/webhook`.

> Note: ngrok free tier gives a new URL every time you restart. Update Meta's webhook URL each session, or use a paid ngrok account for a stable URL.

---

## Using the Platform

### Adding Contacts

**Option A — Manual:** Go to **Contacts**, click **Add Contact**, enter name and phone number in international format (e.g. `+919876543210`).

**Option B — CSV Import:** Click **Import CSV**. Your CSV must have these columns:

```
name,phone,tags
Priya Sharma,+919876543210,purchased
Rahul Mehta,+919123456789,vip
```

- `phone` must be in E.164 format (country code + number, no spaces or dashes)
- `tags` is comma-separated within the cell (or leave blank)
- File must be UTF-8 encoded (standard when exported from Excel or Google Sheets)

Only contacts with **consent** (opted_in = true) will receive campaign messages. Set this manually after import or when a customer explicitly opts in.

### Creating a Campaign

1. Go to **Campaigns > New Campaign**
2. Enter a campaign name
3. Select a message template (these are pre-approved by Meta)
4. Fill in any template placeholders (e.g. customer name, product name)
5. Choose your audience by tag (e.g. send to everyone tagged "vip")
6. Either send immediately or pick a scheduled date and time
7. Click **Create Campaign**

The campaign will appear in the list as `scheduled` or start running immediately.

### Managing Conversations (Inbox)

The **Inbox** shows every customer conversation. On the left, you see a list of contacts with their last message and how much time is left in their 24-hour reply window.

Click a conversation to see the full thread on the right.

**AI Auto-Reply** — There's a toggle at the top of each conversation thread. When on (default), the AI handles replies automatically. When off, you take over and can type replies manually.

> The 24-hour window is a WhatsApp rule: after the customer's last inbound message, you have 24 hours to send free-form replies. After that, you can only reach them again with a new template message.

### Opt-Out Handling

If a customer replies **STOP** (in any case — "stop", "STOP", "Stop"), they are immediately opted out. They will not receive any future campaign messages. This is automatic and instant.

---

## Customising the AI Personality

The AI assistant's personality and rules are defined in `backend/app/ai/system_prompt.txt`. Open this file and edit it to match your business:

- Tell it your business name and what you sell
- Define what offers or discounts it is allowed to mention
- List topics it should escalate to a human (e.g. complaints, refunds)

Example additions:
```
You are Meera, a friendly assistant for Anjali Jewellery, a family-run jewellery shop in Mumbai.
You can offer a 5% discount to customers who leave a review.
If a customer mentions a damaged product or asks for a refund, say you will connect them with a team member and escalate the conversation.
```

Restart the backend container after editing this file for changes to take effect.

---

## Adding Message Templates

Templates must be pre-approved by Meta before they can be used in campaigns. During development, use Meta's sandbox test templates.

To add a template to the platform, edit `backend/templates.json`:

```json
[
  {
    "name": "review_request",
    "display_name": "Post-Purchase Review Request",
    "language": "en",
    "params": [
      { "slot": "1", "label": "Customer name", "example": "Priya" },
      { "slot": "2", "label": "Product name", "example": "Gold Bangle Set" }
    ]
  }
]
```

The `name` must exactly match the template name in your Meta account. Restart the backend after editing.

---

## Running Tests

```bash
# Backend tests
cd backend
pytest

# Run tests for a specific phase only
pytest tests/phase4/

# Frontend tests
cd frontend
npm test
```

---

## Stopping the Platform

```bash
docker compose down
```

To also remove all stored data (contacts, messages, campaigns):

```bash
docker compose down -v
```

---

## Troubleshooting

**Messages aren't being received (webhook not triggering)**
- Check that ngrok is running and the URL in Meta's console matches
- Make sure the `messages` webhook field is subscribed in Meta's console
- Check backend logs: `docker compose logs backend`

**Campaign shows 0 sent**
- Check that your contacts have `opted_in = true`
- Check that the contacts have the tag you specified in the campaign audience filter
- Check Celery worker logs: `docker compose logs celery`

**AI isn't replying**
- Check that `ANTHROPIC_API_KEY` is set correctly in `.env`
- Verify the conversation has `AI auto-reply` toggled on in the Inbox
- Check backend logs for any Claude API errors

**Phone number rejected on import**
- Must be in E.164 format: `+` followed by country code and number, no spaces
- Example: `+919876543210` not `09876543210` or `+91 98765 43210`
