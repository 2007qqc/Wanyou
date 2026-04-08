import requests
import sys

for stream_name in ("stdout", "stderr"):
    stream = getattr(sys, stream_name, None)
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

url = "https://down.mptext.top/api/public/v1/account?keyword=阮一峰&size=1"

payload={}
headers = {
  'X-Auth-Key': ''
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)
