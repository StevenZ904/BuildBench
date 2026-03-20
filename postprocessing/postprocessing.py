import os
import json
import sys
from tqdm import tqdm
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed

from utils import safe_log, find_linux_compiled_artifacts, get_latest_file, is_elf_has_dwarf
from elftools.elf.elffile import ELFFile
from binary_info import GLOBAL_SUMMARY, get_binary_info_per_directory_wrapper
from variable_info import get_variable_info_per_directory_wrapper, VARIABLE_INFO_METRICS


# def per_repo_wrapper(repo_directory, compiled_repos_directory, compiled_results_directory, output_directory, logger=None):
    

def main(compiled_repos_directory, compiled_results_directory, output_directory, logger=None):
    if logger is None:
        logger = logging.Logger('PostProcessingLogger')
        logger.setLevel(logging.INFO)
        # create console handler and set level to debug
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # add formatter to ch
        ch.setFormatter(formatter)
        # add ch to logger
        logger.addHandler(ch)
        
        
    
    ### Set final result save path
    os.makedirs(output_directory, exist_ok=True)
    global_variable_info_save_path = os.path.join(output_directory, 'global_variable_info.json')
    global_binary_info_save_path = os.path.join(output_directory, 'global_binary_info.json')
    
    
    ### Inititalize for variable information extraction step
    unique_variables = set()
    unique_global_variables = set()
    global_num_variables_in_functions = []
    global_variable_info_metrics = VARIABLE_INFO_METRICS.copy()
    
    global_binary_info_summary = GLOBAL_SUMMARY.copy()
    with open(os.path.join(compiled_results_directory, "results.json"), "r") as f:
        data = json.load(f)
    # repo_list = [key for key in data.keys()]
    repo_list = os.listdir(output_directory)
    ### TODO: Change this to compile_results_directory on NFS server
    for repo_directory in tqdm(repo_list):
        if repo_directory== "smoothxg":
            continue
        repo_name = repo_directory
        repo_directory_path = os.path.join(compiled_repos_directory, repo_directory)
        if not os.path.isdir(repo_directory_path):
            safe_log(logger, 'error', f"Repo path {repo_directory_path} is not a directory")
            return None
        
        safe_log(logger, 'info', f"Post processing {repo_name}...")
        repo_result_directory = os.path.join(output_directory, repo_name)
        os.makedirs(repo_result_directory, exist_ok=True)
        
        binary_file_paths_file_path = os.path.join(repo_result_directory, 'all_binary_file_paths.json') # This file contains all the binary file paths found in the repo
        shared_object_and_executable_file_paths_file_path = os.path.join(repo_result_directory, 'shared_object_and_executable_file_paths.json')
        binary_info_file_path = os.path.join(repo_result_directory, 'binary_info.json')
        variable_info_file_path = os.path.join(repo_result_directory, 'variable_info.json')
        
        binary_file_paths = []
        
        if not os.path.exists(binary_file_paths_file_path):
            ### Search for binary results in the compiled_results directory
            pre_computed_binary_results_file_directory = os.path.join(compiled_results_directory, repo_name)
            latest_pre_computed_binary_results_file = get_latest_file(pre_computed_binary_results_file_directory, prefix=f"{repo_name}_binary_functions") # Extract the latest pre-computed binary results file path
            if  latest_pre_computed_binary_results_file is None:
                safe_log(logger, 'info', f"No pre-computed binary results found for repo {repo_name}")
                ### Search for binary files in the repo directory if pre-computed binary results are not found, which is rare
                if os.path.exists(repo_directory_path):
                    binary_file_paths = find_linux_compiled_artifacts(repo_directory_path, logger=logger)
                    with open(binary_file_paths_file_path, 'w') as f:
                        json.dump(binary_file_paths, f, indent=4)
                else:
                    safe_log(logger, 'error', f"Repo {repo_name} at {repo_directory_path} does not exist")
                    return None
            else:
                latest_pre_computed_binary_results_file_path = os.path.join(pre_computed_binary_results_file_directory, latest_pre_computed_binary_results_file)        
                with open(latest_pre_computed_binary_results_file_path, "r") as f:
                    pre_computed_binary_results = json.load(f)
                safe_log(logger, 'info', f"Pre-computed binary results found for repo {repo_name}")
                    
                for results in pre_computed_binary_results:
                    for key, value in results.items():
                        # Key example: '/app/k8s_compiled_repos/ucc/lib/ucx/libuct_cma.so'
                        temp_key = key.replace("/app/k8s_compiled_repos", compiled_repos_directory)
                        temp_key = os.path.normpath(temp_key)
                        binary_file_paths.append(temp_key)
                    
            with open(binary_file_paths_file_path, 'w') as f:
                json.dump(binary_file_paths, f, indent=4)
        
        else:
            with open(binary_file_paths_file_path, 'r') as f:
                binary_file_paths = json.load(f)
        

        if binary_file_paths is None or len(binary_file_paths) == 0:
            safe_log(logger, 'error', f"No binary files found for extracting binary information for repo {repo_name}")
            return None
        
        ### Extracting binary info from this directory
        safe_log(logger, 'info', f"Extracting binary info for {repo_name}...")
        
        if not os.path.exists(binary_info_file_path):
            repo_binary_info_summary = get_binary_info_per_directory_wrapper(directory=repo_directory_path, save_directory= repo_result_directory, binary_source_path=binary_file_paths_file_path  )
            with open(binary_info_file_path, 'w') as f:
                json.dump(repo_binary_info_summary, f, indent=4)
        else:
            with open(binary_info_file_path, 'r') as f:
                repo_binary_info_summary = json.load(f)
        
        if repo_binary_info_summary is None:
            safe_log(logger, 'error', f"No binary info found for repo {repo_name}")
            return None

        ### Extracting variable info from this directory
        safe_log(logger, 'info', f"Extracting variable info for {repo_name}...")
        per_repo_variable_info, auxiliary_variable_info = get_variable_info_per_directory_wrapper(binary_directory=repo_directory_path, output_directory= repo_result_directory, binary_source_path=binary_file_paths_file_path, repo_name=repo_name)
        if per_repo_variable_info is None:
            safe_log(logger, 'error', f"No variable info found for repo {repo_name}")
            return None
        elif auxiliary_variable_info is None:
            safe_log(logger, 'error', f"No auxiliary variable info found for repo {repo_name}")
            return None
        
        result = {
            "repo_binary_info_summary": repo_binary_info_summary,
            "per_repo_variable_info": per_repo_variable_info,
            "auxiliary_variable_info": auxiliary_variable_info
        }
        return result
    
    except Exception as e:
        safe_log(logger, 'error', f"Error in post processing {repo_directory}: {e}")
        return None
    
    

def main(compiled_repos_directory, compiled_results_directory, output_directory, logger=None, max_workers=4):
    if logger is None:
        logger = logging.Logger('PostProcessingLogger')
        logger.setLevel(logging.INFO)
        # create console handler and set level to debug
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # add formatter to ch
        ch.setFormatter(formatter)
        # add ch to logger
        logger.addHandler(ch)
    
    ### Set final result save path
    os.makedirs(output_directory, exist_ok=True)
    global_variable_info_save_path = os.path.join(output_directory, 'global_variable_info.json')
    global_binary_info_save_path = os.path.join(output_directory, 'global_binary_info.json')
    
    
    ### Inititalize for variable information extraction step
    unique_variables = set()
    unique_global_variables = set()
    global_num_variables_in_functions = []
    global_variable_info_metrics = VARIABLE_INFO_METRICS.copy()
    global_binary_info_summary = GLOBAL_SUMMARY.copy()
    
    ### TODO: Change this to compile_results_directory on NFS server
    futures = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        for repo_dir in os.listdir(compiled_repos_directory):
            # Submit a job for each repo
            futures.append(executor.submit(per_repo_wrapper,
                                           repo_dir,
                                           compiled_repos_directory,
                                           compiled_results_directory,
                                           output_directory
                                           ))


        for f in tqdm(as_completed(futures), total=len(futures), desc="Processing repos"):
            # Collect partial results
            result = f.result()
            if result is None:
                continue
            
            repo_binary_info_summary = result['repo_binary_info_summary']
            per_repo_variable_info = result['per_repo_variable_info']
            auxiliary_variable_info = result['auxiliary_variable_info']
            unique_variables_in_repo = auxiliary_variable_info['unique_variables_in_repo']
            unique_global_variables_in_repo = auxiliary_variable_info['unique_global_variables_in_repo']
            num_variables_in_functions = auxiliary_variable_info['num_variables_in_functions']
            
            
            global_binary_info_summary['stripped'] += repo_binary_info_summary['stripped']
            global_binary_info_summary['has_debug_info'] += repo_binary_info_summary['has_debug_info']
            global_binary_info_summary['cython'] += repo_binary_info_summary['cython']
            global_binary_info_summary['inlined_func'] += repo_binary_info_summary['inlined_func']
            global_binary_info_summary['optimization'].update(repo_binary_info_summary['optimization'])
            global_binary_info_summary['elf_info'].update(repo_binary_info_summary['elf_info'])
            global_binary_info_summary['language'].update(repo_binary_info_summary['language'])
            
            
            unique_variables.update(unique_variables_in_repo)
            unique_global_variables.update(unique_global_variables_in_repo)
            global_num_variables_in_functions.extend(num_variables_in_functions)

            global_variable_info_metrics['total_variable_count'] += per_repo_variable_info['total_variable_count']
            global_variable_info_metrics['global_variable_count'] += per_repo_variable_info['global_variable_count']
            global_variable_info_metrics['argument_count'] += per_repo_variable_info['argument_count']
            global_variable_info_metrics['distinct_type_count'] += per_repo_variable_info['distinct_type_count']


    ### Calculate the global variable information
    global_variable_info_metrics['unique_variable_count'] = len(unique_variables)
    global_variable_info_metrics['unique_global_variable_count'] = len(unique_global_variables)
    global_variable_info_metrics['average_variables_per_function'] = sum(global_num_variables_in_functions)/len(global_num_variables_in_functions) 
    
    ### Save the global variable info
    with open(global_binary_info_save_path, 'w') as f:
        json.dump(global_binary_info_summary, f, indent=4)
    with open(global_variable_info_save_path, 'w') as f:
        json.dump(global_variable_info_metrics, f, indent=4)


if __name__ == '__main__':
    compiled_repos_directory = 'compiled_repos'
    compiled_results_directory = 'compiled_results'
    output_directory = 'postprocessed_results'
    main(compiled_repos_directory, compiled_results_directory, output_directory)