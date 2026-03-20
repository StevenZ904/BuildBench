import os
import json
import sys
import argparse
from datetime import datetime
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial                 # <‑‑ helper for passing cfg dict into workers
from pathlib import Path
from itertools import islice
import time

from compilation_base import compilation_base
from assemblage import Assemblage   
from llm_baseline import llm_baseline
from llm_multi_turn import llm_multi_turn
from validation_pipeline import validation_pipeline
from tools import *
from utils import *
from dotenv import load_dotenv
load_dotenv()
EXPERIMENT_TIME = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OPTIONS = {
    'base': compilation_base,
    'llm_baseline': llm_baseline,
    'llm_multi_turn': llm_multi_turn,
    'assemblage': Assemblage,
}
MODEL_NAME = os.getenv("MODEL_NAME", "llm")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
input_file_path = os.path.join(BASE_DIR, 'data', 'sampled_repos_149_cleaned_higher_split_compilable.jsonl')
docker_image = 'compilation_base_image:latest'
repo_logs_dir = os.path.join(BASE_DIR, 'logs', f'baselines_{MODEL_NAME}')
cloned_repos_dir = os.path.join(BASE_DIR, 'cloned_repos')
compiled_repos_dir = os.path.join(BASE_DIR, 'compiled_repos', f'baselines_{MODEL_NAME}')
repo_binaries_dir = os.path.join(BASE_DIR, 'compiled_repos', f'baselines_{MODEL_NAME}', 'binaries')
src_dir = os.path.join(BASE_DIR, 'src', 'compilation_baselines')
compiled_results_dir = os.path.join(BASE_DIR, 'compiled_results', f'baselines_{MODEL_NAME}')

parser = argparse.ArgumentParser(description='LLM Baseline Compilation')
parser.add_argument('--compilation_method', type=str, choices=OPTIONS.keys(), default='llm_baseline', help='Compilation method to use')
parser.add_argument('--input_file_path', type=str, default=input_file_path, help='Path to the input file')
parser.add_argument('--container_image', type=str, default=docker_image, help='Docker container image to use')
parser.add_argument('--repo_logs_dir', type=str, default=repo_logs_dir, help='Directory to save logs for each repo')
parser.add_argument('--cloned_repos_dir', type=str, default = cloned_repos_dir, help='Directory to save cloned repos')
parser.add_argument('--compiled_repos_dir', type=str, default = compiled_repos_dir, help='Directory to save compiled repos')
parser.add_argument('--compiled_results_dir', type=str, default=compiled_results_dir, help='Directory to save compiled results')
parser.add_argument('--repo_binaries_dir', type=str, default=repo_binaries_dir, help='Directory to save repo binaries')
parser.add_argument('--src_dir', type=str, default=src_dir, help='Source directory for the script')
parser.add_argument('--docker_env_vars', type=json.loads, default={}, help='Docker environment variables as JSON string')
parser.add_argument('--parallel_num', type=int, default=1, help='Number of parallel threads to use for compilation')
parser.add_argument('--validation_only', action='store_true', help='Only validate the compiled results without running the compilation process')
parser.add_argument('--search_internet', action='store_true', help='Enable internet search for compilation process')

def batched(iterable, size):
    """
    Yield successive *size*-element lists from *iterable*.
    Last batch may be shorter.
    """
    
    it = iter(iterable)
    while batch := list(islice(it, size)):
        yield batch

def compile_repo(
    repo: dict,
    cfg: dict,
) -> tuple[str, bool]:
    """
    Build *one* repository in its own thread and return (repo_name, succeeded).
    All heavy work – creating the `llm_baseline` instance, starting the Docker
    container, calling OpenAI, etc. – happens *inside* this function so that
    only threads that are actually running create objects and write logs.
    """
    repo_name      = repo["name"]
    repo_full_name = repo["full_name"]

    # Build absolute paths for this repo once, then pass them to the constructor.
    baseline = cfg["method"](
        repo_dir           = Path(cfg["compiled_repos_dir"], repo_name),
        repo_full_name     = repo_full_name,
        container_image    = cfg["container_image"],
        repo_logs_dir      = cfg["repo_logs_dir"],
        cloned_repos_dir   = cfg["cloned_repos_dir"],
        compiled_repos_dir = cfg["compiled_repos_dir"],
        repo_binaries_dir  = cfg["repo_binaries_dir"],
        src_dir            = cfg["src_dir"],
        docker_env_vars    = cfg["docker_env_vars"],
        search_internet    = cfg["search_internet"],
    )

    ok = baseline.run()
    return repo_name, ok


def main(compilation_method, input_file_path, container_image, repo_logs_dir, repo_binaries_dir, cloned_repos_dir, compiled_repos_dir, compiled_results_dir, src_dir, docker_env_vars, parallel_num, validation_only=False, search_internet=False):
    """
    Main function to run the LLM Baseline compilation strategy.
    """
    # with open(input_file_path, 'r') as f:
    #     input_data = json.load(f)

    input_data = [json.loads(l) for l in open(input_file_path) if l.strip()]



    final_result_file_path = os.path.join(repo_logs_dir, f'final_result_{EXPERIMENT_TIME}.json')
    final_results: dict[str, bool] = {}
    success_counter = 0
    
    cfg = dict(
        method             = compilation_method,      # function/class selected
        container_image    = container_image,
        repo_logs_dir      = repo_logs_dir,
        cloned_repos_dir   = cloned_repos_dir,
        compiled_repos_dir = compiled_repos_dir,
        repo_binaries_dir  = repo_binaries_dir,
        src_dir            = src_dir,
        docker_env_vars    = docker_env_vars,
        search_internet    = search_internet,
    )

    if not validation_only:
        print("Starting compilation process...")
        # with ThreadPoolExecutor(max_workers=parallel_num) as executor:
        #     future_to_repo = {}
            
        #     for repo in input_data:
        #         # repo_name = repo['Repo_Name']
        #         # repo_full_name = '/'.join(repo['Github_Url'].split('/')[-2:])
        #         repo_name = repo['name']
        #         repo_full_name = repo['full_name']
        #         repo_log_dir = os.path.join(repo_logs_dir, repo_name)
        #         os.makedirs(repo_log_dir, exist_ok=True)
        #         compiled_repo_dir = os.path.join(compiled_repos_dir, repo_name)
                
        #         # Initialize instance
        #         baseline_instance = compilation_method(
        #             repo_dir=compiled_repo_dir,
        #             repo_full_name=repo_full_name,
        #             container_image=container_image,
        #             repo_logs_dir=repo_log_dir,
        #             cloned_repos_dir=cloned_repos_dir,
        #             repo_binaries_dir=repo_binaries_dir,
        #             compiled_repos_dir=compiled_repos_dir,
        #             src_dir=src_dir,
        #             docker_env_vars=docker_env_vars,
        #             search_internet=search_internet,
        #         )
                
        #         future = executor.submit(baseline_instance.run)
        #         future_to_repo[future] = repo_name



        #     for future in tqdm(as_completed(future_to_repo), total=len(future_to_repo)):
        #         repo_name = future_to_repo[future]
        #         try:
        #             result = future.result()
        #             if result:
        #                 success_counter += 1
        #             final_results[repo_name] = result
        #             with open(final_result_file_path, 'w') as f:
        #                 json.dump(final_results, f)
        #         except Exception as e:
        #             print(f"Error processing {repo_name}: {e}")
        #             final_results[repo_name] = False
                    
        #             with open(final_result_file_path, 'w') as f:
        #                 json.dump(final_results, f)  
        for batch_idx, batch in tqdm(enumerate(batched(input_data, parallel_num), start=1)):
            print(f"\n⇢ Batch {batch_idx}: {len(batch)} repo(s)")

            with ThreadPoolExecutor(max_workers=parallel_num) as pool:
                futures = {
                    pool.submit(compile_repo, repo, cfg): repo["name"]
                    for repo in batch
                }

                for fut in as_completed(futures):
                    repo_name, ok = fut.result()
                    final_results[repo_name] = ok
 
            # ---------- persist incremental results after each batch ----------
            with open(final_result_file_path, 'w') as f:
                f.write(json.dumps(final_results, indent=4))
            # exit()
            # print("Waiting 60 seconds to respect claude rate limits...")
            # sleep(60)
        # ---------- summary ----------

        successes = sum(final_results.values())
        total     = len(input_data)
        print(f"\nFinished {total} repositories "
              f"({successes} succeeded, {total - successes} failed) "
              f"→ success rate {successes/total*100:.2f}%")
        
    else:
        print("Skipping compilation, only validating...")
        # Validation
        validation_results = {}
        with ThreadPoolExecutor(max_workers=parallel_num) as executor:
            future_to_repo = {}
            
            for repo in input_data:
                repo_name = repo['Repo_Name']
                repo_full_name = '/'.join(repo['Github_Url'].split('/')[-2:])
                compiled_results_repo_dir = os.path.join(compiled_results_dir, repo_name)
                source_directory = os.path.join(cloned_repos_dir, repo_name)
                compiled_repo_dir = os.path.join(compiled_repos_dir, repo_name)
                os.makedirs(compiled_results_repo_dir, exist_ok=True)
                future = executor.submit(validation_pipeline, 
                                        repo_name=repo_name,
                                        output_file_path=compiled_results_repo_dir,
                                        source_directory=source_directory,
                                        artifacts_directory=compiled_repo_dir,
                                        threshold=0.5,
                                        max_workers=2,
                                        date_time=EXPERIMENT_TIME,
                                        logger=None)
                future_to_repo[future] = repo_name

            for future in tqdm(as_completed(future_to_repo), total=len(future_to_repo)):
                repo_name = future_to_repo[future]
                try:
                    result = future.result()
                    validation_results[repo_name]['compiled_percentage'] = result
                except Exception as e:
                    print(f"Error validating {repo_name}: {e}")
            
            validation_results_file_path = os.path.join(compiled_results_dir, f'validation_results_{EXPERIMENT_TIME}.json')
            with open(validation_results_file_path, 'w') as f:
                json.dump(validation_results, f, indent=4)
            

if __name__ == '__main__':


    args = parser.parse_args()
    
    main(
        compilation_method=OPTIONS[args.compilation_method],
        input_file_path=args.input_file_path,
        container_image=args.container_image,
        repo_logs_dir=args.repo_logs_dir,
        cloned_repos_dir=args.cloned_repos_dir,
        repo_binaries_dir=args.repo_binaries_dir,
        compiled_repos_dir=args.compiled_repos_dir,
        compiled_results_dir=args.compiled_results_dir,
        src_dir=args.src_dir,
        docker_env_vars=args.docker_env_vars,
        parallel_num = args.parallel_num, 
        validation_only=args.validation_only,
        search_internet=args.search_internet,
    )