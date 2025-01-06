from metagpt.tools.libs.supabase_manager import get_supabase_manager_instance

FE_SUPABASE_PROMPT = """
Supabase is enabled, use it as the backend service (provides Auth, Database, Storage, and Real-time features).

Supabase Configuration:
- Project URL: {project_url}
- Project API Key: {project_key}
- Project REF: {project_ref}

### CRITICAL: DATABASE SETUP MUST BE COMPLETED BEFORE ANY CODE IMPLEMENTATION OR MODIFICATION, Follow These Steps in Order:

Before Starting:
- Review "Table Management Rules" section below for table operation guidelines

For New Project Development:
1. Database First: Create all necessary tables using SupabaseManager.execute_sql
2. Install Dependencies:
   - MUST run: `pnpm install @supabase/supabase-js`
   - This step is REQUIRED before writing any Supabase-related code

For Incremental Development:
1. Database Changes (if needed):
   - Check existing tables using SupabaseManager.get_session_schemas
   - Create new tables or modify existing ones as needed using SupabaseManager.execute_sql

### Table Management Rules
- IMPORTANT: DO NOT CREATE ANY USER TABLES. User management is FULLY handled by Supabase auth.users table
- Table format: {{app_name}}_{{session_id}}_{{entity_name}} (session_id is {session_id})
- ALWAYS use user_email (not user_id) for user identification in tables
- For row-level security, use auth.jwt() ->> 'email' to match user_email fields, so MUST include user_email in ALL insert operations
"""
TL_SUPABASE_PROMPT = "12.1 Default backend service is Supabase(providing Auth, Database, Storage, and Real-time features) insead of localStorage."
PM_SUPABASE_PROMPT = "   - Backend Service: If not specified in the requirements, use Supabase"
ARCHITECT_SUPABASE_PROMPT = "  - Backend: if user or the PRD has not specified, the default backend service is Supabase (providing Auth, Database, Storage, and Real-time features)"

SUPABASE_CODE_REQUIREMENT = """

# Code Requirements
1. When using Supabase JavaScript SDK, MUST use v2 version:

- NOTE that getSession and getUser methods are async, THIS IS CRUCIAL for proper user and session handling:
```jsx
// how to get session (async)
const {{ data: {{ session }} }} = await supabase.auth.getSession();
// how to get user (async)
const {{ data: {{ user }} }} = await supabase.auth.getUser();
```

- NOTE that emailRedirectTo MUST be set to the current origin, THIS IS CRUCIAL for user registration:
```jsx
const {{ error }} = await supabase.auth.signUp({{email, password, options: {{emailRedirectTo: window.location.origin}} }});
```

"""


def get_backend_prompt_for_fe() -> str:
    """Allow frontend engineer to specify Supabase as the backend service only if Supabase is enabled"""
    manager = get_supabase_manager_instance()

    return (
        FE_SUPABASE_PROMPT.format(
            project_url=manager.config.project_url,
            project_key=manager.config.project_key,
            project_ref=manager.config.project_ref,
            session_id=manager.config.session_id,
        )
        if manager.is_supabase_enabled
        else "Supabase is not enabled"
    )


def get_backend_prompt_for_tl() -> str:
    """Allow team leader to specify Supabase as the backend service only if Supabase is enabled"""
    manager = get_supabase_manager_instance()
    return TL_SUPABASE_PROMPT if manager.is_supabase_enabled else ""


def get_backend_prompt_for_pm() -> str:
    """Allow PM to specify Supabase as the backend service only if Supabase is enabled"""
    manager = get_supabase_manager_instance()
    return PM_SUPABASE_PROMPT if manager.is_supabase_enabled else ""


def get_backend_prompt_for_architect() -> str:
    """Allow architect to specify Supabase as the backend service only if Supabase is enabled"""
    manager = get_supabase_manager_instance()
    return ARCHITECT_SUPABASE_PROMPT if manager.is_supabase_enabled else ""


def get_supabase_code_requirement() -> str:
    """Return Supabase code requirement only if Supabase is enabled.

    Some LLMs (like DeepSeek) default to JavaScript v1 SDK syntax despite knowing v2 exists - examples needed.
    """
    manager = get_supabase_manager_instance()
    return SUPABASE_CODE_REQUIREMENT if manager.is_supabase_enabled else ""
