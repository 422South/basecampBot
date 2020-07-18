import requests
import pprint
import socket

print(socket.gethostname())

headers_422 = {'Content-Type': 'image/png', 'User-Agent': '422App (craig@422south.com)'}
auth_422 = ('craig@422south.com', 'Millenium2')
url = 'https://asset1.basecamp.com/2978927/api/v1/projects/17520513/attachments/411298659/0b7d26b0-c814-11ea-8990-a0369f35efbe/original/smiley.png'
cert = ('/etc/ssl/certs/apache-selfsigned.crt', '/etc/ssl/private/apache-selfsigned.key')
# s = requests.Session()
# req = requests.Request('GET', url, headers=headers_422, auth=auth_422)
# prepped = s.prepare_request(req)
# pprint.pprint(prepped.headers)
pprint.pprint(url)
download_file = requests.get(url, headers=headers_422, auth=auth_422)
pprint.pprint(download_file.headers)
pprint.pprint(download_file.content)