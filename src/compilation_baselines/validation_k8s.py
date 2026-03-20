
import os
import yaml
from kubernetes import client, config
import subprocess
import json
import argparse
import logging
import pandas as pd
import datetime


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
orchestrator_log_dir = os.path.join(BASE_DIR, "orchestrator_logs")
yaml_file_dir = os.path.join(BASE_DIR, "yaml_files")
start_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

repo_list_path = os.path.join(BASE_DIR, "data", "sampled_repos_385_higher_split.txt")

JOB_TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job-template.yaml")
DOCKER_IMAGE = 'validation:latest'
CORES = 5
COMPILATION_METHOD = 'cleaner_compiled_results'
'''
OPTIONS:
llm_baseline
llm_baseline_claude
llm_multi_turn_no_search
llm_multi_turn_search
ghcc
assemblage
'''
def load_job_template():
    with open(JOB_TEMPLATE_PATH, 'r') as f:
        return yaml.safe_load(f)


def main():
    with open(repo_list_path, 'r') as f:
        input_data = f.readlines()
        input_data = [line.strip() for line in input_data]
        repos = [line.split('/')[-1] for line in input_data]
    num_repos = len(repos)
    print(f"Validating {num_repos} repositories...")

    configmap_name = "llm-compiler-repos"
    configmap_manifest = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": configmap_name
        },
        "data": {
            # Dump the entire repos array as JSON
            "repos.json": json.dumps(repos)
        }
    }
    config_map_path =  os.path.join(yaml_file_dir, f'configmap-{start_time}.yaml')
    with open(config_map_path, 'w') as f:
        yaml.dump(configmap_manifest, f)
    
    # Apply the ConfigMap
    subprocess.run(["kubectl", "apply", "-f", config_map_path], check=True)
    print(f"Created/Updated ConfigMap '{configmap_name}' with {num_repos} repos.")

    compilation_method_temp = COMPILATION_METHOD.replace("_", "-")
    job_template = load_job_template()
    job_name = f"validation-job-{compilation_method_temp}-temp"
    job_template["metadata"]["name"] = job_name
    job_template["spec"]["completions"] = num_repos
    job_template["spec"]["parallelism"] = 1
    job_template["spec"]["completionMode"] = "Indexed"
    job_template["spec"]["maxFailedIndexes"] = num_repos
    # job_template["spec"]["backoffLimit"] = args.backoff_limit ### TODO: So far the backoff limit is set to 100, should increase it if you are creating more than 50 jobs in total. 

    container = job_template["spec"]["template"]["spec"]["containers"][0]

    container['image'] = DOCKER_IMAGE
    
    ### Setup compiled_repos directories
    container['volumeMounts'][0]['subPath'] = f'user/Compilation_Benchmark/385_higher_split/cloned_repos'
    ### Setup cloned_repos directories
    container['volumeMounts'][1]['subPath'] = f'user/Compilation_Benchmark/385_higher_split/cloned_repos'
    ### Setup compiled_results directories
    container['volumeMounts'][2]['subPath'] = f'user/Compilation_Benchmark/385_higher_split/{COMPILATION_METHOD}/compiled_results'
    ### Setup validation_logs directories
    container['volumeMounts'][3]['subPath'] = f'user/Compilation_Benchmark/385_higher_split/{COMPILATION_METHOD}/validation_logs'
    
    # imagePullPolicy is set to 'IfNotPresent' by default to avoid pulling the image every time
    container['imagePullPolicy'] = 'IfNotPresent'

    container['resources']['requests']['cpu'] = CORES
    
    try:       
        # save the job template to a file
        yaml_file_path =  os.path.join(yaml_file_dir, f'job-{start_time}.yaml')
        with open(yaml_file_path, 'w') as f:
            yaml.dump(job_template, f)  
        
        # Apply the job    
        subprocess.run(["kubectl", "delete", "job", job_name], check=False)
        subprocess.run(["kubectl", "apply", "-f", yaml_file_path], check=True)
        print(f"Submitted job '{job_name}' to Kubernetes.")    
    except Exception as e:
        print(f"Failed to submit job: {e}")
        raise e

if __name__ == "__main__":
    main()
