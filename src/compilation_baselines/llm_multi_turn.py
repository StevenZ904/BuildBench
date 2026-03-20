import os
import sys
import json
import docker
import time
from datetime import datetime
from tqdm import tqdm
import shlex

from tools import *
from utils import *
from compilation_base import compilation_base

MAX_TURN = 10

def update_cwd(prev_cwd: str, cd_arg: str) -> str:
    """
    Resolve a Bash‑style `cd` argument against the previous directory.

    * `cd /abs/path`         → /abs/path
    * `cd ..`                → parent
    * `cd dir`               → prev_cwd/dir   (if relative)
    * `cd ~` or `cd`         → $HOME (assume /root)
    * `cd -`                 → prev_cwd  (Bash swaps OLDPWD, we keep same)
    """
    cd_arg = cd_arg.strip()

    if cd_arg in ("", "~"):
        return "/root"  # container default
    if cd_arg == "-":
        return prev_cwd
    if os.path.isabs(cd_arg):
        return os.path.normpath(cd_arg)
    return os.path.normpath(os.path.join(prev_cwd, cd_arg))

class llm_multi_turn(compilation_base):
    '''
    This class implements a multi-turn LLM Baseline compilation strategy, which will do a multi-shot llm generation of bash commands with proper feedback from previous execution errors and run it in the docker. 
    
    Input to LLM:
    1. The repo name
    2. The root directory of the repo
    3. The README content
    '''
    def __init__(self, repo_dir, repo_full_name, container_image, repo_logs_dir, repo_binaries_dir, cloned_repos_dir, compiled_repos_dir, src_dir, docker_env_vars, max_turn = MAX_TURN, search_internet = False, **kwargs):
        super().__init__(repo_dir, repo_full_name, container_image, repo_logs_dir, cloned_repos_dir, compiled_repos_dir, src_dir, docker_env_vars,repo_binaries_dir,**kwargs)
        self.max_turn = max_turn
        self.search_internet = search_internet
        self.logger.info(f"Multi-turn LLM Baseline initialized for {self.repo_full_name}.")
        if self.search_internet:
            self.logger.info(f"Internet search is enabled.")

    
    
    
    def _llm_prompt(self, repo_full_name, repos_dir_in_docker, readme_content, files_in_root_dir ) -> str:

        
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
            Do not provide any explanations, markdown, or extra comments.
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

            """
            
        if self.search_internet:
            search_result = search_online_using_tavily(self.repo_full_name)
            if search_result:
                prompt_base += f"""
                ** Build instructions results from searching the internet:
                {search_result}
                """
        return prompt_base

    
    def _prepare_system_prompt(self):
        readme_full_path, readme_content = get_readme_path(build_tools_dict=None, repo_dir=self.repo_dir)
        files_in_repo_dir = os.listdir(self.repo_dir)
        dockerfile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dockerfile_compilation")
        with open(dockerfile_path, "r") as f:
            docker_file_content = f.read()
        llm_input = self._llm_prompt(
            repo_full_name = self.repo_full_name, repos_dir_in_docker = self.container_compiled_repos_dir, 
            readme_content = readme_content, files_in_root_dir = files_in_repo_dir ) 
    
        return llm_input

    def _prepare_user_prompt(self, refine = False, previous_commands = None, error_commands = None, execution_result = None, successfully_executed_commands = None):
        if refine:
            user_prompt = f"""
            The previously generated commands are {previous_commands}.
            A cumulative list of successfully executed commands is {successfully_executed_commands}. So you can assume that these commands has been executed successfully.
            The following command was generated but failed to execute successfully:
            {error_commands}
            The execution output is:
            {execution_result}
            Please analyze the error and the previous commands, and provide a refined set of commands to build {self.repo_name} from source in the docker container. Please reply with only the commands, no explanations or comments.
            """
        else:
            user_prompt = f"""
            Based on the information, now generate the commands to build {self.repo_name} from source in the docker container.
            """
            
        return user_prompt
        

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
            system_prompt = self._prepare_system_prompt()
            logger.info(f"System_prompt: {system_prompt}")
            user_prompt = self._prepare_user_prompt(refine=False)
            
            successfully_executed_commands = set()
            for i in range(self.max_turn):
                error_cmd = None
                error_msg = None
                successfully_executed_commands_in_this_turn = []
                
                logger.info(f"---LLM turn: {i+1}/{self.max_turn} ----")
                logger.info(f"User_prompt: {user_prompt}")

                response = openai_client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                raw_output = response.choices[0].message.content
                logger.info(f"LLM output: \n{raw_output}\n")
                
                raw_script = raw_output.strip()
                
                # Figure out the container's *current* directory (usually /, but don't guess)                    
                
                init_cwd = (
                    self.container.exec_run(["/bin/bash", "-c", "pwd"], demux=True).output[0]
                    .decode()
                    .strip()
                    or "/"
                )
                
                cwd = init_cwd
                
                # Normalise: drop blank lines / comments, keep order
                commands = [
                    ln.strip()
                    for ln in raw_script.strip().splitlines()
                    if ln.strip() and not ln.lstrip().startswith("#")
                ]
                
                commands_count = 0
                
                for cmd in commands:
                    # If the line is ONLY a `cd …`, remember it and *do not* wrap it again
                    parts = shlex.split(cmd, posix=True)
                    if parts and parts[0] == "cd" and len(parts) <= 2:
                        # (len==1 handles plain `cd`)
                        cd_arg = parts[1] if len(parts) == 2 else ""
                        # Execute the cd inside the container first
                        full = f"cd {shlex.quote(cwd)} && cd {shlex.quote(cd_arg)}"
                        result = self.container.exec_run(["/bin/bash", "-c", full], demux=True)
                        if result.exit_code != 0:
                            stderr = (result.output[1] or b"").decode("utf-8", "replace")
                            error_cmd = full
                            error_msg = stderr
                            logger.error(f"Bash Command execution failed for {full}")
                            logger.error(f"Error Message: {stderr}")
                            break
                            
                        cwd = update_cwd(cwd, cd_arg)
                        successfully_executed_commands_in_this_turn.append(cmd)
                        commands_count += 1
                        continue
                    
                    # Ordinary command → run it from the *current* cwd
                    full_cmd = f"cd {shlex.quote(cwd)} && set -eo pipefail && {cmd}"
                    result = self.container.exec_run(["/bin/bash", "-c", full_cmd], demux=True)

                    if result.exit_code != 0:
                        stderr = (result.output[1] or b"").decode("utf-8", "replace")
                        error_cmd = full_cmd
                        error_msg = stderr
                        logger.error(f"Bash Command execution failed for {full_cmd}")
                        logger.error(f"Error Message: {stderr}")
                        break

                    successfully_executed_commands_in_this_turn.append(cmd)
                    commands_count += 1
             
                # -- successfully executed all commands in this turn --
                if commands_count == len(commands):
                    # All commands executed successfully
                    logger.info("All commands executed successfully.")
                    return True


                # ── failed: refine prompt and loop again ────────────
                successfully_executed_commands.update(successfully_executed_commands_in_this_turn)
                
                user_prompt = self._prepare_user_prompt(
                    refine=True,
                    previous_commands=raw_output,
                    error_commands=error_cmd,
                    execution_result=error_msg,
                    successfully_executed_commands=successfully_executed_commands,
                )

            logger.info(
                "Giving up – compilation considered failed "
                f"after {self.max_turn} turns"
            )
            return False

        except Exception as exc:
            logger.exception(f"Compilation failed for {repo_name}: {exc}")
            return False

        finally:
            # always tear down the container
            try:
                self.stop_and_remove_container()
            except Exception:
                logger.warning("container cleanup failed", exc_info=True)
            

if __name__ == '__main__':
    # Example usage
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
    repo_full_name='curl/curl'
    container_image='compilation_base_image:latest'
    repo_logs_dir = os.path.join(BASE_DIR, 'logs', 'llm_multi_turn')
    repo_binaries_dir = os.path.join(BASE_DIR, 'compiled_repos', 'llm_multi_turn', 'binaries')
    cloned_repos_dir = os.path.join(BASE_DIR, 'cloned_repos')
    compiled_repos_dir = os.path.join(BASE_DIR, 'compiled_repos', 'llm_multi_turn')
    src_dir = os.path.join(BASE_DIR, 'src', 'compilation_baselines')
    docker_env_vars={}
    max_turn=3
    compiled_repo_dir = os.path.join(compiled_repos_dir, 'curl')
    os.makedirs(compiled_repo_dir, exist_ok=True)

    example_instance = llm_multi_turn(
        repo_dir=compiled_repo_dir,
        repo_full_name=repo_full_name,
        container_image=container_image,
        repo_logs_dir=repo_logs_dir,
        repo_binaries_dir=repo_binaries_dir,
        cloned_repos_dir=cloned_repos_dir,
        compiled_repos_dir=compiled_repos_dir,
        src_dir=src_dir,
        docker_env_vars=docker_env_vars,
        max_turn=max_turn,
    )
    result = example_instance.run()
    print(result)