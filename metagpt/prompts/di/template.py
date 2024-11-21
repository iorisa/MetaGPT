from metagpt.const import REACT_TEMPLATE_PATH, VUE_TEMPLATE_PATH
from metagpt.tools.libs.editor import FileBlock


def read_file(file_path: str) -> str:
    if not file_path.exists():
        return ""
    with open(file_path, "r") as file:
        content = file.read()
    return FileBlock(path=str(file_path), content=content)


VUE_TEMPLATE_PATH = VUE_TEMPLATE_PATH.resolve().absolute() if VUE_TEMPLATE_PATH.exists() else "N/A"
VUE_TEMPLATE_STRUCTURE = (
    """
vue_template/
├── README.md
├── index.html
├── package.json
├── pnpm-lock.yaml
├── postcss.config.js
├── public
│   └── vite.svg
├── src
│    ├── App.vue
│    ├── main.js
│    └── style.css
├── tailwind.config.js
└── vite.config.js
"""
    if VUE_TEMPLATE_PATH != "N/A"
    else ""
)
VUE_INDEX_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "index.html")
VUE_MAIN_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "src/main.js")
VUE_APP_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "src/App.vue")
VUE_INDEX_CSS_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "src/style.css")
VUE_CONFIG_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "vite.config.js")

VUE_APP_TEMPLATE_DESCRIPTION = "general web app or game development. It is based on VUE framework with Tailwind CSS. The template includes the basic structure of a React project, including an index.html file and a src directory with an App.vue file."

VUE_APP_TEMPLATE = """
#### VUE Template Intro
1. This is a template for {VUE_APP_TEMPLATE_DESCRIPTION}
2. The template is at {TEMPLATE_PATH}.
3. Modify index.html, create new jsx files under src if needed, and rewrite src/App.vue to meet the user's requirements.
4. Style your elements with Tailwind CSS classes directly in the vue files.

### Project Structure
{TEMPLATE_STRUCTURE}

### File Content
#### index.html (Modify the title)
{INDEX_CONTENT}

#### src/main.js (You should NOT modify it)
{MAIN_CONTENT}

#### src/App.vue (to be modified)
{APP_CONTENT}

#### src/style.css (You should NOT modify it)
{INDEX_CSS_CONTENT}

#### vite.config.js (only modify it if extra config is absolutely necessary)
{CONFIG_CONTENT}
"""

# REACT_TEMPLATE_PATH = REACT_TEMPLATE_PATH.resolve().absolute() if REACT_TEMPLATE_PATH.exists() else "N/A"
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


VUE_APP_TEMPLATE_PROMPT = VUE_APP_TEMPLATE.format(
    VUE_APP_TEMPLATE_DESCRIPTION=VUE_APP_TEMPLATE_DESCRIPTION,
    TEMPLATE_PATH=VUE_TEMPLATE_PATH,
    TEMPLATE_STRUCTURE=VUE_TEMPLATE_STRUCTURE,
    INDEX_CONTENT=VUE_INDEX_CONTENT,
    MAIN_CONTENT=VUE_MAIN_CONTENT,
    APP_CONTENT=VUE_APP_CONTENT,
    INDEX_CSS_CONTENT=VUE_INDEX_CSS_CONTENT,
    CONFIG_CONTENT=VUE_CONFIG_CONTENT,
)

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
1. description: Template description
2. required_fields: List of required fields

Please ensure that the generated configuration is in valid JSON format.
```json
{
    "style": "{style}",
    "description": "the description of template",
    "required_fields": ["name", "job", "email", "phone", "description", "mbti"]
}
```
"""
