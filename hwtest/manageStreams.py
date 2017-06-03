#!/usr/bin/env python
# -*- coding: utf-8 -*-

from configobj import ConfigObj
from makeFiles import createFiles

import os, sys
from optparse import OptionParser
import multiprocessing
from multiprocessing.pool import ThreadPool
import time,datetime
import random
import math
import json

start_time = datetime.datetime.now()

#______________________________________________________________________________
def main():
    parser = make_option_parser()

    options, args = parser.parse_args()

    if len(args) != 0:
        parser.error("You specified an invalid option - please use -h to review the allowed options")
    
    if (options.configFile == None):
        parser.error('Please specify the configuration file using the -c/--config option')

    theBUId = 10
    if (options.BUId != None):
       theBUId = options.BUId

    theTotalBUs = 1
    if (options.totalBUs != None):
       theTotalBUs = options.totalBUs

    thePath = ""
    if (options.Path != None):
       thePath = options.Path

    theInputPath = "dummy"
    if (options.inputPath != None):
       theInputPath = options.inputPath

    if not os.path.exists(theInputPath):
       msg = "BIG PROBLEM, file does not exists!: %s" % str(theInputPath)
       raise RuntimeError, msg

    lumi_length_mean = 1.
    if (options.lumi_length_mean != None):
       lumi_length_mean = float(options.lumi_length_mean)
    
    lumi_length_sigma = 0.001
    if (options.lumi_length_sigma != None):
       lumi_length_sigma = float(options.lumi_length_sigma)

    params = configureStreams(options.configFile)
    filesNb = int(params['Streams']['number'])
    lumiSections = int(params['Streams']['ls'])
    runNumber = int(params['Streams']['runnumber'])

    thePool = ThreadPool(30)

    contentInputFile = []
    for i in range(filesNb):
        sizePerFile = int(params['Streams']['size' + str(i)])
        fileName = "inputFile_" + str(int(sizePerFile)) + "MB.dat"
        fullFileName = os.path.join(theInputPath, fileName)
        if not os.path.exists(fullFileName):
           msg = "BIG PROBLEM, file does not exists!: %s" % str(fullFileName)
           raise RuntimeError, msg

        #contentInputFile.append(fullFileName)
        with open(fullFileName, 'r') as theInputfile:
           contentInputFile.append(theInputfile.read())
        theInputfile.close()

    init(options, params)
    
    theNumberOfFilesPerLS = 10
    theNInput = 1000
    theNOutput = 10

    for ls in range(lumiSections):
       processs = []

       create_ls_files(options, params, ls, theNumberOfFilesPerLS, theNInput)

       now = datetime.datetime.now()

       print now.strftime("%H:%M:%S"), ": writing ls(%d)" % (ls)

       for i in range(filesNb):
          # Produce files every lumi_length_mean seconds with random flutuation
          sleep_time = seconds_to_sleep(ls, lumi_length_mean, lumi_length_sigma)
          streamName =  params['Streams']['name' + str(i)]
          thePool.apply_async(launch_file_making, [streamName, contentInputFile[i], ls, runNumber, theBUId, thePath, theTotalBUs, sleep_time, theNumberOfFilesPerLS, theNInput, theNOutput])

       print now.strftime("%H:%M:%S"), ": finished LS", ls, ", exiting..."
       time.sleep(1)

    thePool.close()
    thePool.join()

    create_eor_files(options, params, lumiSections, theNumberOfFilesPerLS, theNInput)

    now = datetime.datetime.now()
    print now.strftime("%H:%M:%S"), ": finished, exiting..."
## main
    
#______________________________________________________________________________
def make_option_parser():
    parser = OptionParser(usage="usage: %prog [-h|--help] -c|--config config -b|--bu BUId | -p|--path Path | -i|--inputPath inputPath")

    parser.add_option("-c", "--config",
                      action="store", dest="configFile",
                      help="Configuration file storing the info related to the simulated streams of data. Absolute path is needed")

    parser.add_option("-b", "--bu",
                      action="store", dest="BUId",
                      help="BU number")

    parser.add_option("-p", "--path",
                      action="store", dest="Path",
                      help="Path to make")

    parser.add_option("-i", "--inputPath",
                      action="store", dest="inputPath",
                      help="Input path")

    parser.add_option("-m", "--lumi-length-mean",
                      action="store", dest="lumi_length_mean",
                      help="Mean length of lumi sections in seconds as a float")

    parser.add_option("-s", "--lumi-length-sigma",
                      action="store", dest="lumi_length_sigma",
                      help="Standard deviation of lumi section length " +
                           "distribution as a float")

    parser.add_option("-a", "--number_of_bus",
                      action="store", dest="totalBUs",
                      help="Number of BUs")

    return parser
## make_option_parser


#______________________________________________________________________________
def configureStreams(fileName):
    streamsConfigFile = fileName 

    try:
        if os.path.isfile(streamsConfigFile):
            config = ConfigObj(streamsConfigFile)
        else:
            print "Configuration file not found: {0}!".format(streamsConfigFile)
            sys.exit(1)
    except IOError, e:
        print "Unable to open configuration file: {0}!".format(streamsConfigFile)
        sys.exit(1)
    
    return config

#______________________________________________________________________________
def seconds_to_sleep(ls, lumi_length_mean=20, lumi_length_sigma=0.001):
    mean_offset = ls * lumi_length_mean
    expected_offset = mean_offset + random.gauss(0., lumi_length_sigma)
    actual_offset = total_seconds(datetime.datetime.now() - start_time)
    ret = max(0., expected_offset - actual_offset)
    return ret
## seconds_to_sleep

#______________________________________________________________________________
def total_seconds(tdelta):
    '''
    Returns the total number of seconds of a datetime.timedelta object.
    '''
    return 3600 * 24 * tdelta.days + tdelta.seconds + 1e-6 * tdelta.microseconds
## total_seconds

#______________________________________________________________________________
def launch_file_making(streamName, contentInputFile, lumiSections, runNumber,
                       theBUId, thePath, theTotalBUs, sleep_time, 
		       theNumberOfFilesPerLS, theNInput, theNOutput):
    time.sleep(sleep_time)
    createFiles(streamName, contentInputFile, lumiSections, runNumber,
                theBUId, thePath, theTotalBUs, 0.0, -1,
                theNumberOfFilesPerLS, theNInput, theNOutput)

## launch_file_making


#______________________________________________________________________________
def init(options, params):
    create_data_dir(options, params)
    create_mon_dir(options, params)
    create_ini_files(options, params)
## init

#______________________________________________________________________________
def create_ini_files(options, params):
    path_to_make = options.Path
    if path_to_make == None:
       path_to_make = ""
    RUNNumber = int(params['Streams']['runnumber'])
    filesNb = int(params['Streams']['number'])
    theBUNumber = options.BUId
    ## loop over streams
    for i in range(filesNb):
        streamName =  params['Streams']['name' + str(i)]
	myDir = "%sunmergedDATA/run%d/%s/data" % (path_to_make,RUNNumber,streamName)
        if not os.path.exists(myDir):
           try:
               os.makedirs(myDir)
           except OSError, e:
              print "Looks like the creation of " + myDir + " has failed"
        fileIntNameFullPath = "%sunmergedDATA/run%d/%s/data/run%d_ls0000_%s_BU%s.ini" % (path_to_make,RUNNumber,streamName,RUNNumber,streamName,theBUNumber)
        with open(fileIntNameFullPath, 'w') as thefile:
           thefile.write('0' * 10)
           thefile.write("\n")
## create_ini_files

#______________________________________________________________________________
def create_ls_files(options, params, ls, numberOfFilesPerLS, nInput):
    path_to_make = options.Path
    if path_to_make == None:
       path_to_make = ""
    RUNNumber = int(params['Streams']['runnumber'])
    filesNb = int(params['Streams']['number'])
    theTotalBUs = 1
    if (options.totalBUs != None):
       theTotalBUs = options.totalBUs

    msgHLT = "%sunmergedMON/run%d/hlt" % (path_to_make,RUNNumber)
    if(not os.path.exists(msgHLT)):
       os.mkdir(msgHLT)

    fileLSNameFullPath = "%sunmergedMON/run%d/run%d_ls%d_EoLS.jsn" % (path_to_make,RUNNumber,RUNNumber,ls)
    try:
       with open(fileLSNameFullPath, 'w') as theFileLSName:
    	  theFileLSName.write(json.dumps({'data': (nInput*int(numberOfFilesPerLS), int(numberOfFilesPerLS)*int(theTotalBUs), nInput*int(numberOfFilesPerLS)*int(theTotalBUs), 0)}))
    except OSError, e:
       print "Looks like the file " + fileLSNameFullPath + " has just been created by someone else..."
## create_ls_files

#______________________________________________________________________________
def create_eor_files(options, params, lumiSections, numberOfFilesPerLS, nInput):
    path_to_make = options.Path
    if path_to_make == None:
       path_to_make = ""
    RUNNumber = int(params['Streams']['runnumber'])

    fileEoRNameFullPath = "%sunmergedMON/run%d/run%d_ls0000_EoR.jsn" % (path_to_make,RUNNumber,RUNNumber)
    try:
       with open(fileEoRNameFullPath, 'w') as theFileEoRName:
    	  theFileEoRName.write(json.dumps({'data': (nInput*int(numberOfFilesPerLS)*lumiSections, int(numberOfFilesPerLS)*lumiSections, lumiSections, lumiSections)}))
    except OSError, e:
       print "Looks like the file " + fileEoRNameFullPath + " has just been created by someone else..."

    fileEoRFUNameFullPath = "%sunmergedDATA/run%d/run%d_ls0000_EoR_FU.jsn" % (path_to_make,RUNNumber,RUNNumber)
    try:
       with open(fileEoRFUNameFullPath, 'w') as theFileEoRFUName:
    	  theFileEoRFUName.write(json.dumps({'data': (nInput*int(numberOfFilesPerLS)*lumiSections, int(numberOfFilesPerLS)*lumiSections)}))
    except OSError, e:
       print "Looks like the file " + fileEoRFUNameFullPath + " has just been created by someone else..."
## create_eor_files

#______________________________________________________________________________
def create_data_dir(options, params):
    path_to_make = options.Path
    if path_to_make == None:
       path_to_make = ""
    RUNNumber = int(params['Streams']['runnumber'])
    myDir = "%sunmergedDATA/run%d" % (path_to_make, RUNNumber)
    if not os.path.exists(myDir):
        try:
           os.makedirs(myDir)
        except OSError, e:
           print "Looks like the directory " + myDir + " has just been created by someone else..."
## create_data_dir

#______________________________________________________________________________
def create_mon_dir(options, params):
    path_to_make = options.Path
    if path_to_make == None:
       path_to_make = ""
    RUNNumber = int(params['Streams']['runnumber'])
    myDir = "%sunmergedMON/run%d" % (path_to_make, RUNNumber)
    if not os.path.exists(myDir):
        try:
           os.makedirs(myDir)
        except OSError, e:
           print "Looks like the directory " + myDir + " has just been created by someone else..."
## create_mon_dir


#______________________________________________________________________________
if __name__ == '__main__':
    main()
