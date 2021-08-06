from bs4 import BeautifulSoup
import requests

resp = requests.get('https://pypi.org/project/Django/#history')
resp.raise_for_status()
soup = BeautifulSoup(resp.text)
versions = [p.text.strip() for p in soup.find_all('p', {'class': 'release__version'})]
print(' '.join(v for v in versions if ' ' not in v))
