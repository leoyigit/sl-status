import json
import os
import requests
import re
import threading
from datetime import datetime
from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler

# Try importing FPDF for PDF generation
try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("⚠️ FPDF not installed. PDF features will be disabled.")

# --- CONFIGURATION ---
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
CHANNEL_ID_REPORT = os.environ.get("CHANNEL_ID") # Default channel for reports

# GitHub Gist Config
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GIST_ID = os.environ.get("GIST_ID")
GIST_FILENAME = "projects.json"

# OpenAI Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# OpenAI Model Config (default to gpt-4o-mini, fallback to gpt-3.5-turbo)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # Options: gpt-3.5-turbo, gpt-4o-mini, gpt-4-turbo

# OpenAI Assistant Config (for knowledge base)
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID")  # Will be created if not exists
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID")  # Will be created if not exists

# --- CONFIGURATION LOADING ---
def load_config():
    """Loads the channel map and settings from environment variable or config.json"""
    # First, try to load from environment variable (for Render/secrets)
    config_json = os.environ.get("CONFIG_JSON")
    if config_json:
        try:
            config = json.loads(config_json)
            print("✅ Loaded config from CONFIG_JSON environment variable")
            return config
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing CONFIG_JSON: {e}")
            print("⚠️ Falling back to config.json file...")
    
    # Fallback to config.json file (for local development)
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
            print("✅ Loaded config from config.json file")
            return config
    except FileNotFoundError:
        print("⚠️ config.json not found and CONFIG_JSON not set.")
        print("⚠️ Using default empty configuration.")
        return {"mailbox_channel_id": "", "channel_map": {}, "authorized_users": [], "external_authorized_users": []}
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing config.json: {e}")
        return {"mailbox_channel_id": "", "channel_map": {}, "authorized_users": [], "external_authorized_users": []}

# Load the config once when the app starts
app_config = load_config()
MAILBOX_CHANNEL_ID = app_config.get("mailbox_channel_id")
CHANNEL_MAP = app_config.get("channel_map", {})
AUTHORIZED_USERS = app_config.get("authorized_users", [])  # List of authorized email addresses for INTERNAL channels
EXTERNAL_AUTHORIZED_USERS = app_config.get("external_authorized_users", [])  # List of authorized email addresses for EXTERNAL channels

# --- HELPER: CONFIG MANAGEMENT ---
def save_config(config):
    """Save config to file and update in-memory variables
    
    Note: If using CONFIG_JSON environment variable, you'll need to update it manually
    in your deployment platform (e.g., Render) after making changes here.
    """
    global app_config, MAILBOX_CHANNEL_ID, CHANNEL_MAP, AUTHORIZED_USERS, EXTERNAL_AUTHORIZED_USERS
    
    try:
        # Save to config.json file
        with open("config.json", "w") as f:
            json.dump(config, f, indent=2)
        
        # Update in-memory variables
        app_config = config
        MAILBOX_CHANNEL_ID = config.get("mailbox_channel_id")
        CHANNEL_MAP = config.get("channel_map", {})
        AUTHORIZED_USERS = config.get("authorized_users", [])
        EXTERNAL_AUTHORIZED_USERS = config.get("external_authorized_users", [])
        
        print("✅ Config saved successfully to config.json")
        print("⚠️ If using CONFIG_JSON environment variable, update it in your deployment platform")
        return True
    except Exception as e:
        print(f"❌ Error saving config: {e}")
        import traceback
        traceback.print_exc()
        return False

def reload_config():
    """Reload config from file/environment"""
    global app_config, MAILBOX_CHANNEL_ID, CHANNEL_MAP, AUTHORIZED_USERS, EXTERNAL_AUTHORIZED_USERS
    
    app_config = load_config()
    MAILBOX_CHANNEL_ID = app_config.get("mailbox_channel_id")
    CHANNEL_MAP = app_config.get("channel_map", {})
    AUTHORIZED_USERS = app_config.get("authorized_users", [])
    EXTERNAL_AUTHORIZED_USERS = app_config.get("external_authorized_users", [])
    
    print("✅ Config reloaded")

# Initialize DB Migration check on startup
try:
    migrate_legacy_db()
except Exception as e:
    print(f"⚠️ Migration check failed: {e}")


# --- APP SETUP ---
app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

# --- DATABASE FUNCTIONS ---
# --- DATABASE FUNCTIONS ---
def get_gist_content():
    """Fetch the raw Gist object from GitHub"""
    if not GITHUB_TOKEN or not GIST_ID: return None
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        response = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Error getting Gist content: {e}")
    return None

def load_project(client_name):
    """Load a specific project file from Gist"""
    if not client_name: return None
    
    filename = f"{client_name}.json"
    gist = get_gist_content()
    
    if gist and "files" in gist:
        file_data = gist["files"].get(filename)
        if file_data and file_data.get("content"):
            try:
                return json.loads(file_data["content"])
            except json.JSONDecodeError:
                print(f"❌ Error parsing {filename}")
                return None
    return None

def save_project(project_data):
    """Save a specific project to its own file in Gist"""
    if not GITHUB_TOKEN or not GIST_ID: return False
    
    if not project_data or not isinstance(project_data, dict):
        print("❌ Invalid project data for save")
        return False
        
    client_name = project_data.get("client")
    if not client_name:
        print("❌ Project data missing client name")
        return False
        
    filename = f"{client_name}.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    # payload to update just this file
    payload = {"files": {filename: {"content": json.dumps(project_data, indent=2)}}}
    
    try:
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", json=payload, headers=headers)
        return True
    except Exception as e:
        print(f"❌ Error saving project {client_name}: {e}")
        return False

def delete_project(client_name):
    """Delete a project file from Gist (used for renaming/deleting)"""
    if not GITHUB_TOKEN or not GIST_ID or not client_name: return False
    
    filename = f"{client_name}.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    # Setting content to null deletes the file in Gist
    payload = {"files": {filename: None}}
    
    try:
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", json=payload, headers=headers)
        print(f"🗑️ Deleted project file: {filename}")
        return True
    except Exception as e:
        print(f"❌ Error deleting project {client_name}: {e}")
        return False


def load_db():
    """Legacy/Compat: Loads ALL projects from Gist (aggregates all JSON files)"""
    return load_all_projects()

def load_all_projects():
    """Load all project files from Gist excluding system files"""
    gist = get_gist_content()
    if not gist or "files" not in gist: return []
    
    projects = []
    skipped_files = ["projects.json", "gistfile1.txt"] # Legacy/System files to skip
    
    for filename, file_data in gist["files"].items():
        if filename in skipped_files: continue
        if not filename.endswith(".json"): continue
        
        # Check if it looks like a project file (simple heuristic)
        try:
            content = file_data.get("content", "")
            if not content: continue
            
            data = json.loads(content)
            
            # If it's a dict with 'client' field, it's a project
            if isinstance(data, dict) and "client" in data:
                projects.append(data)
            # If it's a list (legacy format logic?), extend? 
            # Note: We are moving to 1 file = 1 project object (dict).
            # But if we accidentally load the old projects.json list, we should probably ignore it here
            # or handle migration. Migration is separate.
            
        except json.JSONDecodeError:
            continue
            
    return projects

def save_db(data):
    """Legacy/Compat: Saves a LIST of projects, updating each individual file"""
    # This is expensive if data is big, but ensures compatibility
    if not isinstance(data, list):
        print("❌ save_db expected a list of projects")
        return
        
    # We can do a bulk update to Gist in one request
    files_payload = {}
    
    for project in data:
        client_name = project.get("client")
        if client_name:
            filename = f"{client_name}.json"
            files_payload[filename] = {"content": json.dumps(project, indent=2)}
            
    if not files_payload:
        return

    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    payload = {"files": files_payload}
    
    try:
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", json=payload, headers=headers)
    except Exception as e:
        print(f"❌ Error saving bulk DB: {e}")

def migrate_legacy_db():
    """One-time migration: Split projects.json into individual files"""
    print("🔄 Checking for legacy DB migration...")
    gist = get_gist_content()
    if not gist or "files" not in gist:
        return
        
    legacy_file = "projects.json"
    
    if legacy_file in gist["files"]:
        print(f"📦 Found {legacy_file}, attempting migration...")
        content = gist["files"][legacy_file].get("content")
        
        if content:
            try:
                projects = json.loads(content)
                if isinstance(projects, list):
                    # Prepare bulk update: create new files, delete old one
                    files_payload = {}
                    
                    # 1. Create individual files
                    for p in projects:
                        client = p.get("client")
                        if client:
                            files_payload[f"{client}.json"] = {"content": json.dumps(p, indent=2)}
                    
                    # 2. Delete legacy file (set to null)
                    files_payload[legacy_file] = None
                    
                    # 3. Send update
                    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
                    requests.patch(f"https://api.github.com/gists/{GIST_ID}", json={"files": files_payload}, headers=headers)
                    print(f"✅ Migration complete! Split {len(projects)} projects into separate files.")
                else:
                    print("⚠️ projects.json is not a list, skipping migration.")
                    
            except Exception as e:
                print(f"❌ Migration failed: {e}")
        else:
            print("⚠️ projects.json empty.")


# --- HELPER: CONTEXT SECURITY ---
def get_request_context(channel_id):
    """Determines if the request is Internal (Full Access) or External (Restricted)."""
    return CHANNEL_MAP.get(channel_id, {"client": None, "role": "internal"}) # Default to internal if unknown/DM

# --- HELPER: USER AUTHORIZATION ---
def get_user_email(user_id, client):
    """Get user email from Slack user ID"""
    try:
        user_info = client.users_info(user=user_id)
        if user_info.get("ok"):
            return user_info["user"].get("profile", {}).get("email", "")
    except Exception as e:
        print(f"❌ Error getting user email: {e}")
    return None

def is_user_authorized(user_id, client, channel_id=None):
    """Check if user is authorized to use commands based on channel role
    
    Args:
        user_id: Slack user ID
        client: Slack client
        channel_id: Optional channel ID to determine if internal or external authorization
    
    Returns:
        bool: True if user is authorized for the channel, False otherwise
    """
    # Get user email
    user_email = get_user_email(user_id, client)
    if not user_email:
        print(f"⚠️ Could not get email for user {user_id}")
        return False
    
    user_email_lower = user_email.lower()
    
    # Determine channel role if channel_id provided
    if channel_id:
        context = get_request_context(channel_id)
        role = context.get('role', 'internal')
        target_client = context.get('client')
        
        if role == 'external':
            # EXTERNAL CHANNEL - Check external authorization
            # If no external authorized users list, deny access (strict security)
            if not EXTERNAL_AUTHORIZED_USERS or len(EXTERNAL_AUTHORIZED_USERS) == 0:
                print(f"🚫 External channel access denied: No external_authorized_users configured")
                print(f"   User: {user_email}, Channel: {channel_id}, Client: {target_client}")
                return False
            
            # Check if user is in external authorized list
            external_emails_lower = [email.lower() for email in EXTERNAL_AUTHORIZED_USERS]
            is_authorized = user_email_lower in external_emails_lower
            
            if not is_authorized:
                print(f"🚫 Unauthorized external access attempt by {user_email} (user_id: {user_id}, channel: {channel_id}, client: {target_client})")
            else:
                print(f"✅ Authorized external access: {user_email} in channel {channel_id} (client: {target_client})")
            
            return is_authorized
        else:
            # INTERNAL CHANNEL - Check internal authorization
            # If no authorized users list, allow all (backward compatibility for internal)
            if not AUTHORIZED_USERS or len(AUTHORIZED_USERS) == 0:
                print(f"⚠️ No authorized_users configured - allowing all internal access (backward compatibility)")
                return True
            
            # Check if user is in internal authorized list
            internal_emails_lower = [email.lower() for email in AUTHORIZED_USERS]
            is_authorized = user_email_lower in internal_emails_lower
            
            if not is_authorized:
                print(f"🚫 Unauthorized internal access attempt by {user_email} (user_id: {user_id}, channel: {channel_id})")
            else:
                print(f"✅ Authorized internal access: {user_email} in channel {channel_id}")
            
            return is_authorized
    else:
        # No channel context - check internal list (default for commands without channel context)
        # If no authorized users list, allow all (backward compatibility)
        if not AUTHORIZED_USERS or len(AUTHORIZED_USERS) == 0:
            return True
        
        # Check if email is in authorized list (case-insensitive)
        authorized_emails_lower = [email.lower() for email in AUTHORIZED_USERS]
        is_authorized = user_email_lower in authorized_emails_lower
        
        if not is_authorized:
            print(f"🚫 Unauthorized access attempt by {user_email} (user_id: {user_id}, no channel context)")
        
        return is_authorized

def require_authorization(internal_only=False):
    """Decorator to require authorization for commands
    
    Args:
        internal_only: If True, only internal users can use this command (blocks external users)
    """
    def decorator(func):
        import functools
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract body and client from args/kwargs
            body = None
            client = None
            
            # Find body and client in args
            for arg in args:
                if isinstance(arg, dict) and 'user_id' in arg:
                    body = arg
                elif hasattr(arg, 'chat_postEphemeral'):
                    client = arg
            
            # Find in kwargs
            if not body:
                body = kwargs.get('body')
            if not client:
                client = kwargs.get('client')
            
            if not body or not client:
                # If we can't find them, just call the function (fallback)
                return func(*args, **kwargs)
            
            user_id = body.get('user_id')
            channel_id = body.get('channel_id')
            
            # Check if command is internal-only and user is in external channel
            if internal_only and channel_id:
                context = get_request_context(channel_id)
                role = context.get('role', 'internal')
                if role == 'external':
                    # Try to ack if ack is in args
                    ack = None
                    for arg in args:
                        if callable(arg) and arg.__name__ == 'ack':
                            ack = arg
                            break
                    if not ack:
                        ack = kwargs.get('ack')
                    
                    if ack:
                        ack()
                    
                    client.chat_postEphemeral(
                        channel=channel_id,
                        user=user_id,
                        text=(
                            "🚫 *Access Denied*\n\n"
                            "This command is only available to internal team members.\n"
                            "External users can use `/ask` to ask questions about their project."
                        )
                    )
                    return
            
            if not is_user_authorized(user_id, client, channel_id):
                # Try to ack if ack is in args
                ack = None
                for arg in args:
                    if callable(arg) and arg.__name__ == 'ack':
                        ack = arg
                        break
                if not ack:
                    ack = kwargs.get('ack')
                
                if ack:
                    ack()
                
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text=(
                        "🚫 *Access Denied*\n\n"
                        "You are not authorized to use this command.\n"
                        "Please contact your administrator to be added to the authorized users list."
                    )
                )
                return
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

# ==========================================
# FEATURE: OPENAI ASSISTANTS & KNOWLEDGE BASE
# ==========================================
def setup_openai_assistant():
    """Initialize or retrieve OpenAI Assistant with knowledge base"""
    if not ai_client:
        print("⚠️ OpenAI client not configured. Assistant features disabled.")
        return None, None
    
    try:
        # Check if assistant already exists
        if ASSISTANT_ID:
            try:
                assistant = ai_client.beta.assistants.retrieve(ASSISTANT_ID)
                vector_store_id = assistant.tool_resources.file_search.vector_store_ids[0] if assistant.tool_resources and assistant.tool_resources.file_search else None
                
                # Update assistant instructions to ensure email search is enabled
                # This ensures the assistant always has the latest instructions
                try:
                    ai_client.beta.assistants.update(
                        assistant_id=assistant.id,
                        instructions=(
                            "You are a Project Operations Assistant with access to project data and email communications.\n\n"
                            "DATA SOURCES:\n"
                            "1. 'projects.json' - Contains structured project status, blockers, and metadata\n"
                            "2. 'Slack Logs' file - Contains ALL emails from the mailbox channel and Slack chat messages\n\n"
                            "CRITICAL SEARCH RULES:\n"
                            "- ALWAYS use file_search tool when user asks about:\n"
                            "  * Emails, mailbox, email content, email body, communications\n"
                            "  * Specific client names (e.g., 'Mimosa', 'Avvika') combined with 'email'\n"
                            "  * 'What did [client] say in their email?'\n"
                            "  * 'Read the email about [client]'\n"
                            "  * Any question about email content or messages\n\n"
                            "EMAIL IDENTIFICATION IN LOGS:\n"
                            "- Emails are marked with: '📂 Source: MAILBOX_INBOX (Email)'\n"
                            "- Look for entries where type is 'Email' and client is 'MAILBOX_INBOX'\n"
                            "- When searching for a specific client's emails, search for the client name in the Content section\n"
                            "- The full email body/content is in the '📝 EMAIL CONTENT:' or '📝 Content:' section\n\n"
                            "SEARCH STRATEGY:\n"
                            "1. If asked about emails, IMMEDIATELY use file_search on 'Slack Logs'\n"
                            "2. Search for the client name mentioned in the question\n"
                            "3. Return the FULL email content from the '📝 EMAIL CONTENT:' section\n"
                            "4. If multiple emails exist, show the most recent ones first\n\n"
                            "RESPONSE FORMAT:\n"
                            "- Use Slack-friendly formatting (*bold*, • lists)\n"
                            "- When showing email content, quote it clearly\n"
                            "- Include the date/timestamp from the log entry\n"
                            "- No Markdown headers (#)\n\n"
                            "EXAMPLE:\n"
                            "User: 'What did Mimosa say in their email?'\n"
                            "You: Use file_search → Find entries with 'Mimosa' and 'MAILBOX_INBOX' → Return full email content"
                        )
                    )
                    print("✅ Updated assistant instructions for email search")
                except Exception as update_error:
                    print(f"⚠️ Could not update assistant instructions: {update_error}")
                
                return assistant.id, vector_store_id
            except Exception:
                print(f"⚠️ Assistant {ASSISTANT_ID} not found. Creating new one...")
        
        # Create vector store for knowledge base
        # Vector stores are accessed through beta.vector_stores in OpenAI SDK
        try:
            # Check if vector_stores exists in beta
            if hasattr(ai_client.beta, 'vector_stores'):
                vector_store = ai_client.beta.vector_stores.create(
                    name="Projects Knowledge Base"
                )
            else:
                # Try direct access (for newer SDK versions)
                vector_store = ai_client.vector_stores.create(
                    name="Projects Knowledge Base"
                )
        except Exception as e:
            print(f"❌ Error creating vector store: {e}")
            print("⚠️ Vector stores may not be available. Check your OpenAI SDK version.")
            return None, None
        
        vector_store_id = vector_store.id
        print(f"✅ Created vector store: {vector_store_id}")
        
# Create assistant with SLACK-SPECIFIC instructions
        assistant = ai_client.beta.assistants.create(
            name="Shopline Project Assistant",
            instructions=(
                "You are a Project Operations Assistant with access to project data and email communications.\n\n"
                "DATA SOURCES:\n"
                "1. 'projects.json' - Contains structured project status, blockers, and metadata\n"
                "2. 'Slack Logs' file - Contains ALL emails from the mailbox channel and Slack chat messages\n\n"
                "CRITICAL SEARCH RULES:\n"
                "- ALWAYS use file_search tool when user asks about:\n"
                "  * Emails, mailbox, email content, email body, communications\n"
                "  * Specific client names (e.g., 'Mimosa', 'Avvika') combined with 'email'\n"
                "  * 'What did [client] say in their email?'\n"
                "  * 'Read the email about [client]'\n"
                "  * Any question about email content or messages\n\n"
                "EMAIL IDENTIFICATION IN LOGS:\n"
                "- Emails are marked with: '📂 Source: MAILBOX_INBOX (Email)'\n"
                "- Look for entries where type is 'Email' and client is 'MAILBOX_INBOX'\n"
                "- When searching for a specific client's emails, search for the client name in the Content section\n"
                "- The full email body/content is in the '📝 Content:' section\n\n"
                "SEARCH STRATEGY:\n"
                "1. If asked about emails, IMMEDIATELY use file_search on 'Slack Logs'\n"
                "2. Search for the client name mentioned in the question\n"
                "3. Return the FULL email content from the '📝 EMAIL CONTENT:' section\n"
                "4. If multiple emails exist, show the most recent ones first\n\n"
                "RESPONSE FORMAT:\n"
                "- Use Slack-friendly formatting (*bold*, • lists)\n"
                "- When showing email content, quote it clearly\n"
                "- Include the date/timestamp from the log entry\n"
                "- No Markdown headers (#)\n\n"
                "EXAMPLE:\n"
                "User: 'What did Mimosa say in their email?'\n"
                "You: Use file_search → Find entries with 'Mimosa' and 'MAILBOX_INBOX' → Return full email content"
            ),
            model=OPENAI_MODEL,
            tools=[{"type": "file_search"}],
            tool_resources={
                "file_search": {
                    "vector_store_ids": [vector_store_id]
                }
            }
        )
        print(f"✅ Created assistant: {assistant.id}")
        print(f"⚠️ IMPORTANT: Set OPENAI_ASSISTANT_ID={assistant.id} and OPENAI_VECTOR_STORE_ID={vector_store_id} as environment variables")
        return assistant.id, vector_store_id
    except Exception as e:
        print(f"❌ Error setting up assistant: {e}")
        return None, None

def fetch_channel_messages(channel_id, limit=100):
    """Fetch recent messages from a Slack channel (Robust Version)"""
    try:
        # We use a try/except block specifically for the API call
        try:
            result = app.client.conversations_history(
                channel=channel_id,
                limit=limit
            )
        except Exception as e:
            # Check if it's a "not_in_channel" error
            error_str = str(e)
            if "not_in_channel" in error_str:
                print(f"⚠️ Bot is not in channel {channel_id}. Skipping.")
                return []
            elif "channel_not_found" in error_str:
                 print(f"⚠️ Channel {channel_id} not found. Skipping.")
                 return []
            else:
                # If it's a real error, raise it so the outer block catches it
                raise e

        if not result.get("ok"):
            print(f"⚠️ Slack API error for {channel_id}: {result.get('error')}")
            return []
        
        all_messages = result.get("messages", [])
        messages = []
        
        for msg in all_messages:
            # Skip bot messages and system messages
            if msg.get("subtype") in ["bot_message", "channel_join", "channel_leave", "channel_topic"]:
                continue
            
            text = msg.get("text", "")
            if not text and "files" in msg:
                text = f"[File shared]"
            
            # Reduce threshold to capture short status updates
            if text and len(text.strip()) > 2:
                messages.append({
                    "text": text,
                    "user": msg.get("user", "unknown"),
                    "ts": msg.get("ts", ""),
                    "channel": channel_id
                })
        
        return messages

    except Exception as e:
        # Use simple print to avoid massive stack traces in logs for simple errors
        print(f"❌ Error fetching messages from {channel_id}: {str(e)[:100]}")
        return []

def sync_slack_messages_to_knowledge_base():
    """Fetch and sync messages with detailed logging"""
    if not ai_client:
        return "❌ AI Client not configured"
    
    # Get IDs (and ensure they exist)
    assistant_id, vector_store_id = setup_openai_assistant()
    if not assistant_id or not vector_store_id:
        return "❌ Assistant/Vector Store setup failed"
    
    try:
        all_messages = []
        stats = {"mailbox": 0, "channels": 0}

        # --- 1. Fetch Messages ---
        channels_to_sync = []
        
        # Add project channels
        for cid, ctx in CHANNEL_MAP.items():
            if ctx.get("role") in ["internal", "external"]:
                channels_to_sync.append({
                    "id": cid, "client": ctx.get("client", "Unknown"), "role": ctx.get("role", "internal")
                })
        
        # Add Mailbox Channel
        if MAILBOX_CHANNEL_ID:
            channels_to_sync.append({
                "id": MAILBOX_CHANNEL_ID, "client": "MAILBOX_INBOX", "role": "email_source"
            })

        print(f"📥 Starting sync for {len(channels_to_sync)} channels...")

        for ch in channels_to_sync:
            channel_id = ch["id"]
            client_name = ch["client"]
            
            # Fetch messages (Now safe from crashing)
            messages = fetch_channel_messages(channel_id, limit=50)
            
            if messages:
                # Update stats
                if client_name == "MAILBOX_INBOX":
                    stats["mailbox"] += len(messages)
                else:
                    stats["channels"] += len(messages)
                
                for msg in messages:
                    all_messages.append({
                        "client": client_name,
                        "type": "Email" if client_name == "MAILBOX_INBOX" else "Slack Chat",
                        "content": msg["text"],
                        "timestamp": msg["ts"],
                        "user": msg["user"]
                    })
        
        if not all_messages:
            return "⚠️ No messages found in any channel (Bot might not be invited)."
        
        # --- 2. Format File ---
        messages_text = "SLACK LOGS AND EMAIL INBOX DUMP:\n"
        messages_text += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        messages_text += "=" * 50 + "\n\n"
        
        for msg in all_messages:
            try:
                date_str = datetime.fromtimestamp(float(msg['timestamp'])).strftime('%Y-%m-%d %H:%M')
            except:
                date_str = "Unknown"
            
            # Enhanced formatting for better searchability
            client_name = msg['client']
            msg_type = msg['type']
            content = msg['content']
            
            # For emails, add client name extraction for better search
            if msg_type == "Email":
                # Try to extract client name from email content for indexing
                messages_text += f"📅 Date: {date_str}\n"
                messages_text += f"📂 Source: {client_name} ({msg_type})\n"
                messages_text += f"📧 EMAIL MESSAGE - Searchable by client name in content\n"
                messages_text += f"👤 User: {msg['user']}\n"
                messages_text += f"📝 EMAIL CONTENT:\n{content}\n"
                messages_text += f"🔍 Keywords: {client_name}, email, mailbox, communication\n"
            else:
                messages_text += f"📅 Date: {date_str}\n"
                messages_text += f"📂 Source: {client_name} ({msg_type})\n"
                messages_text += f"👤 User: {msg['user']}\n"
                messages_text += f"📝 Content:\n{content}\n"
            
            messages_text += "-" * 50 + "\n\n"
        
        # --- 3. Upload to OpenAI ---
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(messages_text)
            temp_path = f.name
        
        with open(temp_path, 'rb') as f:
            file = ai_client.files.create(file=f, purpose="assistants")
        
        # Add to vector store (Handling API variations)
        try:
            if hasattr(ai_client, 'beta') and hasattr(ai_client.beta, 'vector_stores'):
                ai_client.beta.vector_stores.files.create(
                    vector_store_id=vector_store_id,
                    file_id=file.id
                )
            else:
                # Fallback for older libraries (though you should update requirements.txt)
                ai_client.vector_stores.files.create(
                    vector_store_id=vector_store_id,
                    file_id=file.id
                )
        except Exception as e:
            print(f"❌ OpenAI Vector Store Error: {e}")
            return f"❌ OpenAI Library Error: {str(e)} (Check requirements.txt)"

        os.unlink(temp_path)
        
        return (
            f"✅ *Sync Complete!*\n"
            f"📧 Emails (Mailbox): {stats['mailbox']}\n"
            f"💬 Slack Messages: {stats['channels']}\n"
            f"📚 Total Items: {len(all_messages)}"
        )
        
    except Exception as e:
        print(f"❌ Critical Sync Error: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Critical Sync Error: {str(e)[:100]}"


def sync_data_to_knowledge_base():
    """Sync project data to knowledge base - Uploads individual project files"""
    if not ai_client:
        return
    
    assistant_id, vector_store_id = setup_openai_assistant()
    if not assistant_id or not vector_store_id:
        return
    
    try:
        # Load all projects (now loaded from individual files)
        projects = load_all_projects()
        
        # Limit control: If too many projects, we might hit limits, but for <50 it is fine.
        # Alternatively, we can bundle them if N > 50. 
        # For now, separate files are better.
        
        file_streams = []
        import tempfile
        
        # Create temp files for each project
        temp_files = []
        for p in projects:
            client = p.get("client", "Unknown")
            # Create temp file
            tf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, prefix=f"{client}_")
            tf.write(json.dumps(p, indent=2))
            # Close it to flush
            tf.close()
            
            temp_files.append(tf.name)
            file_streams.append(open(tf.name, 'rb'))
            
        if not file_streams:
            print("⚠️ No projects to sync.")
            return

        # Upload to Vector Store Batch (Efficient for multiple files)
        try:
            if hasattr(ai_client.beta.vector_stores, 'file_batches'):
                file_batch = ai_client.beta.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vector_store_id,
                    files=file_streams
                )
                print(f"✅ Synced {len(temp_files)} project files to vector store (Status: {file_batch.status})")
                print(f"   File counts: {file_batch.file_counts}")
            else:
                 # Fallback for older SDK
                 print("⚠️ Older SDK detected, uploading sequentially...")
                 for fs in file_streams:
                     fs.seek(0)
                     f_obj = ai_client.files.create(file=fs, purpose="assistants")
                     ai_client.beta.vector_stores.files.create(vector_store_id=vector_store_id, file_id=f_obj.id)
                 print(f"✅ Synced {len(temp_files)} project files sequentially")
                 
        except Exception as e:
            print(f"❌ Error uploading file batch: {e}")
        
        # Cleanup
        for f in file_streams:
            f.close()
        for path in temp_files:
            try:
                os.unlink(path)
            except:
                pass
        
    except Exception as e:
        print(f"❌ Error syncing to knowledge base: {e}")


def clean_citation_markers(text):
    """Remove OpenAI Assistant citation markers from text
    
    Removes patterns like 【4:0†source】【4:1†source】 etc.
    These are automatically added by OpenAI when using file_search tool.
    """
    if not text:
        return text
    
    # Remove citation markers: 【number:number†source】
    # Pattern matches: 【 followed by digits, colon, digits, †source, 】
    import re
    # Remove all citation markers
    cleaned = re.sub(r'【\d+:\d+†source】', '', text)
    # Clean up any extra spaces left behind
    cleaned = re.sub(r'\s+', ' ', cleaned)
    # Remove spaces before punctuation
    cleaned = re.sub(r'\s+([.,!?;:])', r'\1', cleaned)
    # Remove multiple spaces
    cleaned = re.sub(r' {2,}', ' ', cleaned)
    return cleaned.strip()

def query_assistant(user_query, channel_id=None, timeout=25):
    """Query OpenAI Assistant with knowledge base
    
    Args:
        user_query: The user's question
        channel_id: Optional channel ID for context
        timeout: Maximum time to wait for response (seconds, default 25)
    
    Returns:
        str: Assistant response or None if timeout/error
    """
    if not ai_client:
        return None
    
    assistant_id, _ = setup_openai_assistant()
    if not assistant_id:
        return None
    
    try:
        # Create thread
        thread = ai_client.beta.threads.create()
        
        # Add message
        ai_client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_query
        )
        
        # Run assistant
        run = ai_client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id
        )
        
        # Wait for completion with timeout
        import time
        start_time = time.time()
        max_wait_time = timeout
        
        while run.status in ['queued', 'in_progress', 'cancelling']:
            elapsed = time.time() - start_time
            if elapsed > max_wait_time:
                print(f"⏱️ Assistant query timeout after {max_wait_time} seconds")
                return None  # Timeout - will fallback to regular chat completion
            
            time.sleep(1)
            run = ai_client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        
        if run.status == 'completed':
            messages = ai_client.beta.threads.messages.list(thread_id=thread.id)
            response_text = messages.data[0].content[0].text.value
            # Clean up citation markers
            return clean_citation_markers(response_text)
        elif run.status == 'failed':
            error_msg = getattr(run, 'last_error', None)
            if error_msg:
                print(f"❌ Assistant run failed: {error_msg}")
            return None
        else:
            print(f"⚠️ Assistant run status: {run.status}")
            return None  # Return None to trigger fallback
            
    except Exception as e:
        print(f"❌ Error querying assistant: {e}")
        import traceback
        traceback.print_exc()
        return None

# ==========================================
# FEATURE: PDF GENERATION (ENHANCED)
# ==========================================
def sanitize_text_for_pdf(text):
    """Remove or replace Unicode characters that can't be encoded in latin-1"""
    if not text:
        return ""
    # Replace common emojis with text equivalents
    replacements = {
        '✅': '[OK]',
        '⛔': '[BLOCKER]',
        '📞': '[CALL]',
        '🚀': '[ROCKET]',
        '📊': '[CHART]',
        '🔴': '[RED]',
        '🔵': '[BLUE]',
        '🟢': '[GREEN]',
        '🟡': '[YELLOW]',
        '📝': '[NOTE]',
        '🎉': '[CELEBRATE]',
    }
    result = str(text)
    for emoji, replacement in replacements.items():
        result = result.replace(emoji, replacement)
    
    # Remove any remaining non-ASCII characters that can't be encoded
    try:
        result.encode('latin-1')
        return result
    except UnicodeEncodeError:
        # Remove characters that can't be encoded
        return result.encode('latin-1', errors='ignore').decode('latin-1')

def generate_pdf_report(projects, title="Project Report", report_type="full"):
    """Generate PDF report with multiple types: full, summary, blockers_only"""
    if not PDF_AVAILABLE:
        return None
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=16, style='B')
    pdf.cell(200, 10, txt=sanitize_text_for_pdf(title), ln=1, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 5, txt=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=1, align='C')
    pdf.ln(10)
    
    # Filter based on report type
    if report_type == "blockers_only":
        projects = [p for p in projects if p.get('blocker', '-') not in ['-', 'None', '']]
        if not projects:
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, txt=sanitize_text_for_pdf("[OK] No blockers found! All projects are on track."), ln=1)
            filename = f"/tmp/report_blockers_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
            pdf.output(filename)
            return filename
    elif report_type == "summary":
        # Only show key info
        pdf.set_font("Arial", size=12, style='B')
        pdf.cell(0, 10, txt="Summary Report", ln=1)
        pdf.set_font("Arial", size=10)
        pdf.ln(5)
        
        for p in projects:
            pdf.set_font("Arial", 'B', 11)
            pdf.set_fill_color(240, 240, 240)
            client_cat = f"{p.get('client')} - {p.get('category', 'N/A')}"
            pdf.cell(0, 8, txt=sanitize_text_for_pdf(client_cat), ln=1, fill=True)
            pdf.set_font("Arial", size=9)
            status = sanitize_text_for_pdf(p.get('status', '-')[:100].replace('\n', ' '))
            pdf.multi_cell(0, 6, txt=f"Status: {status}")
            pdf.ln(3)
        
        filename = f"/tmp/report_summary_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
        pdf.output(filename)
        return filename
    
    # Full report
    for idx, p in enumerate(projects, 1):
        pdf.set_font("Arial", 'B', 12)
        pdf.set_fill_color(240, 240, 240)
        client_name = sanitize_text_for_pdf(f"{idx}. Client: {p.get('client')}")
        pdf.cell(0, 10, txt=client_name, ln=1, fill=True)
        
        pdf.set_font("Arial", size=10)
        
        # Category and team
        category_team = f"Category: {p.get('category', '-')} | PM: {p.get('owner', '-')} | Dev: {p.get('developer', '-')}"
        pdf.cell(0, 6, txt=sanitize_text_for_pdf(category_team), ln=1)
        pdf.ln(2)
        
        # Status
        status = sanitize_text_for_pdf(p.get('status', '-'))
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 6, txt="Status:", ln=1)
        pdf.set_font("Arial", size=9)
        pdf.multi_cell(0, 5, txt=status.replace('\n', ' '))
        pdf.ln(2)
        
        # Blocker
        blocker = p.get('blocker', '-')
        if blocker and blocker not in ["-", "None", ""]:
            pdf.set_text_color(200, 0, 0)
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(0, 6, txt="[BLOCKER] Blocker:", ln=1)
            pdf.set_font("Arial", size=9)
            blocker_text = sanitize_text_for_pdf(blocker.replace('\n', ' '))
            pdf.multi_cell(0, 5, txt=blocker_text)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)
        
        # Next call
        if p.get('call') and p.get('call') != "-":
            pdf.set_font("Arial", size=9)
            call_text = f"[CALL] Next Call: {p.get('call')}"
            pdf.cell(0, 5, txt=sanitize_text_for_pdf(call_text), ln=1)
        
        # Last updated
        pdf.set_font("Arial", size=8, style='I')
        pdf.cell(0, 5, f"Last Updated: {p.get('last_updated', '-')}", ln=1)
        
        pdf.ln(8)
        if idx < len(projects):
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(5)
        
    filename = f"/tmp/report_{report_type}_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
    pdf.output(filename)
    return filename

@app.command("/download-report")
@require_authorization(internal_only=True)
def command_download_pdf(ack, client, body):
    ack()
    user_id = body.get('user_id')
    channel_id = body.get('channel_id')
    command_text = body.get('text', '').strip().lower()
    
    # Determine report type from command
    report_type = "full"
    if "summary" in command_text:
        report_type = "summary"
    elif "blocker" in command_text or "blocked" in command_text:
        report_type = "blockers_only"
    
    projects = load_db()
    context = get_request_context(channel_id)
    
    # SECURITY: If external, only give them their own data
    if context['role'] == 'external':
        if not context.get('client'):
            client.chat_postEphemeral(channel=channel_id, user=user_id, text="❌ Error: Client mapping not configured for this channel.")
            return
        projects = [p for p in projects if p.get('client', '').lower() == context['client'].lower()]
        title = f"Status Report: {context['client']}"
    else:
        title = "Internal Master Project Report"
        if report_type == "summary":
            title = "Project Summary Report"
        elif report_type == "blockers_only":
            title = "Blockers Report"

    if not projects:
        client.chat_postEphemeral(channel=channel_id, user=user_id, text="No data found to generate report.")
        return

    client.chat_postMessage(channel=channel_id, text=f"📄 Generating {report_type} PDF report, please wait...")
    pdf_path = generate_pdf_report(projects, title, report_type)
    
    if pdf_path:
        try:
            client.files_upload_v2(
                channel=channel_id,
                file=pdf_path,
                title=title,
                initial_comment=f"Here is your requested {report_type} report."
            )
        except Exception as e:
            client.chat_postMessage(channel=channel_id, text=f"❌ Error uploading PDF: {e}")
    else:
        client.chat_postMessage(channel=channel_id, text="❌ PDF generation failed (Library not installed).")

# ==========================================
# FEATURE: AI ENGINE (CONTEXT AWARE)
# ==========================================
def process_ai_query(user_query, channel_id, reply_func):
    projects = load_db()
    context = get_request_context(channel_id)
    role = context['role']
    target_client = context['client']

    # --- SECURITY FILTERING ---
    if role == 'external':
        if not target_client:
            reply_func("❌ Error: Client mapping not configured for this channel.")
            return
        # 1. Filter Data
        projects = [p for p in projects if p.get('client', '').lower() == target_client.lower()]
        if not projects:
            reply_func("I can only discuss project details related to this channel.")
            return
        
        # 2. Sanitize Data (Remove internal fields if you add them later)
        safe_projects = []
        for p in projects:
            # Create a clean copy without sensitive internal fields
            safe_p = {k: v for k, v in p.items() if k not in ['internal_notes', 'budget']}
            safe_projects.append(safe_p)
            
        system_prompt = (
            f"You are a helpful Project Assistant for {target_client}. "
            "You are speaking directly to the CLIENT. "
            "Be professional, polite, and focused on progress. "
            "Do not mention other clients."
        )
        data_context = json.dumps(safe_projects, indent=2)

    else:
        # Internal Team Context
        system_prompt = (
            "You are the Project Operations Manager for the internal team. "
            "You are speaking to developers and PMs. "
            "Be direct, highlight blockers, and risks."
        )
        data_context = json.dumps(projects, indent=2)

    # --- OPENAI CALL ---
    if not ai_client:
        reply_func("⚠️ AI Client not configured.")
        return

    try:
        # Show thinking message immediately
        thinking_msg = f"🧠 *Thinking about: {user_query[:50]}{'...' if len(user_query) > 50 else ''}*"
        reply_func(thinking_msg)
        
        # Try using Assistant first (if configured), fallback to chat completion
        # Use shorter timeout to avoid Slack command timeout
        assistant_response = query_assistant(user_query, channel_id, timeout=20)
        if assistant_response:
            reply_func(assistant_response)
            return
        
        # Fallback to regular chat completion (faster, more reliable)
        print("📝 Using fallback chat completion (Assistant timeout or not available)")
        response = ai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": f"{system_prompt}\n\nPROJECT DATA:\n{data_context}"},
                {"role": "user", "content": user_query}
            ],
            timeout=15  # Add timeout to chat completion too
        )
        reply_func(response.choices[0].message.content)
    except Exception as e:
        error_msg = str(e)
        print(f"❌ AI Error: {error_msg}")
        # Provide user-friendly error message
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            reply_func("⏱️ Request timed out. The AI is taking too long to respond. Please try a simpler question or try again later.")
        else:
            reply_func(f"❌ AI Error: {error_msg[:200]}")

# ==========================================
# FEATURE: MAILBOX & EVENTS
# ==========================================
@app.event("app_mention")
def handle_mentions(event, say, client):
    # Check authorization first
    user_id = event.get('user')
    channel_id = event.get('channel')
    if not is_user_authorized(user_id, client, channel_id):
        say(
            text=(
                "🚫 *Access Denied*\n\n"
                "You are not authorized to use this bot.\n"
                "Please contact your administrator to be added to the authorized users list."
            )
        )
        return
    
    text = re.sub(r"<@.*?>", "", event['text']).strip()
    channel = event['channel']
    
    # Routing
    if "update" in text.lower() and "project" in text.lower():
        say(text="Update Project:", blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": "Click to update:"},
             "accessory": {"type": "button", "text": {"type": "plain_text", "text": "Update"}, "action_id": "trigger_update_flow"}}
        ])
    elif "report" in text.lower() and "pdf" in text.lower():
        # Trigger the PDF logic manually if they ask "Give me a PDF report"
        # We need to simulate the body structure for the command function, or just call logic directly
        say("Please use the `/download-report` command for PDFs.")
    else:
        # Default to AI
        process_ai_query(text, channel, say)

def process_email_for_status_update(text, channel_id=None, event_ts=None, user_id=None):
    """Enhanced email processing: updates status and logs brief history"""
    if not ai_client:
        return None
    
    try:
        projects = load_db()
        client_names = [p.get("client", "") for p in projects]
        
        # Enhanced prompt to get better summaries
        prompt = (
            f"Analyze this email/message. "
            f"Available clients: {', '.join(client_names)}\n\n"
            f"Extract:\n"
            f"1. Client name (must match one from the list exactly)\n"
            f"2. Status update (current status based on this email)\n"
            f"3. Blocker (if any mentioned)\n"
            f"4. Summary (1 concise sentence about this update)\n\n"
            f"Return JSON format:\n"
            f'{{"client": "Client Name", "status": "status text", "blocker": "blocker or empty", "summary": "summary text"}}'
        )
        
        response = ai_client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a project status parser. Always return valid JSON."},
                {"role": "user", "content": prompt + "\n\nEmail content:\n" + text}
            ],
            timeout=15
        )
        
        result = json.loads(response.choices[0].message.content)
        client_name = result.get("client", "").strip()
        
        if not client_name:
            return None
            
        # Optimization: Load ONLY this client's project file instead of scanning everything
        # We try to load it. If it doesn't exist, we might check if we need to create it
        # But usually we want to find the existing one.
        
        # Note: client_name from AI might not match exactly the filename if case differs?
        # Ideally we should normalize filenames to lowercase or handle this.
        # For now, let's assume strict matching or we search load_all_projects if load_project fails.
        
        project = load_project(client_name)
        projects_list_for_context = [] # Only need this if we fall back or need context
        
        # If not found directly, maybe we need to search the list to find the canonical name
        if not project:
            # Fallback: Load all to find case-insensitive match
            all_projects = load_all_projects()
            for p in all_projects:
                if p.get("client", "").lower() == client_name.lower():
                    project = p
                    break
            
            # If still not found, are we creating a new one?
            # Current logic implies we update existing projects.
            if not project:
                print(f"⚠️ Project {client_name} not found for update.")
                return None
        
        # Now we have 'project' as a dictionary
        p = project
        
        # 1. Initialize email_history if missing
        if "email_history" not in p:
            p["email_history"] = []
        
        # 2. Create the new entry
        email_entry = {
            "timestamp": email_timestamp,
            "summary": result.get("summary", "Update received"),
            "status_extracted": result.get("status", ""),
            "raw_text_preview": text[:150] + "..." if len(text) > 150 else text, # Limit preview text
            "slack_ts": event_ts
        }
        
        # 3. Append and strict limit (Keep only last 10 to save space)
        p["email_history"].append(email_entry)
        if len(p["email_history"]) > 10:
            p["email_history"] = p["email_history"][-10:]
        
        # 4. Update Main Status Fields
        if result.get("status"):
            p["status"] = result.get("status")
        if result.get("blocker"):
            p["blocker"] = result.get("blocker")
            
        p["last_updated"] = email_timestamp
        p["last_email_received"] = email_timestamp
        p["comm_channel"] = "Email"
        
        # 5. Save ONLY this project
        if save_project(p):
            print(f"✅ Updated project {client_name} via email")
            # Sync to knowledge base so AI memory is up to date
            sync_data_to_knowledge_base()
            return result
        else:
            print(f"❌ Failed to save project {client_name}")
            return None
            
    except Exception as e:
        print(f"❌ Error processing email: {e}")
        import traceback
        traceback.print_exc()
        return None

@app.event("message")
def handle_message_events(event, say, client):
    channel_id = event.get("channel")
    
    # Skip bot messages and own messages
    if event.get("subtype") == "bot_message" or event.get("bot_id"):
        return
    
    # 1. MAILBOX LISTENER - Enhanced with auto-update and email tracking
    if channel_id == MAILBOX_CHANNEL_ID:
        text = event.get("text", "")
        event_ts = event.get("ts", "")
        user_id = event.get("user", "")
        
        # If it's a file share (email attachment), text might be empty
        if not text and "attachments" in event:
            text = event["attachments"][0].get("text", "") or event["attachments"][0].get("pretext", "")
        
        # Also check for email-specific fields (when forwarded from email)
        if not text and "files" in event:
            # Try to get text from file description or title
            for file_info in event.get("files", []):
                if file_info.get("title"):
                    text = file_info.get("title", "")
                elif file_info.get("preview"):
                    text = file_info.get("preview", "")
                break

        if text:
            print(f"📬 Processing email from mailbox channel: {text[:100]}...")
            result = process_email_for_status_update(text, channel_id, event_ts, user_id)
            target_channel = CHANNEL_ID_REPORT or MAILBOX_CHANNEL_ID
            if result:
                client_name = result.get("client", "Unknown")
                summary = result.get("summary", "Status updated")
                if target_channel:
                    say(
                        f"📬 *Email Processed & Status Updated*\n"
                        f"*Client:* {client_name}\n"
                        f"*Summary:* {summary}\n"
                        f"✅ Project status automatically updated!\n"
                        f"📧 Email entry logged in project history.",
                        channel=target_channel
                    )
            else:
                if target_channel:
                    say(
                        f"📬 *New Mailbox Item* (Manual review needed)\n"
                        f"Could not automatically identify client or extract status from email.",
                        channel=target_channel
                    )
    
    # 2. INGEST SLACK MESSAGES INTO KNOWLEDGE BASE (from internal/external channels)
    # Note: This is handled on schedule to avoid rate limits

# ==========================================
# FEATURE: DAILY SCHEDULER
# ==========================================
def scheduled_daily_report():
    """Enhanced daily report with insights and sync to knowledge base"""
    print("⏰ Running Daily Report...")
    if not CHANNEL_ID_REPORT:
        print("⚠️ CHANNEL_ID_REPORT not configured")
        return
    
    try:
        projects = load_db()
        if not projects:
            app.client.chat_postMessage(
                channel=CHANNEL_ID_REPORT,
                text="📊 *Daily Report*\n\nNo projects found in database."
            )
            return
        
        # Categorize projects
        categories = {
            "Stuck / On Hold": [],
            "New / In Progress": [],
            "Almost Ready": [],
            "Ready / Scheduled": [],
            "Launched": []
        }
        
        for p in projects:
            cat = p.get('category', 'Other')
            if cat in categories:
                categories[cat].append(p)
        
        # Build report
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"📊 Daily Project Report - {datetime.now().strftime('%Y-%m-%d')}", "emoji": True}},
            {"type": "divider"}
        ]
        
        # Priority items (stuck projects)
        if categories["Stuck / On Hold"]:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*🔴 Priority: Stuck Projects*"}})
            for p in categories["Stuck / On Hold"]:
                blocker = p.get('blocker', '-')
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{p['client']}*\nStatus: {p.get('status', '-')[:100]}\n⛔ Blocker: {blocker[:100] if blocker not in ['-', 'None'] else 'None'}"
                    }
                })
            blocks.append({"type": "divider"})
        
        # Active projects
        active = categories["New / In Progress"] + categories["Almost Ready"]
        if active:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*🔵 Active Projects ({len(active)})*"}})
            for p in active[:5]:  # Top 5
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{p['client']}* | Dev: {p.get('developer', '-')}\n{p.get('status', '-')[:150]}"
                    }
                })
            blocks.append({"type": "divider"})
        
        # Summary stats
        stats = f"📈 *Summary:* {len(categories['Launched'])} Launched | {len(categories['Ready / Scheduled'])} Ready | {len(active)} Active | {len(categories['Stuck / On Hold'])} Stuck"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": stats}})
        
        app.client.chat_postMessage(channel=CHANNEL_ID_REPORT, blocks=blocks, text="Daily Report")
        
        # Sync to knowledge base after report
        sync_data_to_knowledge_base()
        print("✅ Daily report sent and knowledge base synced")
        
    except Exception as e:
        print(f"❌ Scheduler Error: {e}")

scheduler = BackgroundScheduler()
# Run Monday-Friday at 9:00 AM (Server Time)
scheduler.add_job(scheduled_daily_report, 'cron', day_of_week='mon-fri', hour=9)
scheduler.start()

# ==========================================
# FEATURE: PUBLISH REPORT
# ==========================================
def generate_and_send_report(client, channel_id):
    """Generate and send a formatted report to the specified channel"""
    projects = load_db()
    if not projects:
        client.chat_postMessage(channel=channel_id, text="❌ No projects found!")
        return

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🚀 Shopline Report", "emoji": True}},
        {"type": "divider"}
    ]
    categories = ["Launched", "Ready / Scheduled", "Almost Ready", "New / In Progress", "Stuck / On Hold"]
    grouped = {cat: [] for cat in categories}
    for p in projects:
        grouped.setdefault(p.get("category", "Other"), []).append(p)
    
    emojis = {"Launched": "🎉", "Ready / Scheduled": "🟢", "Almost Ready": "🟡", "New / In Progress": "🔵", "Stuck / On Hold": "🔴"}

    for category in categories:
        if not grouped[category]:
            continue
        emoji = emojis.get(category, "📁")
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{emoji} {category}*"}})
        
        for p in grouped[category]:
            txt = f"*{p['client']}*\n*PM:* {p.get('owner', '-')} | *Dev:* {p.get('developer', '-')}\n\n*Status Update:*\n{p.get('status', '').replace(chr(10), ' ')}\n\n"
            if p.get('blocker') and p['blocker'].lower() not in ["none", "-", ""]:
                txt += f"⛔ *Blocker:* {p['blocker']}\n"
            if p.get('call') and p.get('call') != "-":
                txt += f"📞 *Next Call:* {p.get('call')}\n"
            upd = p.get('last_updated', '-')[:16]
            txt += f"🕒 *Updated:* {upd}\n___________________________________"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": txt}})
            
        blocks.append({"type": "divider"})

    client.chat_postMessage(channel=channel_id, blocks=blocks, text="Weekly Report")

@app.command("/publish-report")
@require_authorization(internal_only=True)
def command_publish_report(ack, client, body):
    ack()
    user_id = body.get('user_id')
    channel_id = body.get('channel_id')
    if not CHANNEL_ID_REPORT:
        print("⚠️ CHANNEL_ID_REPORT not configured. Cannot publish report.")
        return
    generate_and_send_report(client, CHANNEL_ID_REPORT)

# ==========================================
# FEATURE: ASK COMMAND
# ==========================================
# ==========================================
# FEATURE: PROJECT HISTORY
# ==========================================
@app.command("/project-history")
@require_authorization
def command_project_history(ack, respond, command, body):
    """View change history for a project"""
    ack()
    user_id = body.get('user_id')
    channel_id = body.get('channel_id')
    
    # Get client name from command text
    client_name = command.get('text', '').strip()
    
    if not client_name:
        respond(
            text="Please specify a client name. Example: `/project-history Avvika`",
            response_type="ephemeral"
        )
        return
    
    projects = load_db()
    project = None
    
    # Find the project
    for p in projects:
        if p.get("client", "").lower() == client_name.lower():
            project = p
            break
    
    if not project:
        respond(
            text=f"❌ Project '{client_name}' not found.",
            response_type="ephemeral"
        )
        return
    
    # Check authorization for external users
    context = get_request_context(channel_id)
    if context.get('role') == 'external':
        target_client = context.get('client')
        if project.get('client', '').lower() != target_client.lower():
            respond(
                text="❌ You can only view history for your own project.",
                response_type="ephemeral"
            )
            return
    
    # Get history
    history = project.get("history", [])
    
    if not history:
        respond(
            text=f"📋 *{project.get('client')}* - No change history yet.\n\nThis project hasn't been updated since history tracking was enabled.",
            response_type="ephemeral"
        )
        return
    
    # Format history (show last 10 entries)
    history_text = f"📋 *Change History for {project.get('client')}*\n\n"
    history_text += f"*Total Updates:* {len(history)}\n"
    history_text += f"*Last Updated:* {project.get('last_updated', 'N/A')}\n\n"
    history_text += "*Recent Changes (Last 10):*\n\n"
    
    # Show most recent first
    for entry in reversed(history[-10:]):
        timestamp = entry.get("timestamp", "Unknown")
        user = entry.get("user", "Unknown")
        changes = entry.get("changes", {})
        
        history_text += f"🕐 *{timestamp}* by `{user}`\n"
        
        for field, change in changes.items():
            field_name = field.replace('_', ' ').title()
            old_val = change.get('old', '-')
            new_val = change.get('new', '-')
            
            # Truncate long values
            if len(old_val) > 50:
                old_val = old_val[:47] + "..."
            if len(new_val) > 50:
                new_val = new_val[:47] + "..."
            
            history_text += f"   • *{field_name}:* `{old_val}` → `{new_val}`\n"
        
        history_text += "\n"
    
    if len(history) > 10:
        history_text += f"\n_Showing last 10 of {len(history)} total changes. Use `/project-history-full {client_name}` to see all._"
    
    respond(text=history_text, response_type="ephemeral")

@app.command("/project-history-full")
@require_authorization
def command_project_history_full(ack, respond, command, body):
    """View full change history for a project"""
    ack()
    user_id = body.get('user_id')
    channel_id = body.get('channel_id')
    
    # Get client name from command text
    client_name = command.get('text', '').strip()
    
    if not client_name:
        respond(
            text="Please specify a client name. Example: `/project-history-full Avvika`",
            response_type="ephemeral"
        )
        return
    
    projects = load_db()
    project = None
    
    # Find the project
    for p in projects:
        if p.get("client", "").lower() == client_name.lower():
            project = p
            break
    
    if not project:
        respond(
            text=f"❌ Project '{client_name}' not found.",
            response_type="ephemeral"
        )
        return
    
    # Check authorization for external users
    context = get_request_context(channel_id)
    if context.get('role') == 'external':
        target_client = context.get('client')
        if project.get('client', '').lower() != target_client.lower():
            respond(
                text="❌ You can only view history for your own project.",
                response_type="ephemeral"
            )
            return
    
    # Get history
    history = project.get("history", [])
    
    if not history:
        respond(
            text=f"📋 *{project.get('client')}* - No change history yet.",
            response_type="ephemeral"
        )
        return
    
    # Format full history
    history_text = f"📋 *Full Change History for {project.get('client')}*\n\n"
    history_text += f"*Total Updates:* {len(history)}\n\n"
    
    # Show most recent first
    for idx, entry in enumerate(reversed(history), 1):
        timestamp = entry.get("timestamp", "Unknown")
        user = entry.get("user", "Unknown")
        changes = entry.get("changes", {})
        
        history_text += f"*{idx}. {timestamp}* by `{user}`\n"
        
        for field, change in changes.items():
            field_name = field.replace('_', ' ').title()
            old_val = change.get('old', '-')
            new_val = change.get('new', '-')
            
            # Truncate long values
            if len(old_val) > 80:
                old_val = old_val[:77] + "..."
            if len(new_val) > 80:
                new_val = new_val[:77] + "..."
            
            history_text += f"   • *{field_name}:* `{old_val}` → `{new_val}`\n"
        
        history_text += "\n"
    
    respond(text=history_text, response_type="ephemeral")
# ==========================================
# FEATURE: ASK COMMAND (THREADED FIX)
# ==========================================

def process_ask_background(respond, query_text, channel_id, user_id, client):
    """Background worker to handle AI query without blocking Slack"""
    try:
        # Show thinking message
        respond(
            text=f"🧠 *Thinking about: {query_text[:50]}{'...' if len(query_text) > 50 else ''}*",
            response_type="ephemeral"
        )
        
        # ENHANCEMENT: If query mentions email/mailbox, enhance the query to trigger file_search
        enhanced_query = query_text
        query_lower = query_text.lower()
        if any(keyword in query_lower for keyword in ['email', 'mailbox', 'mail', 'message', 'communication', 'said', 'wrote']):
            # Add explicit instruction to search emails
            enhanced_query = (
                f"{query_text}\n\n"
                f"IMPORTANT: If this question is about emails or communications, "
                f"you MUST use the file_search tool to search the 'Slack Logs' file. "
                f"Look for entries marked as 'Source: MAILBOX_INBOX (Email)' and return the full email content."
            )
        
        # 1. Try to get answer from the Knowledge Base (Assistant) FIRST
        # This checks the Vector Store (Slack messages, history, emails, etc.)
        # Increased timeout to 60s for file_search operations
        assistant_response = query_assistant(enhanced_query, channel_id, timeout=60)
        
        if assistant_response:
            # If the Assistant found something (e.g. Slack logs, emails), return it!
            respond(text=assistant_response, response_type="ephemeral")
            return

        # =================================================================
        # FALLBACK: If Assistant fails or is empty, use the "Simple" JSON Chat
        # =================================================================
        
        # Load Data
        projects = load_db()
        context = get_request_context(channel_id)
        role = context.get('role', 'internal')
        target_client = context.get('client')

        # Security & Context Setup
        if role == 'external':
            if not target_client:
                respond(text="❌ Error: Client mapping not configured for this channel.", response_type="ephemeral")
                return
            projects = [p for p in projects if p.get('client', '').lower() == target_client.lower()]
            if not projects:
                respond(text="I can only discuss project details related to this channel.", response_type="ephemeral")
                return
            
            # Sanitize for external
            safe_projects = []
            for p in projects:
                safe_p = {k: v for k, v in p.items() if k not in ['internal_notes', 'budget']}
                safe_projects.append(safe_p)
            
            system_prompt = (
                f"You are a helpful Project Assistant for {target_client}. "
                "You are speaking directly to the CLIENT. "
                "Be professional, polite, and focused on progress. "
                "Do not mention other clients."
            )
            data_context = json.dumps(safe_projects, indent=2)
        else:
            # Internal
            system_prompt = (
                "You are the Project Operations Manager for the internal team. "
                "You are speaking to developers and PMs. "
                "Be direct, highlight blockers, and risks."
            )
            data_context = json.dumps(projects, indent=2)

        if not ai_client:
            respond(text="⚠️ AI Client not configured.", response_type="ephemeral")
            return

        # FALLBACK: If user asked about emails but Assistant didn't find them, be honest
        if any(keyword in query_lower for keyword in ['email', 'mailbox', 'mail', 'message']):
            fallback_prompt = (
                f"{system_prompt}\n\n"
                f"⚠️ IMPORTANT: The user asked about emails/communications, but the Knowledge Base search "
                f"did not return results or timed out. You only have access to structured project data below. "
                f"If the answer isn't in the project data, tell them: 'I couldn't find email content in the "
                f"knowledge base. Please try running `/sync-knowledge messages` to update the email logs, "
                f"or check the mailbox channel directly.'\n\n"
                f"PROJECT DATA:\n{data_context}"
            )
        else:
            fallback_prompt = f"{system_prompt}\n\nPROJECT DATA:\n{data_context}"

        # AI Call (The "Dumb" Fallback)
        response = ai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": fallback_prompt},
                {"role": "user", "content": query_text}
            ],
            timeout=20 
        )
        
        # Send Final Answer
        respond(text=response.choices[0].message.content, response_type="ephemeral")
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error in /ask background worker: {error_msg}")
        
        if "timeout" in error_msg.lower():
            respond(
                text="⏱️ The AI request timed out. Please try a simpler question.",
                response_type="ephemeral"
            )
        else:
            respond(
                text=f"❌ Error processing your question: {error_msg[:200]}",
                response_type="ephemeral"
            )

@app.command("/ask")
def command_ask(ack, respond, command, body, client):
    """Handle /ask command - Uses Threading to prevent Timeout"""
    # 1. Acknowledge Slack immediately (Must happen < 3 seconds)
    ack()
    
    user_id = body.get('user_id')
    channel_id = body.get('channel_id')
    query_text = command.get('text', '').strip()

    # 2. Authorization Check
    if not is_user_authorized(user_id, client, channel_id):
        respond(
            text=(
                "🚫 *Access Denied*\n\n"
                "You are not authorized to use this command.\n"
                "Please contact your administrator."
            ),
            response_type="ephemeral"
        )
        return
    
    if not query_text:
        respond(text="Please provide a question. Example: `/ask What projects are stuck?`", response_type="ephemeral")
        return
    
    # 3. Start Background Thread
    # We pass 'respond' because it contains the response_url which works for 30 minutes
    worker_thread = threading.Thread(
        target=process_ask_background,
        args=(respond, query_text, channel_id, user_id, client)
    )
    worker_thread.start()

# ==========================================
# STANDARD MODAL LOGIC (Add/Edit/Update)
# ==========================================

@app.action("trigger_update_flow")
def action_update_project(ack, body, client):
    ack()
    # Check authorization
    user_id = body.get('user', {}).get('id') if isinstance(body.get('user'), dict) else body.get('user_id')
    if not user_id:
        user_id = body.get('user')
    channel_id = body.get('channel', {}).get('id') if isinstance(body.get('channel'), dict) else body.get('channel_id')
    if not is_user_authorized(user_id, client, channel_id):
        if channel_id and user_id:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=(
                    "🚫 *Access Denied*\n\n"
                    "You are not authorized to use this bot.\n"
                    "Please contact your administrator to be added to the authorized users list."
                )
            )
        return
    # (Reusing your existing modal launch logic here for brevity)
    # Ideally, define launch_update_modal function as in your original file
    # For full code completeness, I will include the critical modal launcher:
    launch_update_modal(client, body["trigger_id"])

@app.command("/update-project")
@require_authorization(internal_only=True)
def command_update_project(ack, body, client):
    ack()
    projects = load_db()
    if not projects:
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text="❌ No projects found. Please add a client first using `/add-client`."
        )
        return
    launch_update_modal(client, body["trigger_id"])

@app.command("/add-client")
@require_authorization(internal_only=True)
def command_add_client(ack, body, client):
    ack()
    client.views_open(trigger_id=body["trigger_id"], view={
        "type": "modal", "callback_id": "add_client_submission",
        "title": {"type": "plain_text", "text": "Add Client"},
        "submit": {"type": "plain_text", "text": "Add"},
        "blocks": [{"type": "input", "block_id": "new_client_name", "element": {"type": "plain_text_input", "action_id": "input"}, "label": {"type": "plain_text", "text": "Client Name"}}]
    })

@app.view("add_client_submission")
def handle_add_submission(ack, view, body, client):
    ack()
    try:
        name = view["state"]["values"].get("new_client_name", {}).get("input", {}).get("value", "").strip()
        
        if not name:
            ack(response_action="errors", errors={"new_client_name": "Client name cannot be empty"})
            return
        
        # Optimization: Check directly if project exists instead of loading all
        if load_project(name):
            ack(response_action="errors", errors={"new_client_name": "A client with this name already exists"})
            return
            
        new_project = {
            "client": name, "owner": "-", "developer": "Unassigned", 
            "category": "New / In Progress", "status": "Initialized", 
            "blocker": "-", "last_updated": datetime.now().strftime("%Y-%m-%d")
        }
        
        if save_project(new_project):
             print(f"✅ Created new client: {name}")
        else:
             raise Exception("Failed to save to Gist")

    except (KeyError, TypeError) as e:
        print(f"❌ Error adding client: {e}")
        ack(response_action="errors", errors={"new_client_name": "Error processing request"})
    except Exception as e:
        print(f"❌ Unexpected error adding client: {e}")
        ack(response_action="errors", errors={"new_client_name": "Unexpected error occurred"})

# ==========================================
# FEATURE: EDIT CLIENT
# ==========================================
def launch_edit_client_modal(client, trigger_id):
    """Opens a modal to edit/rename a client"""
    projects = load_db()
    if not projects:
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "title": {"type": "plain_text", "text": "Error"},
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "⚠️ No clients found."}}]
            }
        )
        return

    client_names = sorted([p["client"] for p in projects])
    options = [{"text": {"type": "plain_text", "text": name[:75]}, "value": name} for name in client_names][:100]

    client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": "edit_client_submission",
            "title": {"type": "plain_text", "text": "Edit Client Name"},
            "submit": {"type": "plain_text", "text": "Rename"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "select_client_block",
                    "label": {"type": "plain_text", "text": "Select Client"},
                    "element": {
                        "type": "static_select",
                        "action_id": "select_action",
                        "options": options,
                        "placeholder": {"type": "plain_text", "text": "Choose client..."}
                    }
                },
                {
                    "type": "input",
                    "block_id": "new_name_block",
                    "element": {"type": "plain_text_input", "action_id": "input"},
                    "label": {"type": "plain_text", "text": "New Client Name"}
                }
            ]
        }
    )

@app.command("/edit-client")
@require_authorization(internal_only=True)
def command_edit_client(ack, body, client):
    ack()
    projects = load_db()
    if not projects:
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text="❌ No clients found. Please add a client first using `/add-client`."
        )
        return
    launch_edit_client_modal(client, body["trigger_id"])

# ==========================================
# FEATURE: ADMIN COMMAND
# ==========================================
def launch_admin_modal(client, trigger_id):
    """Launch admin modal for managing configuration"""
    # Load current config
    config = load_config()
    internal_users = config.get("authorized_users", [])
    external_users = config.get("external_authorized_users", [])
    channel_map = config.get("channel_map", {})
    
    # Format current users for display
    internal_list = "\n".join([f"• {email}" for email in internal_users[:20]]) or "• (none)"
    external_list = "\n".join([f"• {email}" for email in external_users[:20]]) or "• (none)"
    
    # Format current channels for display
    channel_list = "\n".join([
        f"• {channel_id[:12]}... → {info.get('client', 'N/A')} ({info.get('role', 'N/A')})"
        for channel_id, info in list(channel_map.items())[:10]
    ]) or "• (none)"
    
    client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": "admin_main",
            "title": {"type": "plain_text", "text": "🔐 Admin Panel"},
            "submit": {"type": "plain_text", "text": "Save Changes"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Configuration Management"}
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*1. Internal Users* (authorized_users)\n" + internal_list}
                },
                {
                    "type": "input",
                    "block_id": "internal_users_action",
                    "label": {"type": "plain_text", "text": "Action"},
                    "element": {
                        "type": "static_select",
                        "action_id": "internal_action",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Add User"}, "value": "add"},
                            {"text": {"type": "plain_text", "text": "Remove User"}, "value": "remove"}
                        ],
                        "placeholder": {"type": "plain_text", "text": "Select action..."}
                    }
                },
                {
                    "type": "input",
                    "block_id": "internal_user_email",
                    "label": {"type": "plain_text", "text": "Email Address"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "email",
                        "placeholder": {"type": "plain_text", "text": "user@example.com"}
                    },
                    "optional": True
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*2. External Users* (external_authorized_users)\n" + external_list}
                },
                {
                    "type": "input",
                    "block_id": "external_users_action",
                    "label": {"type": "plain_text", "text": "Action"},
                    "element": {
                        "type": "static_select",
                        "action_id": "external_action",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Add User"}, "value": "add"},
                            {"text": {"type": "plain_text", "text": "Remove User"}, "value": "remove"}
                        ],
                        "placeholder": {"type": "plain_text", "text": "Select action..."}
                    }
                },
                {
                    "type": "input",
                    "block_id": "external_user_email",
                    "label": {"type": "plain_text", "text": "Email Address"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "email",
                        "placeholder": {"type": "plain_text", "text": "user@example.com"}
                    },
                    "optional": True
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*3. Channel Mapping*\n{channel_list}\n\n_Showing first 10 channels_"}
                },
                {
                    "type": "input",
                    "block_id": "channel_action",
                    "label": {"type": "plain_text", "text": "Action"},
                    "element": {
                        "type": "static_select",
                        "action_id": "channel_action_select",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Add Channel"}, "value": "add"}
                        ],
                        "placeholder": {"type": "plain_text", "text": "Select action..."}
                    }
                },
                {
                    "type": "input",
                    "block_id": "channel_id_input",
                    "label": {"type": "plain_text", "text": "Channel ID"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "channel_id",
                        "placeholder": {"type": "plain_text", "text": "C09XXXXXX"}
                    },
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "channel_client",
                    "label": {"type": "plain_text", "text": "Client Name"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "client_name",
                        "placeholder": {"type": "plain_text", "text": "Client Name"}
                    },
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "channel_role",
                    "label": {"type": "plain_text", "text": "Role"},
                    "element": {
                        "type": "static_select",
                        "action_id": "role_select",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Internal"}, "value": "internal"},
                            {"text": {"type": "plain_text", "text": "External"}, "value": "external"}
                        ],
                        "placeholder": {"type": "plain_text", "text": "Select role..."}
                    },
                    "optional": True
                }
            ]
        }
    )

@app.command("/admin")
@require_authorization(internal_only=True)
def command_admin(ack, body, client):
    """Admin command for managing configuration"""
    ack()
    launch_admin_modal(client, body["trigger_id"])

@app.command("/superadmin")
@require_authorization(internal_only=True)
def command_superadmin(ack, body, client):
    """Superadmin command - same functionality as /admin command (alias)"""
    ack()
    # Currently, superadmin uses the same admin modal as /admin
    # This provides two command aliases for the same functionality
    launch_admin_modal(client, body["trigger_id"])

@app.view("admin_main")
def handle_admin_submission(ack, body, view, client):
    """Handle admin modal submission"""
    ack()
    
    try:
        values = view["state"]["values"]
        config = load_config()
        updated = False
        messages = []
        
        # 1. Handle Internal Users
        internal_action = values.get("internal_users_action", {}).get("internal_action", {}).get("selected_option", {}).get("value")
        internal_email = values.get("internal_user_email", {}).get("email", {}).get("value", "").strip().lower()
        
        if internal_action and internal_email:
            authorized_users = config.get("authorized_users", [])
            authorized_users_lower = [email.lower() for email in authorized_users]
            
            if internal_action == "add":
                if internal_email not in authorized_users_lower:
                    authorized_users.append(internal_email)
                    config["authorized_users"] = authorized_users
                    updated = True
                    messages.append(f"✅ Added {internal_email} to internal users")
                else:
                    messages.append(f"⚠️ {internal_email} already in internal users")
            elif internal_action == "remove":
                if internal_email in authorized_users_lower:
                    authorized_users = [email for email in authorized_users if email.lower() != internal_email]
                    config["authorized_users"] = authorized_users
                    updated = True
                    messages.append(f"✅ Removed {internal_email} from internal users")
                else:
                    messages.append(f"⚠️ {internal_email} not found in internal users")
        
        # 2. Handle External Users
        external_action = values.get("external_users_action", {}).get("external_action", {}).get("selected_option", {}).get("value")
        external_email = values.get("external_user_email", {}).get("email", {}).get("value", "").strip().lower()
        
        if external_action and external_email:
            external_authorized_users = config.get("external_authorized_users", [])
            external_authorized_users_lower = [email.lower() for email in external_authorized_users]
            
            if external_action == "add":
                if external_email not in external_authorized_users_lower:
                    external_authorized_users.append(external_email)
                    config["external_authorized_users"] = external_authorized_users
                    updated = True
                    messages.append(f"✅ Added {external_email} to external users")
                else:
                    messages.append(f"⚠️ {external_email} already in external users")
            elif external_action == "remove":
                if external_email in external_authorized_users_lower:
                    external_authorized_users = [email for email in external_authorized_users if email.lower() != external_email]
                    config["external_authorized_users"] = external_authorized_users
                    updated = True
                    messages.append(f"✅ Removed {external_email} from external users")
                else:
                    messages.append(f"⚠️ {external_email} not found in external users")
        
        # 3. Handle Channel Mapping
        channel_action = values.get("channel_action", {}).get("channel_action_select", {}).get("selected_option", {}).get("value")
        channel_id = values.get("channel_id_input", {}).get("channel_id", {}).get("value", "").strip()
        client_name = values.get("channel_client", {}).get("client_name", {}).get("value", "").strip()
        role = values.get("channel_role", {}).get("role_select", {}).get("selected_option", {}).get("value")
        
        if channel_action == "add" and channel_id and client_name and role:
            channel_map = config.get("channel_map", {})
            channel_map[channel_id] = {"client": client_name, "role": role}
            config["channel_map"] = channel_map
            updated = True
            messages.append(f"✅ Added channel {channel_id[:12]}... for {client_name} ({role})")
        
        # Save config if updated
        if updated:
            if save_config(config):
                messages.append("\n✅ Configuration saved successfully to config.json!")
                messages.append("⚠️ *Important:* If you're using `CONFIG_JSON` environment variable in Render/deployment:")
                messages.append("   1. Copy the updated config.json content")
                messages.append("   2. Update the `CONFIG_JSON` environment variable in your deployment platform")
                messages.append("   3. Restart the service for changes to take effect")
                # Reload config to update in-memory variables
                reload_config()
            else:
                messages.append("\n❌ Error saving configuration. Check server logs.")
        else:
            messages.append("\n⚠️ No changes made.")
        
        # Send response
        user_id = body["user"]["id"]
        channel_id = body.get("container", {}).get("channel_id") or body.get("channel_id")
        
        if channel_id:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="\n".join(messages) if messages else "No changes made."
            )
        else:
            # Fallback: try to send DM
            try:
                client.chat_postMessage(
                    channel=user_id,
                    text="\n".join(messages) if messages else "No changes made."
                )
            except:
                print(f"Admin update: {'; '.join(messages)}")
    
    except Exception as e:
        print(f"❌ Error in admin submission: {e}")
        import traceback
        traceback.print_exc()
        try:
            user_id = body["user"]["id"]
            channel_id = body.get("container", {}).get("channel_id") or body.get("channel_id")
            if channel_id:
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text=f"❌ Error processing admin changes: {e}"
                )
        except:
            pass

@app.command("/sync-knowledge")
@require_authorization(internal_only=True)
def command_sync_knowledge(ack, client, body):
    ack()
    channel_id = body.get('channel_id')
    command_text = body.get('text', '').strip().lower()
    
    # Check if user wants to sync messages
    sync_messages = 'messages' in command_text or 'full' in command_text
    
    client.chat_postMessage(channel=channel_id, text="🔄 *Syncing Knowledge Base...*")
    
    try:
        # 1. Always sync projects.json (Structured Data)
        sync_data_to_knowledge_base()
        msg = "✅ `projects.json` (Structured Data) updated.\n"
        
        # 2. Sync Slack/Email Logs (Unstructured Data)
        if sync_messages:
            client.chat_postMessage(channel=channel_id, text="📥 Fetching emails and chats (this takes 10s)...")
            result_msg = sync_slack_messages_to_knowledge_base()
            msg += result_msg
        else:
            msg += "ℹ️ _Skipped message logs. Use `/sync-knowledge messages` to include emails/chats._"
            
        client.chat_postMessage(channel=channel_id, text=msg)
        
    except Exception as e:
        client.chat_postMessage(channel=channel_id, text=f"❌ Error: {e}")

@app.view("edit_client_submission")
def handle_edit_client_submission(ack, body, view, client):
    ack()
    try:
        values = view["state"]["values"]
        old_name = values.get("select_client_block", {}).get("select_action", {}).get("selected_option", {}).get("value", "")
        new_name = values.get("new_name_block", {}).get("input", {}).get("value", "").strip()

        if not old_name or not new_name:
            ack(response_action="errors", errors={"new_name_block": "Both client selection and new name are required"})
            return

        if old_name == new_name:
            ack(response_action="errors", errors={"new_name_block": "New name must be different from the current name"})
            return

        # Load specific project to update
        project = load_project(old_name)
        
        if not project:
            ack(response_action="errors", errors={"select_client_block": "Client not found"})
            return
            
        # Update name
        project["client"] = new_name
        
        # Save new file (Creates NewName.json)
        if save_project(project):
            # Delete old file (Deletes OldName.json)
            delete_project(old_name)
            print(f"✅ Renamed client {old_name} -> {new_name}")
        else:
            raise Exception("Failed to save new project file")


    except (KeyError, TypeError) as e:
        print(f"❌ Error editing client: {e}")
        ack(response_action="errors", errors={"new_name_block": "Error processing request"})
    except Exception as e:
        print(f"❌ Unexpected error editing client: {e}")
        ack(response_action="errors", errors={"new_name_block": "Unexpected error occurred"})

# --- RE-ADDING YOUR ORIGINAL MODAL FUNCTIONS FOR COMPLETENESS ---
def launch_update_modal(client, trigger_id):
    projects = load_db()
    options = [{"text": {"type": "plain_text", "text": p["client"][:75]}, "value": p["client"]} for p in projects]
    if not options:
        return
    
    client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal", "callback_id": "project_select_step",
            "title": {"type": "plain_text", "text": "Update Project"},
            "submit": {"type": "plain_text", "text": "Next"},
            "blocks": [{
                "type": "input", "block_id": "client_select",
                "label": {"type": "plain_text", "text": "Select Client"},
                "element": {"type": "static_select", "action_id": "action", "options": options}
            }]
        }
    )

# --- HELPER FUNCTIONS FOR MODAL ---
def is_valid_date(date_str):
    """Check if date string is in YYYY-MM-DD format"""
    if not date_str or date_str == "-":
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except:
        return False

@app.view("project_select_step")
def handle_step_1(ack, view, client):
    try:
        selected = view["state"]["values"]["client_select"]["action"]["selected_option"]["value"]
        projects = load_db()
        project = next((p for p in projects if p["client"] == selected), {})
        
        if not project:
            ack(response_action="errors", errors={"client_select": "Project not found"})
            return
        
        # Helper function to create select elements
        def create_select_element(action_id, options_list, current_val, placeholder_text):
            element = {
                "type": "static_select",
                "action_id": action_id,
                "options": options_list,
                "placeholder": {"type": "plain_text", "text": placeholder_text}
            }
            found_opt = next((opt for opt in options_list if opt["value"] == current_val), None)
            if found_opt:
                element["initial_option"] = found_opt
            return element
        
        # Options for dropdowns
        category_opts = [
            {"text": {"type": "plain_text", "text": "Launched"}, "value": "Launched"},
            {"text": {"type": "plain_text", "text": "Ready / Scheduled"}, "value": "Ready / Scheduled"},
            {"text": {"type": "plain_text", "text": "Almost Ready"}, "value": "Almost Ready"},
            {"text": {"type": "plain_text", "text": "New / In Progress"}, "value": "New / In Progress"},
            {"text": {"type": "plain_text", "text": "Stuck / On Hold"}, "value": "Stuck / On Hold"}
        ]
        owner_opts = [
            {"text": {"type": "plain_text", "text": "Leo"}, "value": "Leo"},
            {"text": {"type": "plain_text", "text": "Jusa"}, "value": "Jusa"},
            {"text": {"type": "plain_text", "text": "Bule"}, "value": "Bule"},
            {"text": {"type": "plain_text", "text": "Alen"}, "value": "Alen"}
        ]
        dev_opts = [
            {"text": {"type": "plain_text", "text": "Unassigned"}, "value": "Unassigned"},
            {"text": {"type": "plain_text", "text": "Evan"}, "value": "Evan"},
            {"text": {"type": "plain_text", "text": "Thanasis"}, "value": "Thanasis"},
            {"text": {"type": "plain_text", "text": "Labros"}, "value": "Labros"},
            {"text": {"type": "plain_text", "text": "Edis"}, "value": "Edis"}
        ]
        comm_opts = [
            {"text": {"type": "plain_text", "text": "Slack"}, "value": "Slack"},
            {"text": {"type": "plain_text", "text": "Email"}, "value": "Email"},
            {"text": {"type": "plain_text", "text": "Google Meet"}, "value": "Google Meet"},
            {"text": {"type": "plain_text", "text": "Call"}, "value": "Call"}
        ]
        
        # Get current values
        current_status = str(project.get("status", "") or "")
        current_blocker = str(project.get("blocker", "") or "").replace("-", "")
        
        # Handle dates
        raw_contact = project.get("last_contact_date", "")
        initial_contact = raw_contact if is_valid_date(raw_contact) else None
        
        raw_call = project.get("call", "")
        initial_call = raw_call if is_valid_date(raw_call) else None
        
        # Handle communication channels (checkboxes)
        curr_chans = project.get("comm_channel", "")
        init_chans = []
        if curr_chans and curr_chans != "-":
            for opt in comm_opts:
                if opt["value"] in curr_chans:
                    init_chans.append(opt)
        
        checkbox_el = {"type": "checkboxes", "action_id": "checkboxes", "options": comm_opts}
        if init_chans:
            checkbox_el["initial_options"] = init_chans
        
        contact_datepicker = {"type": "datepicker", "action_id": "datepicker"}
        if initial_contact:
            contact_datepicker["initial_date"] = initial_contact
        
        call_datepicker = {"type": "datepicker", "action_id": "datepicker"}
        if initial_call:
            call_datepicker["initial_date"] = initial_call
        
        ack(response_action="update", view={
            "type": "modal",
            "callback_id": "project_save_final",
            "title": {"type": "plain_text", "text": "Update Project"},
            "submit": {"type": "plain_text", "text": "Save Changes"},
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"📝 Editing: *{selected}*"}},
                {"type": "input", "block_id": "client_name_hidden", "element": {"type": "plain_text_input", "action_id": "input", "initial_value": selected}, "label": {"type": "plain_text", "text": "Client"}, "optional": True},
                {"type": "input", "block_id": "status", "label": {"type": "plain_text", "text": "Status Update"}, "element": {"type": "plain_text_input", "multiline": True, "action_id": "input", "initial_value": current_status}},
                {"type": "input", "block_id": "category", "label": {"type": "plain_text", "text": "Category"}, "element": create_select_element("selection", category_opts, project.get("category", ""), "Select category...")},
                {"type": "input", "block_id": "owner", "label": {"type": "plain_text", "text": "PM (Owner)"}, "element": create_select_element("selection", owner_opts, project.get("owner", ""), "Select PM...")},
                {"type": "input", "block_id": "developer", "label": {"type": "plain_text", "text": "Developer"}, "element": create_select_element("selection", dev_opts, project.get("developer", ""), "Select Developer...")},
                {"type": "input", "block_id": "blocker", "optional": True, "label": {"type": "plain_text", "text": "Blocker"}, "element": {"type": "plain_text_input", "action_id": "input", "initial_value": current_blocker}},
                {"type": "input", "block_id": "last_contact_date", "label": {"type": "plain_text", "text": "Last Contact Date"}, "element": contact_datepicker},
                {"type": "input", "block_id": "comm_channel", "label": {"type": "plain_text", "text": "Channel"}, "element": checkbox_el},
                {"type": "input", "block_id": "call", "optional": True, "label": {"type": "plain_text", "text": "Next Call"}, "element": call_datepicker}
            ]
        })
    except (KeyError, TypeError) as e:
        print(f"❌ Error processing project selection: {e}")
        ack(response_action="errors", errors={"client_select": "Error loading project data"})

def get_select_value(values, block_name):
    """Helper to get selected value from dropdown"""
    try:
        opt = values.get(block_name, {}).get("selection", {}).get("selected_option")
        return opt["value"] if opt else None
    except:
        return None

def get_checkbox_values(values, block_name):
    """Helper to get selected checkbox values"""
    try:
        selected = values.get(block_name, {}).get("checkboxes", {}).get("selected_options", [])
        return ", ".join([opt["value"] for opt in selected]) if selected else "-"
    except:
        return "-"

def track_project_changes(project, new_data, user_email):
    """Track changes to a project and store history
    
    Args:
        project: The project dictionary (will be modified)
        new_data: Dictionary of new field values
        user_email: Email of user making the change
    
    Returns:
        dict: Summary of changes made
    """
    # Initialize history if it doesn't exist
    if "history" not in project:
        project["history"] = []
    
    # Create snapshot of current state (before changes)
    previous_state = {
        "status": project.get("status", ""),
        "category": project.get("category", ""),
        "owner": project.get("owner", ""),
        "developer": project.get("developer", ""),
        "blocker": project.get("blocker", ""),
        "last_contact_date": project.get("last_contact_date", ""),
        "call": project.get("call", ""),
        "comm_channel": project.get("comm_channel", "")
    }
    
    # Track what changed
    changes = {}
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Compare each field and track changes
    field_mapping = {
        "status": "status",
        "category": "category",
        "owner": "owner",
        "developer": "developer",
        "blocker": "blocker",
        "last_contact_date": "last_contact_date",
        "call": "call",
        "comm_channel": "comm_channel"
    }
    
    for new_key, old_key in field_mapping.items():
        new_value = new_data.get(new_key, "")
        old_value = previous_state.get(old_key, "")
        
        # Normalize empty values
        if new_value in ["", "-", None]:
            new_value = "-"
        if old_value in ["", "-", None]:
            old_value = "-"
        
        # Track if value actually changed
        if str(new_value).strip() != str(old_value).strip() and new_value:
            changes[old_key] = {
                "old": old_value,
                "new": new_value
            }
    
    # Only create history entry if there are actual changes
    if changes:
        history_entry = {
            "timestamp": timestamp,
            "user": user_email,
            "changes": changes,
            "previous_state": previous_state
        }
        project["history"].append(history_entry)
        
        # Keep only last 50 history entries to prevent data bloat
        if len(project["history"]) > 50:
            project["history"] = project["history"][-50:]
        
        return {
            "changed": True,
            "changes": changes,
            "timestamp": timestamp
        }
    
    return {
        "changed": False,
        "changes": {},
        "timestamp": timestamp
    }

@app.view("project_save_final")
def handle_save_final(ack, view, body, client):
    ack()
    try:
        # Get user email for history tracking
        user_id = body.get("user", {}).get("id") if isinstance(body.get("user"), dict) else body.get("user_id")
        user_email = get_user_email(user_id, client) if user_id else "unknown"
        
        vals = view["state"]["values"]
        
        # Get client name (hidden field)
        client_name = vals.get("client_name_hidden", {}).get("input", {}).get("value", "")
        if not client_name:
            print("❌ Error: No client name found in form submission")
            return
        
        # Get all field values
        status = vals.get("status", {}).get("input", {}).get("value", "")
        category = get_select_value(vals, "category")
        owner = get_select_value(vals, "owner")
        developer = get_select_value(vals, "developer")
        blocker = vals.get("blocker", {}).get("input", {}).get("value", "") or "-"
        
        # Get dates (handle optional fields)
        last_contact_date = vals.get("last_contact_date", {}).get("datepicker", {}).get("selected_date", "") or "-"
        next_call = vals.get("call", {}).get("datepicker", {}).get("selected_date", "") or "-"
        
        # Get communication channels
        comm_channel = get_checkbox_values(vals, "comm_channel") or "-"
        
        # Prepare new data
        new_data = {
            "status": status,
            "category": category,
            "owner": owner,
            "developer": developer,
            "blocker": blocker,
            "last_contact_date": last_contact_date,
            "call": next_call,
            "comm_channel": comm_channel
        }
        
        projects = load_db()
        found = False
        change_summary = None
        
        for p in projects:
            if p["client"] == client_name:
                # Track changes before updating
                change_summary = track_project_changes(p, new_data, user_email)
                
                # Update all fields (only update if value provided, otherwise keep existing)
                if status:
                    p["status"] = status
                if category:
                    p["category"] = category
                if owner:
                    p["owner"] = owner
                if developer:
                    p["developer"] = developer
                if blocker:
                    p["blocker"] = blocker
                if last_contact_date and last_contact_date != "-":
                    p["last_contact_date"] = last_contact_date
                if next_call and next_call != "-":
                    p["call"] = next_call
                if comm_channel and comm_channel != "-":
                    p["comm_channel"] = comm_channel
                
                p["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                found = True
                break
        
        if found:
            save_db(projects)
            # Sync to knowledge base
            sync_data_to_knowledge_base()
            
            # Show change summary if available
            if change_summary and change_summary.get("changed"):
                changes_text = []
                for field, change in change_summary["changes"].items():
                    changes_text.append(f"• *{field.replace('_', ' ').title()}:* `{change['old']}` → `{change['new']}`")
                
                # Try to send a response (if we can get channel context)
                try:
                    # This will be handled by the modal response, but we can log it
                    print(f"✅ Project '{client_name}' updated by {user_email}")
                    print(f"   Changes: {', '.join(change_summary['changes'].keys())}")
                except:
                    pass
        else:
            print(f"⚠️ Warning: Project '{client_name}' not found in database")
    except KeyError as e:
        print(f"❌ Error accessing view state: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"❌ Error in handle_save_final: {e}")
        import traceback
        traceback.print_exc()

# --- FLASK ROUTES ---
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

@flask_app.route("/")
def health_check():
    return "Project Bot Operational", 200

# ==========================================
# INITIALIZATION ON STARTUP
# ==========================================
def initialize_app():
    """Initialize app on startup"""
    print("🚀 Initializing Shopline Project Bot...")
    
    # Setup OpenAI Assistant (if configured)
    if ai_client:
        assistant_id, vector_store_id = setup_openai_assistant()
        if assistant_id:
            print(f"✅ OpenAI Assistant ready: {assistant_id}")
            # Initial sync
            sync_data_to_knowledge_base()
        else:
            print("⚠️ OpenAI Assistant setup failed or not configured")
    else:
        print("⚠️ OpenAI client not configured. AI features disabled.")
    
    print("✅ Bot initialized and ready!")

# Initialize on import (for production)
# For development, this runs when script starts
if __name__ == "__main__":
    initialize_app()
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)
else:
    # For production (gunicorn, etc.)
    initialize_app()
