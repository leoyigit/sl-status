# Shopline Project Bot - Setup Guide

## 🚀 Enhanced Features Overview

This bot now includes:
1. **Enhanced Status Updates** - Automatic email/Slack processing with team feedback
2. **OpenAI Assistants with Knowledge Base** - True AI knowledge base for project queries
3. **Daily Automated Updates** - Enhanced daily reports
4. **Enhanced PDF Reports** - Multiple report types (full, summary, blockers)

---

## 📋 Prerequisites

1. **Slack App Setup**
   - Bot Token (`SLACK_BOT_TOKEN`)
   - Signing Secret (`SLACK_SIGNING_SECRET`)
   - Channel IDs configured in `config.json`

2. **OpenAI API**
   - API Key (`OPENAI_API_KEY`)
   - Access to `platform.openai.com` (for Assistants API)

3. **GitHub Gist** (for data storage)
   - GitHub Token (`GITHUB_TOKEN`)
   - Gist ID (`GIST_ID`)

---

## 🔧 Environment Variables

Add these to your Render/Deployment environment:

```bash
# Slack
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-signing-secret
CHANNEL_ID=C09BMF2RKC0  # Your main report channel

# OpenAI
OPENAI_API_KEY=sk-proj-xxxxx  # Your OpenAI API key (NEVER commit this to code!)
OPENAI_MODEL=gpt-4o-mini  # Options: gpt-3.5-turbo, gpt-4o-mini, gpt-4-turbo (default: gpt-3.5-turbo)
# These will be auto-generated on first run, then add them:
OPENAI_ASSISTANT_ID=asst_xxxxx  # Optional - auto-created
OPENAI_VECTOR_STORE_ID=vs_xxxxx  # Optional - auto-created

# GitHub Gist
GITHUB_TOKEN=ghp_your-token
GIST_ID=your-gist-id
```

---

## 🤖 OpenAI Assistants Setup

### Step 1: First Run
When you first deploy, the bot will automatically:
1. Create a Vector Store for the knowledge base
2. Create an Assistant with file search capabilities
3. Print the IDs to console

### Step 2: Get the IDs
Check your deployment logs for:
```
✅ Created vector store: vs_xxxxx
✅ Created assistant: asst_xxxxx
⚠️ IMPORTANT: Set OPENAI_ASSISTANT_ID=asst_xxxxx and OPENAI_VECTOR_STORE_ID=vs_xxxxx
```

### Step 3: Add to Environment
Add these IDs to your environment variables in Render:
- `OPENAI_ASSISTANT_ID=asst_xxxxx`
- `OPENAI_VECTOR_STORE_ID=vs_xxxxx`

### Step 4: Manual Sync (Optional)
Use `/sync-knowledge` command to manually sync project data to the knowledge base.

---

## 📧 Email Integration Setup

### Mailbox Channel
1. Set up email forwarding to your Slack mailbox channel
2. Configure `mailbox_channel_id` in `config.json`
3. The bot will automatically:
   - Parse incoming emails
   - Identify the client
   - Extract status updates and blockers
   - Update project status automatically
   - Post summary to report channel

### Channel Mapping
Your `config.json` should have:
```json
{
  "mailbox_channel_id": "C0A16GEAPD5",
  "channel_map": {
    "C09AH6P7WLD": { "client": "Avvika", "role": "internal" },
    "C096TGF7XJQ": { "client": "Avvika", "role": "external" },
    ...
  }
}
```

---

## 📊 Daily Reports

The bot automatically runs daily reports at 9:00 AM (server time) Monday-Friday.

**Features:**
- Priority items (stuck projects)
- Active projects summary
- Statistics overview
- Auto-sync to knowledge base

---

## 📄 PDF Reports

Enhanced PDF generation with multiple types:

### Commands:
- `/download-report` - Full detailed report
- `/download-report summary` - Summary report (key info only)
- `/download-report blockers` - Only projects with blockers

**Features:**
- Client details
- Status updates
- Blockers highlighted
- Team assignments
- Last updated timestamps

---

## 🔍 AI Assistant Features

### Using Assistants API
The bot now uses OpenAI Assistants with a knowledge base:

1. **Automatic Knowledge Base**
   - Project data synced automatically
   - Updated on status changes
   - Synced daily

2. **Query with `/ask`**
   - Uses knowledge base for context
   - More accurate answers
   - Can reference historical data

3. **Fallback**
   - If Assistant not configured, uses regular chat completion
   - Still works without knowledge base

---

## 🛠️ Available Commands

| Command | Description |
|---------|-------------|
| `/update-project` | Update project status |
| `/publish-report` | Publish report to #shopline-status |
| `/add-client` | Add a new client |
| `/edit-client` | Edit/rename client name |
| `/ask [question]` | Ask AI about projects |
| `/download-report [type]` | Generate PDF (full/summary/blockers) |
| `/sync-knowledge` | Manually sync to knowledge base |

---

## 🔄 Workflow

### Email → Status Update Flow:
1. Email arrives in mailbox channel
2. Bot parses email with AI
3. Extracts: Client, Status, Blocker
4. Updates project automatically
5. Posts summary to report channel
6. Syncs to knowledge base

### Daily Report Flow:
1. Scheduler runs at 9 AM
2. Analyzes all projects
3. Categorizes by status
4. Posts formatted report
5. Syncs data to knowledge base

---

## 🐛 Troubleshooting

### Assistant Not Working?
1. Check `OPENAI_API_KEY` is set
2. Check logs for Assistant ID creation
3. Run `/sync-knowledge` manually
4. Verify API access to `platform.openai.com`

### Email Not Processing?
1. Verify `mailbox_channel_id` in config.json
2. Check bot has access to mailbox channel
3. Verify OpenAI API key is working

### PDF Generation Fails?
1. Check `fpdf` is installed: `pip install fpdf`
2. Verify write permissions to `/tmp` directory
3. Check file size limits

---

## 📝 Notes

- **Knowledge Base Sync**: Happens automatically on:
  - Status updates
  - Daily reports
  - Manual `/sync-knowledge` command

- **Rate Limits**: OpenAI Assistants API has rate limits. The bot handles this gracefully.

- **Security**: External channels only see their own project data (configured in `channel_map`).

---

## 🎯 Next Steps

1. Deploy to Render
2. Check logs for Assistant IDs
3. Add IDs to environment variables
4. Test with `/ask` command
5. Test email processing
6. Verify daily reports

---

## 📞 Support

For issues or questions, check:
- Deployment logs
- Slack bot responses
- OpenAI API status

