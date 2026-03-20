


import os
import glob
import logging
import subprocess
import signal
from typing import Tuple
from compilation_base import compilation_base
import docker
from tools import *
from utils import *

### The following codes are from the original Assemblage code : https://github.com/Assemblage-Dataset/Assemblage/blob/main/assemblage/worker/build_method.py
### We change the codes to include debug information and remove the unused code. Change will be noted.

def get_build_system(files):
    """Analyze build tool from file list"""
    build_systems = {"make": ["makefile"],
                     "cmake": ["cmakelists.txt"],
                     #  "travisci": [".travis.yml"],
                     #  "circleci": ["config.yml"],
                     #  "rake": ["rakefile"],
                    #  "sln": [".sln"],
                     "configure": ["configure"],
                     #  "java": ["build.gradle", "gradlew", "pom.xml"],
                     #  "ninja": ["ninja", "build.ninja"],
                      "bootstrap": ["bootstrap"]
                     }
    build_tools_list = []
    for fname in files:
        for build_tool, file_keywords in build_systems.items():
            for file_keyword in file_keywords:
                if file_keyword in fname.strip().lower():
                    build_tools_list.append(build_tool)
    build_tools = list(set(build_tools_list))
    if len(build_tools_list) == 0:
        return "others"
    else:
        return "/".join(build_tools)



def run_build(
            repo,
            target_dir,
            build_mode,
            library,
            optimization,
            slnfile=None,
            platform='linux',
            compiler_version='v142',
            logger=None, ### Introduced to log the build process
            ):
    """ Generate cmd to execute """
    # if platform.lower() == 'windows':
    #     cmd = ["powershell", "-Command", "msbuild"]
    #     if build_mode in ["Release", "Debug"]:
    #         cmd.append(f"/property:Configuration={build_mode}")
    #     if library == "x86" or library == "x86":
    #         cmd.append("/property:Platform=x86")
    #     elif library == "x64":
    #         cmd.append("/property:Platform=x64")
    #     elif library == "Mixed Platforms":
    #         cmd.append("/property:Platform='Mixed Platforms'")
    #     elif library == "Any CPU":
    #         cmd.append("/p:Platform=Any CPU")
    #     # cmd.append(f"/p:PlatformToolset={compiler_version}")
    #     if compiler_version in ["v140", "v141"]:
    #         cmd.append("/p:WindowsTargetPlatformVersion= ")
    #     cmd.append("/maxcpucount:16")
    #     cmd.append("/property:PostBuildEvent= ")
    #     cmd.append("/property:OutDir=assemblage_outdir_bin/")
    #     cmd.append(f"'{slnfile}'")
    #     cmd = " ".join(cmd)
    #     logging.info("Windows cmd generated: %s", cmd)
    #     return cmd_with_output(cmd, 600, platform)
    if platform.lower() == 'linux':
        cflags = 'CFLAGS="-O0 -g" CXXFLAGS="-O0 -g"' ### Added to include debug information

        files = []
        print(f"target_dir: {target_dir}")
        pattern = os.path.join(target_dir, '**', '*')
        print("files in the directory:")   
        print(os.listdir(target_dir))
        ### This is the original code to get all files in the directory
        # But it would undermine the performance, as it will search all files in the directory, and the wrong build system will be detected.
        # for filename in glob.iglob(pattern, recursive=True):
        #     files.append(os.path.basename(filename))
        files = os.listdir(target_dir)
        build_tool = get_build_system(files)
        
        if len(build_tool) == 0:
            logger.error("No build tool found in the repository.")
            return None
        
        cmd = ""
        if 'bootstrap' in build_tool:
            cmd = (
                f'cd {target_dir} && ./bootstrap && '
                f'{cflags} bash ./configure && '
                'make -j4'
            )
        elif 'configure' in build_tool:
            cmd = (
                f'cd {target_dir} && '
                f'{cflags} bash ./configure && '
                'make -j4'
            )
        elif 'cmake' in build_tool:
            cmd = (
                f'cd {target_dir} && '
                f'cmake -Bbuild -DCMAKE_BUILD_TYPE=Debug '
                f'-DCMAKE_C_FLAGS_DEBUG="-O0 -g" '
                f'-DCMAKE_CXX_FLAGS_DEBUG="-O0 -g" ./ && '
                'cd build && make -j4'
            )
        elif 'make' in build_tool:
            cmd = (
                f'cd {target_dir} && '
                f'{cflags} make -j4'
            )
        return cmd

####### The start of our code #######

class Assemblage(compilation_base):
    """ Assemblage class """
    def __init__(self, repo_dir, repo_full_name, container_image, repo_logs_dir, repo_binaries_dir, cloned_repos_dir, compiled_repos_dir, src_dir, docker_env_vars, **kwargs):
        
        super().__init__(repo_dir, repo_full_name, container_image, repo_logs_dir, cloned_repos_dir, compiled_repos_dir, src_dir, docker_env_vars,repo_binaries_dir,**kwargs)
        self.logger.info(f"Assemblage initialized for {self.repo_full_name}.")
        
    def compile_in_container(self, github_repo, repo_name, cloned_repos_dir, compiled_repos_dir, logger, compilation_script_path=None, **kwargs):
        try:
            remove_and_copy_directory_wrapper(
                container=None, 
                repo_name=repo_name,
                cloned_repos_path=self.cloned_repos_dir,
                compiled_repos_path=self.compiled_repos_dir,
                logger=logger,
            )                        
            ### Setup docker client
            self.docker_client = docker.from_env()
            self.container = self.initlize_docker_container()

            assemblage_generated_cmd = run_build(
                repo=repo_name,
                target_dir=self.cloned_repos_dir,
                build_mode="None",
                library="None",
                optimization="O0",
                slnfile=None,
                platform='linux',
                compiler_version='None',
                logger=logger,
            )
            
            if not assemblage_generated_cmd:
                raise ValueError("No build command generated.")
            
            assemblage_generated_cmd = assemblage_generated_cmd.replace(self.cloned_repos_dir, self.container_compiled_repos_dir)  # Replace single quotes with double quotes
            logger.info(f"Generated command: {assemblage_generated_cmd}")
            
            script = f"""
            set -euxo pipefail
            {assemblage_generated_cmd}
            """
            
            result = self.container.exec_run(
                ["bash", "-c", script],
                demux=True
            )


            # Safely unpack stdout and stderr from exec_run
            output = result.output
            if isinstance(output, tuple):
                out_bytes, err_bytes = output
            else:
                out_bytes, err_bytes = output, None

            # Provide empty bytes fallback
            out_bytes = out_bytes or b""
            err_bytes = err_bytes or b""

            stdout = out_bytes.decode("utf-8", errors="replace")
            stderr = err_bytes.decode("utf-8", errors="replace")
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
            self.stop_and_remove_container()
            return False