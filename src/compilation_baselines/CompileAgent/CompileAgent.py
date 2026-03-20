import multiprocessing.pool
import os
import csv
import json
import uuid
import shutil
import logging
import datetime
import subprocess
import httpx
import itertools
import multiprocessing
import pandas as pd
from langchain.agents import create_react_agent
from langchain.agents import AgentExecutor,Tool
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain import hub
from langchain.prompts import PromptTemplate
import argparse
import click

from Tools import InteractiveDockerShell, SearchCompilationInstruction
from CustomAgentExecutor import CompilationAgentExecutor
from MultiAgentGetInstructions import CompileNavigator
from MultiAgentDiscussion import ErrorSolver
from DownloadProject import download_project, copy_project
from Logs import is_compiled, save_logs
from Config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')
logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('chromadb').setLevel(logging.ERROR)

os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT

prompt = PromptTemplate.from_template(template)
question_template = model_decision_template

def start_compile(dataset_base_path,log_path,clean_copied_project,download_proxy,strict_checker,retry,projects):
    DATASET_BASE_PATH = None
    if os.environ.get("DATASET_BASE_PATH"):
        DATASET_BASE_PATH = os.environ.get("DATASET_BASE_PATH")
    if dataset_base_path:
        DATASET_BASE_PATH = dataset_base_path
    if not DATASET_BASE_PATH:
        DATASET_BASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),"dataset")
    if not os.path.exists(DATASET_BASE_PATH):
        os.makedirs(DATASET_BASE_PATH)

    COMPILED_REPOS_PATH = os.path.join(os.path.dirname(os.path.abspath(DATASET_BASE_PATH)), 'compiled_repos')
    if not os.path.exists(COMPILED_REPOS_PATH):
        os.makedirs(COMPILED_REPOS_PATH)

    print(f"[+] Dataset base path: {DATASET_BASE_PATH}")
    print(f"[+] Compiled repos path: {COMPILED_REPOS_PATH}")
    
    if download_proxy != None:
        download_proxy=PROXY

    for info in projects:
        proj_name = info["name"]
        for _ in range(retry+1):
            url = info["url"]
            files = info.get("files",None)
            cloned_repo_path = info.get("local_path",os.path.join(DATASET_BASE_PATH,proj_name))
            compiled_repo_path = os.path.join(COMPILED_REPOS_PATH,proj_name)
            if not os.path.exists(cloned_repo_path) or not os.listdir(cloned_repo_path): # if the project path is not exist or is empty
                download_project(url,cloned_repo_path,download_proxy)
            # copy new project path for compilation
            compiled_repo_path = copy_project(cloned_repos_path=cloned_repo_path, compiled_repos_path=compiled_repo_path)
            os.environ["LOCAL_PATH"] = compiled_repo_path

            llm = ChatOpenAI(
                base_url=OPENAI_BASE_URL,
                model=OPENAI_MODEL,
                api_key=OPENAI_API_KEY,
                temperature=1,
                timeout=120
                # http_client=httpx.Client(proxies=PROXY) if PROXY else None
            )
            with InteractiveDockerShell(local_path=compiled_repo_path,cmd_timeout=1200,use_proxy=False) as shell:
                # define tools
                GetIns = CompileNavigator(local_path=compiled_repo_path, project_name=proj_name)
                Dis = ErrorSolver(project_name=proj_name)
                tools = [
                    Tool(
                        name="Shell",
                        description=shell.execute_command.__doc__,
                        func=shell.execute_command
                    ),
                    Tool(
                        name="CompileNavigator",
                        description=GetIns.get_instructions.__doc__,
                        func=GetIns.get_instructions
                    ),
                    Tool(
                        name="ErrorSolver",
                        description=Dis.discussion.__doc__,
                        func=Dis.discussion
                    )
                ]
                # define agent
                agent = create_react_agent(llm=llm,tools=tools,prompt=prompt)
                agent_executor = CompilationAgentExecutor(agent=agent,tools=tools,verbose=True,return_intermediate_steps=True,max_iterations=30,handle_parsing_errors=True)

                res = {}
                question = question_template.format(project_name=proj_name)
                try:
                    for step in agent_executor.iter({"input":question},include_run_info=True):
                        if "intermediate_step" in step:
                            pass
                        else:
                            res = {
                                "final_answer" : step["output"],
                                "intermediate_steps" : step["intermediate_steps"],
                                "output" : step["messages"][0].content,
                                "run_id" : str(step["__run"].run_id)
                            }
                            if not res["output"]:
                                res["output"] = res["final_answer"]
                    checker_ok = is_compiled(compiled_repo_path, files, strict=strict_checker)
                    checker_ok = f"{str(checker_ok)}(strict={str(strict_checker)})"
                except Exception as e:
                    print(res)
                    logging.error(f"[!] Compilation failed with error: {e}")
                    checker_ok = f"False(strict={str(strict_checker)})"
                
                final_answer = (res or {}).get("final_answer", "")

                if "COMPILATION-SUCCESS" in final_answer:
                    model_ok = "True"
                elif "COMPILATION-UNCERTAIN" in final_answer:
                    model_ok = "UNCERTAIN"
                else:
                    model_ok = "False"

                logging.info("[-] Project {}, model result: {}, checker result: {}, path: {}".format(proj_name,model_ok,checker_ok,compiled_repo_path))

                if clean_copied_project:
                    # shutil.rmtree(compiled_repo_path)
                    cmd = f"echo {PASSWORD} | sudo -S rm -rf {compiled_repo_path}"
                    # cmd = f'rm -rf {compiled_repo_path}'
                    subprocess.run(cmd,shell=True)
                    logging.info(f"[+] Cleared project compilation path {compiled_repo_path}")

                tools_log = {
                    "Shell":shell.logger,
                    "CompileNavigator":GetIns.logger,
                    "ErrorSolver":Dis.logger
                }

                save_logs(log_path,proj_name,question,tools,res,tools_log,compiled_repo_path,checker_ok,model_ok)

            if checker_ok.startswith("False"):
                continue
            else:
                break


@click.command()
@click.option('-j', '--json_path', type=str, required=True,
              help='the path to the project file to be compiled')
@click.option('-p', '--dataset_base_path', type=str, required=True,
              help='the base path to store the projects need to compile')
@click.option('-l', '--log_path', type=str, required=True, 
               help='the path to store the logs of compilation')
@click.option('-c', '--clean_copied_project', type=bool, required=True, 
              help='whether to clear the new project path after the compilation, set to True when debugging')
@click.option('-r', '--retry', type=int, default=0,
              help='the times to retry when fail to pass checker')
@click.option('-s', '--strict_checker', type=bool, default=False,
              help='if True, only return True when all target files are in the file list, otherwise return True when any target file is in the file list')
@click.option('--download_proxy', type=str, 
              help='pass to git --config http.proxy=${}, e.g., socks5://127.0.0.1:29999, if do not set: do not use proxy')
@click.option('--multi_process', type=bool, default=False, 
              help='whether to enable the multi-process to compile the projects')
def main(json_path,dataset_base_path,log_path,clean_copied_project,download_proxy,strict_checker,retry,multi_process):
    '''
    Compile the projects from source code with the help of AI assistant
    '''
    with open(json_path, 'r') as fp:
        projects = json.load(fp)

    base_tuple=(dataset_base_path,log_path,clean_copied_project,download_proxy,strict_checker,retry)
    if multi_process:
        args = [base_tuple+([project],) for project in projects]
        with multiprocessing.Pool(processes=len(projects)) as pool:
            pool.starmap(start_compile, args)
    else:
        args = base_tuple+(projects,)
        start_compile(*args)

    # merge csv_data
    merge_data = []
    for filename in os.listdir(PROCESS_LOG_CSV_PATH):
        if filename.endswith(".csv") and filename[:-4].isdigit():
            file_path = os.path.join(PROCESS_LOG_CSV_PATH,filename)
            with open(file_path,"r") as fp:
                csv_reader = csv.reader(fp)
                csv_data = list(csv_reader)  
                merge_data.append(csv_data)
            # os.system(f"rm {file_path}")

    with open(f"{log_path}/statistics.csv","a") as fp:
        csv_writer = csv.writer(fp)
        for data in merge_data:
            for row in data:
                csv_writer.writerow(row)



if __name__ == "__main__":
    main()