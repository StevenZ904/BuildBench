import os
import argparse
import json
import subprocess
from collections import defaultdict
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import hashlib
from multiprocessing import Manager


# def classify_file(file_path, extensions):
#     """
#     Classify a single file into one of your categories:
#       - by extension first;
#       - otherwise by `file --brief` output:
#          * 'executable'|'shared object' → Executables
#          * 'relocatable'            → Object Files
#     Returns the matching category string, or None.
#     """
#     fname = file_path.lower()
#     for category, exts in extensions.items():
#         for ext in exts:
#             if fname.endswith(ext):
#                 return category

#     # fallback to `file` on Unix
#     try:
#         desc = subprocess.check_output(
#             ["file", "--brief", file_path],
#             text=True, stderr=subprocess.DEVNULL
#         ).lower()
#         if 'elf' in desc:
#             if "executable" in desc or "shared object" in desc:
#                 return "Executables (no extension)"
#             elif "relocatable" in desc:
#                 return "Object Files (.o)"
#     except Exception:
#         pass

#     return None



def classify_file(file_path, extensions, seen_hashes, git_modules_paths):
    """
    - Compute MD5; skip if already in seen_hashes.
    - Otherwise add hash to seen_hashes and do classification.
    """
    if len(git_modules_paths) > 0:
        for git_path in git_modules_paths:
            if git_path in file_path:
                return None
    
    try:
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        file_hash = hasher.hexdigest()
    except (FileNotFoundError, PermissionError):
        return None
    except Exception:
        return None
    if file_hash in seen_hashes:
        return None
    seen_hashes[file_hash] = True

    # --- Extension-based classification ---
    fname = file_path.lower()
    for category, exts in extensions.items():
        if any(fname.endswith(ext) for ext in exts):
            return category

    # --- Fallback via `file --brief` ---
    try:
        desc = subprocess.check_output(
            ["file", "--brief", file_path],
            text=True, stderr=subprocess.DEVNULL
        ).lower()
        if 'elf' in desc:
            if "executable" in desc or "shared object" in desc:
                return "Executables (no extension)"
            elif "relocatable" in desc:
                return "Object Files (.o)"
    except Exception:
        pass

    return None


def count_files_parallel(directory, extensions, max_workers=None):
    """
    Walk `directory`, gather all files, then classify them in parallel,
    skipping duplicates via a shared MD5 dict.
    Returns a dict mapping category → count.
    """
    # 1) Gather all file paths
    file_paths = [
        os.path.join(root, f)
        for root, _, files in os.walk(directory)
        for f in files
    ]

    repo_file_lists = os.listdir(directory)
    
    if '.gitmodules' in repo_file_lists:
        git_modules_paths = []
        with open(os.path.join(directory, '.gitmodules'), 'r') as f:
            lines = f.readlines()
            for line in lines:
                if 'path' in line:
                    path = line.split('=')[1].strip()
                    git_modules_paths.append(path)
    else:
        git_modules_paths = []    

    # 2) Shared dict for seen hashes
    manager = Manager()
    seen_hashes = manager.dict()

    counts = defaultdict(int)
    # 3) Bind extensions & shared seen_hashes
    classifier = partial(classify_file, extensions=extensions, seen_hashes=seen_hashes, git_modules_paths=git_modules_paths)

    # 4) Parallel classification
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        for category in pool.map(classifier, file_paths):
            if category:
                counts[category] += 1

    return counts

# def count_files_parallel(directory, extensions, max_workers=None):
#     """
#     Walk `directory`, collect all file paths, then classify them in parallel.
#     Returns a dict mapping category → count.
#     """
#     counts = defaultdict(int)
#     # gather
#     file_paths = [
#         os.path.join(root, f)
#         for root, _, files in os.walk(directory)
#         for f in files
#     ]

#     # set up worker
#     classifier = partial(classify_file, extensions=extensions)
#     with ProcessPoolExecutor(max_workers=max_workers) as pool:
#         for category in pool.map(classifier, file_paths):
#             if category:
#                 counts[category] += 1
#     return counts

def load_json(json_path):
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading JSON file '{json_path}': {e}")
        return {}

def main(compilation_method):
    # args = parse_arguments()
    # print("Compiling with method:", compilation_method)
    # main_directory = f"compiled_repos/"
    # json_file_path = f"compiled_results/validation_cleaned_results.json"

    main_directory = "compiled_repos/"  # Update this path to your compiled repos directory
    json_file_path = "compiled_results/validation_cleaned_results.json"  # Update this path

    if not os.path.isdir(main_directory):
        print(f"Error: '{main_directory}' is not a directory.")
        return

    json_data = load_json(json_file_path)
    if not json_data:
        print("No data loaded from JSON. Exiting.")
        return

    file_extensions = {
        "Source Files (.c)": [".c"],
        "Header Files (.h)": [".h"],
        "Object Files (.o)": [".o"],
        "Shared Libraries (.so/.dll/.dylib)": [".so", ".dll", ".dylib"],
        "Dependency Files (.d)": [".d"],
        "Executables (.exe/.bat/.cmd)": [".exe", ".bat", ".cmd"],
        # the classifier will catch any ELF without extension here:
        "Executables (no extension)": []
    }

    total_counts = defaultdict(int)
    processed_repos = []
    source_function_counts = 0
    binary_function_counts = 0
    counts_per_repo = defaultdict(lambda: defaultdict(int))
    for repo_name, data_list in tqdm(json_data.items(), desc="Repos"):
        repo_path = os.path.join(main_directory, repo_name)
        if not os.path.isdir(repo_path):
            print(f"Skipping missing repo dir '{repo_name}'.")
            continue

        if not data_list:
            print(f"Skipping empty data for '{repo_name}'.")
            continue

        entry = data_list[-1]
        pct = entry.get("compiled_percentage")
        if pct is None:
            print(f"Skipping '{repo_name}' (no compiled_percentage).")
            continue
        if pct == 0:
            continue

        source_function_counts += entry.get("len_source_func", 0)
        binary_function_counts += entry.get("len_binary_func", 0)
        counts = count_files_parallel(repo_path, file_extensions, max_workers=os.cpu_count())
        for cat, cnt in counts.items():
            total_counts[cat] += cnt

        for cat, cnt in counts.items():
            counts_per_repo[repo_name][cat] += cnt
        processed_repos.append(repo_name)

    # report
    print("\n=== File Type Counts ===")
    if processed_repos:
        print(f"Processed {len(processed_repos)} repos: {', '.join(processed_repos)}\n")
        print(f"{'-'*40}")
        for cat, cnt in total_counts.items():
            print(f"{cat}: {cnt}")
        print(f"{'-'*40}")
        print(f"Total source functions: {source_function_counts}")
        print(f"Total binary functions: {binary_function_counts}")
    else:
        print("No repositories met the compiled_percentage > 0 criteria.")

    parent_dir = os.path.dirname(json_file_path)
    output_file = os.path.join(parent_dir, "file_counts.json")
    with open(output_file, 'w') as f:
        json.dump(counts_per_repo, f, indent=4)
    print(f"Counts per repo saved to '{output_file}'.")

if __name__ == "__main__":
    # for compilation_method in ["assemblage", "llm_baseline", "llm_baseline_claude","llm_baseline_o3-mini",]:  # args.directory
    #     main(compilation_method=compilation_method)
    main('ghcc')
    # file_extensions = {
    #     "Source Files (.c)": [".c"],
    #     "Header Files (.h)": [".h"],
    #     "Object Files (.o)": [".o"],
    #     "Shared Libraries (.so/.dll/.dylib)": [".so", ".dll", ".dylib"],
    #     "Dependency Files (.d)": [".d"],
    #     "Executables (.exe/.bat/.cmd)": [".exe", ".bat", ".cmd"],
    #     # the classifier will catch any ELF without extension here:
    #     "Executables (no extension)": []
    # }
    
    # result = count_files_parallel("compiled_repos/dbcc", file_extensions, max_workers=os.cpu_count())
    # print(result
    #       )