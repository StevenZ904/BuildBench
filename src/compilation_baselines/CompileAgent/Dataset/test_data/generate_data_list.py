import json
import sys
raw_data_file_path = sys.argv[1] 

with open(raw_data_file_path, "r") as f:
    repo_list = f.readlines()

repo_data_list = []

for repo in repo_list:
    repo = repo.strip()
    if not repo:
        continue
    repo_data = {
        "name": repo.split("/")[-1],
        "url": repo
    }
    repo_data_list.append(repo_data)

result_file_path = raw_data_file_path.replace(".txt", ".json")
with open(result_file_path, "w") as f:
    json.dump(repo_data_list, f, indent=4)
    