from metagpt.const import SUPABASE_TASK
from metagpt.tools.libs.supabase_manager import supabase_manager_instance

QUICK_THINK_SUPABASE_TASK_PROMPT = """

## SUPABASE_TASK
For requests that need backend functionality without specifying a backend solution, particularly suitable for Supabase integration. 
Key indicators include needs for:
- User authentication/authorization
- Data storage and CRUD operations
- Real-time features
- File storage
- Simple API endpoints

**Note:** Categorize as SUPABASE_TASK only if ALL conditions are met:
1. Request requires backend functionality (auth, database, etc.)
2. No specific backend technology is specified
3. No explicit rejection of Supabase
4. Requirements align with Supabase's capabilities

"""

QUICK_THICK_SUPABASE_TASK_EXAMPLE = """

Request: "Create a todo list app with user login and task management"
Thought: Needs auth and data storage with no specific backend requirement. Supabase can handle this perfectly.
Response Category: SUPABASE_TASK

Request: "Build a chat app with message history"
Thought: Requires real-time features and data persistence without specified backend. Suitable for Supabase.
Response Category: SUPABASE_TASK

Request: "Create a todo app using MySQL and Express.js"
Thought: Backend solution is explicitly specified as MySQL and Express.js.
Response Category: TASK

Request: "Build a todo app, but don't use Supabase"
Thought: Explicitly requests not to use Supabase.
Response Category: TASK

"""

FE_SUPABASE_PROMPT = f"""
Supabase is enabled, use it as the backend service (provides Auth, Database, Storage, and Real-time features).

The Supabase configuration for this project:
- Project URL: {supabase_manager_instance.config.project_url}
- Project API Key: {supabase_manager_instance.config.project_key}
- Session ID: {supabase_manager_instance.config.session_id}

### Database Schema Management (MANDATORY BEFORE Engineer2.write_new_code)
Create necessary database tables for this project using SupabaseManager.execute_sql before write any code.
- Note that you DO NOT need to create users table as it is already provided by Supabase in the 'auth' schema (auth.users)
- Table format: {{app_name}}_{{session_id}}_{{entity_name}}
- ALWAYS create new tables with current Session ID for new development
- For incremental development, only use tables matching current Session ID (if needed, use SupabaseManager.get_session_schemas to check tables)
- ALWAYS use user_email (not user_id) for user identification in tables
- For row-level security, use auth.jwt() ->> 'email' to match user_email fields, so MUST include user_email in ALL insert operations

### Supabase Client Integration
- When using HTML/JavaScript
   * If using NPM/module imports: Run "pnpm install @supabase/supabase-js"

### Code Requirements
- When using Supabase JavaScript SDK, MUST use v2 version, NOTE that auth methods are async:
```jsx
// how to get user (async)
const {{ data: {{ user }} }} = await supabase.auth.getUser();
// how to get session (async)
const {{ data: {{ session }} }} = await supabase.auth.getSession();
```
"""

TL_SUPABASE_PROMPT = "12.1 Default backend service is Supabase(providing Auth, Database, Storage, and Real-time features) insead of localStorage."
PM_SUPABASE_PROMPT = "   - Backend Service: If not specified in the requirements, use Supabase"
ARCHITECT_SUPABASE_PROMPT = "  - Backend: if user or the PRD has not specified, the default backend service is Supabase (providing Auth, Database, Storage, and Real-time features)"


def get_supabase_task_prompt():
    """Add SUPABASE_TASK intent recognition only if Supabase is not enabled"""
    return QUICK_THINK_SUPABASE_TASK_PROMPT if not supabase_manager_instance.is_supabase_enabled else ""


def get_supabase_task_example():
    """Add SUPABASE_TASK example only if Supabase is not enabled"""
    return QUICK_THICK_SUPABASE_TASK_EXAMPLE if not supabase_manager_instance.is_supabase_enabled else ""


def get_supabase_task_with_comma():
    """Add SUPABASE_TASK intent option only if Supabase is not enabled"""
    return f"{SUPABASE_TASK}, " if not supabase_manager_instance.is_supabase_enabled else ""


def get_supabase_task_with_slash():
    """Add SUPABASE_TASK intent option only if Supabase is not enabled"""
    return f"{SUPABASE_TASK}/" if not supabase_manager_instance.is_supabase_enabled else ""


def get_backend_prompt_for_fe():
    """Allow frontend engineer to specify Supabase as the backend service only if Supabase is enabled"""
    return FE_SUPABASE_PROMPT if supabase_manager_instance.is_supabase_enabled else "Supabase is not enabled"


def get_backend_prompt_for_tl():
    """Allow team leader to specify Supabase as the backend service only if Supabase is enabled"""
    return TL_SUPABASE_PROMPT if supabase_manager_instance.is_supabase_enabled else ""


def get_backend_prompt_for_pm():
    """Allow PM to specify Supabase as the backend service only if Supabase is enabled"""
    return PM_SUPABASE_PROMPT if supabase_manager_instance.is_supabase_enabled else ""


def get_backend_prompt_for_architect():
    """Allow architect to specify Supabase as the backend service only if Supabase is enabled"""
    return ARCHITECT_SUPABASE_PROMPT if supabase_manager_instance.is_supabase_enabled else ""
