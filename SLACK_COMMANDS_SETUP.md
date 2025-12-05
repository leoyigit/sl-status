# 📋 Slack Commands Setup Guide

## Quick Answer

**Short answer:** Commands will work automatically, but **registering them in Slack App settings is recommended** for better user experience.

## How It Works

### Automatic (Current Setup)
With Slack Bolt framework, commands registered with `@app.command()` will work automatically if:
- ✅ Your app has the `commands` scope
- ✅ Your app is installed in the workspace
- ✅ Your request URL is configured correctly

**Commands will work without registration**, but users won't see them in Slack's command autocomplete.

### Recommended: Register Commands
Registering commands in Slack App settings provides:
- ✅ Command descriptions in autocomplete
- ✅ Better discoverability
- ✅ Short descriptions when typing `/`
- ✅ Professional user experience

## All Commands in Your Bot

Here's the complete list of commands you should register:

### 1. `/admin`
- **Description:** Manage bot configuration (users, channels)
- **Short Description:** Admin panel for configuration
- **Usage Hint:** (optional)

### 2. `/ask`
- **Description:** Ask questions about projects using AI
- **Short Description:** Ask AI about projects
- **Usage Hint:** `What projects are stuck?`

### 3. `/update-project`
- **Description:** Update project status and details
- **Short Description:** Update project information
- **Usage Hint:** (optional)

### 4. `/add-client`
- **Description:** Add a new client to the database
- **Short Description:** Add new client
- **Usage Hint:** (optional)

### 5. `/edit-client`
- **Description:** Edit or rename a client name
- **Short Description:** Edit client name
- **Usage Hint:** (optional)

### 6. `/publish-report`
- **Description:** Publish project report to channel
- **Short Description:** Publish project report
- **Usage Hint:** (optional)

### 7. `/download-report`
- **Description:** Download PDF report (full, summary, or blockers)
- **Short Description:** Download PDF report
- **Usage Hint:** `summary` or `blockers`

### 8. `/sync-knowledge`
- **Description:** Sync project data to OpenAI knowledge base
- **Short Description:** Sync to knowledge base
- **Usage Hint:** `messages` to also sync Slack messages

### 9. `/project-history`
- **Description:** View change history for a project
- **Short Description:** View project change history
- **Usage Hint:** `Avvika`

### 10. `/project-history-full`
- **Description:** View full change history for a project
- **Short Description:** View full project history
- **Usage Hint:** `Avvika`

## How to Register Commands

### Step 1: Go to Slack App Settings
1. Visit https://api.slack.com/apps
2. Select your app
3. Navigate to **Slash Commands** in the left sidebar

### Step 2: Create Each Command
For each command above:

1. Click **"Create New Command"**
2. Fill in:
   - **Command:** `/command-name` (e.g., `/admin`)
   - **Request URL:** Your app's endpoint (e.g., `https://your-app.onrender.com/slack/events`)
   - **Short Description:** Brief description (shown in autocomplete)
   - **Usage Hint:** Optional example (shown when typing)
3. Click **"Save"**

### Step 3: Verify Request URL
Make sure your Request URL matches your deployment:
- For Render: `https://your-app-name.onrender.com/slack/events`
- For local dev: `https://your-ngrok-url.ngrok.io/slack/events`

### Step 4: Reinstall App (If Needed)
If you're adding commands to an existing app:
1. Go to **Install App** in left sidebar
2. Click **"Reinstall to Workspace"**
3. Approve the installation

## Required Slack Scopes

Make sure your app has these scopes in **OAuth & Permissions**:

### Bot Token Scopes
- `commands` - Required for slash commands
- `chat:write` - Post messages
- `chat:write.public` - Post in channels bot isn't in
- `channels:history` - Read channel messages
- `groups:history` - Read private channel messages
- `users:read.email` - Get user emails (for authorization)
- `files:write` - Upload PDFs
- `app_mentions:read` - Handle @mentions

## Testing Commands

After registering:

1. **Type `/` in Slack** - You should see your commands in the list
2. **Try a command** - `/ask What projects are stuck?`
3. **Check autocomplete** - Commands should show descriptions

## Troubleshooting

### Issue: Commands not showing in autocomplete
- ✅ Make sure commands are registered in Slack App settings
- ✅ Reinstall the app to workspace
- ✅ Wait a few minutes for Slack to update

### Issue: "Command not found" error
- ✅ Check Request URL is correct
- ✅ Verify app is installed in workspace
- ✅ Check server logs for errors
- ✅ Ensure `commands` scope is added

### Issue: Commands work but no description
- ✅ Register commands in Slack App settings
- ✅ Add short descriptions
- ✅ Reinstall app

## Optional: Command Shortcuts

You can also create **Shortcuts** in Slack App settings for common actions:
- **Message Shortcuts:** Right-click message → action
- **Global Shortcuts:** Quick actions from anywhere

But slash commands are the primary interface for your bot.

## Summary

**Do you need to register?**
- **No** - Commands will work automatically
- **Yes (Recommended)** - For better UX and discoverability

**Quick Setup:**
1. Go to https://api.slack.com/apps → Your App
2. Click **Slash Commands**
3. Add each command from the list above
4. Save and reinstall app

**Time Required:** ~5-10 minutes for all commands

