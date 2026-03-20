import os
import json
import sys
import docker
import shutil
import subprocess

from datetime import datetime
from tqdm import tqdm
from flutes.run import run_command
from validation_pipeline import validation_pipeline
from tools import setup_logger, remove_and_copy_directory_wrapper, copy_directory_from_container, clone_repository, parse_args, get_target_github_repos 
ELF_FILE_TAG = b"ELF"  # Linux

class compilation_base():
    def __init__(self, repo_dir, repo_full_name, container_image, repo_logs_dir, cloned_repos_dir, compiled_repos_dir, src_dir, docker_env_vars, binary_repos_dir, **kwargs):
        self.repo_dir = repo_dir
        self.repo_name = os.path.basename(repo_dir)
        self.repo_full_name = repo_full_name
        self.experiment_start_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")   
        
        ### Setup directories
        self.cloned_repos_dir = os.path.join(cloned_repos_dir, self.repo_name)
        os.makedirs(self.cloned_repos_dir, exist_ok=True)
        self.compiled_repos_dir = os.path.join(compiled_repos_dir, self.repo_name)
        os.makedirs(self.compiled_repos_dir, exist_ok=True)
        self.repo_logs_dir = os.path.join(repo_logs_dir, self.repo_name)
        os.makedirs(self.repo_logs_dir, exist_ok=True)     
        self.binary_repo_dir = os.path.join(binary_repos_dir, self.repo_name)
        os.makedirs(self.binary_repo_dir, exist_ok=True)
        self.src_dir = src_dir
        
        self.logger = setup_logger(self.repo_name, self.repo_logs_dir, self.experiment_start_time)
        self.logger.info(f"Directories for {self.repo_full_name} are set up.")
        
        ### Setup container directories
        self.container_cloned_repos_dir = f'/app/cloned_repos/{self.repo_name}/'
        self.container_compiled_repos_dir = f'/app/compiled_repos/{self.repo_name}'
        self.container_src_dir = f'/app/src'
        self.container_all_logs_dir = f'/app/all_logs/'
        
        self.compilation_script_path = None
        
        self.container_image = container_image
        self.docker_env_vars = docker_env_vars


        self.logger.info(f"Starting compilation process for {self.repo_full_name}...")    
    
        
    def initlize_docker_container(self):
        container = self.docker_client.containers.run(
            image=self.container_image,
            command="tail -f /dev/null",
            detach=True,
            # auto_remove=True,
            working_dir="/app",
            volumes={
                self.src_dir: {"bind": self.container_src_dir, "mode": "ro"},
                self.cloned_repos_dir: {"bind": self.container_cloned_repos_dir, "mode": "ro"},
                self.compiled_repos_dir: {"bind": self.container_compiled_repos_dir, "mode": "rw"},
            },
            environment=self.docker_env_vars,
        )
        self.logger.info(f"Container started from image {self.container_image}.")
        return container 
        
    def find_binary_files_and_copy(self, compiled_repo_directory):
        ### This function credits to GHCC repo
        binary_file_paths = []
        
        output = run_command(["git", "ls-files", "--others"], cwd=compiled_repo_directory,return_output=True).captured_output
        assert output is not None
        diff_files = [
            # files containing escape characters are in quotes
            file if file[0] != '"' else file[1:-1]
            for file in output.decode('unicode_escape').split("\n") if file]  # file names could contain spaces

        # Inspect each file and find ELF files.
        for file in diff_files:
            if self._check_elf_fn(compiled_repo_directory, file):
                binary_file_paths.append(file)
        
        for path in binary_file_paths:
            full_path = os.path.join(compiled_repo_directory, path)
            shutil.copy(full_path, self.binary_repo_dir)
        
        self.logger.info(f"Copied {len(binary_file_paths)} binary files to {self.binary_repo_dir}.")
        
        return binary_file_paths
    
    
    def _check_elf_fn(self, directory: str, file: str) -> bool:
        r"""Checks whether the specified file is a binary file.

        :param directory: The directory containing the Makefile.
        :param file: The path to the file to check, relative to the directory.
        :return: If ``True``, the file is a binary (ELF) file.
        """
        path = os.path.join(directory, file)
        output = subprocess.check_output(["file", path], timeout=10)
        output = output[len(path):]  # first part is file name
        return ELF_FILE_TAG in output

    def run(self):
        try:
            result = self.compile_in_container(
                github_repo=f"https://github.com/{self.repo_full_name}",
                repo_name=self.repo_name,
                cloned_repos_dir=self.cloned_repos_dir,
                compiled_repos_dir=self.compiled_repos_dir,
                logger=self.logger,
                compilation_script_path=self.compilation_script_path,
            )
            if result:
                self.find_binary_files_and_copy(self.compiled_repos_dir)
        except Exception as e:
            self.logger.error(f"Function run failed for {self.repo_name}: {e}")
            result = False
        return result
    
    def stop_and_remove_container(self):
        if self.container:
            self.container.stop()
            self.container.remove(force=True)
            self.logger.info(f"Container {self.container.id} stopped and removed.")
        else:
            self.logger.warning("No container to stop or remove.")
    
    def compile_in_container(self, github_repo, repo_name, cloned_repos_dir,compiled_repos_dir, logger, compilation_script_path='/app/src/compilation.py', **kwargs):
        try:
            ### Setup docker client
            self.docker_client = docker.from_env()
            self.container = self.initlize_docker_container()
            
            # Execute compilation.py inside container
            # # make it async
            # _, stream = container.exec_run(
            #     cmd=f"find /usr/local /usr /opt -type f > /app/before_install.txt",
            #     workdir="/app/",
            #     stream=True  # Enable streaming
            # )
            _, stream = self.container.exec_run(
                cmd=f"/opt/venv/bin/python {compilation_script_path} --repo_url {github_repo} --compiled_dir={compiled_repos_dir}",
                workdir="/app/",
                stream=True  # Enable streaming
            )
            for data in stream:
                logger.info(data.decode('utf-8'))
            return True  # Indicate success
                
        except Exception as e:
            logger.error(f"Compilation failed for {repo_name}: {e}")
            return False  # Indicate failure
        
    