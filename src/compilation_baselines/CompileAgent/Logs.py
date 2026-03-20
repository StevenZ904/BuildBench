import datetime
import logging
import json
import csv
import os

from Config import *

def is_elf(file):
    with open(file,"rb") as f:
        return f.read(4) == b"\x7fELF"
    
def is_archive(file):
    with open(file, "rb") as f:
        return f.read(8) in {b'!<arch>\n',b'!<thin>\n'}

def is_compiled(local_path, target_files, strict=False):
    if not target_files:
        return None
    elf_file_list = []
    for root, dirs, files in os.walk(local_path):
        for file in files:
            fp = os.path.join(root,file)
            if is_elf(fp) or is_archive(fp):
                elf_file_list.append(file)
    if strict: # only if all target files are in the file list
        for file in target_files:
            file = os.path.basename(file)
            if file not in elf_file_list:
                return False
        return True
    else: # if any target file is in the file list
        for file in target_files:
            file = os.path.basename(file)
            if file in elf_file_list:
                return True
        return False

def assemble_all_to_txt(template,tools,input,output,intermediate_steps):
    tool_names = ", ".join([tool.name for tool in tools])
    tool_info = "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
    agent_scratchpad = ""
    for idx, (action, value) in enumerate(intermediate_steps):
        model_response = action.log
        tool_response = value
        agent_scratchpad += "\nThought: " + model_response if idx!=0 else model_response
        agent_scratchpad += "\nObservation: " + str(tool_response)
    agent_scratchpad += "\nThought: " + output
    result = template.format(tools=tool_info,tool_names=tool_names,input=input,agent_scratchpad=agent_scratchpad)
    return result

def assemble_all_to_json(template,tools,input,output,intermediate_steps):
    tool_names = ", ".join([tool.name for tool in tools])
    tool_info = "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
    init_question = template.format(tools=tool_info,tool_names=tool_names,input=input,agent_scratchpad="")
    _pair = [init_question]
    log_list = []
    for idx, (action, value) in enumerate(intermediate_steps):
        model_response = action.log
        _pair.append(model_response)
        log_list.append(_pair)
        tool_response = value
        _pair = [tool_response]
    final_output = output
    _pair.append(final_output)
    log_list.append(_pair)
    return log_list

def save_logs(log_path,proj_name,question,tools,res,tools_logs,local_path,checker_ok,model_ok):
    # logging process
    now = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S:%f")
    project_log_path = os.path.join(log_path, proj_name)
    if not os.path.exists(project_log_path):
        os.makedirs(project_log_path)
    log_local_file = os.path.join(project_log_path, f"{now}.txt")
    logging.info(f"[-] Saving logs to {log_local_file}")
    
    with open(log_local_file,"w") as file:
        s = assemble_all_to_txt(template,tools,question,res["output"],res["intermediate_steps"])
        file.write(s)
        
    # Save a copy as latest log
    latest_log_file = os.path.join(project_log_path, "latest.txt")
    with open(latest_log_file,"w") as file:
        s = assemble_all_to_txt(template,tools,question,res["output"],res["intermediate_steps"])
        file.write(s)
        
            
    log_local_file_json = log_local_file.replace('.txt','.json')
    logging.info(f"[-] Saving logs to {log_local_file_json}")
    with open(log_local_file_json,"w") as file:
        s = assemble_all_to_json(template,tools,question,res["output"],res["intermediate_steps"])
        json.dump({"autocompiler":s, "tools":tools_logs},file,indent='\t')

    # Save a copy as latest log in json format
    latest_log_file_json = latest_log_file.replace('.txt','.json')
    with open(latest_log_file_json,"w") as file:
        s = assemble_all_to_json(template,tools,question,res["output"],res["intermediate_steps"])
        json.dump({"autocompiler":s, "tools":tools_logs},file,indent='\t')
        
        
    # logging result
    run_id = res["run_id"]
    log_url = LOG_URL_TEMPLATE.format(run_id=run_id)
    process_id = os.getpid()
    process_log_csv_file_path = os.path.join(PROCESS_LOG_CSV_PATH, f"{process_id}-{now}.csv")
    with open(process_log_csv_file_path,"a") as file:
        csv_writer = csv.writer(file)
        csv_writer.writerow([run_id, log_url, log_local_file, local_path, model_ok, checker_ok])