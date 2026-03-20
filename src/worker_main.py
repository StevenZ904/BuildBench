import os
import sys
import pandas as pd
from tqdm import tqdm
import json
from time import time, sleep
import datetime
import shutil
import subprocess
from default_values import DEFAULT_VALUES
from validation_pipeline import validation_pipeline
from tools import setup_logger, remove_and_copy_directory_wrapper, create_tarball, extract_tarball_subprocess, clone_repository

job_index = int(os.environ["JOB_INDEX"])

# The configMap was mounted at /app/config, containing repos.json
with open("/app/config/repos.json", "r") as f:
    repos = json.load(f)

REPO_URL = repos[job_index]
print(f"Starting compilation for repo at index {job_index}: {REPO_URL}")

# REPO_URL = os.environ.get("REPO_URL")
if not REPO_URL:
    print("No REPO_URL provided. Exiting.")
    sys.exit(1)
CLONED_DIR = DEFAULT_VALUES["CLONED_DIR"]
### NFS mount directory on K8S to save the compiled repos
NFS_COMPILED_DIR = DEFAULT_VALUES["COMPILED_DIR"]
### K8S local directory to actually conduct the compilation
K8S_COMPILED_DIR = DEFAULT_VALUES["K8S_COMPILED_DIR"]
if not os.path.exists(K8S_COMPILED_DIR):
    os.makedirs(K8S_COMPILED_DIR)
RESULTS_DIR = DEFAULT_VALUES["RESULTS_DIR"]
AUTOGEN_LOGS_DIR = DEFAULT_VALUES["AUTOGEN_LOGS_DIR"]
ALL_LOGS_DIR = DEFAULT_VALUES["ALL_LOGS_DIR"]   
CORES = os.environ.get("CORES", DEFAULT_VALUES["CORES"])

def transfer_files_to_nfs(repo_name, logger, execution_start_time, k8s_compiled_repo_dir):
    try:
        # Copy the compiled repo to the NFS
        tarball_path = f'/app/{repo_name}.tar.gz'
        logger.info(f"Creating tarball for {repo_name} at {tarball_path}...")
        create_tarball(source_dir=k8s_compiled_repo_dir, tarball_path=tarball_path)
        create_tarball_time = time() - execution_start_time
        logger.info(f"Created tarball for {repo_name} using {create_tarball_time} seconds.")
        # First, copy tarball to NFS directory /app/compiled_repos/{repo_name}.tar.gz
        tarball_nfs_destination = os.path.join(NFS_COMPILED_DIR, os.path.basename(tarball_path))
        shutil.copy2(tarball_path, tarball_nfs_destination)  # copy2 preserves metadata
        move_to_nfs_time = time() - execution_start_time
        logger.info(f"Moved compiled repo to NFS using {move_to_nfs_time} seconds.")    
        # # Then, extract the tarball to /app/compiled_repos/{repo_name}
        # nfs_repo_path = os.path.join(NFS_COMPILED_DIR, repo_name)
        # os.makedirs(nfs_repo_path, exist_ok=True)
        # extract_tarball_subprocess(tarball_nfs_destination, nfs_repo_path)
        # logger.info(f"Extracted tarball to {nfs_repo_path}")
        # os.remove(tarball_nfs_destination)
        # logger.info(f"Removed tarball: {tarball_nfs_destination}")
        # extract_and_remove_time = time() - execution_start_time
        # logger.info(f"Extracted tarball and removed tarball using {extract_and_remove_time} seconds.")   
         
    except Exception as e:
        logger.error(f"Error transferring files to NFS: {e}")
        # sys.exit(1)

def main():
    repo_name = REPO_URL.split('/')[-1].replace('.git', '')

    start_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    execution_start_time = time()
    repo_logs_dir = os.path.join(ALL_LOGS_DIR, repo_name)
    os.makedirs(repo_logs_dir, exist_ok=True)    
    
    ### Setup logger
    logger = setup_logger(repo_name, repo_logs_dir, start_time)
    
    cloned_repo_dir = os.path.join(CLONED_DIR, repo_name)
    k8s_compiled_repo_dir = os.path.join(K8S_COMPILED_DIR, repo_name)
    results_file_path = os.path.join(RESULTS_DIR, f'results.json')
        
    repo_output_dir = os.path.join(RESULTS_DIR, repo_name)
    os.makedirs(repo_output_dir, exist_ok=True)
    
    # Clone the repo if not present
    clone_repository(repo_url=REPO_URL, save_path=CLONED_DIR, logger=logger)
    
    
        
    clone_time = time() - execution_start_time
    logger.info(f"Cloned {REPO_URL} to {cloned_repo_dir} using {clone_time} seconds.")
            
            

    # Run compilation steps (this replaces the docker exec logic)
    
    remove_and_copy_directory_wrapper(repo_name=repo_name, logger=logger, container=None, cloned_repos_path=CLONED_DIR, compiled_repos_path=K8S_COMPILED_DIR)
    
    total_setup_time = time() - execution_start_time
    logger.info(f"Setup completed for {repo_name} using {total_setup_time} seconds.")
    
    logger.info(f"Compiling {repo_name}...")
    
    # Mark the compiled repo as a safe directory for git
    safe_dir = f"/app/k8s_compiled_repos/{repo_name}"
    try:
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", safe_dir],
            check=True
        )
        logger.info(f"Added {safe_dir} to git safe.directory.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to add {safe_dir} to git safe.directory: {e}")
        
    # Assuming compilation.py is in /app/src and can run directly
    # and that it uses env vars or parameters to know what to compile
    # NOTE: This is specifically for running on K8S with the virtual env
    cmd = ["/opt/venv/bin/python", "/app/src/compilation.py", "--repo_url", REPO_URL, '--compiled_dir', K8S_COMPILED_DIR]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    for line in proc.stdout:
        logger.info(line.rstrip())

    return_code = proc.wait()
    if return_code != 0:
        errors = proc.stderr.read()
        logger.error(f"Compilation failed:\n{errors}")
        sys.exit(1)
    logger.info(f"Compilation finished for {repo_name}.")
    
    compile_time = time() - execution_start_time
    logger.info(f"Compiled {repo_name} using {compile_time} seconds.")
    
    # Transfer files to NFS
    transfer_files_to_nfs(repo_name, logger, execution_start_time, k8s_compiled_repo_dir)

    # Validation step
    
    # Install Java since we need it for the validation step and we removed it from the docker image
    # subprocess.run(["apt-get", "update"], check=True)
    # subprocess.run(["apt-get", "install", "-y", "openjdk-17-jdk"], check=True)
    # subprocess.run(["apt-get", "install", "-y", "openjdk-17-jre"], check=True)
    # subprocess.run(["rm", "-rf", "/var/lib/apt/lists/*"], check=True)
    # logger.info(f"Installed Java for {repo_name}.")
    
    # Run validation pipeline
    logger.info(f"Running validation for {repo_name}...")
    is_compiled, compiled_percentage, len_binary_func, len_source_func, binary_file_num, source_file_num = validation_pipeline(repo_name=repo_name, output_file_path=repo_output_dir, source_directory=k8s_compiled_repo_dir, artifacts_directory=k8s_compiled_repo_dir, threshold=0.5, max_workers=int(CORES), date_time=start_time, logger = logger)
    logger.info(f'Validation process completed for {repo_name}.')
    logger.info(f'Compiled percentage: {compiled_percentage}')
    
    validation_time = time() - execution_start_time
    logger.info(f"Validated {repo_name} using {validation_time} seconds.")
    
    # Update results.json
    total_time = time() - execution_start_time
    repo_result = {
        "compiled_percentage": compiled_percentage,
        "clone_time": f"{clone_time:.2f} seconds",
        "compile_time": f"{compile_time:.2f} seconds",
        "validation_time": f"{validation_time:.2f} seconds",
        "total_setup_time": f"{total_setup_time:.2f} seconds",
        "total_execution_time": f"{total_time:.2f} seconds",
        "len_binary_func": len_binary_func,
        "len_source_func": len_source_func,
        'binary_file_num': binary_file_num,
        'source_file_num': source_file_num
    }
    logger.info(f"Final result for {repo_name}: {repo_result}")
    if not os.path.exists(results_file_path):
        with open(results_file_path, 'w') as f:
            json.dump({}, f, indent=4)

    with open(results_file_path, 'r') as f:
        previous_results = json.load(f)

    if repo_name not in previous_results:
        previous_results[repo_name] = []
    previous_results[repo_name].append(repo_result)
    
    ### TODO: Add a try except block here to handle the case where the file is being written by another worker
    with open(results_file_path, 'w') as f:
        json.dump(previous_results, f, indent=4)

    logger.info(f"Task completed for {repo_name}. Exiting worker.")
    return True

if __name__ == "__main__":
    main()