# Running MGX_ENV
Here is the environment setup for running MGX.

- Engineers use FrontendEngineer here, which requires a template.

Below are instructions about templates.

## Prepare Template

### 1. Template Setup
- Download the default web project template from [MGX Template Repository](https://gitlab.deepwisdomai.com/metagpt/mgx_template/-/tree/main/templates/default_web_project)
- Place it in your project's `/template` directory.
- The specific `/path/to/your/project/template/` is specified as the `TEMPLATE_FOLDER_PATH` in `metagpt/const.py`

### 2. Download Tree package
- On Ubuntu/Debian:
  - `sudo apt-get install tree`
- On MacOS:
  - `brew install tree`

### 3. Using Template in Frontend Engineer
```python
# Import template tool
from metagpt.tools.libs.search_template import FixedSearchTemplate
from metagpt.const import REACT_TEMPLATE_PATH

# Initialize Frontend Engineer with template support
engineer = FrontendEngineer(template_tool=FixedSearchTemplate(template_path=REACT_TEMPLATE_PATH))
```

### 4. Available Templates

#### Default Web Project
- **React Template**: Full-stack React.js project structure
- **Vue Template**: Full-stack Vue.js project structure

## Run MGX
### 1. Run MGX
To run MGX, execute the following command in the terminal:
```bash
python ./tests/metagpt/environment/mgx_ops/run_mgx_env.py
```
### 2. Modify Recipient 
If you want to send message to specific someone, you can specify a direct recipient, the `user_defined_recipient` parameter in the main script. 

Also if you want to send requirement in terminal, you can set `enable_human_input` to True
:
```python
asyncio.run(
    main(
        requirement=requirement,
        user_defined_recipient=user_defined_recipient,
        enable_human_input=True,
        allow_idle_time=600,
      )
    )
```