# 🔐 User Authorization Setup Guide

## Overview

The bot now supports restricting command access to only authorized users. This allows you to:
- Add the bot to channels without giving all members command access
- Control who can modify projects, sync data, and run reports
- Maintain security while allowing the bot to read channel messages

---

## 📋 Setup Steps

### Step 1: Add Required Slack Scope

The bot needs to read user email addresses to check authorization:

1. Go to https://api.slack.com/apps → Your App
2. Navigate to **OAuth & Permissions**
3. Under **Bot Token Scopes**, add:
   - `users:read.email` (to get user emails for authorization)

4. **Reinstall the app** to your workspace

### Step 2: Configure Authorized Users

Edit `config.json` and add the `authorized_users` array with email addresses:

```json
{
  "channel_id": "C09BMF2RKC0",
  "mailbox_channel_id": "C0A16GEAPD5",
  "authorized_users": [
    "admin@yourcompany.com",
    "pm@yourcompany.com",
    "manager@yourcompany.com"
  ],
  "channel_map": {
    ...
  }
}
```

### Step 3: Deploy

After updating `config.json`, redeploy your application.

---

## 🔒 How It Works

### Authorization Check

When a user runs a command:
1. Bot gets the user's email from Slack API
2. Checks if email is in `authorized_users` list
3. If authorized → command executes
4. If not authorized → user sees "Access Denied" message

### Protected Commands

All these commands require authorization:
- `/update-project` - Update project status
- `/add-client` - Add new client
- `/edit-client` - Edit client name
- `/publish-report` - Publish report
- `/download-report` - Download PDF
- `/sync-knowledge` - Sync to knowledge base
- `/ask` - AI queries

### Public Features (No Authorization Required)

These features work for everyone:
- Reading channel messages (for knowledge base)
- Viewing reports (if bot posts them)
- Daily automated reports

---

## ⚙️ Configuration Options

### Allow All Users (Disable Authorization)

To allow all users (backward compatibility), set an empty array:

```json
"authorized_users": []
```

Or remove the field entirely.

### Case-Insensitive Matching

Email matching is case-insensitive:
- `Admin@Company.com` matches `admin@company.com`
- `user@example.com` matches `USER@EXAMPLE.COM`

---

## 🚨 Troubleshooting

### "Access Denied" for Authorized Users

**Check:**
1. Email in `config.json` matches exactly (case doesn't matter)
2. Bot has `users:read.email` scope
3. User's Slack profile has email set
4. App was reinstalled after adding scope

### Can't Get User Email

**Possible causes:**
- Bot missing `users:read.email` scope
- User's email not set in Slack profile
- Check server logs for error messages

### Bot Can't Read Channel Messages

**Note:** Reading channel messages (for knowledge base) doesn't require authorization. The bot just needs:
- `channels:history` scope
- Bot added to channels

This is separate from command authorization.

---

## 📝 Example Configuration

```json
{
  "channel_id": "C09BMF2RKC0",
  "mailbox_channel_id": "C0A16GEAPD5",
  "authorized_users": [
    "leo@shopline.com",
    "pm@shopline.com",
    "admin@shopline.com"
  ],
  "channel_map": {
    "C09AH6P7WLD": { "client": "Avvika", "role": "internal" },
    "C096TGF7XJQ": { "client": "Avvika", "role": "external" }
  }
}
```

---

## 🔍 Security Notes

1. **Email Privacy**: The bot only checks emails for authorization, doesn't store them
2. **Logging**: Unauthorized access attempts are logged to server logs
3. **Channel Access**: Bot can be in channels without giving command access to all members
4. **Ephemeral Messages**: Access denied messages are only visible to the user who tried

---

## ✅ Testing

1. Add your email to `authorized_users` in `config.json`
2. Redeploy
3. Try a command - should work
4. Remove your email
5. Redeploy
6. Try a command - should show "Access Denied"

---

## 💡 Best Practices

1. **Start with empty list** to test, then add users gradually
2. **Use team email addresses** for easier management
3. **Keep list updated** when team members change
4. **Monitor logs** for unauthorized access attempts
5. **Document** who has access and why

