import requests
from datetime import datetime

def get_fear_greed_index_api():
    """
    Fetches the CNN Fear & Greed Index using the provided API.
    Returns the current index score and rating.
    """
    # Get the current date in the required format YYYY-MM-DD
    current_date = datetime.now().strftime('%Y-%m-%d')
    url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{current_date}"
    print(f"Requesting URL: {url}") # Log the URL

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        # Extract score and rating from the nested structure
        score = data.get("fear_and_greed", {}).get("score")
        rating = data.get("fear_and_greed", {}).get("rating")

        if score is not None and rating is not None:
            return rating.capitalize(), str(score) # Return category and score as strings
        else:
            return "Error", "Could not find score or rating in API response."

    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}") # Log the error
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response Status Code: {e.response.status_code}")
            print(f"Response Headers: {e.response.headers}")
        return "Error", f"API request failed: {e}"
    except Exception as e:
        print(f"An unexpected error occurred: {e}") # Log unexpected errors
        return "Error", f"An unexpected error occurred: {e}"

if __name__ == "__main__":
    print("Fetching Fear & Greed Index from API...")
    category, index_value = get_fear_greed_index_api()
    print(f"Current Fear & Greed Index: {category} ({index_value})")