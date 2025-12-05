# 🔐 Admin Command Guide

## Overview

The `/admin` command provides a user-friendly interface for managing bot configuration directly from Slack. This command is **only available to internal authorized users**.

## Features

### 1. Manage Internal Users (`authorized_users`)
- **Add users:** Add new Power Commerce team members who can access internal channels
- **Remove users:** Remove users from the internal authorization list

### 2. Manage External Users (`external_authorized_users`)
- **Add users:** Add client users who can access their external channels
- **Remove users:** Remove client users from external authorization

### 3. Manage Channel Mapping (`channel_map`)
- **Add channels:** Map Slack channels to clients with roles (internal/external)

## Usage

### Step 1: Open Admin Panel
```
/admin
```

### Step 2: Make Changes

#### Adding/Removing Users
1. Select the user list (Internal or External)
2. Choose action: "Add User" or "Remove User"
3. Enter the email address
4. Click "Save Changes"

#### Adding Channel Mapping
1. Scroll to "Channel Mapping" section
2. Select "Add Channel"
3. Enter:
   - **Channel ID:** The Slack channel ID (e.g., `C09XXXXXX`)
   - **Client Name:** The client name (e.g., "Avvika")
   - **Role:** Select "Internal" or "External"
4. Click "Save Changes"

### Step 3: Review Changes
After saving, you'll receive a confirmation message showing what was changed.

## Important Notes

### Environment Variables
If you're using `CONFIG_JSON` environment variable (e.g., in Render):

1. **After making changes via `/admin`:**
   - The changes are saved to `config.json` file
   - **You must manually update** the `CONFIG_JSON` environment variable in your deployment platform
   - Restart the service for changes to take effect

2. **To update CONFIG_JSON:**
   - Go to your deployment platform (e.g., Render Dashboard)
   - Navigate to Environment Variables
   - Update `CONFIG_JSON` with the new JSON content from `config.json`
   - Restart the service

### File-Based Config
If you're using `config.json` file directly (local development):
- Changes are saved automatically
- No additional steps needed
- Config reloads on next request

## Examples

### Example 1: Add Internal User
```
1. Run /admin
2. Under "Internal Users", select "Add User"
3. Enter: leo@powercommerce.com
4. Click "Save Changes"
```

### Example 2: Remove External User
```
1. Run /admin
2. Under "External Users", select "Remove User"
3. Enter: oldclient@example.com
4. Click "Save Changes"
```

### Example 3: Add Channel Mapping
```
1. Run /admin
2. Under "Channel Mapping", select "Add Channel"
3. Enter:
   - Channel ID: C09NEWCHANNEL
   - Client Name: New Client
   - Role: External
4. Click "Save Changes"
```

## Security

- **Access Control:** Only users in `authorized_users` can use `/admin`
- **Internal Only:** External users cannot access admin commands
- **Validation:** Email addresses are validated and stored in lowercase
- **Case Insensitive:** Email matching is case-insensitive

## Troubleshooting

### Issue: "Access Denied"
- ✅ Check if your email is in `authorized_users` list
- ✅ Make sure you're using the command in an internal channel

### Issue: Changes Not Taking Effect
- ✅ If using `CONFIG_JSON` env var: Update it manually and restart service
- ✅ Check server logs for errors
- ✅ Verify `config.json` file was updated

### Issue: Can't Find Channel ID
- ✅ Right-click on the channel in Slack → "View channel details"
- ✅ Or use `/invite @bot` and check the channel ID from the URL
- ✅ Channel IDs start with `C` (public) or `G` (private)

### Issue: Email Already Exists
- ✅ The system will warn you if trying to add a duplicate
- ✅ Use "Remove User" first, then "Add User" if needed

## Best Practices

1. **Test Changes:** Test with a single user first before bulk changes
2. **Backup Config:** Keep a backup of your `config.json` before major changes
3. **Document Changes:** Keep track of who was added/removed and when
4. **Regular Review:** Periodically review authorized users to remove inactive accounts
5. **Channel Naming:** Use consistent client names in channel mappings

## Command Reference

| Command | Access | Description |
|---------|--------|-------------|
| `/admin` | Internal Only | Open admin panel for configuration management |

## Related Commands

- `/ask` - Ask questions (available to external users)
- `/update-project` - Update project status (internal only)
- `/add-client` - Add new client (internal only)
- `/sync-knowledge` - Sync data to knowledge base (internal only)

