from metagpt.const import REACT_TEMPLATE_PATH
from metagpt.tools.libs.editor import FileBlock


def read_file(file_path: str) -> str:
    with open(file_path, "r") as file:
        content = file.read()
    return FileBlock(path=str(file_path), content=content)


INDEX_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "index.html")
MAIN_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "src/main.jsx")
APP_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "src/App.jsx")
INDEX_CSS_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "src/index.css")
CONFIG_CONTENT = read_file(REACT_TEMPLATE_PATH.resolve().absolute() / "vite.config.js")


GENERAL_WEB_APP_TEMPLATE = f"""
### Template Intro
1. This is a template for gneral web app or game development. It is based on React framework with Tailwind CSS. The template includes the basic structure of a React project, including an index.html file and a src directory with an App.jsx file.
2. The template is at {REACT_TEMPLATE_PATH.resolve().absolute()}
3. Modify index.html, create new jsx files under src if needed, and rewrite src/App.jsx to meet the user's requirements.
4. Style your elements with Tailwind CSS classes directly in the jsx files.

### Project Structure
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

### File Content
#### index.html (Modify the title)
{INDEX_CONTENT}

#### src/main.jsx (You should NOT modify it)
{MAIN_CONTENT}

#### src/App.jsx (to be modified)
{APP_CONTENT}

#### src/index.css (You should NOT modify it)
{INDEX_CSS_CONTENT}

#### vite.config.js (only modify it if extra config is absolutely necessary)
{CONFIG_CONTENT}
"""
