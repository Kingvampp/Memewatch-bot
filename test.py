import requests
import time

def check_bonk_price():
    # CoinGecko API endpoint for BONK token
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bonk&vs_currencies=usd"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        # Extract BONK price in USD
        bonk_price = data['bonk']['usd']
        print(f"Current BONK price: ${bonk_price:.10f}")
        
    except Exception as e:
        print(f"Error fetching BONK price: {e}")

def main():
    # Run for 1 minute (6 iterations of 10 seconds each)
    for _ in range(6):
        check_bonk_price()
        # Wait for 10 seconds before checking again
        time.sleep(10)

if __name__ == "__main__":
    main()
