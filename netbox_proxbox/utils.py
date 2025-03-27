def get_fastapi_url(object):
    domain_or_ip = None
    ip = str(object.ip_address).split('/')[0]
    if object.domain:
        domain_or_ip = object.domain
    else:
        domain_or_ip = ip
    
    # Define WebSocket Domain
    websocket_domain = None
    if object.use_websocket and object.websocket_domain:
        websocket_domain = object.websocket_domain
    else:
        websocket_domain = ip
    
    # Define HTTP(S) URL for FastAPI
    fastapi_url_https = f"https://{domain_or_ip}:{object.port}"
    fastapi_url_http = f"http://{domain_or_ip}:{object.port}"
    fastapi_url = fastapi_url_https if object.verify_ssl else fastapi_url_http
    
    # Define (Secure) WebSocket URL for FastAPI
    fastapi_wss_url = f"wss://{websocket_domain}:{object.websocket_port}/ws"
    fastapi_ws_url = f"ws://{websocket_domain}:{object.websocket_port}/ws"
    fastapi_websocket_url = fastapi_wss_url if object.verify_ssl else fastapi_ws_url
    
    if any(host in fastapi_url for host in ['proxbox.backend.local', 'localhost', '127.0.0.1']):
        # If proxbox.backend.local is in the URL, set the REQUESTS_CA_BUNDLE environment variable.
        # It means user used mkcert to generate a certificate for the domain.
        # This is necessary to avoid SSL errors, so that python requests library can trust the certificate.
        
        import os
        import subprocess
        
        try:
            # Run mkcert -CAROOT to get the root certificate path.
            ca_root_folder = subprocess.run(['mkcert', '-CAROOT'], capture_output=True, text=True, check=True).stdout.strip()
            
            os.environ['REQUESTS_CA_BUNDLE'] = f'/{ca_root_folder}/rootCA.pem'
        except subprocess.CalledProcessError as e:
            print(f'Error running mkcert -CAROOT: {e}')
        
        except Exception as e:
            print(f'Error setting REQUESTS_CA_BUNDLE: {e}\nLikely because the user did not use mkcert to generate a certificate.')
    
    return {
        'domain': object.domain,
        'ip_address': object.ip_address,
        'ip_address_url': f'https://{ip}:{object.port}',
        'http_url': fastapi_url,
        'websocket_url': fastapi_websocket_url,
        'verify_ssl': object.verify_ssl
    }
