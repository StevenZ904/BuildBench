import os
import argparse
import json
from time import time
from agents import Agent
from default_values import DEFAULT_VALUES
API_KEY = os.environ.get("API_KEY")
SUDO_PASSWORD = os.environ.get("SUDO_PASSWORD")
MODEL_NAME = os.environ.get("MODEL_NAME")   
TIMEOUT_BASH = int(os.environ.get("TIMEOUT_BASH", "300"))
AGENTS_NUMBER = int(os.environ.get("AGENTS_NUMBER", "2"))
RETRIEVAL = os.environ.get("RETRIEVAL")
if RETRIEVAL == 'True':
    RETRIEVAL = True
else:
    RETRIEVAL = False
PERFECT_RETRIEVAL = os.environ.get("PERFECT_RETRIEVAL")
if PERFECT_RETRIEVAL == 'True' and RETRIEVAL:
    PERFECT_RETRIEVAL = True
else:
    PERFECT_RETRIEVAL = False
    
RAG_RETRIEVAL = os.environ.get("RAG_RETRIEVAL")
if RAG_RETRIEVAL == 'True' and RETRIEVAL:
    RAG_RETRIEVAL = True
else:
    RAG_RETRIEVAL = False

CORES = DEFAULT_VALUES["CORES"]
REFINE_TIMES = int(os.environ.get("REFINE_TIMES", "1"))
MAX_TURNS = os.environ.get("MAX_TURNS", "10")
def initialize_agents():
    agent = Agent(
        human_in_loop = DEFAULT_VALUES["HUMAN_IN_LOOP"],
        model_name = MODEL_NAME,
        max_tokens = DEFAULT_VALUES["MAX_TOKENS"],
        api_key = API_KEY,
        operating_system = DEFAULT_VALUES["OPERATING_SYSTEM"],
        silent = DEFAULT_VALUES["SILENT"],
        max_turns = MAX_TURNS,
        temperature = DEFAULT_VALUES["TEMPERATURE"],
        sudo_password = SUDO_PASSWORD,
        if_docker_executor=DEFAULT_VALUES["IF_DOCKER_EXECUTOR"],
        docker_image=DEFAULT_VALUES["DOCKER_IMAGE"], # used for docker executor
        timeout_bash = TIMEOUT_BASH,
        timeout_llm = DEFAULT_VALUES["TIMEOUT_LLM"],
        # project_dir=DEFAULT_VALUES["COMPILED_DIR"], 
        agents_number=AGENTS_NUMBER,
        retrieval=RETRIEVAL,
        perfect_retrieval=PERFECT_RETRIEVAL,
        RAG_retrieval=RAG_RETRIEVAL,
    )
    print('Agents initialized...\n')
    return agent

def parse_args():
    parser = argparse.ArgumentParser(description='Multi-LLM Compilation Agent')
    # parser.add_argument('--repo_name', type=str, help='Name of the repository')
    parser.add_argument('--repo_url', type=str, help='GitHub repository to clone and compile')
    parser.add_argument('--compiled_dir', type=str, help='Directory to save the compiled files')
    return parser.parse_args()  


def main(args):
    github_repo = args.repo_url
    agent = initialize_agents()
    start_time = time()
    print(f'Compiling {github_repo}...')
    print(f"Using the following parameters: {CORES} cores, {REFINE_TIMES} refine times")
    agent.compile_repo(
        repo_url = github_repo,
        optimization_level = DEFAULT_VALUES["OPTIMIZATION_LEVEL"],
        compiled_dir = args.compiled_dir,
        log_dir = DEFAULT_VALUES["LOG_DIR"],
        # venv_dir = DEFAULT_VALUES["VENV_DIR"],
        print_cost = DEFAULT_VALUES["PRINT_COST"],
        cores = CORES,
        refine_times=REFINE_TIMES,
    )
    print(f'Compilation completed for {github_repo}, took {time() - start_time} seconds.')
    
    
    

if __name__ == '__main__':

    repo_args = parse_args()
    assert repo_args.repo_url is not None, "Please provide the URL of the repository"
    
    ### TODO: the path of args.json is hardcoded for docker container; Change it for compatibility with local machine
    
    # with open('/app/src/args.json', 'r') as f:
    #     args_dict = json.load(f)
    # args = argparse.Namespace(**args_dict)
    # args.log_dir = os.path.join(args.project_dir, args.log_dir)
    # args.venv_dir = os.path.join(args.project_dir, args.venv_dir)
    github_repo = repo_args.repo_url
    main(repo_args)