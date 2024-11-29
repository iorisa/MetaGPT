from metagpt.prompts.di.frontend_engineer import FE_EXAPMLE, FRONTEND_ENGINEER_PROMPT
from metagpt.roles.di.engineer2 import Engineer2


class FrontendEngineer(Engineer2):
    instruction: str = FRONTEND_ENGINEER_PROMPT
    tools: list[str] = [
        "Editor:read,write,edit_file_by_replace,insert_content_at_line,append_file",
        "RoleZero",
        "Terminal:run_command",
        "SearchEnhancedQA",
        "ImageGetter",
        "Deployer",
        "Engineer2",
        "SupabaseManager",
    ]

    def _retrieve_experience(self) -> str:
        return FE_EXAPMLE
