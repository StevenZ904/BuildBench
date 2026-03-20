import os
from elftools.elf.elffile import ELFFile
# 
# collect function details from binary info
class BinaryInfo:

    def __init__(self, binary_name, binary_path):
        self.binary_name = binary_name
        self.binary_path = binary_path
        self.hash = None
        self.language = None
        self.function_count = 0  
        self.functions = {}  
        self.function_line_numbers()

    def set_function_count(self, count):
        self.function_count = count

    def add_function(self, function_obj):
        self.functions[function_obj.name] = function_obj

    def get_function(self, function_name):
        return self.functions.get(function_name, None)

    def get_binary_name(self):
        return self.binary_name
    
    def function_line_numbers(self):
        return Dwarf().collect_func_start_line_numbers(self.binary_path)


class Function:

    def __init__(self, name, addr, decompiled_code):
        self.name = name
        self.addr = addr


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

    # @classmethod 
    # def collect_func_start_line_numbers(cls, binary_path):
    #     # import ipdb; ipdb.set_trace()
    #     funcname_to_funcline_and_file = {}
    #     elffile, dwarf_info = Dwarf.is_elf_has_dwarf(binary_path)

    #     for CU in dwarf_info.iter_CUs():
    #         try:
    #             # import ipdb; ipdb.set_trace()
    #             # caches die info 
    #             top_DIE = CU.get_top_DIE()
    #             Dwarf.die_info_rec(top_DIE)
                
    #             # for line mapping
    #             line_program = dwarf_info.line_program_for_CU(CU)

    #             for i in range(0, len(CU._dielist)):
    #                 # import ipdb; ipdb.set_trace()
    #                 die = CU._dielist[i]
    #                 if die.tag == 'DW_TAG_subprogram':
    #                     if Dwarf.is_artifical(die) or Dwarf.is_inlined(die):
    #                         continue
    #                     func_name = Dwarf.get_name(die) 
    #                     if not func_name:
    #                         print("Dwarf error: No function name found 123")
    #                         continue 

    #                     funcline =  Dwarf.get_line_number(die)
    #                     if not funcline:
    #                         continue

    #                     file_index = Dwarf.get_file_index(die)
    #                     if not file_index:
    #                         continue

    #                     # get mapping from lineprogram header
    #                     filepath = Dwarf.filename_and_decl_mapping(line_program, file_index)
    #                     funcname_to_funcline_and_file[func_name] = {'line': funcline,
    #                                                                 'filename': filepath}
      
    #         except Exception as e:
    #             print("Validation error", e, die)
    #     # import ipdb; ipdb.set_trace()        
    #      # Sort the dictionary by filename first (with .c files prioritized) and then by line number
    #     sorted_funcname_to_funcline_and_file = dict(sorted(funcname_to_funcline_and_file.items(), key=lambda item: (
    #     item[1]['filename'].split('.')[-1],  # file extension
    #     item[1]['filename'],  # file name
    #     item[1]['line']  # line number
    #     )))

    #     # print(sorted_funcname_to_funcline_and_file)
    #     return sorted_funcname_to_funcline_and_file


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
                    
                    # Skip system headers
                    if '/usr/include' in filepath:
                        continue
                    
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

