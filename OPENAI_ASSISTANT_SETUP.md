# 🤖 OpenAI Assistant Configuration Guide

## Overview

You can configure your OpenAI Assistant in two ways:
1. **Via Code** (automatic on first run)
2. **Via OpenAI Platform** (recommended for advanced settings)

---

## 🌐 Configuring in OpenAI Platform (platform.openai.com)

### Step 1: Access Your Assistant

1. Go to https://platform.openai.com/assistants
2. Find your assistant (named "Shopline Project Assistant" or check your `OPENAI_ASSISTANT_ID`)
3. Click on it to open the editor

### Step 2: Configure Settings

#### **System Instructions**
Edit the **Instructions** field with detailed system prompts:

```
You are a Project Operations Assistant for Project Management Team. 
You help manage multiple ecommerce projects, track status, blockers, and provide insights.

Your responsibilities:
- Answer questions about project status, blockers, and timelines
- Analyze project data from the knowledge base
- Provide actionable insights and recommendations
- Identify risks and priorities
- Format responses in Slack-friendly markdown

Guidelines:
- Use *bold* for client names and important information
- Structure responses with bullet points when helpful
- Highlight blockers and risks clearly (use ⛔ for blockers)
- Provide actionable next steps
- Reference specific project data from the knowledge base
- Be professional, concise, and action-oriented
- If information isn't in the knowledge base, say so clearly

Current Date: {current_date}
```

#### **Model**
- Select your model: `gpt-4o-mini`, `gpt-4-turbo`, or `gpt-4o`
- This should match your `OPENAI_MODEL` environment variable

#### **Temperature**
- Range: 0.0 to 2.0
- **Recommended:** 0.7 (balanced creativity/accuracy)
- Lower (0.0-0.3): More deterministic, factual
- Higher (0.7-1.0): More creative, varied responses
- Set via `OPENAI_ASSISTANT_TEMPERATURE` env var or in platform

#### **Tools & Functions**

**File Search (Knowledge Base):**
- ✅ Enable "File search"
- Connect to your Vector Store (set in `tool_resources`)

**Code Interpreter (Optional):**
- Enable if you want the assistant to run Python code
- Useful for data analysis, calculations
- Add: `{"type": "code_interpreter"}` to tools array

**Function Calling (Optional):**
- Define custom functions for specific actions
- Example: Functions to update project status, query database

#### **Tool Resources**

**Vector Store:**
- Connect your Vector Store ID (`OPENAI_VECTOR_STORE_ID`)
- This is where your project data and Slack messages are stored
- Files uploaded here become searchable

---

## 💻 Configuring via Code

### Environment Variables

Add these to your Render environment:

```bash
# Assistant Configuration
OPENAI_ASSISTANT_ID=asst_xxxxx  # Your assistant ID
OPENAI_VECTOR_STORE_ID=vs_xxxxx  # Your vector store ID
OPENAI_ASSISTANT_TEMPERATURE=0.7  # Optional: 0.0-2.0 (default: 0.7)
```

### Code Configuration

The assistant is created with these defaults:
- **Model:** From `OPENAI_MODEL` env var (default: `gpt-4o-mini`)
- **Temperature:** From `OPENAI_ASSISTANT_TEMPERATURE` (default: 0.7)
- **Tools:** File search (knowledge base)
- **Instructions:** Basic project assistant instructions

---

## 🔧 Advanced Configuration

### Adding Code Interpreter

If you want to enable code interpreter, update the code:

```python
tools=[
    {"type": "file_search"},
    {"type": "code_interpreter"}  # Add this
]
```

### Adding Custom Functions

Example function for project updates:

```python
tools=[
    {"type": "file_search"},
    {
        "type": "function",
        "function": {
            "name": "get_project_status",
            "description": "Get status of a specific project",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {
                        "type": "string",
                        "description": "Name of the client/project"
                    }
                },
                "required": ["client_name"]
            }
        }
    }
]
```

### Updating Assistant via API

You can also update the assistant programmatically:

```python
ai_client.beta.assistants.update(
    assistant_id=ASSISTANT_ID,
    instructions="Your new instructions here",
    temperature=0.8,
    tools=[{"type": "file_search"}]
)
```

---

## 📋 Recommended Settings

### For Project Management Assistant

**System Instructions:**
- Clear role definition
- Guidelines for formatting
- Instructions to use knowledge base
- Date awareness

**Temperature:** 0.7
- Balanced between factual accuracy and helpful explanations

**Tools:**
- ✅ File search (required for knowledge base)
- ⚪ Code interpreter (optional, for data analysis)
- ⚪ Functions (optional, for custom actions)

**Model:** `gpt-4o-mini` or `gpt-4-turbo`
- `gpt-4o-mini`: Faster, cheaper, good for most tasks
- `gpt-4-turbo`: More capable, better for complex analysis

---

## 🔄 Updating Assistant

### Via Platform (Recommended)

1. Go to https://platform.openai.com/assistants
2. Click on your assistant
3. Edit settings directly
4. Click **Save**
5. Changes take effect immediately

### Via Code

Update the `setup_openai_assistant()` function and redeploy, or use the update API.

---

## ✅ Verification

After configuring:

1. **Test in Platform:**
   - Use the "Playground" tab in OpenAI platform
   - Test queries to see how assistant responds

2. **Test in Slack:**
   - Use `/ask` command
   - Check if responses match your instructions
   - Verify knowledge base is being used

3. **Check Logs:**
   - Look for assistant creation/retrieval messages
   - Verify vector store is connected

---

## 🎯 Best Practices

1. **Start Simple:** Begin with basic instructions, refine based on usage
2. **Test Temperature:** Try different values (0.5, 0.7, 0.9) to see what works best
3. **Iterate Instructions:** Update based on actual user questions
4. **Monitor Usage:** Check OpenAI dashboard for token usage and costs
5. **Version Control:** Keep track of instruction changes

---

## 📞 Need Help?

- OpenAI Assistants Docs: https://platform.openai.com/docs/assistants
- API Reference: https://platform.openai.com/docs/api-reference/assistants


