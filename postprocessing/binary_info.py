import os
import subprocess
import json
from multiprocessing import Manager
import re
from collections import defaultdict, Counter
import concurrent.futures
from elftools.elf.elffile import ELFFile

from typing import Iterable
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import convert_sets_to_lists
# c c++ binaries
# dwarf
# not stripped
# -O0 and -O2 (inlined functions) or any other optimizations
# inlined function

class Dwarf:
    
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
                
    @staticmethod
    def die_info_rec(die, indent_level='    '):
        """ A recursive function for showing information about a DIE and its
            children.
        """ 
        child_indent = indent_level + '  '
        for child in die.iter_children():
            Dwarf.die_info_rec(child, child_indent)



    @classmethod 
    def collect_func_start_line_numbers(cls, binary_path):
        funcname_to_funcline_and_file = {}
        elffile, dwarf_info = Dwarf.is_elf_has_dwarf(binary_path)

        for CU in dwarf_info.iter_CUs():
            try:
                # Caches DIE info
                top_DIE = CU.get_top_DIE()
                Dwarf.die_info_rec(top_DIE)
            except Exception as e:
                print("Error caching DIE info:", e)
                continue

            try:
                # For line mapping
                line_program = dwarf_info.line_program_for_CU(CU)
            except Exception as e:
                print("Error getting line program for CU:", e)
                continue

            for i in range(len(CU._dielist)):
                die = CU._dielist[i]
                #print(die)
                if die.tag != 'DW_TAG_subprogram':
                    continue

                try:
                    # Skip artificial or inlined functions
                    if Dwarf.is_artifical(die) or Dwarf.is_inlined(die) or Dwarf.is_abstract(die) :
                        continue
                except Exception as e:
                    print("Error checking artificial/inlined status for DIE:", e)
                    continue

                try:
                    func_name = Dwarf.get_name(die)
                    if not func_name:
                        #import ipdb; ipdb.set_trace()
                        print("Dwarf error: No function name found")
                        continue
                except Exception as e:
                    print("Error retrieving function name:", e)
                    continue

                try:
                    funcline = Dwarf.get_line_number(die)
                    if not funcline:
                        continue
                except Exception as e:
                    print("Error retrieving function line number:", e)
                    continue

                try:
                    file_index = Dwarf.get_file_index(die)
                    if not file_index:
                        continue
                except Exception as e:
                    print("Error retrieving file index:", e)
                    continue

                try:
                    # Get mapping from line program header
                    filepath = Dwarf.filename_and_decl_mapping(line_program, file_index)
                    funcname_to_funcline_and_file[func_name] = {
                        'line': funcline,
                        'filename': filepath
                    }
                except Exception as e:
                    print("Error mapping filename and line number:", e)
                    continue

        # Sort the dictionary by filename first (prioritizing .c files), then by line number
        sorted_funcname_to_funcline_and_file = dict(
            sorted(funcname_to_funcline_and_file.items(), key=lambda item: (
                item[1]['filename'].split('.')[-1],  # file extension
                item[1]['filename'],  # file name
                item[1]['line']  # line number
            ))
        )

        return sorted_funcname_to_funcline_and_file


    # 
    # DWARF Utils
    #

    @staticmethod
    def _get_die_attribute(die, attr_name):
        attr = die.attributes.get(attr_name, None)
        if attr:
            return attr.value
        
    # file index
    @staticmethod
    def get_file_index(die):
        return Dwarf._get_die_attribute(die, 'DW_AT_decl_file')
    
    # func name
    @staticmethod
    def get_name(die):
        fname = Dwarf._get_die_attribute(die, 'DW_AT_name')
        if fname is None:
       
            return None
        else:
            ### TODO: check if this is the right way to handle this
            #print("Dwarf._get_die_attribute(die, 'DW_AT_name')", Dwarf._get_die_attribute(die, 'DW_AT_name'))
            return fname.decode('ascii')
    
    @staticmethod
    def get_linkage_name(die):
        return Dwarf._get_die_attribute(die, 'DW_AT_linkage_name').decode('ascii')

    # func start addr   
    @staticmethod 
    def get_low_pc(die):
        return Dwarf._get_die_attribute(die, 'DW_AT_low_pc')
    
    # func line number
    @staticmethod
    def get_line_number(die):
        return Dwarf._get_die_attribute(die, 'DW_AT_decl_line')
    
    # compiler generated variables or functions (destructors, ...)
    @staticmethod
    def is_artifical(die):
        return Dwarf._get_die_attribute(die, 'DW_AT_artificial')
    
    @staticmethod
    def is_inlined(die):
        return Dwarf._get_die_attribute(die, 'DW_AT_inline')
    
    @staticmethod
    def is_external(die):
        return Dwarf._get_die_attribute(die, 'DW_AT_external')
    
    @staticmethod
    def is_abstract(die):
        return Dwarf._get_die_attribute(die, 'DW_AT_abstract_origin')
    
    @staticmethod
    def filename_and_decl_mapping(line_program, file_index):
        
        line_header = line_program.header
        filentry = line_header.file_entry[file_index - 1]
        dir_index = filentry.dir_index
        if dir_index > 0:
            dirname = line_header.include_directory[dir_index - 1]
            if type(dirname) == bytes:
                dirname = dirname.decode('utf-8')
        else:
            dirname = ''
            
        if filentry.name == None:
            filentry_name = ''
            print("Dwarf error: No file entry name found")            
        elif type(filentry.name) == bytes:
            filentry_name = filentry.name.decode('utf-8')
        else:
            filentry_name = filentry.name
            
        try:
            filepath = os.path.join(dirname, filentry_name)
        except Exception as e:
            print("Dwarf error: Error in file path", e)
            filepath = ''
        return filepath








class BinaryInfo :

    def __init__(self, name, path) -> None:
        self.name = name
        self.binary_path = path
        self.elf = None
        self.elffile = None
        self.dwarf_info = None
        self.stripped = None
        self.has_debug_info = None  
        self.arch = None
        self.language = None
        self.inlined_func = None
        self.optimization = set()
        self.cython = None
        self.elf_info = None
        self.hash = None
        # self.collect_binary_info()
        
    
    def __dir__(self) -> Iterable[str]:
        return {
            'name': self.name,
            'elf': self.elf,
            'arch': self.arch,
            'language': self.language,
            'optimization': self.optimization,
            'dwarf': self.dwarf_info,
            'stripped': self.stripped,
            'inlined_functions': self.inlined_func,
            'cython': self.cython,
            'path': self.binary_path,
            'hash':  self.hash,
            'path': self.binary_path
        }


    def is_elf(self, rb):       
        def is_pe_file(rb):
            rb.seek(0)
            bytes = rb.read(2)
            if bytes == b'MZ':
                return True
                     
        bytes = rb.read(4)
        if bytes == b"\x7fELF":
            rb.seek(0)
            self.elffile = ELFFile(rb)
            return 'ELF'
        elif is_pe_file(rb):
                return "PE"
            

    
    def collect_binary_info(self):

        # try:
            with open(self.binary_path, 'rb') as rb:
                if self.is_elf(rb) == 'PE':
                    print("It's a PE file!")
                    self.pe = 'PE'
                    return
                self.elf = 'ELF'
                if self.elffile.has_dwarf_info():
                    self.dwarf_info = self.elffile.get_dwarf_info()   
                    
                self.arch = self.elffile.get_machine_arch() 

            self.hash = self.md5_sum()  
            self.stripped, self.has_debug_info = self.is_stripped(self.run_file())
            self.language, self.optimization = self.get_opt_and_language() # type: ignore
            self.cython = self.is_cython()
            self.inlined_func = self.has_inlined_functions()
            self.elf_info = self.get_elf_info(self.run_file())
            # print("Stripped: ", self.stripped)
            # print("Language: ", self.language)
            # print("Optimization: ", self.optimization)
            # print("Cython: ", self.cython)
            # print("Inlined functions: ", self.inlined_func)
            # print("ELF info: ", self.elf_info)
            return self.stripped, self.language, self.optimization, self.cython, self.inlined_func, self.elf_info, self.has_debug_info
            
            # import ipdb; ipdb.set_trace()

        # except subprocess.CalledProcessError as call_e:
        #     print(call_e)
        # except Exception as e:
        #     print(e)

    def md5_sum(self):
        return subprocess.check_output(['md5sum', self.binary_path]).decode('utf-8').strip().split(' ')[0]
    
    def run_file(self):
        return subprocess.check_output(['file', self.binary_path]).decode('utf-8')       

    def run_readelf(self, cmd):
        return subprocess.run([f'readelf -wi {self.binary_path} | grep {cmd}'], capture_output=True, shell=True)

    def run_string(self, cmd):
        return subprocess.run([f'strings {self.binary_path} | grep "{cmd}"'], shell=True, capture_output=True) 
    
    def get_elf_info(self, run_str):
        file_tmp = run_str.strip().split(',')
        file_res = [f_res.strip() for f_res in file_tmp]   
        EFL_info = file_res[0].split(':')[1].strip()
        return EFL_info
    
    def is_stripped(self, run_str):
        file_tmp = run_str.strip().split(',')
        file_res = [f_res.strip() for f_res in file_tmp]
        
        is_stripped = False if 'not stripped' in file_res else True
        has_debug_info = True if 'with debug_info' in file_res else False
        return is_stripped, has_debug_info
    
    def get_opt_and_language(self):

        result = self.run_string(cmd="GNU C")
        # check c or cpp and optimization 
        # GNU C17 8.3.0 -mtune=generic -march=x86-64 -g -O0
        # print(result)
        if result.stdout:              
            res_lines = result.stdout.decode('utf-8').strip().split('\n')
            lang_res, opt_res = set(), set()
            for line in res_lines:                               
                str_tmp = line.strip().split(' ')
                str_res = [s_res.strip() for s_res in str_tmp]
                if not str_res:
                    continue
                # multiple languages!
                if str_res[0].strip() == 'GNU':
                    if 'C++' in str_res[1]:
                        lang_res.add('CPP')                            
                    elif len(str_res[1]) > 1:
                        if str_res[1][2].isdigit() and str_res[1][0] == 'C':
                            lang_res.add('C')
                    elif str_res[1][0] == 'C' and len(str_res[1]) == 1:
                        lang_res.add('C')

                # multiple optimization flags!        
                for s_res in str_res:
                    if s_res.startswith('-O'):
                        opt_res.add(s_res)
            # print("Language: ", lang_res)
            # print("Optimization: ", opt_res)
            if len(lang_res) == 1:       
                return lang_res.pop(), opt_res
            elif len(lang_res) > 1:
                return 'Both', opt_res
            else:
                return None, None
        else:
            print("No GNU C found")
            return None, None
    
    def is_cython(self):
        result = self.run_string(cmd="cython_runtime")
        return True if result.stdout else False
    
    def has_inlined_functions(self):
        result = self.run_readelf(cmd='DW_TAG_inlined_subroutine -m 1')
        return True if result.stdout.decode('utf-8') else False
    
    
    
    @classmethod
    def filter_binaries(cls, filter_: list):
        for elem in filter_:
            pass

    @classmethod
    def dump_binary_info(cls):
        pass


def get_binary_info_per_directory(binary_directory, save_path, binary_source_path=None) -> dict:
    repo_name = binary_directory.split('/')[-1]
    save_path = os.path.join(save_path, f'{repo_name}_binary_info.json')
    if os.path.exists(save_path):
        with open(save_path, 'r') as f:
            data = json.load(f)
            summary = data['summary']
        print(f"Binary info for {repo_name} already exists at {save_path}")
        return summary
    else:
        if binary_source_path is not None:
            with open(binary_source_path, 'r') as f:
                binary_files = json.load(f)
            # binary_files = [list(entry.keys())[0] for entry in data]
        else:
            raise ValueError("No binary files found for repo during extracting binary info : {}".format(repo_name))
        
        repo_binary_info = {}
        
        summary = {
            'stripped': 0,
            'has_debug_info': 0,
            'cython': 0,
            'inlined_func': 0,
            'optimization': Counter(),
            'elf_info': Counter(),
            'language': Counter()
        }
            
        for binary in binary_files:
            # try:
                binary_name = binary
                bin = BinaryInfo(binary_name, binary)
                stripped, language, optimization, cython, inlined_func, elf_info, has_debug_info = bin.collect_binary_info() 
                
                #type: ignore
                repo_binary_info[binary_name] = {
                    'stripped': stripped,
                    'has_debug_info': has_debug_info,
                    'language': language,
                    'optimization': optimization,
                    'cython': cython,
                    'inlined_func': inlined_func,
                    'elf_info': elf_info
                }
                
                summary['stripped'] += stripped
                summary['has_debug_info'] += has_debug_info
                summary['cython'] += cython
                summary['inlined_func'] += inlined_func
                
                summary['optimization'].update(optimization)
                summary['elf_info'][elf_info] += 1
                summary['language'][language] += 1            
            # except Exception as e:
            #     print(e)
            #     continue

        result = {"repo_name": repo_name, "binary_info": repo_binary_info, "summary": summary}
        result = convert_sets_to_lists(result)
        with open(save_path, 'w') as f:
            json.dump(result, f)
    
    return summary

            
def get_binary_info_per_directory_wrapper(directory, save_directory, binary_source_path=None):
    try:
        return get_binary_info_per_directory(directory, save_directory, binary_source_path)
    except Exception as e:
        print(f"Error processing {directory}: {e}")
        return None

GLOBAL_SUMMARY = {
    'stripped': 0,
    'has_debug_info': 0,
    'cython': 0,
    'inlined_func': 0,
    'optimization': Counter(),
    'elf_info': Counter(),
    'language': Counter()
}

def post_processing_wrapper(binary_directory, save_directory, binary_function_directory=None, max_workers=8):

    global_summary = GLOBAL_SUMMARY.copy()
    directories = [
        os.path.join(binary_directory, d)
        for d in os.listdir(binary_directory)
        if os.path.isdir(os.path.join(binary_directory, d))
    ]

    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(get_binary_info_per_directory_wrapper, directory, save_directory): directory
            for directory in directories
        }
        for future in concurrent.futures.as_completed(futures):
            repo_bin_info_summary = future.result()
            
            if repo_bin_info_summary is None:
                continue
            
            global_summary['stripped'] += repo_bin_info_summary['stripped']
            global_summary['has_debug_info'] += repo_bin_info_summary['has_debug_info']
            global_summary['cython'] += repo_bin_info_summary['cython']
            global_summary['inlined_func'] += repo_bin_info_summary['inlined_func']
            global_summary['optimization'].update(repo_bin_info_summary['optimization'])
            global_summary['elf_info'].update(repo_bin_info_summary['elf_info'])
            global_summary['language'].update(repo_bin_info_summary['language'])

            # Save global summary to JSON
            summary_path = os.path.join(save_directory, "global_summary.json")
            with open(summary_path, "w") as f:
                json.dump({
                    'stripped': global_summary['stripped'],
                    'has_debug_info': global_summary['has_debug_info'],
                    'cython': global_summary['cython'],
                    'inlined_func': global_summary['inlined_func'],
                    'optimization': dict(global_summary['optimization']),
                    'elf_info': dict(global_summary['elf_info']),
                    'language': dict(global_summary['language'])
                }, f, indent=4)
            
    print("Global summary:", global_summary)
    print(f"Global summary saved to {summary_path}")
       
     
            
# Example usage:
# BinaryInfo('redis-cli', 'compiled_repos/redis/src/adlist.o').collect_binary_info()
# summary = get_binary_info_per_directory('compiled_repos/openssl', 'output/')
