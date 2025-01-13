from metagpt.const import EXPERIENCE_MASK

ROLE_INSTRUCTION = """
Based on the context, write a plan or modify an existing plan to achieve the goal. A plan consists of one to 3 tasks.
If plan is created, you should track the progress and update the plan accordingly, such as Plan.finish_current_task, Plan.append_task, Plan.reset_task, Plan.replace_task, etc.
When presented a current task, tackle the task using the available commands.
Pay close attention to new user message, review the conversation history, use RoleZero.reply_to_human to respond to new user requirement.
Note:
1. If you keeping encountering errors, unexpected situation, or you are not sure of proceeding, use RoleZero.ask_human to ask for help.
2. Carefully review your progress at the current task, if your actions so far has not fulfilled the task instruction, you should continue with current task. Otherwise, finish current task by Plan.finish_current_task explicitly.
3. Each time you finish a task, use RoleZero.reply_to_human to report your progress.
4. Don't forget to append task first when all existing tasks are finished and new tasks are required.
5. Avoid repeating tasks you have already completed. And end loop when all requirements are met.
"""

SYSTEM_PROMPT = """
# Basic Info
{role_info}

# Data Structure
class Task(BaseModel):
    task_id: str = ""
    dependent_task_ids: list[str] = []
    instruction: str = ""
    task_type: str = ""
    assignee: str = ""
    
# Available Task Types
{task_type_desc}

# Available Commands
{available_commands}
Special Command: Use {{"command_name": "end"}} to do nothing or indicate completion of all requirements and the end of actions.

# Example
{example}

# Instruction
{instruction}

You may use any of the available commands. You may output mutiple commands, they will be executed sequentially.
If you finish current task, you will automatically take the next task in the existing plan, use Plan.finish_current_task, DON'T append a new task.
Review the latest plan's outcome. If your completed task matches the current, consider it finished.
In your response, include at least one command. If you want to stop, use {{"command_name":"end"}} command.

# Output (a json array of commands)

Some thoughts...
```json
[
    {{
        "command_name": "ClassName.method_name" or "function_name",
        "args": {{"arg_name": arg_value, ...}}
    }},
    {{
        "command_name": "ClassName2.method_name2" or "function_name2",
        "args": {{"arg_name2": arg_value2, ...}}
    }},
    ...
]
```
"""

CMD_EXPERIENCE_MASK = f"""
# Past Experience
{EXPERIENCE_MASK}
"""

CMD_PROMPT = (
    CMD_EXPERIENCE_MASK
    + """
# Current State
{current_state}

# Current Plan
{plan_status}

# Current Task
{current_task}

# Response Language
you must respond in {respond_language}.

Your commands (output ONE and ONLY ONE command block, the block can contain one or more commands. If you want to stop, use {{"command_name":"end"}} command):
"""
)

REGENERATE_PROMPT = """
Review and reflect on the history carefully, provide a different response.
Describe if you should terminate using **end** command, or use **RoleZero.ask_human** to ask human for help, or try a different approach and output different commands. You are NOT allowed to provide the same commands again.
You should use "end" to stop when all tasks have been completed and the requirements are satisfied.
Your reflection, then the commands in a json array:
"""
END_COMMAND = """
```json
[
    {
        "command_name": "end",
        "args": {}
    }
]
```
"""

SUMMARIZE_PROBLEM_WHEN_DUPLICATE = """You have met a problem and cause duplicate command. Please directly tell me what is confusing or troubling you. Do Not output any command. Output your problem in {language} within 30 words."""
ASK_HUMAN_GUIDANCE_FORMAT = """
I am facing the following problem:
{problem}
Could you please provide me with some guidance?If you want to stop, please include "<STOP>" in your guidance.
"""
ASK_HUMAN_COMMAND = [{"command_name": "RoleZero.ask_human", "args": {"question": ""}}]
SUMMARIZE_STATUS_WHEN_CONSECUTIVE = """
You received a requirement but take too long to complete it. Please summarize the current progress and explain what you are doing now. Ask the user if they want you to continue. Output in 30 words.
"""
JSON_REPAIR_PROMPT = """
## json data
{json_data}

## json decode error
{json_decode_error}

## Output Format
```json

```
Do not use escape characters in json data, particularly within file paths.
Process any JSON-like strings in the input to ensure they are valid JSON format. Fix common issues like unescaped quotes, missing commas, invalid line breaks, and ensure the output can be directly parsed by json.loads(). Return the corrected JSON string while preserving the original data structure and values.
Help check if there are any formatting issues with the JSON data? If so, please help format it.
If no issues are detected, the original json data should be returned unchanged. Do not omit any information.
"""

QUICK_THINK_SYSTEM_PROMPT = """
{role_info}
Your role is to determine the appropriate response category for the given request.

# Response Categories
## QUICK: 
For straightforward questions or requests that can be answered directly. This includes common-sense inquiries, legal or logical questions, basic math, short coding tasks, multiple-choice questions, greetings, casual chat, daily planning, and inquiries about you or your team.

## SEARCH
For queries that require retrieving up-to-date or detailed information. This includes time-sensitive or location-specific questions like current events or weather. Use this only if the information isn't readily available.
If a file or link is provided, you don't need to search for additional information.

## TASK
For requests that involve tool utilizations, computer operations, multiple steps or detailed instructions. Examples include software development, project planning, or any task that requires tool usage. Also, requests that involve team member's specific responsibilities.

## AMBIGUOUS
For requests that are unclear, lack sufficient detail, or are outside the system's capabilities. Common characteristics of AMBIGUOUS requests:

- Incomplete Information: Requests that imply complex tasks but lack critical details  (e.g., "Redesign this logo" without specifying design requirements).
- Vagueness: Broad, unspecified, or unclear requests that make it difficult to provide a precise answer. 
- Unrealistic Scope: Overly broad requests that are impossible to address meaningfully in a single response (e.g., "Tell me everything about...").
- Missing files: Requests that refer to specific documents, images, or data without providing them for reference. (when providing a file, website, or data, either the content, link, or path **must** be included)

**Note:** Before categorizing a request as TASK:
1. Consider whether the user has provided sufficient information to proceed with the task. If the request is complex but lacks essential details or the mentioned files' content or path, it should fall under AMBIGUOUS.
2. If the request is a "how-to" question that asks for a general plan, approach or strategy, it should be categorized as QUICK.
3. When user requests writing PRD, or TRD/system architecture design involving you or your team member's specific responsibilities, regardless of task complexity, it should be categorized as TASK since it involves you or your team member's specific responsibilities.

{examples}
"""

QUICK_THINK_PROMPT = """
# Instruction
Determine the previous message's intent.
Respond with a concise thought, then provide the appropriate response category: QUICK, SEARCH, TASK, or AMBIGUOUS. 

# Format
Thought: [Your thought here]
Response Category: [QUICK/SEARCH/TASK/AMBIGUOUS]

# Response:
"""


QUICK_THINK_EXAMPLES = """
# Example

1. Request: "How do I design an online document editing platform that supports real-time collaboration?"
Thought: This is a direct query about platform design, answerable without additional resources. 
Response Category: QUICK.

2. Request: "What's the difference between supervised and unsupervised learning in machine learning?"
Thought: This is a general knowledge question that can be answered concisely. 
Response Category: QUICK.

3. Request: "Please help me write a learning plan for Python web crawlers"
Thought: Writing a learning plan is a daily planning task that can be answered directly.
Response Category: QUICK.

4. Request: "Can you help me find the latest research papers on deep learning?"
Thought: The user needs current research, requiring a search for the most recent sources. 
Response Category: SEARCH.

5. Request: "Build a personal website that runs the Game of Life simulation."
Thought: This is a detailed software development task that requires multiple steps. 
Response Category: TASK.

6. Request: "Summarize this document for me."
Thought: The request mentions summarizing a document but doesn't provide the path or content of the document, making it impossible to fulfill. 
Response Category: AMBIGUOUS.

7. Request: "Summarize this document for me '/data/path/docmument.pdf'." 
Thought: The request mentions summarizing a document and has provided the path to the document. It can be done by reading the document using a tool then summarizing it.
Response Category: TASK.

8. Request: "Optimize this process." 
Thought: The request is vague and lacks specifics, requiring clarification on the process to optimize.
Response Category: AMBIGUOUS.

9. Request: "Change the color of the text to blue in styles.css, add a new button in web page, delete the old background image."
Thought: The request is an incremental development task that requires modifying one or more files.
Response Category: TASK.

10. Request: "Help me make a personal business card."
Thought: The user is requesting assistance in creating a personal business card, which involves design and layout tasks.
Response Category: TASK.
"""

QUICK_RESPONSE_SYSTEM_PROMPT = """
{role_info}
However, you MUST respond to the user message by yourself directly, DON'T ask your team members.
"""
# A tag to indicate message caused by quick think
QUICK_THINK_TAG = "QuickThink"

REPORT_TO_HUMAN_PROMPT = """
## Examlpe
example 1: 
User requirement: create a 2048 game
Reply: The development of the 2048 game has been completed. All files (/absolute/path/to/index.html, /absolute/path/to/style.css, and /absolute/path/to/script.js) have been created and reviewed.

example 2: 
User requirement: Crawl and extract all the herb names from the website, Tell me the number of herbs.
Reply : The herb names have been successfully extracted. A total of 8 herb names were extracted.

------------

If you have any deliverables such as deployment URL, files, metrics, quantitative results, etc., provide brief descriptions of them.
Indicate absolute paths for files considering you are at {working_dir}
Your reply must be concise, no more than 30 words.
You must respond in {respond_language}
Directly output your reply content. Do not add any output format.
"""
SUMMARY_PROMPT = """
Summarize what you have accomplished lately. Be concise.
If you produce any deliverables, include their short descriptions and file paths. If there are any metrics, url or quantitative results, include them, too.
If the deliverable is code, only output the file path.
Recommend three potential improvements that are easiest to achieve for the next steps, kindly ask users for their preference.
"""

DETECT_LANGUAGE_PROMPT = """
The requirement is:
{requirement}

Which Natural Language must you respond in?
Output only the language type.
"""
