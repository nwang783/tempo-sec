import requests

base = 'https://prodhpadmin.zomans.com/public/api/seller'

paths = [
    '',
    '/',
    '/login',
    '/otp',
    '/send-otp',
    '/verify-otp',
    '/resend-otp',
    '/auth',
    '/session',
    '/me',
]

methods = ['GET', 'POST']

payloads = [
    None,
    {},
    {'phone': '0000000000'},
    {'phone_number': '0000000000'},
    {'mobile': '0000000000'},
    {'contactNumber': '0000000000'},
]

headers_list = [
    {},
    {'Content-Type': 'application/json'},
]

for path in paths:
    url = base + path
    for method in methods:
        for headers in headers_list:
            data_options = payloads if method == 'POST' else [None]
            for data in data_options:
                try:
                    if method == 'GET':
                        r = requests.get(url, headers=headers, timeout=10)
                    else:
                        if data is None:
                            r = requests.post(url, headers=headers, timeout=10)
                        else:
                            if headers.get('Content-Type') == 'application/json':
                                r = requests.post(url, json=data, headers=headers, timeout=10)
                            else:
                                r = requests.post(url, data=data, headers=headers, timeout=10)
                    snippet = r.text[:200].replace('\n', ' ')
                    print(f"{method} {url} headers={headers} data={data} -> {r.status_code} {r.reason} | {snippet}")
                except Exception as e:
                    print(f"ERROR {method} {url} headers={headers} data={data}: {e}")
