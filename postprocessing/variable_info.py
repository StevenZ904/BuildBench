import logging
import os
import json
from elftools.elf.elffile import ELFFile

from elftools.dwarf.locationlists import (
    LocationEntry, LocationExpr, LocationParser)
from elftools.dwarf.descriptions import (
    describe_DWARF_expr, _import_extra, describe_attr_value,set_global_machine_arch)
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import concurrent.futures
from time import time
from tqdm import tqdm
l = logging.getLogger('main')
from utils import safe_log, find_linux_compiled_artifacts

VARIABLE_INFO_METRICS = {
    "unique_variable_count": 0,
    "total_variable_count": 0,
    "average_variables_per_function": 0.0,
    "global_variable_count": 0,
    "unique_global_variable_count": 0,
    "argument_count": 0,
    "distinct_type_count": 0
}



class Dwarf_info:
    
    @staticmethod
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
                



def is_elf(binary_path: str):

    with open(binary_path, 'rb') as rb:
        if rb.read(4) != b"\x7fELF":
            l.error(f"File is not an ELF format: {binary_path}")
            return None
        rb.seek(0)
        elffile = ELFFile(rb)
        if not elffile.has_dwarf_info():
            l.error(f"No DWARF info found in: {binary_path}")
            return None
        return elffile.get_dwarf_info()

class Dwarf:
    """
    Collects variables from an ELF binary with DWARF info:
      - Global variables
      - Function parameters
      - Local variables

    Omits any use of DW_AT_linkage_name or mangled names.
    """

    def __init__(self, binary_path, binary_name="unknown") -> None:
        self.binary_path = binary_path
        self.binary_name = binary_name
        self.dwarf_info  = is_elf(self.binary_path)
        self.argument_count = 0
        # Mapping of function_name (or address fallback) -> list of variable/param names
        self.vars_in_each_func = defaultdict(list)

        # Load DWARF data now
        self._load()

    def _load(self):
        """Populate vars_in_each_func by reading from DWARF info."""
        if not self.dwarf_info:
            l.error(f"Failed to load DWARF information for: {self.binary_path}")
            return

        self.vars_in_each_func = self._read_dwarf()
        # self.metrics = self.count(self.vars_in_each_func)


    # def count(self, variable_in_each_func):
    #     # (a) Unique variable count (by name)
    #     all_var_names = set(file
    #     for fn, var_list in variable_in_each_func.items():
    #         for varinfo in var_list:
    #             all_var_names.add(varinfo)
    #     unique_variable_count = len(all_var_names)  
        
    #     # (b) Average variables per function (exclude 'global_vars')
    #     function_counts = []
    #     for fn, var_list in variable_in_each_func.items():
    #         if fn == "global_vars":
    #             continue
    #         function_counts.append(len(var_list))
    #     average_variables_per_function = 0.0
    #     if function_counts:
    #         average_variables_per_function = sum(function_counts) / len(function_counts)      
            
    #     # (c) Global variable count
    #     global_variable_count = len(variable_in_each_func["global_vars"])

    #     # (d) Argument (formal parameter) count
    #     #     We already tracked it via 'argument_count'.


        
    #     return {
    #         "unique_variable_count": unique_variable_count,
    #         "average_variables_per_function": average_variables_per_function,
    #         "global_variable_count": global_variable_count,
    #         "argument_count": self.argument_count,
    #     }
                
                
    # def get_variable_type_name(die):
    #     """
    #     Return a best-effort type name for a variable DIE by:
    #       1) Looking at DW_AT_type -> offset -> type DIE
    #       2) If type DIE has DW_AT_name, return it
    #       3) If type DIE references a deeper type (DW_AT_type),
    #          recursively follow it
    #       4) If none found, return "unknown"
    #     """
    #     if 'DW_AT_type' not in die.attributes:
    #         return "unknown"

    #     type_offset = die.attributes['DW_AT_type'].value
    #     type_die    = dwarf_info.get_DIE_at(type_offset)

    #     return resolve_type_name(type_die)

    # def resolve_type_name(type_die):
    #     """Helper to recursively follow DW_AT_type references until we find a DW_AT_name or run out."""
    #     if not type_die:
    #         return "unknown"

    #     name_attr = type_die.attributes.get('DW_AT_name')
    #     if name_attr:
    #         return name_attr.value.decode('ascii', errors='replace')

    #     # If this type DIE has its own DW_AT_type, follow it recursively
    #     if 'DW_AT_type' in type_die.attributes:
    #         nested_offset = type_die.attributes['DW_AT_type'].value
    #         nested_die    = dwarf_info.get_DIE_at(nested_offset)
    #         return resolve_type_name(nested_die)

    #     return "unknown"

    def _read_dwarf(self):
        """
        Iterates through the compilation units (CUs) in the DWARF info.
        Collects global variables and subprogram variables/parameters.

        Returns:
            dict(func_name -> list_of_var_names)
        """
        vars_in_each_func = defaultdict(list)

        for CU in self.dwarf_info.iter_CUs():
            try:
                current_func_name = 'global_vars'
                tmp_list = []
                global_vars_list = []

                top_DIE = CU.get_top_DIE()
                self._die_info_rec(top_DIE)

                # We iterate over all DIEs in the CU
                for die in CU._dielist:
                    #------------------------------------------
                    # 1) Handle (global) DW_TAG_variable
                    #------------------------------------------
                    if die.tag == 'DW_TAG_variable':
                        # Only consider variables that have a location
                        if not die.attributes.get('DW_AT_location'):
                            continue
                        if self._is_artificial(die):
                            continue
                        var_name = self._get_name(die)
                        if var_name:
                            tmp_list.append(var_name)

                    #------------------------------------------
                    # 2) Handle function parameters (DW_TAG_formal_parameter)
                    #------------------------------------------
                    elif die.tag == 'DW_TAG_formal_parameter':
                        if self._is_artificial(die):
                            continue
                        param_name = self._get_name(die)
                        if param_name:
                            self.argument_count += 1
                            tmp_list.append(param_name)

                    #------------------------------------------
                    # 3) When we encounter a Subprogram, treat
                    #    it as the start of a new function context
                    #------------------------------------------
                    elif die.tag == 'DW_TAG_subprogram':
                        if self._is_artificial(die):
                            continue

                        func_name = self._get_subprogram_name(die)
                        if not func_name:
                            continue

                        # Append any discovered variables to the
                        # current function/global before switching
                        if current_func_name == 'global_vars':
                            global_vars_list.extend(tmp_list)
                            vars_in_each_func[current_func_name].extend(global_vars_list)
                        else:
                            vars_in_each_func[current_func_name].extend(tmp_list)

                        # Switch context to the newly found subprogram
                        current_func_name = func_name
                        tmp_list = []

                #------------------------------------------
                # At the end of the CU, flush remaining vars
                #------------------------------------------
                if current_func_name == 'global_vars':
                    vars_in_each_func[current_func_name].extend(tmp_list)
                else:
                    vars_in_each_func[current_func_name].extend(tmp_list)

            except Exception as e:
                l.error(f"Error in _read_dwarf :: {self.binary_name} :: {e}")

        return vars_in_each_func

    # ----------------------------------------------------------------------
    # Helper methods
    # ----------------------------------------------------------------------

    def _get_subprogram_name(self, die):
        """
        Return the best name we can find for a subprogram DIE:
         1) DW_AT_name
         2) DW_AT_low_pc (converted to string)
         3) DW_AT_ranges' first entry (if available)

        (We omit DW_AT_linkage_name to keep things simpler.)
        """
        name = self._get_name(die)
        if name:
            return name

        low_pc = die.attributes.get('DW_AT_low_pc')
        if low_pc:
            return str(low_pc.value)

        ranges_attr = die.attributes.get('DW_AT_ranges')
        if ranges_attr:
            try:
                range_list = self.dwarf_info.range_lists().get_range_list_at_offset(ranges_attr.value)
                if len(range_list):
                    return str(range_list[0].begin_offset)
            except:
                pass

        return None

    def _get_name(self, die):
        """Retrieve the name from DW_AT_name."""
        name_attr = die.attributes.get('DW_AT_name')
        if name_attr:
            return name_attr.value.decode('ascii', errors='replace')
        return None

    def _is_artificial(self, die):
        """
        Check if a DIE is marked as 'artificial' by the compiler (e.g., 
        compiler-generated parameters or functions like constructors/destructors).
        """
        return die.attributes.get('DW_AT_artificial') is not None

    def _die_info_rec(self, die, indent_level='    '):
        """
        Recursive function for visiting children. If you don't need to
        traverse or print child DIE info, you can remove this entirely.
        """
        for child in die.iter_children():
            self._die_info_rec(child, indent_level + '  ')


    # ----------------------------------------------------------------------
    # Classmethods for convenience
    # ----------------------------------------------------------------------
    @classmethod
    def get_vars_in_each_func(cls, binary_path):
        """
        Create a Dwarf instance and return its dictionary of
        function_name -> [variables/params].
        """
        dwarf = cls(binary_path, binary_name="unknown")
        return dwarf.vars_in_each_func

    @classmethod
    def get_vars_for_func(cls, binary_path, func_name):
        """
        Create a Dwarf instance and return the combined list of
        variables for the specified function plus global variables.
        """
        dwarf = cls(binary_path, binary_name="unknown")
        return dwarf.vars_in_each_func[func_name] + dwarf.vars_in_each_func['global_vars']


def get_variable_info_per_directory_wrapper(binary_directory, output_directory, repo_name = None, binary_source_path = None):
    if repo_name is None:
        repo_name = binary_directory.split('/')[-1]
    try:
        per_repo_metrics = VARIABLE_INFO_METRICS.copy()
        save_path = os.path.join(output_directory, f'{repo_name}_variable_info.json')
        auxiliary_info_save_path = os.path.join(output_directory, f'{repo_name}_unique_variables.json')
        summary_save_path = os.path.join(output_directory, f'{repo_name}_summary_variable_info.json')
        
        if os.path.exists(summary_save_path):
            with open(summary_save_path, 'r') as f:
                per_repo_metrics = json.load(f)
            print(f"Variable info for {repo_name} already exists at {summary_save_path}")
            
            with open(auxiliary_info_save_path, 'r') as f:
                auxiliary_info = json.load(f)
                
            return per_repo_metrics, auxiliary_info
        
        else:
            if binary_source_path is not None:
                with open(binary_source_path, 'r') as f:
                    binary_files = json.load(f)
                # binary_files = [list(entry.keys())[0] for entry in data]
            else:
                raise ValueError("No binary files found for repo during extracting variable info: {}".format(repo_name))
            
            per_repo_variable_in_func = {}
            num_argument_variables = 0
            all_variables_in_repo = []
            all_global_variables_in_repo = []
            num_variables_in_functions = []
            
            for binary in binary_files:
                
                binary_path = os.path.join(binary_directory, binary)
                dwarf = Dwarf(binary_path, binary_name=binary)
                variable_in_func = dwarf.vars_in_each_func # dict(func_name : list_of_var_names)
                per_repo_variable_in_func[binary] = variable_in_func
                num_argument_variables += dwarf.argument_count

                for key, value in variable_in_func.items():
                    # Key is function name or 'global_vars'
                    # Value is list of variable names
                    if key == 'global_vars':
                        all_global_variables_in_repo.extend(value)
                    else:
                        all_variables_in_repo.extend(value)
                        num_variables_in_functions.append(len(value)) ### Not counting global variables for this metric
            
            unique_variables_in_repo = set(all_variables_in_repo)
            unique_global_variables_in_repo = set(all_global_variables_in_repo)
            per_repo_metrics["unique_variable_count"] = len(unique_variables_in_repo)
            per_repo_metrics["total_variable_count"] = len(all_variables_in_repo)
            per_repo_metrics["average_variables_per_function"] = sum(num_variables_in_functions) / len(num_variables_in_functions)
            per_repo_metrics["global_variable_count"] = len(all_global_variables_in_repo)
            per_repo_metrics["unique_global_variable_count"] = len(unique_global_variables_in_repo)
            per_repo_metrics["argument_count"] = num_argument_variables
            
            with open(save_path, 'w') as f:
                json.dump(per_repo_variable_in_func, f, indent=4)
            print(f"Saved variable info for {repo_name} at {save_path}")
        
            with open(auxiliary_info_save_path, 'w') as f:
                auxiliary_info = {
                    "unique_variables_in_repo": list(unique_variables_in_repo), "unique_global_variables_in_repo": list(unique_global_variables_in_repo),
                    "num_variables_in_functions":num_variables_in_functions}
                json.dump(auxiliary_info, f, indent=4)
            print(f"Saved unique variable info for {repo_name} at {auxiliary_info_save_path}")
            
            with open(summary_save_path, 'w') as f:
                json.dump(per_repo_metrics, f, indent=4)
            print(f"Saved summary variable info for {repo_name} at {summary_save_path}")   
            
        return per_repo_metrics, auxiliary_info
    
    except Exception as e:
        print(f"Error in extracting variable information for repo {repo_name}: {e}")
        return None, None, None

def wrapper(binary_parent_directory, output_directory):
    start_time = time()
    global_metrics = VARIABLE_INFO_METRICS.copy()
    directories = [
        os.path.join(binary_parent_directory, d)
        for d in os.listdir(binary_parent_directory)
        if os.path.isdir(os.path.join(binary_parent_directory, d))
    ]

    with concurrent.futures.ProcessPoolExecutor(max_workers=16) as executor:
            futures = {
                executor.submit(get_variable_info_per_directory_wrapper, directory, output_directory): directory
                for directory in directories
            }
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures)):
                per_repo_metrics = future.result()
                
                if per_repo_metrics is None:
                    continue
                
                else:
                    for key, value in per_repo_metrics.items():
                        global_metrics[key] += value
                    with open(os.path.join(output_directory, 'global_variable_info.json'), 'w') as f:
                        json.dump(global_metrics, f, indent=4)
    
    print("Global metrics:")
    print(global_metrics)
    
    end_time = time()
    print(f"Total time taken: {end_time - start_time} seconds")
    return global_metrics
            
            
 
if __name__ == '__main__':
    # import sys
    # if len(sys.argv) < 2:
    #     print("Usage: dwarf_info.py <binary_path>")
    #     sys.exit(1)
    # binary_path = sys.argv[1]
    # dwarf = Dwarf(binary_path, binary_name="unknown")
    # print(dwarf.vars_in_each_func)
    # print(dwarf.linkage_name_to_func_name)
    # print(Dwarf.get_vars_in_each_func(binary_path))
    # print(Dwarf.get_vars_for_func(binary_path, 'main'))
    
    # Example usage:
    # get_variable_info_per_directory_wrapper(
    #     binary_directory="compiled_repos/example_repo/",
    #     output_directory="variable_info",
    #     binary_source_path="compiled_results/example_repo/binary_functions.json"
    # )
    pass