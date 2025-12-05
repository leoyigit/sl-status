# 🔐 Environment Variables Setup

## ⚠️ SECURITY WARNING

**NEVER share your API keys publicly or commit them to git!**

If you've shared a key, **rotate it immediately** in your OpenAI dashboard.

---

## 🚀 Quick Setup for Render

### Step 1: Go to Render Dashboard
1. Navigate to your service
2. Go to **Environment** tab
3. Click **Add Environment Variable**

### Step 2: Add These Variables

```bash
OPENAI_API_KEY=sk-proj-YOUR_ACTUAL_KEY_HERE
OPENAI_MODEL=gpt-4o-mini
```

### Step 3: Other Required Variables

Make sure you also have:
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `CHANNEL_ID`
- `GITHUB_TOKEN`
- `GIST_ID`

---

## 📝 For Local Development

Create a `.env` file in your project root (DO NOT commit this):

```bash
OPENAI_API_KEY=sk-proj-YOUR_ACTUAL_KEY_HERE
OPENAI_MODEL=gpt-4o-mini
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-secret
CHANNEL_ID=C09BMF2RKC0
GITHUB_TOKEN=ghp_your-token
GIST_ID=your-gist-id
```

Then load it with:
```bash
export $(cat .env | xargs)
python slprojects.py
```

---

## ✅ Verification

After setting up, your bot will:
1. Use `gpt-4o-mini` model by default
2. Create Assistant and Vector Store on first run
3. Print IDs to logs (add them to env vars for persistence)

---

## 🔄 If You Need to Rotate Your Key

1. Generate new key in OpenAI dashboard
2. Update `OPENAI_API_KEY` in Render
3. Redeploy service
4. Delete old key from OpenAI dashboard

