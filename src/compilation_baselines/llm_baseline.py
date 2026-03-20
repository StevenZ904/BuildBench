import os
import sys
import json
import docker
import time
from datetime import datetime
from tqdm import tqdm
from pathlib import Path
from tools import *
from utils import *
from compilation_base import compilation_base
from openai import OpenAI
from google import genai

from dotenv import load_dotenv
load_dotenv()
API_KEY= os.getenv("API_KEY")
MODEL_NAME= os.getenv("MODEL_NAME")
print(f"Using MODEL_NAME: {MODEL_NAME}")

HUGGINGFACE_BASE_URL = "https://router.huggingface.co/v1"
GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/'

class llm_baseline(compilation_base):
    '''
    This class implements the LLM Baseline compilation strategy, which will do a one shot llm generation of bash commands and run it in the docker. 
    
    Input to LLM:
    1. The repo name
    2. The root directory of the repo
    3. The README content
    '''
    def __init__(self, repo_dir, repo_full_name, container_image, repo_logs_dir, repo_binaries_dir, cloned_repos_dir, compiled_repos_dir, src_dir, docker_env_vars, **kwargs):
        super().__init__(repo_dir, repo_full_name, container_image, repo_logs_dir, cloned_repos_dir, compiled_repos_dir, src_dir, docker_env_vars,repo_binaries_dir,**kwargs)
        self.logger.info(f"LLM Baseline initialized for {self.repo_full_name}.")


        
    def _llm_prompt(self, repo_full_name, repos_dir_in_docker, readme_content, files_in_root_dir ) -> str:
        """
        Compose the system‑prompt that we’ll send to the LLM.
        The placeholders in curly‑braces are filled by _prepare_input().
        """
        prompt_base = f"""
            You are an expert Linux build engineer working inside a **Ubuntu‑based Docker container**. 


            ### Your task
            Generate a **sequence of Bash commands** (one command per line, no comments, no explanations) that will:

            1. Install every build‑time dependency needed to compile the repository **{repo_full_name}** that lives at **{repos_dir_in_docker}**.  
            • Use non‑interactive `apt-get update && apt-get install -y …` when possible.  
            • Avoid PPAs unless strictly necessary.  
            • Assume you run as root, so no `sudo` is required.
            
            2. **Configure debug build:**  
            Configure the build system in Debug mode (i.e., include DWARF symbols, disable optimizations).  
            
            3. **Install the main binary:**  
            Identify the primary or main binary (for example, the one built from the project’s main executable) and install it into {repos_dir_in_docker} 
            - Ensure the installation directory exists (create it if necessary with `mkdir -p`).
            - Copy the main binary into that directory and set executable permissions if needed.

            ### Strict requirements:
            * **Output only Bash commands, seperated using the newline character.**  
            Do not provide any explanations, markdown, or extra comments and do not wrap.
            * The commands must be **fully sequential and ready-to-run** when concatenated.  
            There should be no interactive prompts or assumptions beyond what is provided.
            * All steps must run successfully in a typical Docker Ubuntu environment.
            * Assume the current working directory is ** "/app" **.

            ### Repository context
            **Repo name:** {repo_full_name}  
            **Root path in container:** {repos_dir_in_docker}

            **README:**
            {readme_content}

            **Top‑level file list:**  
            {files_in_root_dir}

            ### Produce the Bash commands now:
            """
        return prompt_base

    
    def _prepare_input(self):
        readme_full_path, readme_content = get_readme_path(build_tools_dict=None, repo_dir=self.repo_dir)
        files_in_repo_dir = os.listdir(self.repo_dir)
        # with open("/app/src/compilation_baselines/Dockerfile_compilation", "r") as f:
        #     docker_file_content = f.read()
        llm_input = self._llm_prompt(
            repo_full_name = self.repo_full_name, repos_dir_in_docker = self.container_compiled_repos_dir, 
            readme_content = readme_content, files_in_root_dir = files_in_repo_dir ) 
    
        return llm_input


    def create_client(self, model_name, system_prompt, input):
        if 'gpt' in str(model_name).lower() or 'o3' in str(model_name).lower() or 'o4' in str(model_name).lower():
            client = OpenAI(
                api_key=API_KEY,
            )
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input},
                ],
            )
            output = response.choices[0].message.content   
        
        elif 'claude' in str(model_name).lower():
            client = OpenAI(
                api_key=API_KEY,
                base_url="https://api.anthropic.com/v1/"  # Anthropic's API endpoint
            )
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input},
                ],
            )
            output = response.choices[0].message.content
        
        elif 'qwen' in str(model_name).lower():
            client = OpenAI(api_key=API_KEY,
                    base_url=HUGGINGFACE_BASE_URL)
            
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input}
                ],
            )
            output = completion.choices[0].message.content
            
        elif 'gemini' in str(model_name).lower():
            client = genai.Client(api_key=API_KEY)
            response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=system_prompt + input,
            )
            output = response.text
        else: 
            raise ValueError(f"Unsupported model: {model_name}")
            
        
        return output

    def compile_in_container(self, github_repo, repo_name, cloned_repos_dir, compiled_repos_dir, logger, compilation_script_path=None, **kwargs):
        try:
            remove_and_copy_directory_wrapper(
                container=None, 
                repo_name=repo_name,
                cloned_repos_path=cloned_repos_dir,
                compiled_repos_path=compiled_repos_dir,
                logger=logger,
            )
            
            ### Setup docker client
            self.docker_client = docker.from_env()
            self.container = self.initlize_docker_container()
            
            ### Get the llm generated bash commands
            llm_input = self._prepare_input()
            # logger.info(f"LLM input: {llm_input}")
            
            raw_output = self.create_client(
                model_name=MODEL_NAME,
                system_prompt="You are a helpful assistant that helps software engineers to compile open source repositories by generating bash commands.",
                input=llm_input
            )
            logger.info(f"LLM output: {raw_output}")
            # … after you’ve fetched raw_output …
            raw_script = raw_output.strip()

            # Build a single shell command:
            # 1. cd into the repo’s folder
            # 2. turn on “exit on error” (set -e)
            # 3. run everything from the LLM in one go
            script = f"""
            set -e
            {raw_script}
            """

            logger.info("Executing unified script")

            # Execute it once
            result = self.container.exec_run(
                ["/bin/sh", "-c", script],
                demux=True
            )

            out, err = result.output or (b"", b"")
            stdout = out.decode("utf-8", errors="replace")
            stderr = err.decode("utf-8", errors="replace")
            return_code = result.exit_code

            logger.info(f"Script stdout: {stdout}")
            if stderr:
                logger.error(f"Script stderr: {stderr}")
            logger.info(f"Script return code: {return_code}")

            self.stop_and_remove_container()

            if return_code == 0:
                logger.info("All commands executed successfully.")
                return True
            else:
                logger.error("Script failed with non‑zero exit code.")
                return False
            
        except Exception as e:
            logger.error(f"Compilation failed for {repo_name}: {e}")
            return False
            

if __name__ == "__main__":
    # Example usage
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
    repo_full_name = "taviso/ctypes.sh"
    container_image = "compilation_base_image:latest"
    docker_env_vars = {"ENV_VAR": "value"}

    input_file_path = os.path.join(BASE_DIR, 'data', 'sampled_repos_385_cleaned_higher_split.jsonl')
    docker_image = 'compilation_base_image:latest'
    repo_logs_dir = os.path.join(BASE_DIR, 'logs', 'llm_baseline')
    cloned_repos_dir = os.path.join(BASE_DIR, 'cloned_repos')
    compiled_repos_dir = os.path.join(BASE_DIR, 'compiled_repos', 'llm_baseline')
    repo_binaries_dir = os.path.join(BASE_DIR, 'compiled_repos', 'llm_baseline', 'binaries')
    src_dir = os.path.join(BASE_DIR, 'src', 'compilation_baselines')
    compiled_results_dir = os.path.join(BASE_DIR, 'compiled_results', 'llm_baseline')

    repo_dir = compiled_repos_dir
    llm_compiler = llm_baseline(repo_dir, repo_full_name, container_image, repo_logs_dir, repo_binaries_dir, cloned_repos_dir, compiled_repos_dir, src_dir, docker_env_vars)
    llm_compiler.run()