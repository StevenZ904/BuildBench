# No changes needed to count_result_file.py based on the instructions. Outputting the original file as is.

import json
import sys


if __name__ == '__main__':
    # first argument is the path to the JSON file
    file_path = "compiled_results/validation_cleaned_results.json"  # Update this path

    raw_json_file_path = "data/sampled_repos_385_cleaned_higher_split.jsonl"  # Update this path
    with open(raw_json_file_path, 'r') as file:
        lines = file.readlines()
        raw_data = [json.loads(line) for line in lines]
    
    with open(file_path, 'r') as file:
        data = json.load(file)

    if isinstance(data, dict):
        num_keys = len(data)
        print(f"Number of keys in the dictionary: {num_keys}")
    else:
        print("The JSON data is not a dictionary.")
    
    
    
    true_success_counter = 0
    # for x in data.keys():
    #     print(x)
        # print(data[x][0]['compiled_percentage'])
        # print(data[x][0]['compiled_percentage'] >= 0.05)
    star_counter = 0
    size_counter = 0
    total_list = []
    total_binary_func = 0
    total_source_func = 0
    
    for x in data:
        total_list.append(x)
        total_binary_func+=data[x][0]['len_binary_func']
        total_source_func+=data[x][0]['len_source_func']
        for y in raw_data:
            if x == y['name']:
                star_counter+=y['stargazers_count']
                size_counter+=y['size']
        if data[x][0]['compiled_percentage'] > 0.1:
            if data[x][0]['len_binary_func'] > 2:
                # print(data[x][0]['compiled_percentage'])
                # print(data[x][0]['compiled_percentage'] >= 0.05)
                # print(data[x][0]['compiled_percentage'] < 0.05)
                # print('True')
                true_success_counter+=1
            # else:            
    print(true_success_counter)
    print("The average number of stars is: ", star_counter/len(data))
    print("The average size is: ", size_counter/len(data))
    for x in total_list:
        print(x)
    print("The total number of binary functions is: ", total_binary_func)
    print("The total number of source functions is: ", total_source_func)
    