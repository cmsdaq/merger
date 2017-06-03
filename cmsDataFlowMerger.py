#!/usr/bin/env python
import os, time, sys, getopt, fcntl
import shutil
import json
import glob
import multiprocessing
from multiprocessing.pool import ThreadPool
from multiprocessing.dummy import Pool as SimplePool
import logging
import thread
import datetime
import fileinput
import socket
import filecmp
import cmsActualMergingFiles
import cmsDataFlowCleanUp
import cmsDataFlowMakeFolders
import zlibextras
import requests
import threading
import traceback

from Logging import getLogger
log = getLogger()
logging.getLogger("urllib3").setLevel(logging.WARNING)
merging_threshold_size = 2.0 * 1024 * 1024 * 1024

# program to merge (cat) files given a list

"""
Do actual merging
"""

def esMonitorMapping(esServerUrl,esIndexName,numberOfShards,numberOfReplicas,debug):
# subroutine which creates index and mappings in elastic search database
   indexExists = False
   # check if the index exists:
   try:
      checkIndexResponse=requests.get(esServerUrl+'/'+esIndexName+'/_stats/_shards/')
      if '_shards' in json.loads(checkIndexResponse.text):
         if(float(debug) >= 10): log.info('found index '+esIndexName+' containing '+str(json.loads(checkIndexResponse.text)['_shards']['total'])+' total shards')
         indexExists = True
      else:
         if(float(debug) >= 10): log.info('did not find existing index '+esIndexName+', attempting to create it...')
         indexExists = False
   except requests.exceptions.ConnectionError as e:
      log.error('esMonitorMapping: Could not connect to ElasticSearch database!')
   if indexExists:
      # if the index already exists, we put the mapping in the index for redundancy purposes:
      # JSON follows:
      minimerge_mapping = {
         'minimerge' : {
	    '_all'       : {'enabled' : 'false'},
            'properties' : {
               'fm_date'       :{'type':'date'},
               'id'            :{'type':'string','index' : 'not_analyzed'}, #run+appliance+stream+ls
               'appliance'     :{'type':'string','index' : 'not_analyzed'},
               'host'          :{'type':'string','index' : 'not_analyzed'},
               'stream'        :{'type':'string','index' : 'not_analyzed'},
               'fname'         :{'type':'string','index' : 'not_analyzed'},
               'ls'            :{'type':'integer'},
               'processed'     :{'type':'integer'},
               'accepted'      :{'type':'integer'},
               'errorEvents'   :{'type':'integer'},
               'size'          :{'type':'long'},
               'eolField1'     :{'type':'integer'},
               'eolField2'     :{'type':'integer'},
               'adler32'       :{'type':'long'},
               'runNumber'     :{'type':'integer'}
            }
         }
      }
      macromerge_mapping = {
         'macromerge' : {
	    '_all'       : {'enabled' : 'false'},
            'properties' : {
               'fm_date'       :{'type':'date'},
               'id'            :{'type':'string','index' : 'not_analyzed'}, #run+appliance+stream+ls
               'appliance'     :{'type':'string','index' : 'not_analyzed'},
               'host'          :{'type':'string','index' : 'not_analyzed'},
               'stream'        :{'type':'string','index' : 'not_analyzed'},
               'fname'         :{'type':'string','index' : 'not_analyzed'},
               'ls'            :{'type':'integer'},
               'processed'     :{'type':'integer'},
               'accepted'      :{'type':'integer'},
               'errorEvents'   :{'type':'integer'},
               'size'          :{'type':'long'},
               'eolField1'     :{'type':'integer'},
               'eolField2'     :{'type':'integer'},
               'runNumber'     :{'type':'integer'}
            }
         }
      }
      try:
         putMappingResponse=requests.put(esServerUrl+'/'+esIndexName+'/_mapping/minimerge',data=json.dumps(minimerge_mapping))
         putMappingResponse=requests.put(esServerUrl+'/'+esIndexName+'/_mapping/macromerge',data=json.dumps(macromerge_mapping))
      except requests.exceptions.ConnectionError as e:
         log.error('esMonitorMapping: Could not connect to ElasticSearch database!')
   else:   
      # if the index/mappings don't exist, we must create them both:
      # JSON data for index settings, and merge document mappings
      settings = {
         "analysis":{
            "analyzer": {
               "prefix-test-analyzer": {
                  "type": "custom",
                     "tokenizer": "prefix-test-tokenizer"
                  }
            },
            "tokenizer": {
               "prefix-test-tokenizer": {
                  "type": "path_hierarchy",
                  "delimiter": " "
               }
            }
         },
         "index":{
            'number_of_shards' : numberOfShards,
            'number_of_replicas' : numberOfReplicas,
            'translog':{'durability':'async'},
            'mapper':{'dynamic':'false'}
         },
      }

      mapping = {
         'minimerge' : {
            'properties' : {
               '_all'          :{'enabled': 'false'},
               '_timestamp'    :{'enabled': 'true'},
               'fm_date'       :{'type':'date'},
               'id'            :{'type':'string','index' : 'not_analyzed'}, #run+appliance+stream+ls
               'appliance'     :{'type':'string','index' : 'not_analyzed'},
               'host'          :{'type':'string','index' : 'not_analyzed'},
               'stream'        :{'type':'string','index' : 'not_analyzed'},
               'fname'         :{'type':'string','index' : 'not_analyzed'},
               'ls'            :{'type':'integer'},
               'processed'     :{'type':'integer'},
               'accepted'      :{'type':'integer'},
               'errorEvents'   :{'type':'integer'},
               'size'          :{'type':'long'},
               'eolField1'     :{'type':'integer'},
               'eolField2'     :{'type':'integer'},
               'adler32'       :{'type':'long'},
               'runNumber'     :{'type':'integer'}
            }
         },
         'macromerge' : {
            'properties' : {
               '_all'          :{'enabled': 'false'},
               '_timestamp'    :{'enabled': 'true'},
               'fm_date'       :{'type':'date'},
               'id'            :{'type':'string','index' : 'not_analyzed'}, #run+appliance+stream+ls
               'appliance'     :{'type':'string','index' : 'not_analyzed'},
               'host'          :{'type':'string','index' : 'not_analyzed'},
               'stream'        :{'type':'string','index' : 'not_analyzed'},
               'fname'         :{'type':'string','index' : 'not_analyzed'},
               'ls'            :{'type':'integer'},
               'processed'     :{'type':'integer'},
               'accepted'      :{'type':'integer'},
               'errorEvents'   :{'type':'integer'},
               'size'          :{'type':'long'},
               'eolField1'     :{'type':'integer'},
               'eolField2'     :{'type':'integer'},
               'runNumber'     :{'type':'integer'}
            }
         }
      }
      try:
         createIndexResponse=requests.post(esServerUrl+'/'+esIndexName,data=json.dumps({ 'settings': settings, 'mappings': mapping }))
      except requests.exceptions.ConnectionError as e:
         log.error('esMonitorMapping: Could not connect to ElasticSearch database!')

def mergeFiles(triggerMergingThreshold, inpSubFolder, outSubFolder, outputMergedFolder, outputSMMergedFolder, outputDQMMergedFolder, doCheckSum, outMergedFile, outMergedJSON, inputDataFolder, infoEoLS, eventsO, filesDyn, checkSum, fileSize, filesJSONDyn, errorCode, transferDest, timeRead, timeIni, mergeType, doRemoveFiles, outputEndName, optionMerging, esServerUrl, esIndexName, debug):

   # making them local
   files     = [word_in_list for word_in_list in filesDyn]
   filesJSON = [word_in_list for word_in_list in filesJSONDyn]

   # streamDQMHistograms stream uses always with optionA
   fileNameString = filesJSON[0].replace(inputDataFolder,"").replace("/","").split('_')

   specialStreams = False
   if(fileNameString[2] == "streamDQMHistograms" or fileNameString[2] == "streamHLTRates" or fileNameString[2] == "streamL1Rates" or fileNameString[2] == "streamError"):
      specialStreams = True

   theMergingThreshold = triggerMergingThreshold[1]
   if(fileNameString[2] == "streamDQMEventDisplay"):
      theMergingThreshold = triggerMergingThreshold[0]

   if ((optionMerging == "optionA") or ("DQM" in fileNameString[2] and specialStreams == False and theMergingThreshold < 1) or (specialStreams == True) or (infoEoLS[0] == 0)):
      try:
         cmsActualMergingFiles.mergeFilesA(inpSubFolder, outSubFolder, outputMergedFolder,                       outputDQMMergedFolder, doCheckSum, outMergedFile, outMergedJSON, inputDataFolder, infoEoLS, eventsO, files, checkSum, fileSize, filesJSON, errorCode, transferDest, timeRead, timeIni, mergeType, doRemoveFiles, outputEndName, esServerUrl, esIndexName, debug)
      except Exception, e:
         log.error("cmsActualMergingFilesA crashed: {0}, {1}, {2}, {3}, {4}, {5}, {6}, {7}, {8}, {9}, {10}".format(outputMergedFolder, outMergedFile, outMergedJSON, inputDataFolder, infoEoLS, eventsO, files, checkSum, fileSize, filesJSON, errorCode))

   elif (optionMerging == "optionC"):
      try:
         cmsActualMergingFiles.mergeFilesC(inpSubFolder, outSubFolder, outputMergedFolder, outputSMMergedFolder,                        doCheckSum, outMergedFile, outMergedJSON, inputDataFolder, infoEoLS, eventsO, files, checkSum, fileSize, filesJSON, errorCode, transferDest, timeRead, timeIni, mergeType, doRemoveFiles, outputEndName, esServerUrl, esIndexName, debug)
      except Exception, e:
         log.error("cmsActualMergingFilesC crashed: {0}, {1}, {2}, {3}, {4}, {5}, {6}, {7}, {8}, {9}, {10}".format(outputMergedFolder, outMergedFile, outMergedJSON, inputDataFolder, infoEoLS, eventsO, files, checkSum, fileSize, filesJSON, errorCode))

   else:
      log.error("Wrong option!: {0}".format(optionMerging))
      msg = "Wrong option!: %s" % (optionMerging)
      raise RuntimeError, msg

"""
Function to move files
"""
def moveFiles(debug, theInputDataFolder, theOutputDataFolder, jsonName, theSettings):
   try:

      initMergingTime = time.time()
      if(float(debug) > 0): log.info("Start moving of {0}".format(jsonName))

      if(float(debug) >= 10): log.info("moving parameters files: {0} {1} {2}".format(theInputDataFolder, theOutputDataFolder, jsonName))

      eventsInput       = int(theSettings['data'][0])
      eventsOutput      = int(theSettings['data'][1])
      eventsOutputError = int(theSettings['data'][2])
      errorCode         = int(theSettings['data'][3])
      fileName          = str(theSettings['data'][4])
      fileSize          = int(theSettings['data'][5])
      checkSum          = int(theSettings['data'][7]) 	       
      transferDest      = "dummy"
      if(len(theSettings['data']) >= 9):
         transferDest   = str(theSettings['data'][8])

      jsonNameString = jsonName.split('_')
      outSubFolder = jsonNameString[2]

      inpMergedFileFullPath = os.path.join(theInputDataFolder, fileName)
      inpMergedJSONFullPath = os.path.join(theInputDataFolder, jsonName)

      theOutputDataFolderFullPath      = os.path.join(theOutputDataFolder,outSubFolder, "data")
      theOutputDataFolderFullPathOpen  = os.path.join(theOutputDataFolder,outSubFolder, "data", "open")
      theOutputJSONFolderFullPath      = os.path.join(theOutputDataFolder,outSubFolder, "jsns")
      theOutputJSONFolderFullPathOpen  = os.path.join(theOutputDataFolder,outSubFolder, "jsns", "open")

      outMergedFileFullPath       = theOutputDataFolderFullPathOpen + "/" + fileName
      outMergedJSONFullPath       = theOutputJSONFolderFullPathOpen + "/" + jsonName
      outMergedFileFullPathStable = theOutputDataFolderFullPath     + "/" + fileName
      outMergedJSONFullPathStable = theOutputJSONFolderFullPath     + "/" + jsonName.replace("_TEMP.jsn",".jsn")

      if not os.path.exists(theOutputDataFolderFullPathOpen):
         log.warning("Moving operation, folder did not exist, {0}, creating it".format(theOutputDataFolderFullPathOpen))
         try:
   	    os.makedirs(theOutputDataFolderFullPathOpen)
         except Exception, e:
   	    log.warning("Looks like the directory {0} has just been created by someone else...".format(theOutputDataFolderFullPathOpen))

      if not os.path.exists(theOutputJSONFolderFullPathOpen):
         log.warning("Moving operation, folder did not exist, {0}, creating it".format(theOutputJSONFolderFullPathOpen))
         try:
   	    os.makedirs(theOutputJSONFolderFullPathOpen)
            msg = "sudo lfs setstripe -c 1 -S 1m {0}".format(theOutputJSONFolderFullPathOpen)
            os.system(msg)
         except Exception, e:
   	    log.warning("Looks like the directory {0} has just been created by someone else...".format(theOutputJSONFolderFullPathOpen))

      if(float(debug) >= 10): log.info("moving info: {0} {1} {2} {3} {2} {3}".format(inpMergedFileFullPath, outMergedFileFullPath, outMergedFileFullPathStable, 
                                                                                     inpMergedJSONFullPath, outMergedJSONFullPath, outMergedJSONFullPathStable))

      # first thing we do is to delete the input jsn file, no second try will happen
      try:
         os.remove(inpMergedJSONFullPath)
      except Exception, e:
         log.error("remove json file failed: {0} - {1}".format(inpMergedJSONFullPath,e))

      # moving dat files
      if not os.path.exists(inpMergedFileFullPath):
         log.error("MOVE PROBLEM, inpMergedFileFullPath does not exist: {0}".format(inpMergedFileFullPath))

      try:
         shutil.move(inpMergedFileFullPath,outMergedFileFullPath)
      except Exception, e:
         log.error("copy dat file failed: {0}, {1}".format(inpMergedFileFullPath,outMergedFileFullPath))

      if not os.path.exists(outMergedFileFullPath):
         log.error("MOVE PROBLEM, outMergedFileFullPath does not exist: {0}".format(outMergedFileFullPath))

      try:
         shutil.move(outMergedFileFullPath,outMergedFileFullPathStable)
      except Exception, e:
         log.error("move dat file failed: {0}, {1}".format(outMergedFileFullPath,outMergedFileFullPathStable))

      # making json files
      theMergedJSONfile = open(outMergedJSONFullPath, 'w')
      theMergedJSONfile.write(json.dumps({'data': (eventsInput, eventsOutput, errorCode, fileName, fileSize, checkSum, 1, eventsInput, 0, transferDest)}))
      theMergedJSONfile.close()

      if not os.path.exists(outMergedJSONFullPath):
         log.error("COPY PROBLEM, outMergedJSONFullPath does not exist: {0}".format(outMergedJSONFullPath))

      # moving json files
      try:
         shutil.move(outMergedJSONFullPath,outMergedJSONFullPathStable)
      except Exception, e:
         log.error("move json file failed: {0}, {1}".format(outMergedJSONFullPath,outMergedJSONFullPathStable))

      # Removing BoLS file, the last step
      fileNameString = jsonName.split('_')
      BoLSFileName = fileNameString[0] + "_" + fileNameString[1] + "_" + fileNameString[2] + "_BoLS.jsn"
      BoLSFileNameFullPath = os.path.join(theInputDataFolder, BoLSFileName)
      if os.path.exists(BoLSFileNameFullPath):
         os.remove(BoLSFileNameFullPath)

      endMergingTime = time.time() 
      if(float(debug) > 0): log.info("Time for moving({0}): {1}".format(outMergedFileFullPathStable, endMergingTime-initMergingTime))

   except Exception, e:
      log.error("copyFile failed: {0} - {1}".format(outMergedJSONFullPath,e))

"""
Functions to handle errors properly
"""
def error(msg, *args):
    return multiprocessing.get_logger().error(msg, *args)

class LogExceptions(object):
    def __init__(self, callable):
        self.__callable = callable
        return

    def __call__(self, *args, **kwargs):
        try:
            result = self.__callable(*args, **kwargs)

        except Exception as e:
            # Here we add some debugging help. If multiprocessing's
            # debugging is on, it will arrange to log the traceback
            error(traceback.format_exc())
            # Re-raise the original exception so the ThreadPool worker can
            # clean up
            raise

        # It was fine, give a normal answer
        return result
    pass

class LoggingPool(ThreadPool):
    def apply_async(self, func, args=(), kwds={}, callback=None):
        return ThreadPool.apply_async(self, LogExceptions(func), args, kwds, callback)

"""
Functions to partial match dictionary keys
"""
def match(tup,target):
   if len(tup) != len(target):
      return False
   for i in xrange(len(tup)):
      if target[i] != "*" and tup[i] != target[i]:
         return False
   return True

def get_tuples(mydict,target):
   keys = filter(lambda x: match(x,target),mydict.keys())
   return [mydict[key] for key in keys]

def remove_key_tuples(mydict,target):
   keys = filter(lambda x: match(x,target),mydict.keys())
   for key in keys:
      del mydict[key]

"""
Do recovering JSON files
"""
def doTheRecovering(paths_to_watch, streamType, mergeType, debug):
   inputDataFolders = glob.glob(paths_to_watch)
   log.info("Recovering: inputDataFolders: {0}".format(inputDataFolders))
   if(float(debug) >= 10): log.info("**************recovering JSON files***************")
   for nf in range(0, len(inputDataFolders)):
      inputDataFolder = inputDataFolders[nf]	   

      after = dict()
      listFolders = sorted(glob.glob(os.path.join(inputDataFolder, 'stream*')));
      for nStr in range(0, len(listFolders)):
         try:
            after_temp = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], '*.jsn'))])
            after.update(after_temp)
            after_temp = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], '*.ini'))])
            after.update(after_temp)
            after_temp = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], 'jsns', '*.jsn'))])
            after.update(after_temp)
            after_temp = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], 'data', '*.ini'))])
            after.update(after_temp)
         except Exception, e:
            log.error("glob.glob operation failed: {0} - {1}".format(inputDataFolder,e))

      afterStringNoSorted = [f for f in after]
      afterString = sorted(afterStringNoSorted, reverse=False)

      # loop over JSON files, which will give the list of files to be recovered
      for i in range(0, len(afterString)):

	 fileString = afterString[i].split('_')
         if(streamType != "0" and (afterString[i].endswith(".jsn") or afterString[i].endswith(".ini"))):
            isOnlyDQMRates = ("DQM" in fileString[2] or "Rates" in fileString[2])
            isStreamEP = isOnlyDQMRates == False and ("streamP" in fileString[2] or "streamH" in fileString[2])
            if  (streamType == "onlyDQMRates" and isOnlyDQMRates == False): continue
            elif(streamType == "onlyStreamEP" and isStreamEP == False): continue
            elif(streamType == "noDQMRatesnoStreamEP" and (isOnlyDQMRates == True or isStreamEP == True)): continue
      
         try:
            if afterString[i].endswith("_TEMP.jsn"):
               inputJsonRenameFile = afterString[i].replace("_TEMP.jsn",".jsn")
               os.rename(afterString[i],inputJsonRenameFile)
            if afterString[i].endswith("_TEMP.ini"):
               inputIniRenameFile = afterString[i].replace("_TEMP.ini",".ini")
               os.rename(afterString[i],inputIniRenameFile)
         except Exception, e:
           log.error("file could not be renamed: {0} - {1}".format(afterString[i],e))

"""
Check if file is completed
"""
def is_completed(filepath):
   """Checks if a file is completed by opening it in append mode.
   If no exception thrown, then the file is not locked.
   """
   completed = False
   file_object = None
   buffer_size = 8
   # Opening file in append mode and read the first 8 characters
   file_object = open(filepath, 'a', buffer_size)
   if file_object:
      completed = True
      file_object.close()

   return completed

"""
Read json files
"""
def readJsonFile(inputJsonFile, debug):
   try:
      settingsLS = "bad"
      if(os.path.getsize(inputJsonFile) > 0):
         try:
            if(float(debug) >= 50): log.info("trying to load: {0}".format(inputJsonFile))
            settingsLS = json.loads(open(inputJsonFile, "r").read())
         except Exception, e:
            log.warning("Looks like the file {0} is not available, I'll try again...".format(inputJsonFile))
            try:
               time.sleep (0.1)
   	       settingsLS = json.loads(open(inputJsonFile, "r").read())
            except Exception, e:
               log.warning("Looks like the file {0} is not available (2nd try)...".format(inputJsonFile))
               try:
                  time.sleep (1.0)
   	          settingsLS = json.loads(open(inputJsonFile, "r").read())
               except Exception, e:
                  log.warning("Looks like the file {0} failed for good (3rd try)...".format(inputJsonFile))
                  inputJsonFailedFile = inputJsonFile.replace("_TEMP.jsn","_FAILED.bad")
                  os.rename(inputJsonFile,inputJsonFailedFile)

      return settingsLS
   except Exception, e:
      log.error("readJsonFile {0} failed {1}".format(inputJsonFile,e))

"""
Do loops
"""
def doTheMerging(paths_to_watch, path_eol, mergeType, streamType, debug, outputMerge, outputSMMerge, outputDQMMerge, doCheckSum, outputEndName, doRemoveFiles, optionMerging, triggerMergingThreshold, completeMergingThreshold, esServerUrl, esIndexName):
   filesDict      = dict()
   jsonsDict      = dict()    
   eventsIDict    = dict()
   variablesDict  = dict()
   eventsEoLSDict = dict()
   timeDict       = dict()
   # Maximum time to analyze json file to be considered standard
   tooSlowTime = 1000
   if(float(debug) >= 10): log.info("I will watch: {0}".format(paths_to_watch))
   # < 0 == will always use ThreadPool option
   nWithPollMax = 1
   # Maximum number of threads to be allowed with the pool option
   nThreadsMax     = 20
   nThreadsMaxDQM  = 10
   nThreadsMaxDQMH = 1 # not used for mini-merger now
   nThreadsMaxRates = 1 # not used for mini-merger now
   maxParallelLSs = 1
   if mergeType == "macro":
      nThreadsMax     = 25
      nThreadsMaxDQM  = 20
      nThreadsMaxDQMH = 5
      nThreadsMaxRates = 5
      maxParallelLSs = 3
  # Number of loops
   nLoops = 0

   if nWithPollMax < 0:
      # conservative call
      #thePool = ThreadPool(nThreadsMax)
      # agressive call
      multiprocessing.log_to_stderr()
      multiprocessing.get_logger().setLevel(logging.ERROR)
      thePool     = LoggingPool(processes=nThreadsMax)
      thePoolDQM  = LoggingPool(processes=nThreadsMaxDQM)
      thePoolDQMH = LoggingPool(processes=nThreadsMaxDQMH)
      thePoolRates = LoggingPool(processes=nThreadsMaxRates)

   else:
      thePool     = multiprocessing.Pool(nThreadsMax)
      thePoolDQM  = multiprocessing.Pool(nThreadsMaxDQM)
      thePoolDQMH = multiprocessing.Pool(nThreadsMaxDQMH)
      thePoolRates = multiprocessing.Pool(nThreadsMaxRates)

   jsonReaderPool = None
   jsonReaderPoolSize = 0

   while 1:
      time.sleep (0.3)
      nLoops = nLoops + 1
      inputDataFoldersNoSorted = glob.glob(paths_to_watch)
      inputDataFolders = sorted(inputDataFoldersNoSorted, reverse=True)
      if(float(debug) >= 20 or nLoops%10000 == 1): log.info("***************NEW LOOP************** {0}".format(nLoops))
      if(float(debug) >= 20 or nLoops%1000 == 1): log.info("inputDataFolders: {0}, loop: {1}".format(inputDataFolders, nLoops))
      timeSpentListStreams = 0
      timeSpenthandleIniFiles = 0
      timeSpentListJsons = 0
      timeSpentGetJsons = 0
      timeSpentAnalyzeJsons = 0
      timeSpentCheckEoR = 0
      timeLastRun = -1
      # check the last 50 runs only
      for nf in range(0, min(len(inputDataFolders),50)):
          inputDataFolder = inputDataFolders[nf]
	  # making output folders
	  inputDataFolderString = inputDataFolder.split('/')
	  # if statement to allow ".../" or ... for input folders 
	  if inputDataFolderString[len(inputDataFolderString)-1] == '':
	    outputMergedFolder    = os.path.join(outputMerge,    inputDataFolderString[len(inputDataFolderString)-2])
	    outputSMMergedFolder  = os.path.join(outputSMMerge,  inputDataFolderString[len(inputDataFolderString)-2])
	    outputDQMMergedFolder = os.path.join(outputDQMMerge, inputDataFolderString[len(inputDataFolderString)-2])
	    theRunNumber          = inputDataFolderString[len(inputDataFolderString)-2]
	    outputBadFolder       = os.path.join(outputMerge,    inputDataFolderString[len(inputDataFolderString)-2])
	    outputSMBadFolder     = os.path.join(outputSMMerge,  inputDataFolderString[len(inputDataFolderString)-2])
	    outputSMRecoveryFolder= os.path.join(outputSMMerge,  inputDataFolderString[len(inputDataFolderString)-2])
          else:
	    outputMergedFolder    = os.path.join(outputMerge,    inputDataFolderString[len(inputDataFolderString)-1])
	    outputSMMergedFolder  = os.path.join(outputSMMerge,  inputDataFolderString[len(inputDataFolderString)-1])
	    outputDQMMergedFolder = os.path.join(outputDQMMerge, inputDataFolderString[len(inputDataFolderString)-1])
	    theRunNumber          = inputDataFolderString[len(inputDataFolderString)-1] 
	    outputBadFolder       = os.path.join(outputMerge,    inputDataFolderString[len(inputDataFolderString)-1])
	    outputSMBadFolder     = os.path.join(outputSMMerge,  inputDataFolderString[len(inputDataFolderString)-1])
	    outputSMRecoveryFolder= os.path.join(outputSMMerge,  inputDataFolderString[len(inputDataFolderString)-1])

	  # reading the list of files in the given folder
          if(float(debug) >= 50): time.sleep (1)
          if(float(debug) >= 20): log.info("Begin folder iteration")

          listStreamsTime = time.time()
          listFolders = sorted(glob.glob(os.path.join(inputDataFolder, 'stream*')));
          tlock  = threading.Lock()

	  def loop_func_makedirs(nStr):
	    outSubFolder = os.path.basename(listFolders[nStr].rstrip('/'))
            if (float(debug) >= 3): log.info("creating subdirs under: {0}/{1}".format(outputMergedFolder, outSubFolder))
            cmsDataFlowMakeFolders.doMakeFolders(os.path.join(outputMergedFolder,     outSubFolder, "jsns", "open"), 
		                                 os.path.join(outputSMMergedFolder,   outSubFolder, "jsns", "open"), 
						 os.path.join(outputDQMMergedFolder,  outSubFolder, "jsns", "open"), 
						 os.path.join(outputMergedFolder,     outSubFolder, "data", "open"), 
		                                 os.path.join(outputSMMergedFolder,   outSubFolder, "data", "open"), 
						 os.path.join(outputDQMMergedFolder,  outSubFolder, "data", "open"), 
						 os.path.join(outputBadFolder,        outSubFolder, "bad"),
						 os.path.join(outputSMBadFolder,      outSubFolder, "bad"),
						 os.path.join(outputSMRecoveryFolder, outSubFolder, "recovery"))


          def loop_func_ini(nStr):
            after = dict()
            try:
              after_temp = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], '*.ini'))])
              after.update(after_temp)
              after_temp = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], 'data', '*.ini'))])
              after.update(after_temp)
            except Exception, e:
                log.error("glob.glob operation failed: {0} - {1}".format(inputDataFolder,e))

            afterStringNoSortedINI = [f for f in after if ( (f.endswith(".ini")) and ("TEMP" not in f) and ("EoR" not in f) and ("index" not in f)  and ("EoLS" not in f) and ("BoLS" not in f))]
            afterStringINI = sorted(afterStringNoSortedINI, reverse=False)

            # create for folders only if there is anything to either merge or copy
            if(len(afterStringINI) > 0):
               loop_func_makedirs(nStr)

	    # loop over ini files, needs to be done first of all
	    for i in range(0, len(afterStringINI)):

	      if(afterStringINI[i].endswith(".ini")):
                baseName = os.path.basename(afterStringINI[i])
          	inputName  = afterStringINI[i]
          	if (float(debug) > 2): log.info("inputName: {0}".format(inputName))

                fileIniString = baseName.split('_')
		isOnlyDQMRates = ("DQM" in fileIniString[2] or "Rates" in fileIniString[2])
		isStreamEP = isOnlyDQMRates == False and ("streamP" in fileIniString[2] or "streamH" in fileIniString[2])
                if  (streamType == "onlyDQMRates" and isOnlyDQMRates == False): continue
                elif(streamType == "onlyStreamEP" and isStreamEP == False): continue
                elif(streamType == "noDQMRatesnoStreamEP" and (isOnlyDQMRates == True or isStreamEP == True)): continue

                inpSubFolder = fileIniString[2]
                outSubFolder = fileIniString[2]

                if (float(debug) >= 1): log.info("create the witness ini file")

          	if((mergeType == "mini") or (optionMerging == "optionA") or ("DQM" in fileIniString[2]) or ("streamError" in fileIniString[2]) or ("streamHLTRates" in fileIniString[2]) or ("streamL1Rates" in fileIniString[2])):
          	    theIniOutputFolder = outputSMMergedFolder
	  	    #if((optionMerging == "optionA") or ("DQM" in fileIniString[2]) or ("streamError" in fileIniString[2]) or ("streamHLTRates" in fileIniString[2]) or ("streamL1Rates" in fileIniString[2])):
          	    #   theIniOutputFolder = outputMergedFolder

          	if (is_completed(inputName) == True and (os.path.getsize(inputName) > 0 or fileIniString[2] == "streamError" or fileIniString[2] == "streamDQMHistograms")):
	     	   # init name: runxxx_ls0000_streamY_HOST.ini
	     	   inputNameString = baseName.split('_')
          	   # outputIniName will be modified in the next merging step immediately, while outputIniNameToCompare will stay forever
	     	   outputIniNameTEMP          = theIniOutputFolder + "/" + outSubFolder + "/data/open/" + inputNameString[0] + "_ls0000_" + inputNameString[2] + "_" +    outputEndName + ".ini_TMP1"
	     	   outputIniName              = theIniOutputFolder + "/" + outSubFolder +      "/data/" + inputNameString[0] + "_ls0000_" + inputNameString[2] + "_" +    outputEndName + ".ini"
          	   outputIniNameToCompareTEMP = theIniOutputFolder + "/" + outSubFolder + "/data/open/" + inputNameString[0] + "_ls0000_" + inputNameString[2] + "_" +    outputEndName + ".ini_TMP2"
          	   outputIniNameToCompare     = theIniOutputFolder + "/" + outSubFolder + "/data/open/" + inputNameString[0] + "_ls0000_" + inputNameString[2] + "_" + "StorageManager" + ".ini"
	     	   inputNameRename  = inputName.replace(".ini","_TEMP.ini")
          	   os.rename(inputName,inputNameRename)
          	   if(float(debug) >= 10): log.info("iniFile: {0}".format(baseName))
	  	   # getting the ini file, just once per stream
	     	   if (not os.path.exists(outputIniNameToCompare) or (fileIniString[2] != "streamError" and fileIniString[2] != "streamDQMHistograms" and os.path.exists(outputIniNameToCompare) and os.path.getsize(outputIniNameToCompare) == 0)):
	     	      try:
          		 with open(outputIniNameToCompareTEMP, 'a', 1) as file_object:
                            tlock.acquire()
          		    fcntl.flock(file_object, fcntl.LOCK_EX)
	     		    shutil.copy(inputNameRename,outputIniNameToCompareTEMP)
          		    fcntl.flock(file_object, fcntl.LOCK_UN)
                            tlock.release()
	     		 file_object.close()
                         shutil.move(outputIniNameToCompareTEMP,outputIniNameToCompare)
	     	      except Exception, e:
                         try:tlock.release()
                         except:pass
	     		 log.warning("Looks like the outputIniNameToCompare file {0} has just been created by someone else...".format(outputIniNameToCompare))

	  	   # otherwise, checking if they are identical
	  	   else:
          	      try:
	     		 if filecmp.cmp(outputIniNameToCompare,inputNameRename) == False:
	     		    log.warning("ini files: {0} and {1} are different!!!".format(outputIniNameToCompare,inputNameRename))
          	      except Exception, e:
          		    log.error("Try to move a .ini to a _TEMP.ini, disappeared under my feet. Carrying on...")

	     	   if (not os.path.exists(outputIniName) or (fileIniString[2] != "streamError" and fileIniString[2] != "streamDQMHistograms" and os.path.exists(outputIniName) and os.path.getsize(outputIniName) == 0)):
	     	      try:
          		 with open(outputIniNameTEMP, 'a', 1) as file_object:
                            tlock.acquire()
          		    fcntl.flock(file_object, fcntl.LOCK_EX)
	     		    shutil.copy(inputNameRename,outputIniNameTEMP)
          		    fcntl.flock(file_object, fcntl.LOCK_UN)
                            tlock.release()
	     		 file_object.close()
                         shutil.move(outputIniNameTEMP,outputIniName)
	     	      except Exception, e:
                         try:tlock.release()
                         except:pass
	     		 log.warning("Looks like the outputIniName file {0} has just been created by someone else...".format(outputIniName))

	  	   # otherwise, checking if they are identical
	  	   else:
          	      try:
	     		 if filecmp.cmp(outputIniName,inputNameRename) == False:
	     		    log.warning("ini files: {0} and {1} are different!!!".format(outputIniName,inputNameRename))
          	      except Exception, e:
          		    log.error("Try to move a .ini to a _TEMP.ini, disappeared under my feet. Carrying on...")

          	   if(doRemoveFiles == "True"): 
          	      os.remove(inputNameRename)

                   # only for streamHLTRates and streamL1Rates, need another file
                   if(("streamHLTRates" in fileIniString[2]) or ("streamL1Rates" in fileIniString[2])):
	     	      inputJsdNameString = baseName.split('_')
		      inputJsdName  = inputDataFolder + "/"  + inpSubFolder + "/data/" + inputJsdNameString[0] + "_ls0000_" + inputJsdNameString[2] + ".jsd"
		      if(os.path.exists(inputJsdName)):
          		 # outputIniName will be modified in the next merging step immediately, while outputIniNameToCompare will stay forever
	     		 outputIniNameTEMP          = outputMergedFolder + "/" + outSubFolder + "/data/open/" + inputJsdNameString[0] + "_ls0000_" + inputJsdNameString[2] + "_" +    outputEndName  + ".jsd_TMP1"
	     		 outputIniName              = outputMergedFolder + "/" + outSubFolder +      "/data/" + inputJsdNameString[0] + "_ls0000_" + inputJsdNameString[2]			     + ".jsd"
          		 outputIniNameToCompareTEMP = outputMergedFolder + "/" + outSubFolder + "/data/open/" + inputJsdNameString[0] + "_ls0000_" + inputJsdNameString[2] + "_" +    outputEndName  + ".jsd_TMP2"
          		 outputIniNameToCompare     = outputMergedFolder + "/" + outSubFolder + "/data/open/" + inputJsdNameString[0] + "_ls0000_" + inputJsdNameString[2]			     + ".jsd"
          		 if(float(debug) >= 10): log.info("iniFile: {0}".format(baseName))
	  		 # getting the ini file, just once per stream
	     		 if (not os.path.exists(outputIniNameToCompare) or (os.path.exists(outputIniNameToCompare) and os.path.getsize(outputIniNameToCompare) == 0)):
	     		    try:
          		       with open(outputIniNameToCompareTEMP, 'a', 1) as file_object:
                                  tlock.acquire()
          			  fcntl.flock(file_object, fcntl.LOCK_EX)
	     			  shutil.copy(inputJsdName,outputIniNameToCompareTEMP)
          			  fcntl.flock(file_object, fcntl.LOCK_UN)
                                  tlock.release()
	     		       file_object.close()
                               shutil.move(outputIniNameToCompareTEMP,outputIniNameToCompare)
	     		    except Exception, e:
                               try:tlock.release()
                               except:pass
	     		       log.warning("Looks like the outputIniNameToCompare-Rates file {0} has just been created by someone else...".format(outputIniNameToCompare))

	  		 # otherwise, checking if they are identical
	  		 else:
          		    try:
	     		       if filecmp.cmp(outputIniNameToCompare,inputJsdName) == False:
	     			  log.warning("ini files: {0} and {1} are different!!!".format(outputIniNameToCompare,inputJsdName))
          		    except Exception, e:
          			  log.error("Try to move a .ini to a _TEMP.ini, disappeared under my feet. Carrying on...")

	     		 if (not os.path.exists(outputIniName) or (os.path.exists(outputIniName) and os.path.getsize(outputIniName) == 0)):
	     		    try:
          		       with open(outputIniNameTEMP, 'a', 1) as file_object:
                                  tlock.acquire()
          			  fcntl.flock(file_object, fcntl.LOCK_EX)
	     			  shutil.copy(inputJsdName,outputIniNameTEMP)
          			  fcntl.flock(file_object, fcntl.LOCK_UN)
                                  tlock.release()
	     		       file_object.close()
                               shutil.move(outputIniNameTEMP,outputIniName)
	     		    except Exception, e:
                               try:tlock.release()
                               except:pass
	     		       log.warning("Looks like the outputIniName-Rates file {0} has just been created by someone else...".format(outputIniName))

	  		 # otherwise, checking if they are identical
	  		 else:
          		    try:
	     		       if filecmp.cmp(outputIniName,inputJsdName) == False:
	     			  log.warning("ini files: {0} and {1} are different!!!".format(outputIniName,inputJsdName))
          		    except Exception, e:
          			  log.error("Try to move a .ini to a _TEMP.ini, disappeared under my feet. Carrying on...")

                      else:
                         log.error("jsd file does not exists!: {0}".format(inputJsdName))

	     	else:
	     	   log.info("Looks like the file {0} is being copied by someone else...".format(inputName))


          def loop_func_list(params):
            nStr = params[0]
            glob_res = params[1]

	    if len(glob_res[nStr])==0:
              after = dict()
              try:
                after_temp = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], '*.jsn'))])
                after.update(after_temp)
                after_temp = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], 'jsns', '*.jsn'))])
                after.update(after_temp)
              except Exception, e:
                log.error("glob.glob operation failed: {0} - {1}".format(inputDataFolder,e))

              afterStringNoSortedJSN = [f for f in after if ( (f.endswith(".jsn")) and ("TEMP" not in f) and ("EoR" not in f) and ("index" not in f)  and ("EoLS" not in f) and ("BoLS" not in f))]
              afterStringJSN = sorted(afterStringNoSortedJSN, reverse=False)

	      glob_res[nStr]["afterStringJSN"]=afterStringJSN
	    else:
	      #log.info('inheriting directory list for directory '+listFolders[nStr])
	      afterStringJSN = glob_res[nStr]["afterStringJSN"]


          def loop_func_read(params):
            nStr = params[0]
            theMaxLS = params[1]
            theLS = params[2]
            glob_res = params[3]
	    afterStringJSN = glob_res[nStr]["afterStringJSN"]

            #read all JSON files
            iniReadingTotalTime = time.time()
            sumReadingJsonTime = 0
	    sumReadingJsonCount = 0
	    settingsDict = {}
	    for i in range(0, len(afterStringJSN)):

              if(float(debug) > 2): log.info("Working on {0}".format(afterStringJSN[i]))
              baseName = os.path.basename(afterStringJSN[i])
              fileNameString = baseName.split('_')
	     
	      if(int(fileNameString[1].split("ls")[1])%int(theMaxLS) != int(theLS)):
                continue
	
              isOnlyDQMRates = ("DQM" in fileNameString[2] or "Rates" in fileNameString[2])
              isStreamEP = isOnlyDQMRates == False and ("streamP" in fileNameString[2] or "streamH" in fileNameString[2])
              if  (streamType == "onlyDQMRates" and isOnlyDQMRates == False): continue
              elif(streamType == "onlyStreamEP" and isStreamEP == False): continue
              elif(streamType == "noDQMRatesnoStreamEP" and (isOnlyDQMRates == True or isStreamEP == True)): continue

	      if(float(debug) >= 50): log.info("FILE: {0}".format(baseName))
              inputJsonFile = afterStringJSN[i]
	      if(float(debug) >= 50): log.info("inputJsonFile: {0}".format(inputJsonFile))
             
              iniReadingJsonTime = time.time()
              try:
                # renaming the file to avoid issues
                inputJsonRenameFile = inputJsonFile.replace(".jsn","_TEMP.jsn")
                os.rename(inputJsonFile,inputJsonRenameFile)
                settings = readJsonFile(inputJsonRenameFile,debug)

              except Exception, e:
                log.error("file could not be renamed: {0} - {1}".format(inputJsonFile,e))
                settings = "bad"

	      #put into dictionary for next loop
	      readingJsonTime = time.time() - iniReadingJsonTime
	      sumReadingJsonTime += readingJsonTime
	      sumReadingJsonCount += 1
	      settingsDict[inputJsonRenameFile]=[settings,readingJsonTime]

            #loop ended
            endReadingTotalTime = time.time()

	    # store settings in global object
	    glob_res[nStr][theLS] = settingsDict

	    if (endReadingTotalTime-iniReadingTotalTime)*1000>tooSlowTime:
	      log.warning("Too slow reading json (stream/LS: {0} - {1}): total({2} msecs) - reading({3} msecs) files. count:{4} files".format(nStr,theLS,(endReadingTotalTime-iniReadingTotalTime)*1000,sumReadingJsonTime*1000,sumReadingJsonCount))
	    
	  def loop_func_analyze(nStr,theLS,theMaxLS,glob_res):
            afterStringJSN=glob_res[nStr]["afterStringJSN"]
	    settingsDict = glob_res[nStr][theLS]

	    for i in range(0, len(afterStringJSN)):

             iniReadingTotalTime = time.time()
             if(float(debug) > 2): log.info("Working on {0}".format(afterStringJSN[i]))
             baseName = os.path.basename(afterStringJSN[i])
             fileNameString = baseName.split('_')
	     
	     if(int(fileNameString[1].split("ls")[1])%int(theMaxLS) != int(theLS)):
                continue
	   
             isOnlyDQMRates = ("DQM" in fileNameString[2] or "Rates" in fileNameString[2])
             isStreamEP = isOnlyDQMRates == False and ("streamP" in fileNameString[2] or "streamH" in fileNameString[2])
             if  (streamType == "onlyDQMRates" and isOnlyDQMRates == False): continue
             elif(streamType == "onlyStreamEP" and isStreamEP == False): continue
             elif(streamType == "noDQMRatesnoStreamEP" and (isOnlyDQMRates == True or isStreamEP == True)): continue

	     if(float(debug) >= 50): log.info("FILE: {0}".format(baseName))
             inpSubFolder = fileNameString[2]
             outSubFolder = fileNameString[2]

             inputJsonFile = afterStringJSN[i]
	     if(float(debug) >= 50): log.info("inputJsonFile: {0}".format(inputJsonFile))
             
             try:
                # renaming the file to avoid issues
                inputJsonRenameFile = inputJsonFile.replace(".jsn","_TEMP.jsn")
                #os.rename(inputJsonFile,inputJsonRenameFile)
                jsonObj = settingsDict[inputJsonRenameFile]
                settings = jsonObj[0]
		jsonTime=jsonObj[1]

             except Exception, e:
                log.error("file not found in settings map? : {0} - {1}".format(inputJsonFile,e))
                settings = "bad"
		jsonTime=0

             # This is just for streamEvD files
             if  ("bad" not in settings and "streamEvDOutput" in fileNameString[2]):

                jsonName = baseName.replace(".jsn","_TEMP.jsn")
                if nWithPollMax < 0:
                   process = thePool.apply_async(moveFiles, [debug, inputDataFolder + "/" + inpSubFolder, outputSMMergedFolder, jsonName, settings])
                else:
                   process = thePool.apply_async(moveFiles, [debug, inputDataFolder + "/" + inpSubFolder, outputSMMergedFolder, jsonName, settings])
		
                settings = "bad"

             # avoid corrupted files or streamEvD files
             if("bad" in settings):
                if("streamEvDOutput" not in fileNameString[2]):
                   log.error("BAD FILE!!!: {0}".format(inputJsonRenameFile))
                continue

             # this is the number of input and output events, and the name of the dat file, something critical
	     # eventsOutput is actually the total number of events to merge in the macromerged stage
             if(float(debug) > 2): log.info("Start building statistics {0}".format(inputJsonRenameFile))
             eventsInput       = int(settings['data'][0])
             eventsOutput      = int(settings['data'][1])
             errorCode         = 0
	     file              = ""
	     fileErrorString   = None
	     fileSize          = 0
             nFilesBU          = 0
             eventsTotalInput  = 0
             checkSum          = 0
             NLostEvents       = 0
	     transferDest      = "dummy"
	     if mergeType == "mini":
                eventsOutputError = int(settings['data'][2])
		errorCode	  = int(settings['data'][3])
		file              = str(settings['data'][4])
		fileSize          = int(settings['data'][5])
		checkSum          = int(settings['data'][7])
		# Avoid wrongly reported checksum values
		if(checkSum == -1):
		   checkSum = 1
		if(len(settings['data']) >= 9):
		   transferDest   = str(settings['data'][8])
		#else:
                #   log.warning("wrong format for checksum: {0}".format(baseName))
	        if(float(debug) >= 50): log.info("Info from json file(eventsInput, eventsOutput, eventsOutputError, errorCode, file, fileSize): {0}, {1}, {2}, {3}, {4}, {5}".format(eventsInput, eventsOutput, eventsOutputError, errorCode, file, fileSize))
	        # processed events == input + error events
		eventsInput = eventsInput + eventsOutputError

		if fileNameString[2] == "streamError":
		   file            = str(settings['data'][6])
		   fileErrorString = file.split(',')
	     else:
		errorCode	 = int(settings['data'][2])
		file             = str(settings['data'][3])
		fileSize         = int(settings['data'][4])
		checkSum	 = int(settings['data'][5])
                nFilesBU	 = int(settings['data'][6])
                eventsTotalInput = int(settings['data'][7])
		NLostEvents      = int(settings['data'][8])
                if(len(settings['data']) >= 10):
                   transferDest  = str(settings['data'][9])

		if fileNameString[2] == "streamError":
		   file            = str(settings['data'][3])
		   fileErrorString = file.split(',')

             key = (fileNameString[0],fileNameString[1],fileNameString[2])
             # procedure to remove DQM left-behind files
             try:
                if(doRemoveFiles == "True" and 
                   key in eventsIDict.keys() and eventsIDict[key][0] < 0):
                   settings = "bad"
                   os.remove(inputJsonRenameFile)
                   inputDataFile = os.path.join(inputDataFolder, inpSubFolder, "data", file)
                   if(os.path.isfile(inputDataFile)):
                      os.remove(inputDataFile)
                   BoLSFileName = fileNameString[0] + "_" + fileNameString[1] + "_" + fileNameString[2] + "_BoLS.jsn"
                   BoLSFileNameFullPath = os.path.join(inputDataFolder, inpSubFolder, "jsns", BoLSFileName)
                   if os.path.exists(BoLSFileNameFullPath):
                      os.remove(BoLSFileNameFullPath)
                   #else:
                   #   log.warning("BoLS File not found: {0}".format(BoLSFileNameFullPath))
             except Exception, e:
                log.error("Deleting file failed {0} {1}".format(inputJsonRenameFile,e))
             if("bad" in settings): continue

             if key in filesDict.keys():
                if(float(debug) > 2): log.info("{0} already exist in filesDict".format(inputJsonRenameFile))
	        if fileErrorString != None and len(fileErrorString) >= 2:
	           for theFiles in range(0, len(fileErrorString)):
		      filesDict[key].append(fileErrorString[theFiles])
	     	else:
		   filesDict[key].append(file)

	     	jsonsDict[key].append(inputJsonRenameFile)

		eventsInput = eventsIDict[key][0] + eventsInput
	     	eventsIDict.update({key:[eventsInput]})

                errorCode = (variablesDict[key][0]|errorCode)
		eventsOutput = variablesDict[key][1] + eventsOutput
		# Needs to be computed before the fileSize is updated
		checkSum = zlibextras.adler32_combine(variablesDict[key][2],checkSum,fileSize)
		checkSum = checkSum & 0xffffffff
		fileSize = variablesDict[key][3] + fileSize
		nFilesBU = variablesDict[key][4] + nFilesBU
		NLostEvents = variablesDict[key][5] + NLostEvents

                variablesDict.update({key:[errorCode,eventsOutput,checkSum,fileSize,nFilesBU,NLostEvents,transferDest]})

                timeJson = timeDict[key][0] + jsonTime
                timeDict.update({key:[timeJson,timeDict[key][1]]})

	     else:
                if(float(debug) > 2): log.info("Adding {0} to filesDict".format(inputJsonRenameFile))
	        if fileErrorString != None and len(fileErrorString) >= 2:
		   filesDict.update({key:[fileErrorString[0]]})
	           for theFiles in range(1, len(fileErrorString)):
		      filesDict[key].append(fileErrorString[theFiles])
                else:
		   filesDict.update({key:[file]})

	     	jsonsDict.update({key:[inputJsonRenameFile]})

                if key in eventsIDict.keys():
                   eventsInput = eventsIDict[key][0] + eventsInput
                   eventsIDict.update({key:[eventsInput]})
                else:
                   eventsIDict.update({key:[eventsInput]})

                variablesDict.update({key:[errorCode,eventsOutput,checkSum,fileSize,nFilesBU,NLostEvents,transferDest]})

                timeDict.update({key:[jsonTime,iniReadingTotalTime]})

             specialStreams = False
             if(fileNameString[2] == "streamDQMHistograms" or fileNameString[2] == "streamHLTRates" or fileNameString[2] == "streamL1Rates" or fileNameString[2] == "streamError"):
                specialStreams = True

             theMergingThreshold = triggerMergingThreshold[1]
             if(fileNameString[2] == "streamDQMEventDisplay"):
                theMergingThreshold = triggerMergingThreshold[0]

             theOutputEndName = outputEndName
	     if (optionMerging != "optionA" and ("DQM" not in fileNameString[2] or theMergingThreshold == 1) and (specialStreams == False) and eventsIDict[key][0] != 0):
                theOutputEndName = "StorageManager"

	     if (optionMerging != "optionA" and ("DQM" not in fileNameString[2] or theMergingThreshold == 1) and (specialStreams == False) and eventsIDict[key][0] == 0 and mergeType == "macro"):
                theOutputEndName = "StorageManager"

             extensionName = ".dat"
             if fileNameString[2] == "streamError":
                extensionName = ".raw"
             elif fileNameString[2] == "streamDQMHistograms":
                extensionName = ".pb"
             elif (fileNameString[2] == "streamHLTRates" or fileNameString[2] == "streamL1Rates"):
                extensionName = ".jsndata"

	     if mergeType == "mini": 
        	keyEoLS = (fileNameString[0],fileNameString[1],fileNameString[2])
		if keyEoLS not in eventsEoLSDict.keys():
	           EoLSName = path_eol + "/" + fileNameString[0] + "/" + fileNameString[0] + "_" + fileNameString[1] + "_EoLS.jsn"
                   if(float(debug) >= 10): log.info("EoLSName: {0}".format(EoLSName))
                   if os.path.exists(EoLSName) and os.path.getsize(EoLSName) > 0:
                      if(float(debug) > 3): log.info("Got EoLSName: {0}".format(EoLSName))
                      inputEoLSName = open(EoLSName, "r").read()
                      settingsEoLS  = json.loads(inputEoLSName)
                      eventsEoLS    = int(settingsEoLS['data'][0])
                      filesEoLS     = int(settingsEoLS['data'][1])
                      eventsAllEoLS = int(settingsEoLS['data'][2])
		      NLostEvents   = int(settingsEoLS['data'][3])
		      eventsEoLSDict.update({keyEoLS:[eventsEoLS,filesEoLS,eventsAllEoLS,NLostEvents]})
                   else:
		      print "PROBLEM WITH: ",EoLSName

        	if keyEoLS in eventsEoLSDict.keys(): # and key in filesDict.keys():
        	#try:
		   if(float(debug) > 2): log.info("mini expected events: {0}, mini received events: {1}, LS: {2}, stream: {3}, run: {4}".format(eventsEoLSDict[keyEoLS][0], eventsIDict[key][0], fileNameString[1], fileNameString[2], fileNameString[0]))
                   if((eventsEoLSDict[keyEoLS][0] == eventsIDict[key][0]) or
                     ((eventsEoLSDict[keyEoLS][0]*triggerMergingThreshold[0] <= eventsIDict[key][0] or variablesDict[key][3] > merging_threshold_size)                                and fileNameString[2] == "streamDQMEventDisplay") or 
                     ((eventsEoLSDict[keyEoLS][0]*triggerMergingThreshold[1] <= eventsIDict[key][0] or variablesDict[key][3] > merging_threshold_size) and "DQM" in fileNameString[2] and fileNameString[2] != "streamDQMHistograms")):
		      # merged files
	              outMergedFile = fileNameString[0] + "_" + fileNameString[1] + "_" + fileNameString[2] + "_" + theOutputEndName + extensionName;
	              outMergedJSON = fileNameString[0] + "_" + fileNameString[1] + "_" + fileNameString[2] + "_" +    outputEndName + ".jsn";

                      inputDataFolderModified = inputDataFolder
		      # need to modify the input data area
		      if fileNameString[2] == "streamError":
                         inputDataFolderModified = path_eol + "/" + fileNameString[0]

                      eventsInputReal = []
		      eventsInputReal.append(eventsIDict[key][0])
		      eventsInputReal.append(eventsEoLSDict[keyEoLS][1])
		      eventsInputReal.append(eventsEoLSDict[keyEoLS][2])
		      eventsInputReal.append(eventsEoLSDict[keyEoLS][3])
                      eventsIDict.update({key:[-1.01*eventsEoLSDict[keyEoLS][0]-1.0]})
                      filesDATA = [word_in_list for word_in_list in filesDict[key]]
                      filesJSON = [word_in_list for word_in_list in jsonsDict[key]]
		      varDictAux = []
		      varDictAux.append(variablesDict[key][1])
		      varDictAux.append(variablesDict[key][2])
		      varDictAux.append(variablesDict[key][3])
		      varDictAux.append(variablesDict[key][0])
		      varDictAux.append(variablesDict[key][6])
                      varDictAux.append(timeDict[key][0])
                      varDictAux.append(timeDict[key][1])

		      loop_func_makedirs(nStr)

                      if(float(debug) > 0): log.info("Spawning merging of {0}".format(outMergedJSON))
                      if("DQM" in fileNameString[2] or fileNameString[2] == "streamHLTRates" or fileNameString[2] == "streamL1Rates"):
                         process = thePoolDQM.apply_async(mergeFiles, [triggerMergingThreshold, inpSubFolder, outSubFolder, outputMergedFolder, outputSMMergedFolder, outputDQMMergedFolder, doCheckSum, outMergedFile, outMergedJSON, inputDataFolderModified, eventsInputReal, varDictAux[0], filesDATA, varDictAux[1], varDictAux[2], filesJSON, varDictAux[3], varDictAux[4], varDictAux[5], varDictAux[6], mergeType, doRemoveFiles, outputEndName, optionMerging, esServerUrl, esIndexName, debug])
		      else:
                         process = thePool.apply_async(   mergeFiles, [triggerMergingThreshold, inpSubFolder, outSubFolder, outputMergedFolder, outputSMMergedFolder, outputDQMMergedFolder, doCheckSum, outMergedFile, outMergedJSON, inputDataFolderModified, eventsInputReal, varDictAux[0], filesDATA, varDictAux[1], varDictAux[2], filesJSON, varDictAux[3], varDictAux[4], varDictAux[5], varDictAux[6], mergeType, doRemoveFiles, outputEndName, optionMerging, esServerUrl, esIndexName, debug])

                      # delete dictionaries to avoid too large memory use
                      try:
                         del timeDict[key]
                         del filesDict[key]
                         del jsonsDict[key] 
                         del variablesDict[key]
                         del eventsEoLSDict[keyEoLS]
                         if("DQM" not in fileNameString[2] and eventsIDict[key][0] != -1 and mergeType != "mini"):
                            del eventsIDict[key]
			 if(float(debug) >= 3): log.info("Dict size/length({0}): files = {1}/{2}, jsons = {3}/{4}, variables = {5}/{6}, eventsEoLS = {7}/{8}, eventsI = {9}/{10}".format(outMergedJSON,sys.getsizeof(filesDict),len(filesDict),sys.getsizeof(jsonsDict),len(jsonsDict),sys.getsizeof(variablesDict),len(variablesDict),sys.getsizeof(eventsEoLSDict),len(eventsEoLSDict),sys.getsizeof(eventsIDict),len(eventsIDict)))
                      except Exception, e:
                         log.warning("cannot delete dictionary {0} - {1}".format(outMergedJSON,e))
                   else:
                      if (float(debug) >= 20):
                	  log.info("Events number does not match: EoL says {0} we have in the files: {1}".format(eventsEoLSDict[keyEoLS][0], eventsIDict[key][0]))
        	else:
        	#except Exception:
                      if (float(debug) >= 20):
                	  log.warning("Looks like {0} is not in filesDict".format(key))

             else:
		if(float(debug) >= 20): log.info("macro-EventsTotalInput/EventsInput/NLostEvents-LS/Stream: {0}, {1}, {2}, {3}".format(eventsTotalInput,eventsIDict[key][0],variablesDict[key][5],fileNameString[1],fileNameString[2]))
                if((eventsTotalInput == (eventsIDict[key][0]+variablesDict[key][5])) or
		  ((eventsTotalInput*triggerMergingThreshold[0] <= (eventsIDict[key][0]+variablesDict[key][5]) or variablesDict[key][3] > merging_threshold_size) and                                fileNameString[2] == "streamDQMEventDisplay") or
		  ((eventsTotalInput*triggerMergingThreshold[1] <= (eventsIDict[key][0]+variablesDict[key][5]) or variablesDict[key][3] > merging_threshold_size) and "DQM" in fileNameString[2] and fileNameString[2] != "streamDQMHistograms")):
	           # merged files
	           outMergedFile = fileNameString[0] + "_" + fileNameString[1] + "_" + fileNameString[2] + "_" + theOutputEndName + extensionName;
	           outMergedJSON = fileNameString[0] + "_" + fileNameString[1] + "_" + fileNameString[2] + "_" + theOutputEndName + ".jsn";

        	   keyEoLS = (fileNameString[0],fileNameString[1],fileNameString[2])
                   eventsEoLS	 = eventsIDict[key][0]
                   filesEoLS	 = variablesDict[key][4]
                   eventsAllEoLS = eventsTotalInput
                   NLostEvents   = variablesDict[key][5]
		   eventsEoLSDict.update({keyEoLS:[eventsEoLS,filesEoLS,eventsAllEoLS,NLostEvents]})

                   eventsInputReal = []
		   eventsInputReal.append(eventsIDict[key][0])
		   eventsInputReal.append(eventsEoLSDict[keyEoLS][1])
		   eventsInputReal.append(eventsEoLSDict[keyEoLS][2])
		   eventsInputReal.append(eventsEoLSDict[keyEoLS][3])
                   eventsIDict.update({key:[-1.01*eventsTotalInput-1.0]})
                   filesDATA = [word_in_list for word_in_list in filesDict[key]]
                   filesJSON = [word_in_list for word_in_list in jsonsDict[key]]
		   varDictAux = []
		   varDictAux.append(variablesDict[key][1])
		   varDictAux.append(variablesDict[key][2])
		   varDictAux.append(variablesDict[key][3])
		   varDictAux.append(variablesDict[key][0])
		   varDictAux.append(variablesDict[key][6])
		   varDictAux.append(timeDict[key][0])
		   varDictAux.append(timeDict[key][1])

		   loop_func_makedirs(nStr)

                   if(float(debug) > 0): log.info("Spawning merging of {0}".format(outMergedJSON))
                   if("DQMHistograms" in fileNameString[2]):
                      process = thePoolDQMH.apply_async(mergeFiles, [triggerMergingThreshold, inpSubFolder, outSubFolder, outputMergedFolder, outputSMMergedFolder, outputDQMMergedFolder, doCheckSum, outMergedFile, outMergedJSON, inputDataFolder, eventsInputReal, varDictAux[0], filesDATA, varDictAux[1], varDictAux[2], filesJSON, varDictAux[3], varDictAux[4], varDictAux[5], varDictAux[6], mergeType, doRemoveFiles, outputEndName, optionMerging, esServerUrl, esIndexName, debug])
                   elif(fileNameString[2] == "streamHLTRates" or fileNameString[2] == "streamL1Rates"):
                      process = thePoolRates.apply_async(mergeFiles,  [triggerMergingThreshold, inpSubFolder, outSubFolder, outputMergedFolder, outputSMMergedFolder, outputDQMMergedFolder, doCheckSum, outMergedFile, outMergedJSON, inputDataFolder, eventsInputReal, varDictAux[0], filesDATA, varDictAux[1], varDictAux[2], filesJSON, varDictAux[3], varDictAux[4], varDictAux[5], varDictAux[6], mergeType, doRemoveFiles, outputEndName, optionMerging, esServerUrl, esIndexName, debug])
                   elif("DQM" in fileNameString[2]):
                      process = thePoolDQM.apply_async(mergeFiles,  [triggerMergingThreshold, inpSubFolder, outSubFolder, outputMergedFolder, outputSMMergedFolder, outputDQMMergedFolder, doCheckSum, outMergedFile, outMergedJSON, inputDataFolder, eventsInputReal, varDictAux[0], filesDATA, varDictAux[1], varDictAux[2], filesJSON, varDictAux[3], varDictAux[4], varDictAux[5], varDictAux[6], mergeType, doRemoveFiles, outputEndName, optionMerging, esServerUrl, esIndexName, debug])
                   else:
                      process = thePool.apply_async(mergeFiles,  [triggerMergingThreshold, inpSubFolder, outSubFolder, outputMergedFolder, outputSMMergedFolder, outputDQMMergedFolder, doCheckSum, outMergedFile, outMergedJSON, inputDataFolder, eventsInputReal, varDictAux[0], filesDATA, varDictAux[1], varDictAux[2], filesJSON, varDictAux[3], varDictAux[4], varDictAux[5], varDictAux[6], mergeType, doRemoveFiles, outputEndName, optionMerging, esServerUrl, esIndexName, debug])

                   # delete dictionaries to avoid too large memory use
                   try:
                      del timeDict[key]
                      del filesDict[key]
                      del jsonsDict[key] 
                      del variablesDict[key]
                      del eventsEoLSDict[keyEoLS]
                      if("DQM" not in fileNameString[2] and eventsIDict[key][0] != -1 and mergeType != "mini"):
                         del eventsIDict[key]
                      if(float(debug) >= 3): log.info("Dict size/length({0}): files = {1}/{2}, jsons = {3}/{4}, variables = {5}/{6}, eventsEoLS = {7}/{8}, eventsI = {9}/{10}".format(outMergedJSON,sys.getsizeof(filesDict),len(filesDict),sys.getsizeof(jsonsDict),len(jsonsDict),sys.getsizeof(variablesDict),len(variablesDict),sys.getsizeof(eventsEoLSDict),len(eventsEoLSDict),sys.getsizeof(eventsIDict),len(eventsIDict)))
                   except Exception, e:
                      log.warning("cannot delete dictionary {0} - {1}".format(outMergedJSON,e))
                else:
                   if (float(debug) >= 20):
                       log.info("Events number does not match: EoL says {0}, we have in the files: {1}".format(eventsOutput, eventsIDict[key][0]))

             endReadingTotalTime = time.time()
	     if((endReadingTotalTime-iniReadingTotalTime)*1000 > tooSlowTime):
                log.warning("Too slow analyzing json({0}): analyzing({1} msecs)".format(inputJsonRenameFile,(endReadingTotalTime-iniReadingTotalTime)*1000))
             #end loop function


          #prepare thread pools
	  numParalel = len(listFolders)*maxParallelLSs or 1
	  if not jsonReaderPool or jsonReaderPoolSize<numParalel:
            log.info('initializing pool of '+str(numParalel))
	    jsonReaderPool = SimplePool(numParalel)
	    jsonReaderPoolSize=numParalel

          iniParalelLoopTime = time.time()
          deltaT = iniParalelLoopTime-listStreamsTime
	  if deltaT*1000>tooSlowTime:
		  log.info("Time for listing runs: {0} msecs".format(deltaT*1000))
          timeSpentListStreams += deltaT
	  #directory listing and reading json files (1st loop, serial)
          #loop_ini_params = []
          for nStr in range(0, len(listFolders)):
             loop_func_ini(nStr)
          #for nStr in range(0, len(listFolders)):
          #   loop_ini_params.append(nStr)
          #if len(loop_ini_params):
          #  log.info(str(loop_ini_params))
          #  jsonReaderPool.map(loop_func_ini,loop_ini_params)
          lumisParalelLoopTime = time.time()
	  deltaT = lumisParalelLoopTime-iniParalelLoopTime
	  if deltaT*1000>tooSlowTime*5:
		  log.info("Time for paralel reading of ini files: {0} msecs".format(deltaT*1000))
	  timeSpenthandleIniFiles += deltaT

	  #directory listing and reading json files (2nd loop, listing is paralel for streams, reading is paralel for streams and max paralel lumisections)
	  glob_result = {}
          loop_params_list = []
	  for nStr in range(0, len(listFolders)):
	        glob_result[nStr]={}
                loop_params_list.append([nStr, glob_result])
          if len(loop_params_list):
            jsonReaderPool.map(loop_func_list,loop_params_list)
          loop_params_list = []
          lumisListLoopEndTime = time.time()
	  deltaT = lumisListLoopEndTime-lumisParalelLoopTime
	  timeSpentListJsons += deltaT
	  if deltaT*1000>tooSlowTime*5:
		  log.info("Time for listing stream/LS json files: {0} msecs".format(deltaT*1000))

	  loop_params=[]
	  for nStr in range(0, len(listFolders)):
	     glob_lock = threading.Lock()
             for nLs in range(0, maxParallelLSs):
	        glob_result[nStr][nLs]={}
                loop_params.append([nStr, maxParallelLSs, nLs, glob_result])
          if len(loop_params):
            jsonReaderPool.map(loop_func_read,loop_params)
	  loop_params=[]

          lumisParalelLoopEndTime = time.time()
	  deltaT = lumisParalelLoopEndTime-lumisListLoopEndTime
	  #print reading times longer than 1 second
	  if deltaT*1000>tooSlowTime*5:
		  log.info("Time for reading of stream/LS json files: {0} msecs".format(deltaT*1000))
	  timeSpentGetJsons += deltaT

          #json data analysis (4th loop, serial)
	  for nStr in range(0, len(listFolders)):
             for nLs in range(0, maxParallelLSs):
		loop_func_analyze(nStr,nLs,maxParallelLSs,glob_result)
	  glob_result = None
          lumisAnalysisLoopEndTime = time.time()
	  deltaT = lumisAnalysisLoopEndTime-lumisParalelLoopEndTime
	  if deltaT*1000>tooSlowTime*5:
		  log.info("Time for analysis of stream/LS json files: {0} msecs".format(deltaT*1000))
	  timeSpentAnalyzeJsons += deltaT

	  # clean-up work is done here
          EoRFileName = path_eol + "/" + theRunNumber + "/" + theRunNumber + "_ls0000_EoR.jsn"
          try:
             if(os.path.exists(EoRFileName) and os.path.getsize(EoRFileName) > 0):

                if(doRemoveFiles == "True" and mergeType == "mini"):
                   if(float(debug) >= 3): log.info("Try to create dirs under {0} before cleaning up folder".format(outputSMMergedFolder))
                   if not os.path.exists(outputSMMergedFolder):
                      try:
                         os.makedirs(outputSMMergedFolder)
                      except Exception, e:
                         log.error("CleanUp-creadir dir folder error: {0}".format(e))

                   listFolders = sorted(glob.glob(os.path.join(inputDataFolder, 'stream*')));
                   after_eor = dict()
                   try:
                      after_temp_eor = dict ([(f, None) for f in glob.glob(os.path.join(inputDataFolder, '*.jsn'))])
                      after_eor.update(after_temp_eor)
                      for nStr in range(0, len(listFolders)):
                         after_temp_eor = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], '*.jsn'))])
                         after_eor.update(after_temp_eor)
                         after_temp_eor = dict ([(f, None) for f in glob.glob(os.path.join(listFolders[nStr], 'jsns', '*.jsn'))])
                         after_eor.update(after_temp_eor)
                   except Exception, e:
                      log.error("glob.glob operation failed: {0} - {1}".format(inputDataFolder,e))

                   afterStringNoSortedEOR = [f for f in after_eor if ( (f.endswith(".jsn")) and ("TEMP" not in f) and (("EoR" in f) or ("BoLS" in f))) ]
                   afterStringEOR =sorted(afterStringNoSortedEOR, reverse=False)

                   isRunComplete = cmsDataFlowCleanUp.cleanUpRun(debug, EoRFileName, inputDataFolder, afterStringEOR, path_eol, theRunNumber, outputSMMergedFolder, outputEndName, completeMergingThreshold)
                   if(float(debug) >= 3): log.info("isRunComplete({0}): {1}".format(theRunNumber,isRunComplete))
                   if(isRunComplete == True):
                      remove_key_tuples(eventsIDict,(theRunNumber,'*','*'))
                      if(float(debug) >= 1): log.info("Remaining keys in eventsIDict: {0}".format(eventsIDict))
          except Exception, e:
             log.error("CleanUp folder error: {0}".format(e))

          eorCheckEndTime = time.time()
	  deltaT = eorCheckEndTime-lumisAnalysisLoopEndTime
	  if deltaT*1000>tooSlowTime:
		  log.info("Time for EoR checks: {0} msecs".format(deltaT*1000))
	  timeSpentCheckEoR += deltaT

          if timeLastRun == -1: timeLastRun = eorCheckEndTime - listStreamsTime
      totTime = (timeSpentListStreams+timeSpenthandleIniFiles+timeSpentListJsons+timeSpentGetJsons+timeSpentAnalyzeJsons+timeSpentCheckEoR)*1000
      if(float(debug) >= 1) and totTime>tooSlowTime*5:
        log.info("Main loop summary: ListStreams: {0:.2} FindINIFiles: {1:.1f} FindJsons: {2:.1f} ReadJsons: {3:.1f} AnalyzeJsons: {4:.1f} EoRChecks: {5:.1f} msecs. Time spent on last run: {6:.1f} Total: {7:.1f} msecs".format(timeSpentListStreams*1000,timeSpenthandleIniFiles*1000,timeSpentListJsons*1000,timeSpentGetJsons*1000,timeSpentAnalyzeJsons*1000,timeSpentCheckEoR*1000,timeLastRun*1000,totTime))

   if nWithPollMax > 0:
      thePool.close()
      thePool.join()
      thePoolDQM.close()
      thePoolDQM.join()
      thePoolDQMH.close()
      thePoolDQMH.join()
      thePoolRates.close()
      thePoolRates.join()

def start_merging(paths_to_watch, path_eol, mergeType, streamType, outputMerge, outputSMMerge, outputDQMMerge, doCheckSum, outputEndName, doRemoveFiles, optionMerging, esServerUrl, esIndexName, numberOfShards, numberOfReplicas, debug):

    triggerMergingThreshold = [0.5001, 0.8000] # DQMEventDisplay and DQM
    #triggerMergingThreshold = [1.0, 1.0] # DQMEventDisplay and DQM
    completeMergingThreshold = 1.0

    if(triggerMergingThreshold[0] == 1 or triggerMergingThreshold[1] == 1):
       merging_threshold_size = 5000 * 1024 * 1024 * 1024 # just an unreasonable large value

    if mergeType != "mini" and mergeType != "macro" and mergeType != "auto":
       msg = "Wrong type of merging: %s" % mergeType
       raise RuntimeError, msg
    
    if mergeType == "auto":
       theHost = socket.gethostname()
       if "bu" in theHost.lower():
          mergeType = "mini"
       else:
          mergeType = "macro"
    
    if mergeType == "mini":
       triggerMergingThreshold[0] = 0.80
       triggerMergingThreshold[1] = 0.90
       #triggerMergingThreshold[0] = 1.00
       #triggerMergingThreshold[1] = 1.00
       if(triggerMergingThreshold[0] == 1 or triggerMergingThreshold[1] == 1):
          merging_threshold_size = 5000 * 1024 * 1024 * 1024 # just an unreasonable large value
       if not os.path.exists(path_eol):
          msg = "End of Lumi folder Not Found: %s" % path_eol
          raise RuntimeError, msg
    
    if not os.path.exists(outputMerge):
       try:
          os.makedirs(outputMerge)
       except Exception, e:
          log.warning("Looks like the directory {0} has just been created by someone else...".format(outputMerge))
    
    if not os.path.exists(outputSMMerge):
       try:
          os.makedirs(outputSMMerge)
       except Exception, e:
          log.warning("Looks like the directory {0} has just been created by someone else...".format(outputSMMerge))
    
    if not os.path.exists(outputDQMMerge):
       try:
          os.makedirs(outputDQMMerge)
       except Exception, e:
          log.warning("Looks like the directory {0} has just been created by someone else...".format(outputDQMMerge))
    
    if not (esServerUrl == '' or esIndexName==''):
        esMonitorMapping(esServerUrl,esIndexName,numberOfShards,numberOfReplicas,debug)

    doTheRecovering(paths_to_watch, streamType, mergeType, debug)
    doTheMerging(paths_to_watch, path_eol, mergeType, streamType, debug, outputMerge, outputSMMerge, outputDQMMerge, doCheckSum, outputEndName, doRemoveFiles, optionMerging, triggerMergingThreshold, completeMergingThreshold, esServerUrl, esIndexName)
