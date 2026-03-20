import json
import os
import sys
def parse_log(log_line):
    try:
        # Try to parse the line as a JSON object
        log = json.loads(log_line)
    except json.JSONDecodeError:
        # If it's not a valid JSON, it's likely the first line that indicates the start of the session
        return None

    # Remove specific keys
    keys_to_remove = ["source_id", "timestamp", "thread_id"]
    for key in keys_to_remove:
        log.pop(key, None)
    
    if "json_state" in log and isinstance(log["json_state"], str):
        try:
            log["json_state"] = json.loads(log["json_state"])
            # Remove specific keys
            keys_to_remove = ["valid"]
            for key in keys_to_remove:
                log['json_state'].pop(key, None)
        except json.JSONDecodeError:
            # If parsing fails, keep it as a string
            pass

    # Determine the type of log entry based on the available fields
    if log.get("event_name") == "received_message":
        if log['source_name'] in ["speaker_selection_agent", 'checking_agent']:
            return None
        log_type = "received_message"

    elif log.get("event_name") == "reply_func_executed":
        if log['source_name'] in ["speaker_selection_agent", 'checking_agent']:
            return None
        if log['json_state'].get('reply_func_name', '') == 'check_termination_and_human_reply':
            return None
        if not log['json_state'].get('reply', None):
            return None
        log_type = "function_execution"
    
    elif "source_id" in log and "source_name" in log:
        log_type = "event_log"
    
    elif "client_id" in log and "wrapper_id" in log:
        if 'api_key' in log.get('json_state', {}):
            return None
        if log['request']['messages'][0]['content'][:63] == 'You are in a role play game. The following roles are available:':
            return None
        log_type = "client_initialization"
    
    elif "id" in log and "agent_name" in log:
        return None
        # log_type = "agent_initialization"
    
    else:
        log_type = "unknown"

    # Add the determined type to the log
    log["type"] = log_type

    return log

def process_logs(file_path):
    parsed_logs = []

    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            parsed_log = parse_log(line)
            if parsed_log:
                parsed_logs.append(parsed_log)

    return parsed_logs

def filter_logs_by_type(logs, log_type):
    if log_type == '':
        return logs
    return [log for log in logs if log["type"] == log_type]

def generate_parsed_files(log_dir_path):
    for repo_folder in os.listdir(log_dir_path):
        for auto_gen_fold in os.listdir(os.path.join(log_dir_path, repo_folder)): ### NOTE: Hardcoded to only look at auto_gen_fold folder
            
            for log_file in os.listdir(os.path.join(log_dir_path, repo_folder, auto_gen_fold)):
                file_path = os.path.join(log_dir_path, repo_folder, auto_gen_fold, log_file)
                
                new_file_path = file_path.replace('.jsonl', '_parsed.txt')
                    
                with open(new_file_path, 'w') as f:
                    # Path to your JSONL file

                    # Parse the logs
                    logs = process_logs(file_path)

                    # received_message, function_execution, event_log, client_initialization
                    # agent_initialization, unknown  -- There shouldn't be any logs of these types
                    log_type_to_view = 'function_execution'
                    filtered_logs = filter_logs_by_type(logs, log_type_to_view)
                    
                    if filtered_logs:
                        for log in filtered_logs:
                            print("-" * 50, file=f)
                            print(log['source_name'], file=f)
                            print("-" * 50, file=f)
                            
                            if type(log['json_state']['reply']) == dict:
                                if 'tool_calls' in log['json_state']['reply'] and log['json_state']['reply']['tool_calls']:
                                    print(log['json_state']['reply']['content'], file=f)
                                    print('-' * 50, file=f)
                                    print('TOOLS CALLED:', file=f)
                                    print('-' * 50, file=f)
                                    for tool_call in log['json_state']['reply']['tool_calls']:
                                        print('Calling Function --', end=' ', file=f)
                                        print(f"{tool_call['function']['name']}({tool_call['function']['arguments']})", file=f)
                                    print('-' * 50, file=f)
                                elif 'tool_responses' in log['json_state']['reply'] and log['json_state']['reply']['tool_responses']:
                                    print('-' * 50, file=f)
                                    print('TOOLS RESPONSES:', file=f)
                                    print('-' * 50, file=f)
                                    for tool_response in log['json_state']['reply']['tool_responses']:
                                        print(tool_response['content'], file=f)
                                        print('-' * 35, file=f)
                                        print('-' * 35, file=f)
                                    print('-' * 50, file=f)
                            
                            elif type(log['json_state']['reply']) == list:
                                for reply in log['json_state']['reply']:
                                    print(reply['content'], file=f)
                                    print('-' * 50, file=f)
                                    for tool_call in reply['tool_calls']:
                                        print('Calling Function --', end=' ', file=f)
                                        print(f"{tool_call['function']['name']}({tool_call['function']['arguments']})", file=f)
                                    print('-' * 50, file=f)
                            
                            else:
                                try:
                                    print(log['json_state']['reply'], file=f)
                                except:
                                    print(log['json_state']['reply'].encode('utf-8'), file=f)
                            
                            print('\n\n', file=f)
                    
                    else:
                        print(f"No logs found for the type: {log_type_to_view}", file=f)    

if __name__ == "__main__":
    # Path to your JSONL file
    args = sys.argv
    if len(args) != 2:
        print("Usage: python log_parse.py <path_to_autogen_logs>")
        sys.exit(1)
    
    log_dir_path = args[1]
    generate_parsed_files(log_dir_path)