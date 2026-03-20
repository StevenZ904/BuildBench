import os
import json
from validation_pipeline import validation_pipeline
job_index = int(os.environ["JOB_INDEX"])

# The configMap was mounted at /app/config, containing repos.json
with open("/app/config/repos.json", "r") as f:
    repos = json.load(f)

REPO_NAME = repos[job_index]

compiled_repo_dir = "/app/compiled_repos"
compiled_repo_dir = os.path.join(compiled_repo_dir, REPO_NAME)
os.makedirs(compiled_repo_dir, exist_ok=True)
compiled_results_dir = "/app/compiled_results"
compiled_results_dir = os.path.join(compiled_results_dir, REPO_NAME)
os.makedirs(compiled_results_dir, exist_ok=True)

source_repo_dir = f"/app/cloned_repos/{REPO_NAME}"

final_results_file_path = os.path.join("/app/validation_logs/", f"validation_results.json") 

is_compiled, compiled_percentage, len_binary_func, len_source_func, binary_file_num, source_file_num = validation_pipeline(repo_name=REPO_NAME, 
                    source_directory=source_repo_dir,
                    artifacts_directory=compiled_repo_dir, 
                    output_file_path=compiled_results_dir, 
                    max_workers=8)

repo_result = {
    "compiled_percentage": compiled_percentage,
    "len_binary_func": len_binary_func,
    "len_source_func": len_source_func,
    'binary_file_num': binary_file_num,
    'source_file_num': source_file_num
}
if not os.path.exists(final_results_file_path):
        with open(final_results_file_path, 'w') as f:
            json.dump({}, f, indent=4)

with open(final_results_file_path, 'r') as f:
    previous_results = json.load(f)

if REPO_NAME not in previous_results:
    previous_results[REPO_NAME] = []
previous_results[REPO_NAME].append(repo_result)

### TODO: Add a try except block here to handle the case where the file is being written by another worker
with open(final_results_file_path, 'w') as f:
    json.dump(previous_results, f, indent=4)

