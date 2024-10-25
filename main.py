import json
from river import River


def main():
  
  # key = "\ObservedPrimary\""
  f = open('data.json') # open the data.json file
  dict = json.load(f) # convert the json object into a dictionary
  f.close() # close the file
  keys = dict['river'] # obtain primary keys and save as list
  gauges = list()

  # create River objects for each gauge and store in gauges
  for rivers in keys:
    for x in dict['river'][rivers]:
      if rivers != 'UMR':
        gauges.append(River(x['Name'], x['Coordinates'], x['URL'], 
                          x['USGS'], x['LowAction'], x['LowWatch'], x['Normal'],
                          x['HighWatch'], x['HighAction'], None, None))
      else:
        gauges.append(River(x['Name'], x['Coordinates'], x['URL'], 
                          x['USGS'], None, None, x['Normal'],
                          None, None, x['Watch'],  x['Action']))

  # print River object results
  for i in gauges:
    i.set_current()
    print(i.name, ": ", i.current)


if __name__ == '__main__':
  main()


