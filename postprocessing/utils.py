from concurrent.futures import ThreadPoolExecutor, as_completed
from elftools.elf.elffile import ELFFile
import os
import re

def safe_log(logger, level, message):
    if logger:
        log_func = getattr(logger, level, None)
        if callable(log_func):
            log_func(message)
    else:
        print(message)  # Fallback to print if logger is not defined

def convert_sets_to_lists(obj):
    if isinstance(obj, dict):
        return {k: convert_sets_to_lists(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets_to_lists(item) for item in obj]
    elif isinstance(obj, set):
        return list(obj)
    else:
        return obj
    
from datetime import datetime

def get_latest_file(directory, prefix):
    # This regex matches filenames like:
    # prefix_YYYY-MM-DD_HH-MM-SS.json
    pattern = re.compile(
        rf'^{re.escape(prefix)}_(\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}-\d{{2}})\.json$'
    )
    latest_file = None
    latest_time = None

    for filename in os.listdir(directory):
        match = pattern.match(filename)
        if match:
            # Extract the timestamp string from the filename
            timestamp_str = match.group(1)
            # Convert the timestamp string to a datetime object
            file_time = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
            # Update if this file is more recent
            if latest_time is None or file_time > latest_time:
                latest_time = file_time
                latest_file = filename
        else:
            return None
    return latest_file


def is_elf_has_dwarf(binary_path):  
    with open(binary_path, 'rb') as rb:
        # Read only the first 4 bytes to check for ELF magic number
        bytes = rb.read(4)
        if bytes == b"\x7fELF":
            rb.seek(0)
            elffile = ELFFile(rb)
            if elffile and elffile.has_dwarf_info():
                dwarf_info = elffile.get_dwarf_info()
                return elffile, dwarf_info
    return None, None

def find_linux_compiled_artifacts(directory, logger=None, exclude_dirs=[ 'test', 'Test'], max_workers=4):
    """
    Find all Linux compiled artifacts (e.g., object files, executables, shared libraries) 
    in a given directory, excluding specified directories and using multi-threading.

    Parameters:
        directory (str): The root directory to search.
        exclude_dirs (list): List of directory names to exclude from search.
        max_workers (int): The maximum number of threads to use for searching.

    Returns:
        list: List of all found compiled artifact paths.
    """
    
    max_workers = max_workers * 2 # (I/O‐bound)
    
    if exclude_dirs is None:
        exclude_dirs = []

    # Only Linux-related compiled artifact extensions
    artifact_extensions = ['.o', '.a', '.so', '.out', '.bin'] 
    compiled_files = []
    all_elf_counter = 0
    all_dwarf_info_counter = 0
    def process_directory(root_dir):
        elf_counter = 0
        dwarf_info_counter = 0
    
        local_files = []
        for root, dirs, files in os.walk(root_dir):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            # Collect relevant compiled files
            for file in files:
                file_path = os.path.abspath(os.path.join(root, file))
                try:
                    elffile, dwarf_info = is_elf_has_dwarf(file_path)
                    if elffile:
                        elf_counter += 1
                        local_files.append(file_path)
                    if dwarf_info:
                        dwarf_info_counter += 1                    
                except Exception as e:
                    safe_log(logger, 'warning', f"Error checking file {file_path}: {e}")
                    continue
        # return local_files, elf_counter, dwarf_info_counter
        return local_files, elf_counter, dwarf_info_counter


    # Use ThreadPoolExecutor to parallelize the file search
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_directory, directory)]
        for future in futures:
            local_files, elf_counter, dwarf_info_counter = future.result()
            
            compiled_files.extend(local_files)
            all_elf_counter += elf_counter
            all_dwarf_info_counter += dwarf_info_counter
    
    safe_log(logger, 'info', (f"Total ELF files found: {str(all_elf_counter)}" ))
    safe_log(logger, 'info',f"Total ELF files with DWARF info found: {str(all_dwarf_info_counter)}")
    return compiled_files