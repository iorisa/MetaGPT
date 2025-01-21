# Guidance to Run MGX

## Prepare Template
Engineers use FrontendEngineer here, which requires a template. Below are instructions about templates.

### 1. Template Setup
- Download the default web project template from [MGX Template Repository](https://gitlab.deepwisdomai.com/metagpt/mgx_template/-/tree/main/templates/default_web_project)
- Place it in your project's `/path/to/your/project/template` directory.
- The specific `/path/to/your/project/template/` is specified as the `TEMPLATE_FOLDER_PATH` in `metagpt/const.py`

### 2. Download Tree package (if necessary)
- On Ubuntu/Debian:
  - `sudo apt-get install tree`
- On MacOS:
  - `brew install tree`

### 3. Available Templates

#### Default Web Project
- **React Template**: Full-stack React.js project structure
- **Vue Template**: Full-stack Vue.js project structure

## Run MGX
### 1. Quick Start
To run MGX, execute the following command in the terminal:
```bash
python ./tests/scripts/run_mgx_env.py
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

### 3. Specify A Different Templates
You may change the template_path argument at the following code
```python
engineer = FrontendEngineer(template_tool=FixedSearchTemplate(template_path=REACT_TEMPLATE_PATH))
```
