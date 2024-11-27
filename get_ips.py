import socket
import requests

def get_ip_info():
    ip_info = {}
    
    # Get local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_info['local_ip'] = s.getsockname()[0]
        s.close()
    except Exception as e:
        ip_info['local_ip'] = f"Error: {str(e)}"
    
    # Get public IP
    try:
        response = requests.get('https://api.ipify.org')
        ip_info['public_ip'] = response.text
    except Exception as e:
        ip_info['public_ip'] = f"Error: {str(e)}"
    
    return ip_info

# Get all IP information
ip_info = get_ip_info()
print(f"Local IP: {ip_info['local_ip']}")
print(f"Public IP: {ip_info['public_ip']}")
