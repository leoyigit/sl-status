# 🔐 Config.json via Environment Variables (Render)

## Overview

You can store your `config.json` as an environment variable in Render instead of committing it to your repository. This is a **better security practice** for sensitive configuration.

---

## 🚀 Setup in Render

### Step 1: Prepare Your JSON

Take your `config.json` content and format it as a **single-line JSON string**:

```json
{"channel_id":"C09BMF2RKC0","mailbox_channel_id":"C0A16GEAPD5","authorized_users":["adis@powercommerce.com","leo@powercommerce.com"],"channel_map":{"C09AH6P7WLD":{"client":"Avvika","role":"internal"}}}
```

**Or use a JSON minifier:**
- Online: https://jsonformatter.org/json-minify
- Or remove all whitespace/newlines manually

### Step 2: Add to Render Environment Variables

1. Go to your Render service dashboard
2. Navigate to **Environment** tab
3. Click **Add Environment Variable**
4. Add:
   - **Key:** `CONFIG_JSON`
   - **Value:** Your minified JSON string (paste the entire JSON on one line)

### Step 3: Deploy

After adding the environment variable, Render will automatically redeploy your service.

---

## 📋 Example Configuration

### In Render Environment Variables:

**Key:** `CONFIG_JSON`

**Value:**
```json
{"channel_id":"C09BMF2RKC0","mailbox_channel_id":"C0A16GEAPD5","authorized_users":["adis@powercommerce.com","adis.p@powercommerce.com","a@powercommerce.com","a@flyrank.com","b@flyrank.com","edis@powercommerce.com","evan@powercommerce.com","jusa@powercommerce.com","labros@powercommerce.com","leo@flyrank.com","leo@powercommerce.com","mirza.n@powercommerce.com","pavel@powercommerce.com","sela@flyrank.com","thanasis@flyrank.com"],"channel_map":{"C09AH6P7WLD":{"client":"Avvika","role":"internal"},"C096TGF7XJQ":{"client":"Avvika","role":"external"},"C09BD6QAA1F":{"client":"Miami Beach Bum","role":"internal"},"C09A390J5V4":{"client":"Miami Beach Bum","role":"external"},"C09A17LEV0D":{"client":"Caire Beauty","role":"internal"},"C099PJRSVPH":{"client":"Caire Beauty","role":"external"},"C09A69R94GP":{"client":"AnaOno","role":"external"},"C09AGQ33RE3":{"client":"Fresh Peaches","role":"internal"},"C09BMMCANQ0":{"client":"Fresh Peaches","role":"external"},"C09A0HRF415":{"client":"Untoxicated","role":"internal"},"C09A0HUT0DD":{"client":"Untoxicated","role":"external"},"C09ANMNAB7Z":{"client":"Miss Commando","role":"internal"},"C09BDEMFFFB":{"client":"Miss Commando","role":"external"},"C09BH2AGNJY":{"client":"Shield Wallet","role":"internal"},"C09BSAZ10AV":{"client":"Shield Wallet","role":"external"},"C09BA317NF6":{"client":"Oku Energy","role":"internal"},"C09BZ8KBF08":{"client":"Oku Energy","role":"external"},"C09BHCBLFM2":{"client":"MagLynx","role":"internal"},"C09BHCHLDS8":{"client":"MagLynx","role":"external"}}}
```

---

## ✅ How It Works

The code now checks in this order:

1. **First:** Tries to load from `CONFIG_JSON` environment variable
2. **Fallback:** If not found, loads from `config.json` file
3. **Default:** If neither exists, uses empty defaults

This means:
- ✅ **Production (Render):** Uses environment variable (secure)
- ✅ **Local Development:** Uses `config.json` file (convenient)
- ✅ **Both work:** Flexible setup

---

## 🔧 Quick Setup Script

To convert your `config.json` to a minified string for Render:

```bash
# Using Python
python3 -c "import json; print(json.dumps(json.load(open('config.json')), separators=(',', ':')))"
```

Or use an online JSON minifier.

---

## 📝 Benefits

✅ **Security:** Config not in git repository  
✅ **Flexibility:** Easy to update without code changes  
✅ **Secrets:** Can store sensitive channel IDs securely  
✅ **Team Access:** Only Render admins can see/edit  
✅ **Backward Compatible:** Still works with config.json file locally  

---

## ⚠️ Important Notes

1. **JSON must be valid:** Ensure no syntax errors
2. **Single line:** Remove all newlines/whitespace
3. **Escape quotes:** If you have quotes in values, they'll be escaped automatically
4. **Test after deploy:** Check logs to confirm config loaded correctly

---

## 🧪 Testing

After deployment, check your logs. You should see:
- `✅ Loaded config from CONFIG_JSON environment variable` (if using env var)
- `✅ Loaded config from config.json file` (if using file)

If you see warnings, check your JSON format.

---

## 🔄 Updating Config

To update your configuration:

1. Edit your `config.json` locally
2. Minify it to a single line
3. Update the `CONFIG_JSON` environment variable in Render
4. Render will auto-redeploy

No code changes needed! 🎉

