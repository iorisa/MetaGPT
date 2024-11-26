from pathlib import Path
from typing import Union

from metagpt.const import REACT_TEMPLATE_PATH
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


REACT_TEMPLATE_PATH = REACT_TEMPLATE_PATH.resolve().absolute() if REACT_TEMPLATE_PATH.exists() else "N/A"
REACT_TEMPLATE_STRUCTURE = (
    """
react_template/
|-- eslint.config.js
|-- index.html
|-- package.json
|-- pnpm-lock.yaml
|-- postcss.config.js
|-- public
|-- src
|   |-- App.jsx
|   |-- index.css
|   `-- main.jsx
|-- tailwind.config.js
`-- vite.config.js
"""
    if REACT_TEMPLATE_PATH != "N/A"
    else ""
)
REACT_INDEX_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "index.html")
REACT_MAIN_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "src/main.jsx")
REACT_APP_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "src/App.jsx")
REACT_INDEX_CSS_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "src/index.css")
REACT_CONFIG_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "vite.config.js")


REACT_APP_TEMPLATE = f"""
#### REACT Template Intro
1. This is a template for general web app or game development. It is based on React framework with Tailwind CSS. The template includes the basic structure of a React project, including an index.html file and a src directory with an App.jsx file.
2. The template is at {REACT_TEMPLATE_PATH}.
3. Modify index.html, create new jsx files under src if needed, and rewrite src/App.jsx to meet the user's requirements.
4. Style your elements with Tailwind CSS classes directly in the jsx files.

### Project Structure
{REACT_TEMPLATE_STRUCTURE}

### File Content
#### index.html (Modify the title)
{REACT_INDEX_CONTENT}

#### src/main.jsx (You should NOT modify it)
{REACT_MAIN_CONTENT}

#### src/App.jsx (to be modified)
{REACT_APP_CONTENT}

#### src/index.css (You should NOT modify it)
{REACT_INDEX_CSS_CONTENT}

#### vite.config.js (only modify it if extra config is absolutely necessary)
{REACT_CONFIG_CONTENT}
"""

GENERAL_WEB_APP_TEMPLATE = """
#### {TEMPLATE_NAME} Template Intro
1. This is a template for {TEMPLATE_DESCRIPTION}
2. The template is at {TEMPLATE_PATH}.
3. {REQUIRED_FILES_INSTRUCTION}
4. {REQUIRED_FIELDS_INSTRUCTION}
5. The template is written in {TEMPLATE_LANG} language.

### Project Structure
{TEMPLATE_STRUCTURE}

### File Content
{FILE_CONTENT}
"""

GENERAL_WEB_APP_TEMPLATE_PROMPT = "### Template Intro\n" + REACT_APP_TEMPLATE

GENERATE_TEMPLATE_CONFIG_PROMPT = """
Please generate a template configuration based on the following template 
directory information:
Directory structure:
{dir_structure}
README content:
{readme_content}
Please generate a configuration in JSON format that includes the following 
fields:
1. description: Template description. It is necessary to explain what this template is and its purpose.
2. required_fields: List of required fields. It is necessary to provide a list of fields in the template for modification.
3. required_files: List of required files. This should be a list of relative file paths, and each file in the list is essential for the AI to understand the content of this template. Note that the document cannot contain images, audio, or video.
4. lang: Template language. It is necessary to provide the language of the template.

Please ensure that the generated configuration is in valid JSON format.
```json
{{
    "description": "the description of template",
    "required_fields": ["Please provide a list of fields in the template for modification."],
    "required_files": ["Please provide a list of file's relative paths in the template."],
    "lang": "Please provide the language of the template."
}}
```
"""
