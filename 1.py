import requests

url = "https://down.mptext.top/api/public/v1/account?keyword=阮一峰&size=1"

payload={}
headers = {
  'X-Auth-Key': ''
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)
