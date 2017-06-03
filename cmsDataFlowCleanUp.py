#!/usr/bin/env python
import os, time, sys, getopt, fcntl
import shutil
import json
import glob
import cmsDataFlowMerger
from datetime import datetime, timedelta, date

from Logging import getLogger
log = getLogger()

"""
clean up run folder if some conditions are met
"""
def cleanUpRun(debug, EoRFileName, inputDataFolder, afterString, path_eol, 
      theRunNumber, outputSMMergedFolder, outputEndName, 
      completeMergingThreshold):
   
   settingsEoR = cmsDataFlowMerger.readJsonFile(EoRFileName, debug)

   if("bad" in settingsEoR): return False

   eventsInputBU = int(settingsEoR['data'][0])

   eventsInputFU = 0
   for nb in range(0, len(afterString)):
      if "EoR" not in afterString[nb]: continue
      inputEoRFUJsonFile = afterString[nb]
      settingsLS = cmsDataFlowMerger.readJsonFile(inputEoRFUJsonFile, debug)

      if("bad" in settingsLS): continue

      eventsInputFU = eventsInputFU + int(settingsLS['data'][0])
   
   if(float(debug) >= 50): log.info(
      "eventsInputBU vs. eventsInputFU: {0} vs. {1}".format
      (eventsInputBU,eventsInputFU))
   if (eventsInputBU*completeMergingThreshold <= eventsInputFU):
      numberBoLSFiles = 0
      for nb in range(0, len(afterString)):
         if not afterString[nb].endswith("_BoLS.jsn"): continue
         if "DQM" in afterString[nb]: continue
         if "streamError" in afterString[nb]: continue
         numberBoLSFiles = numberBoLSFiles + 1
      if(float(debug) >= 50): log.info(
         "numberBoLSFiles: {0}".format(numberBoLSFiles))
      
      EoLSFolder    = os.path.join(path_eol, theRunNumber)
      eventsEoLS          = [0, 0, 0]
      eventsEoLS_noLastLS = [0, 0, 0]
      lastLumiBU = doSumEoLS(EoLSFolder, eventsEoLS, eventsEoLS_noLastLS)

      if(eventsEoLS[0] != eventsInputBU):
         log.info("PROBLEM eventsEoLS != eventsInputBU: {0} vs. {1}".format(
                  eventsEoLS[0],eventsInputBU))

      # This is done to make sure there won't be files created after we start deleting the folder
      deltaTimeHLTFolderCreation = timedelta(minutes=10)
      hltFolder = os.path.join(EoLSFolder,"hlt")
      if(os.path.exists(hltFolder)):
          m_time_stamp = int(os.stat(hltFolder).st_ctime)
          m_utc_date_time = datetime.utcfromtimestamp(m_time_stamp)
          deltaTimeHLTFolderCreation = datetime.utcnow() - m_utc_date_time
      else:
         log.error("PROBLEM HLT folder does not exist {0}".format(hltFolder))

      if(numberBoLSFiles == 0 and eventsInputBU == eventsInputFU and
        (deltaTimeHLTFolderCreation > timedelta(minutes=5) or lastLumiBU > 3)):
         # This is needed to cleanUp the macroMerger later
         EoRFileNameMiniOutput       = (
            outputSMMergedFolder + "/" + theRunNumber + "_ls0000_MiniEoR_" + 
            outputEndName + ".jsn_TEMP")
         EoRFileNameMiniOutputStable = (
            outputSMMergedFolder + "/" + theRunNumber + "_ls0000_MiniEoR_" + 
            outputEndName + ".jsn")

         theEoRFileMiniOutput = open(EoRFileNameMiniOutput, 'w')
         theEoRFileMiniOutput.write(
            json.dumps({'eventsInputBU':   eventsInputBU, 
                        'eventsInputFU':   eventsInputFU, 
                        'numberBoLSFiles': numberBoLSFiles,
                        'eventsTotalRun':  eventsEoLS[1],
                        'eventsLostBU':    eventsEoLS[2],
                        'eventsInputBU_noLastLS':   eventsEoLS_noLastLS[0], 
                        'eventsTotalRun_noLastLS':  eventsEoLS_noLastLS[1],
                        'eventsLostBU_noLastLS':    eventsEoLS_noLastLS[2],
                        'lastLumiBU':      lastLumiBU}))
         theEoRFileMiniOutput.close()

         shutil.move(EoRFileNameMiniOutput, EoRFileNameMiniOutputStable)

         log.info("Run folder deletion is triggered!: {0} and {1}".format(
                 inputDataFolder,EoLSFolder))
         time.sleep(10)
         try:
            shutil.rmtree(inputDataFolder)
         except Exception,e:
            log.error("Failed removing {0} - {1}".format(inputDataFolder,e))
         try:
            if os.path.islink(EoLSFolder):
               link_dir = os.readlink(EoLSFolder)
               log.info("EoLS run dir is a symlink pointing to {0}".format(
                       link_dir))
               os.unlink(EoLSFolder)
               EoLSFolder = link_dir
            shutil.rmtree(EoLSFolder)
         except Exception,e:
            log.error("Failed removing {0} - {1}".format(EoLSFolder,e))

         return True

      else:
          if(numberBoLSFiles == 0 and eventsInputBU == eventsInputFU):
              log.info("Open run({0}) all DONE, lastLumiBU = {1}, deltaCreation: {2}".format(EoLSFolder,lastLumiBU,deltaTimeHLTFolderCreation))
          return False

   else:
      return False

def doSumEoLS(inputDataFolder, eventsEoLS, eventsEoLS_noLastLS):

   after = dict ([(f, None) for f in glob.glob(os.path.join(inputDataFolder, '*.jsn'))])
   afterStringNoSorted = [f for f in after if (f.endswith("EoLS.jsn"))]

   afterString = sorted(afterStringNoSorted, reverse=True)
   numberLS = 0

   lastLumiBU = -1

   # total number of processed events in a given BU (not counting last LS)
   eventsEoLS_noLastLS[0] = 0
   # total number of processed events in all BUs (not counting last LS)
   eventsEoLS_noLastLS[1] = 0
   # total number of lost events in a given BU (not counting last LS)
   eventsEoLS_noLastLS[2] = 0

   # total number of processed events in a given BU
   eventsEoLS[0] = 0
   # total number of processed events in all BUs
   eventsEoLS[1] = 0
   # total number of lost events in a given BU
   eventsEoLS[2] = 0
   for nb in range(0, len(afterString)):

      EoLSFileName = afterString[nb]

      if(os.path.exists(EoLSFileName) and os.path.getsize(EoLSFileName) > 0):
         inputEoLSName = open(EoLSFileName, "r").read()
         settingsEoLS  = json.loads(inputEoLSName)

         if(int(settingsEoLS['data'][0]) > 0 or 
            int(settingsEoLS['data'][2]) > 0 or
            int(settingsEoLS['data'][3]) > 0):
            numberLS = numberLS + 1
            if numberLS != 1:
               eventsEoLS_noLastLS[0] += int(settingsEoLS['data'][0])
               eventsEoLS_noLastLS[1] += int(settingsEoLS['data'][2])
               eventsEoLS_noLastLS[2] += int(settingsEoLS['data'][3])

            else:
               fileNameString = EoLSFileName.split('_')
               try:
                  lastLumiBU = int(fileNameString[1].replace("ls",""))
               except Exception,e:
                  log.error("lastLumiBU assignment failed {0} - {1}".format(
                           fileNameString[1],e))

            eventsEoLS[0] += int(settingsEoLS['data'][0])
            eventsEoLS[1] += int(settingsEoLS['data'][2])
            eventsEoLS[2] += int(settingsEoLS['data'][3])

   return lastLumiBU
