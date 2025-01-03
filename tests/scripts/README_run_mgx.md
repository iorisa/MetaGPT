# Running MGX_ENV
Here is the environment setup for running MGX.

- Engineers use FrontendEngineer here, which requires a template.
- The message recipient can be modified in `env.publish_message()`.

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

# Initialize Frontend Engineer with template support
frontend_engineer = FrontendEngineer(template_tool=FixedSearchTemplate())
```

### 4. Available Templates

#### Default Web Project
- **React Template**: Full-stack React.js project structure
- **Vue Template**: Full-stack Vue.js project structure

## Run MGX
### 1. change to Frontend Engineer
Change roles in ENV.roles. Replace Engineer with FrontendEngineer.
```python
from metagpt.roles.di.frontend_engineer import FrontendEngineer
from metagpt.tools.libs.search_template import FixedSearchTemplate

env = MGXEnv()
env.roles = [FrontendEngineer(template_tool=FixedSearchTemplate())...]
```
### 2. Run MGX
To run MGX, execute the following command in the terminal:
```bash
python ./tests/metagpt/environment/mgx_ops/run_mgx_env.py
```
### 3. Modify Recipient 
If you want to send message to specific someone, you can modify the recipient in the script by changing this line:
```python
user_defined_recipient = "Alex"
env.publish_message(Message(content=requirement, send_to={user_defined_recipient}), user_defined_recipient=user_defined_recipient)
```