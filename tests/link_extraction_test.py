import re
import os
from typing import Dict, List
from urllib.parse import urlparse, unquote
from tools import extract_and_process_links

# Example Usage
if __name__ == "__main__":
    # Path to your local README file
    readme_file_path = 'cloned_repos/obs-studio/README.rst'  # Update this path as needed
    
    # Ensure the README file exists
    if not os.path.isfile(readme_file_path):
        print(f"README file not found at: {readme_file_path}")
        exit(1)
    
    # Sample text simulating an LLM response with embedded links
    sample_text = """
    ### Extracted Instructions:

    1. **Clone the Repository:**
        ```bash
        git clone https://github.com/username/sample-project.git
        cd sample-project
        ```

    2. **Install Dependencies:**
        ```bash
        npm install
        ```
        Ensure you have Node.js installed. ###[external][https://nodejs.org/]###

    3. **Configure Environment Variables:**
        - Create a `.env` file in the root directory.
        - Add the following variables:
            ```
            API_KEY=your_api_key
            DB_HOST=localhost
            DB_PORT=5432
            ```

    4. **Run the Application:**
        ```bash
        npm start
        ```
        For more details, refer to the ###[internal][docs/sphinx/requirements.txt]###.

    ### **Contributing:**
    Please read the ###[internal][https://github.com/obsproject/obs-studio/blob/master/CONTRIBUTING.rst]### for guidelines.

    For additional resources, visit the [OpenAI website](https://www.openai.com).
    """

    # Extract and process links
    extracted_links = extract_and_process_links(sample_text, readme_file_path)

    # Display the results
    print("Extracted External Links:")
    for url in extracted_links['external']:
        print(f"- {url}")

    print("\nExtracted Internal Links:")
    for link in extracted_links['internal']:
        print(f"- {link}")
