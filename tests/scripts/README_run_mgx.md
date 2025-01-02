# Running MGX_ENV
Here is the environment setup for running MGX.

- Engineers use FrontendEngineer here, which requires a template.
- The message recipient can be modified in `env.publish_message()`.

Below are instructions about templates.

## Template Management

### 1. Template Setup
- Download the default web project template from [MGX Template Repository](https://gitlab.deepwisdomai.com/metagpt/mgx_template/-/tree/main/templates/default_web_project)
- Place it in your project's `/template` directory following this structure:
  ```
  /path/to/your/project/template/
  └── default_web_project/
      ├── react_template/
      └── vue_template/
  ```
- Reference path configuration in `MetaGPT/metagpt/const.py`

### 2. Download Tree package
- On Ubuntu/Debian:
  - `sudo apt-get install tree`
- On MacOS:
  - `brew install tree`

### 3. Using Template in Frontend Engineer
```python
# Import template tool
from metagpt.tools.libs.search_template import FixedSearchTemplate

# Initialize Frontend Engineer with template support
frontend_engineer = FrontendEngineer(template_tool=FixedSearchTemplate())
```

### 4. Available Templates

#### Default Web Project
- **React Template**: Full-stack React.js project structure
- **Vue Template**: Full-stack Vue.js project structure
