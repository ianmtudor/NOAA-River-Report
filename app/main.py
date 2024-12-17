import json
import pandas as pd
import requests
import os
import shutil
import re
import time
# import platform # check os version
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path


def set_current(url):
  """ returns a BeautifulSoup object for the requested website"""
  html = requests.get(url)
  value =  re.search(r'\"ObservedPrimary\":+\d+\.\d+', BeautifulSoup(html.text, 'html.parser').prettify())
  if value == None:
    return None
  return re.search(r'\d+.\d+', value.group()).group()
  
  # self.updated = time.ctime()


def archive_files() -> None:
  """ archives all files in the log folder  """
  
  # TODO check if system needs the r'' for Linux and Mac
  # os_type = platform.system()
  # if os_type == 'Windows':
  #   source_dir, target_dir = r'log/', r'log/archive/'
  # elif os_type == 'Linux':
  #   source_dir, target_dir = 'log/', 'log/archive/'
  # elif os_type == 'Mac':
  #   print('application still in development for Mac systems')
  # else:
  #   print('unknown system')
  
  source_dir, target_dir = r'app/log/', r'app/log/archive/'
  
  # copy current file names
  file_names = os.listdir(source_dir)
  
  for file in file_names:
    # check if the file is a directory
    if os.path.isfile(source_dir + file):
      shutil.copy(source_dir + file, source_dir + file[:3] + r'.csv')
      shutil.move(source_dir + file, target_dir)


def del_files():
  """ deletes the most recent files in the log folder """
  path = r'app/log/'
  files = os.listdir(path)
  for file in files:
    if os.path.isfile(path + file):
      os.remove(path + file)


def main():
  
  del_files() # delete all the files in the log folder
  print('Welcome to the NOAA River Report application\n')
  
  rivers = ['ilr', 'mor', 'umr']
  river_index = 0
  df = []
  temp_current = []
  
  # dataframes for each river in a list
  for river in rivers:
    df.append(pd.read_csv('app/src/' + river + '_src.csv', na_filter = False))

  print('obtaining current levels...\n')
  
  # get current river levels and save the dataframe to a csv
  for data in df:
    for x in data['URL']:
      # skip empty urls
      if x != '':
        temp_value = set_current(x)
        # check if the website returned a value
        if temp_value != None:
          temp_current.append(temp_value)
        else:
          print('retrieval error on url:', x)
          temp_current.append('no data')
      else:
        temp_current.append('')
    data['Current'] = temp_current
    data = data.drop('URL', axis=1)
    temp_current.clear() # reset list to None for next dataframe
    # save dataframe to csv
    if data.to_csv('app/log/' + rivers[river_index] + '_' + datetime.now().strftime('%Y-%m-%d_%Hh%Mm%Ss') + '.csv', index=False) != None:
      print('CSV file saving error ocurred')
    print(rivers[river_index].upper() + ' gauge current levels retrieved')
    river_index += 1
  
  print('\ncsv files saved to the log directory')
  archive_files()
  print('\ncurrent levels archived in logs/archive directory\n')
  print('Success!')
  time.sleep(5)

if __name__ == '__main__':
  main()