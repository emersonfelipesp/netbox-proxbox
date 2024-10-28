import requests

def get(**kwargs):
    
    owner = "netdevopsbr"
    repo = "netbox-proxbox"
    #branch = "develop"
    
    # Get variable passed from function
    if kwargs.get("filename"):
        filename = kwargs.get("filename")

        # Construct the API endpoint URL
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{filename}"
        
        # Make the GET request
        response = requests.get(url)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            # Retrieve the content from the response
            content_url = response.json()["download_url"]
        
            if content_url:
                markdown_content = requests.get(content_url)
                
                if markdown_content.status_code == 200:
                    return markdown_content.text
        else:
            # Print the error message if the request was not successful
            print(f"Error: {response.status_code} - {response.json()['message']}")