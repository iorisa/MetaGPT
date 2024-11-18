from metagpt.const import REACT_TEMPLATE_PATH, VUE_TEMPLATE_PATH
from metagpt.tools.libs.editor import FileBlock


def read_file(file_path: str) -> str:
    if not file_path.exists():
        return ""
    with open(file_path, "r") as file:
        content = file.read()
    return FileBlock(path=str(file_path), content=content)


TEMPLATE_PATH = VUE_TEMPLATE_PATH.resolve().absolute() if VUE_TEMPLATE_PATH.exists() else "N/A"
TEMPLATE_STRUCTURE = (
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
    if TEMPLATE_PATH != "N/A"
    else ""
)
INDEX_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "index.html")
MAIN_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "src/main.js")
APP_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "src/App.vue")
INDEX_CSS_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "src/style.css")
CONFIG_CONTENT = read_file(VUE_TEMPLATE_PATH.resolve().absolute() / "vite.config.js")

GENERAL_WEB_APP_TEMPLATE_DESCRIPTION = "general web app or game development. It is based on React framework with Tailwind CSS. The template includes the basic structure of a React project, including an index.html file and a src directory with an App.jsx file."

GENERAL_WEB_APP_TEMPLATE = f"""
### Template Intro
1. This is a template for {{GENERAL_WEB_APP_TEMPLATE_DESCRIPTION}}
2. The template is at {{TEMPLATE_PATH}}.
3. Modify index.html, create new jsx files under src if needed, and rewrite src/App.vue to meet the user's requirements.
4. Style your elements with Tailwind CSS classes directly in the vue files.

### Project Structure
{{TEMPLATE_STRUCTURE}}

### File Content
#### index.html (Modify the title)
{{INDEX_CONTENT}}

#### src/main.js (You should NOT modify it)
{{MAIN_CONTENT}}

#### src/App.vue (to be modified)
{{APP_CONTENT}}

#### src/style.css (You should NOT modify it)
{{INDEX_CSS_CONTENT}}

#### vite.config.js (only modify it if extra config is absolutely necessary)
{{CONFIG_CONTENT}}
"""

GENERAL_WEB_APP_TEMPLATE_PROMPT = GENERAL_WEB_APP_TEMPLATE.format(
    GENERAL_WEB_APP_TEMPLATE_DESCRIPTION=GENERAL_WEB_APP_TEMPLATE_DESCRIPTION,
    TEMPLATE_PATH=TEMPLATE_PATH,
    TEMPLATE_STRUCTURE=TEMPLATE_STRUCTURE,
    INDEX_CONTENT=INDEX_CONTENT,
    MAIN_CONTENT=MAIN_CONTENT,
    APP_CONTENT=APP_CONTENT,
    INDEX_CSS_CONTENT=INDEX_CSS_CONTENT,
    CONFIG_CONTENT=CONFIG_CONTENT
)
