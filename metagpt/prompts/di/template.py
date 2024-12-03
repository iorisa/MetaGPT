from pathlib import Path
from typing import Union

from metagpt.tools.libs.editor import FileBlock


def read_file(file_path: Union[str, Path], encoding: str = "utf-8") -> FileBlock:
    """Read a file and return its content as a FileBlock.

    Args:
        file_path: Path to the file (str or Path object)
        encoding: File encoding (default: utf-8)

    Returns:
        FileBlock with file path and content
    """
    path = Path(file_path)
    if not path.exists():
        return FileBlock(path=str(path), content="")

    with open(path, "r", encoding=encoding) as file:
        content = file.read()

    return FileBlock(path=str(path), content=content)


# a backup desc for https://gitlab.deepwisdomai.com/metagpt/mgx_template/-/blob/main/templates/default_web_project/react_template/template_config.json
REACT_APP_TEMPLATE_DESC = """
 - This is a template for general web app or game development. It is based on React framework with Tailwind CSS. The template includes the basic structure of a React project, including an index.html file and a src directory with an App.jsx file.
 - Modify index.html, create new jsx files under src if needed, and rewrite src/App.jsx to meet the user's requirements. You should NOT modify src/main.jsx and src/index.css. Modify vite.config.js only if extra config is absolutely necessary.
 - Style your elements with Tailwind CSS classes directly in the jsx files.
"""

GENERAL_WEB_APP_TEMPLATE = """
### {TEMPLATE_NAME} Template Intro
1. {TEMPLATE_DESCRIPTION}
2. The template is at {TEMPLATE_PATH}.
3. {REQUIRED_FILES_INSTRUCTION}
4. {REQUIRED_FIELDS_INSTRUCTION}
5. The template is written in {TEMPLATE_LANG}.
6. The template is based on {TEMPLATE_FRAMEWORK}.

### Project Structure
{TEMPLATE_STRUCTURE}

### File Content
{FILE_CONTENT}
"""

GENERAL_WEB_APP_TEMPLATE_PROMPT = """No template available"""

EXRTA_INFO_PROMPT = """
1. {template_style} template successfully copied to {target_dir}. Rename the template and navigate to it before starting the project. 
2. If the project root directory exists README.md, read it first.
3. If user does not provide additional information, you should deploy the project directly without updating any code. However, if the user instructs obtaining their information from a certain website or file, use the appropriate tools to retrieve it, and then update the obtained information into the project.
4. Make sure you have understood the content of the code file before updating or writing the code.
"""

GENERATE_TEMPLATE_CONFIG_PROMPT = """
Please generate a template configuration based on the following template 
directory information:
Directory structure:
{dir_structure}
README content:
{readme_content}
Please generate a configuration in JSON format that includes the following 
fields:
1. description (str): Template description. It is necessary to explain what this template is and its purpose.
2. required_fields (list[str]): List of required fields. It is necessary to provide a list of fields in the template for modification.
3. required_files (list[str]): List of required files. This should be a list of relative file paths, and each file in the list is essential for the AI to understand the content of this template. Note that the document cannot contain images, audio, or video.
4. lang (str): Template language. It is necessary to provide the programming language of the template.
5. framework (str): Template framework. It is necessary to provide the framework of the template.

Please ensure that the generated configuration is in valid JSON format.
```json
{{
    "description": "the description of template",
    "required_fields": ["Please provide a list of fields in the template for modification."],
    "required_files": ["Please provide a list of file's relative paths in the template."],
    "lang": "Please provide the language of the template.",
    "framework": "Please provide the framework of the template."
}}
```
"""
