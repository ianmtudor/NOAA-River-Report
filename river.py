import re
import requests
from bs4 import BeautifulSoup


class River:
  """ Class to create object for each river gauge """


  def __init__(self, name, coordinates, url, usgs, low_action, low_watch, normal,
                high_watch, high_action, watch, action):
    self.name = name
    self.coordinates = coordinates
    self.url = url
    self.current = None
    self.usgs = usgs
    self.low_action = low_action
    self.low_watch = low_watch
    self.normal = normal
    self.high_watch = high_watch
    self.high_action = high_action
    self.watch = watch
    self.action = action

  
  def set_current(self):
    """ returns a BeautifulSoup object for the requested website"""
    html = requests.get(self.url)
    value =  re.search(r'\"ObservedPrimary\":+\d+\.\d+', BeautifulSoup(html.text, 'html.parser').prettify())
    self.current = re.search(r'\d+.\d+', value.group()).group()
