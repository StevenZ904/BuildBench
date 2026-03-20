from pathlib import Path
from docker.errors import ContainerError
from autogen.coding import LocalCommandLineCodeExecutor, DockerCommandLineCodeExecutor
# Assuming DockerCommandLineCodeExecutor is properly imported
# from the provided class definition

# Define the executor
executor = DockerCommandLineCodeExecutor(
    image="buildbench/llm_assisted_compilation:2",  # Use the docker image
    container_name='autogen_docker_executor',  # Name of the container
    timeout=60,  # Timeout for each code execution in seconds
    work_dir=Path("."),  # Work directory in the container
    bind_dir=Path(".")  # Bind project directory on the host
)

# Function to check if a directory exists within the container
def check_directory_exists(executor: DockerCommandLineCodeExecutor, directory_name: str) -> bool:
    try:
        # Run the command 'ls /workspace' to list directories inside /workspace (bound to host directory)
        result = executor._container.exec_run(f"ls /workspace/cloned_repos/")
        output = result.output.decode("utf-8")

        # Print the output (for debugging purposes)
        print("Output from container ls command:\n", output)

        # Check if the specific directory exists in the output
        if directory_name in output:
            print(f"Directory '{directory_name}' exists in /workspace.")
            return True
        else:
            print(f"Directory '{directory_name}' does not exist in /workspace.")
            return False

    except ContainerError as e:
        print(f"Error executing the container command: {e}")
        return False

# Example usage to check if 'cloned_repo' exists
directory_to_check = "linikatz"
directory_exists = check_directory_exists(executor, directory_to_check)
# Stop the executor once done
executor.stop()
