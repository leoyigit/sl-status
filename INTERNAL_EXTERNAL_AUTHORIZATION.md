# 🔐 Internal vs External Channel Authorization

## Overview

This system implements **strict separation** between internal (Power Commerce team) and external (client) channels with separate authorization lists.

## Authorization Lists

### 1. `authorized_users` (Internal)
- **Purpose:** Power Commerce team members with full access
- **Access:** All internal channels + all project data
- **Location:** `config.json` → `authorized_users`

### 2. `external_authorized_users` (External)
- **Purpose:** Client users who can access their external channels
- **Access:** Only their specific external channel + only their project data
- **Location:** `config.json` → `external_authorized_users`

## How It Works

### Internal Channels
- **Role:** `"role": "internal"` in `channel_map`
- **Authorization:** Users must be in `authorized_users` list
- **Data Access:** Full access to all projects
- **Commands:** All commands available

### External Channels
- **Role:** `"role": "external"` in `channel_map`
- **Authorization:** Users must be in `external_authorized_users` list
- **Data Access:** Only their client's project data (filtered by `client` field)
- **Commands:** Limited access (can ask questions, view their project status)

## Security Features

### 1. Strict Separation
- External users **cannot** access internal channels
- External users **cannot** see other clients' data
- Internal users have full access to everything

### 2. Channel-Based Authorization
- Authorization is checked based on the channel where the command is used
- Same user can be authorized for internal channels but not external (or vice versa)

### 3. Data Filtering
- External users only see data for their client (matching `channel_map` → `client`)
- Internal fields (like `internal_notes`, `budget`) are hidden from external users

## Configuration Example

```json
{
  "authorized_users": [
    "leo@powercommerce.com",
    "adis@powercommerce.com",
    "pavel@powercommerce.com"
  ],
  "external_authorized_users": [
    "client@avvika.com",
    "pm@miamibeachbum.com",
    "contact@freshpeaches.com"
  ],
  "channel_map": {
    "C09AH6P7WLD": { "client": "Avvika", "role": "internal" },
    "C096TGF7XJQ": { "client": "Avvika", "role": "external" },
    "C09BD6QAA1F": { "client": "Miami Beach Bum", "role": "internal" },
    "C09A390J5V4": { "client": "Miami Beach Bum", "role": "external" }
  }
}
```

## Use Cases

### Scenario 1: Internal Team Member
- **User:** `leo@powercommerce.com`
- **In List:** `authorized_users`
- **Can Access:**
  - ✅ All internal channels
  - ✅ All project data
  - ✅ All commands (`/ask`, `/update-project`, `/download-report`, etc.)

### Scenario 2: Client User
- **User:** `client@avvika.com`
- **In List:** `external_authorized_users`
- **Can Access:**
  - ✅ Only Avvika external channel (`C096TGF7XJQ`)
  - ✅ Only Avvika project data
  - ✅ Limited commands (can ask questions, cannot update projects)
- **Cannot Access:**
  - ❌ Internal channels
  - ❌ Other clients' data
  - ❌ Admin commands

### Scenario 3: Unauthorized User
- **User:** `guest@example.com`
- **Not in any list**
- **Cannot Access:**
  - ❌ Any channels
  - ❌ Any commands
  - Gets "Access Denied" message

## Commands Behavior

### `/ask` Command
- **Internal:** Can ask about all projects
- **External:** Can only ask about their client's project

### `/update-project` Command
- **Internal:** Can update any project
- **External:** ❌ Not available (access denied)

### `/download-report` Command
- **Internal:** Can download full reports
- **External:** ❌ Not available (access denied)

### `/add-client`, `/edit-client`, `/sync-knowledge`
- **Internal:** ✅ Available
- **External:** ❌ Not available (access denied)

## Setup Instructions

### Step 1: Add External Users
Add client email addresses to `external_authorized_users` in `config.json`:

```json
"external_authorized_users": [
  "client1@example.com",
  "client2@example.com",
  "pm@clientcompany.com"
]
```

### Step 2: Verify Channel Mapping
Ensure external channels are properly mapped:

```json
"channel_map": {
  "C09XXX": { "client": "Client Name", "role": "external" }
}
```

### Step 3: Deploy
- Update `CONFIG_JSON` environment variable in Render with the new config
- Or update `config.json` file if using file-based config

### Step 4: Test
1. Test with internal user → Should have full access
2. Test with external user → Should only see their client's data
3. Test with unauthorized user → Should get "Access Denied"

## Important Notes

⚠️ **Security:**
- If `external_authorized_users` is empty, external channels will **deny all access** (strict security)
- If `authorized_users` is empty, internal channels allow all (backward compatibility)

⚠️ **Email Matching:**
- Authorization is case-insensitive
- Must match exactly (no wildcards)

⚠️ **Channel Context:**
- Authorization is checked based on the channel where the command is used
- Same user can have different access levels in different channels

## Troubleshooting

### Issue: External user getting "Access Denied"
- ✅ Check if email is in `external_authorized_users` list
- ✅ Check if channel is mapped with `"role": "external"`
- ✅ Check if channel's `client` matches the project's `client` field

### Issue: Internal user can't access external channel
- ✅ This is **expected behavior** - internal users should use internal channels
- ✅ If needed, add them to `external_authorized_users` as well

### Issue: User can see other clients' data
- ✅ Check channel mapping - ensure external channel has correct `client` name
- ✅ Check project data - ensure `client` field matches channel mapping

## Logging

The system logs authorization attempts:
- ✅ Successful authorization: `"✅ Authorized [internal/external] access: email"`
- 🚫 Failed authorization: `"🚫 Unauthorized [internal/external] access attempt by email"`

Check your deployment logs to debug authorization issues.

