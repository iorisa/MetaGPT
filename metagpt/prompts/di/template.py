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
 - This is a template for general web app or game development. It is based on React framework with Tailwind CSS and JavaScript. The template includes the basic structure of a React project, including an index.html file and a src directory with an App.jsx file.
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
1. {template_style} template successfully copied to {target_dir}. Navigate to it before starting the project. 
2. If the project root directory exists README.md, read it first.
3. Make sure you have understood the content of the code file before updating or writing the code.
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


CODE_TOOL_USAGE_EXAMPLE = """
1. Setting a Background Image:
```jsx
// example.jsx
// existing code
backgroundImage: 'url(<tool_call> ImageGetter.get(search_term="a beautiful sunset", image_save_path="/absolute_path/to/public/images/sonnet-bj.png", mode="search") </tool_call>)',
// existing code
```

2. To use an image as a game character or element:
```jsx
// example.jsx
// existing code
<img src=\"<tool_call> ImageGetter.get(search_term="a cute bird", image_save_path="/absolute_path/to/public/images/bird.png", mode="search") </tool_call>\" alt="bird" />
// existing code
```

3. To create a image and use it in the code:
```jsx
// example.jsx
// existing code
<img src=\"<tool_call> ImageGetter.get(search_term="a fly pig", image_save_path="/absolute_path/to/public/images/fly_pig.png", mode="create") </tool_call>\" alt="pig" />
// existing code
```

4. To remove the background of an image:
```jsx
// example.jsx
// existing code
<img src=\"<tool_call> ImageGetter.process(image_path="/absolute_path/to/will/be/process/image.png", image_save_path="/absolute_path/to/public/images/image_rembg.png", mode="rembg") </tool_call>\" />
// existing code
```
"""
