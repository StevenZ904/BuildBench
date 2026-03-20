import os
from dotenv import load_dotenv
load_dotenv()

# langsmith config
LANGCHAIN_TRACING_V2=os.environ.get("LANGCHAIN_TRACING_V2", "true")
LANGCHAIN_PROJECT=os.environ.get("LANGCHAIN_PROJECT")
LANGCHAIN_API_KEY= os.environ.get("LANGCHAIN_API_KEY")

SERPER_API_KEY=os.environ.get("SERPER_API_KEY")
LOG_URL_TEMPLATE=""

## Multi-Agent Discussion
# openai
OPENAI_BASE_URL=os.environ.get("OPENAI_BASE_URL")
OPENAI_MODEL=os.environ.get("OPENAI_MODEL")
OPENAI_EMBEDDING_MODEL=os.environ.get("OPENAI_EMBEDDING_MODEL")
OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY")

# claude
ANTHROPIC_BASE_URL=os.environ.get("ANTHROPIC_BASE_URL")
ANTHROPIC_MODEL=os.environ.get("ANTHROPIC_MODEL")
ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY")

# deepseek (MasterAgent and MultiAgentDiscussion)
DEEPSEEK_BASE_URL=os.environ.get("DEEPSEEK_BASE_URL")
DEEPSEEK_MODEL=os.environ.get("DEEPSEEK_MODEL")
DEEPSEEK_API_KEY=os.environ.get("DEEPSEEK_API_KEY")

PROXY=""
PASSWORD=os.environ.get("PASSWORD")

# logs
PROCESS_LOG_CSV_PATH=os.environ.get("PROCESS_LOG_CSV_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "process_log_csv"))
FLOW_BASED_LOG_CSV_PATH=os.environ.get("FLOW_BASED_LOG_CSV_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "flow_based_log_csv"))

# to compile projects
COMPILE_PROJECTS_PATH=""

# ========================== agent config ==========================
template = """You are an experienced software development engineer. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [ {tool_names} ]
Action Input: the input to the action, do not explain the input further
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)

Thought: I now know the final answer
Final Answer: the final answer to the original input question


Begin!
Question: {input}

Thought:{agent_scratchpad}"""


model_decision_template = """I want you to help me compile the project {project_name} from source code. Please complete the compilation task step by step.

The project has been downloaded into /work/, which is also the Shell's initial path.
You should follow these rules:
1. Use the Shell tool to execute any command for compilation, and it is recommended to use `tree . -L 2` command to show the project structure.
2. Use the CompileNavigator tool to looking for compilation instructions. Try to avoid reading documents in Shell tool, unless you think it's necessary.
3. If there are any difficulties during compilation, try to break them without calling tools.
4. Unless you encounter a problem that you cannot solve, there is no need to call the ErrorSolver tool.
5. No need to install this project or test it, just compile it.
6. Compilation target should be the main body of the project, for example, the executable programs for a tool-type project or the shared/static libraries for a library project.
7. When you've done your best, you need to check if the project actually compiled successfully and output COMPILATION-SUCCESS, COMPILATION-FAIL, or COMPILATION-UNCERTAIN as the final answer.
"""

discussion_template1="""You are an experienced compiler troubleshooting expert. Your task is to analyze provided error messages, identify likely causes, and deliver specific solutions. 

The entire compilation process was performed on Ubuntu 22.04 with root user.
the error messages during {project} compilation are as follows:
{input}

Unless you really don't know how to solve this problem, there is no need to call the following tools:
{tools}

Output the answer in JSON format as follows (Strict JSON, NO Additional Text):
{{
    "reasoning": "Concise explanation of problem-solving process",
    "solution": "Specific instructions, requiring conciseness, professionalism and accuracy(No additional relevant texts)",
    "confidence_level": <numeric confidence between 0.0 and 1.0>
}}

Begin!
"""

discussion_template2="""You are an experienced compiler troubleshooting expert. Your task is to analyze provided error messages, identify likely causes, and deliver specific solutions.

The entire compilation process was performed on Ubuntu 22.04 with root user.
the error messages during {project} compilation are as follows:
{input}

Unless you really don't know how to solve this problem, there is no need to call the following tools:
{tools}

Carefully review the following solutions from other agents as additional information, and provide your own answer. Clearly states that which pointview do you agree or disagree and why.
{chat_history}

Output the answer in JSON format as follows (Strict JSON, NO Additional Text):
{{
    "reasoning": "Concise explanation of problem-solving process",
    "solution": "Specific instructions, requiring conciseness, professionalism and accuracy(No additional relevant texts)",
    "confidence_level": <numeric confidence between 0.0 and 1.0>
}}

Begin!
"""

get_instructions_template="""You are an experienced software development engineer. I want you to help me find out the project {project_name} compilation instructions. Please complete the searching task step by step, use the tools provided if require (one tool each time).

Project structure: {project_structure}

You should follow these rules:
1. Analyze the given project structure and reference the document file which exists compilation instructions, and then use DEBATE tool to check it.
2. Use the SEARCH_INSTRUCTIONS_FROM_FILES tool to looking for compilation instructions within the file inferred in the previous step. 
3. If URLs are found, fetch their content using GET_CONTENT_FROM_URL.
4. Compile all information into clear compilation instructions, do not include test commands.
5. Keep the instructions concise, professional and accurate.
"""
