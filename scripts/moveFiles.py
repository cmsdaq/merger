#!/usr/bin/env python                                                                                                                                                                

import os, shutil, sys, getopt, glob

def doMove(theInput,theOutput):

    listJsonFiles = sorted(glob.glob(os.path.join(theInput, 'run*.jsn')));
    for i in range(0, len(listJsonFiles)):

        inputJsonFile = listJsonFiles[i]
        iniName = os.path.basename(inputJsonFile).split('_')

        if("MiniEoR" in iniName):
            shutil.move(inputJsonFile,os.path.join(theOutput,os.path.basename(inputJsonFile)))
        else:
            inputDataFile = inputJsonFile.replace(".jsn",".dat")
            if not os.path.exists(inputDataFile):
        	inputDataFile = inputJsonFile.replace(".jsn",".pb")
        	if not os.path.exists(inputDataFile):
                    inputDataFile = inputJsonFile.replace(".jsn",".jsndata")
                    if not os.path.exists(inputDataFile) and iniName[2] != "streamError":
                       msg = "input file %s does not have associated data file" % inputJsonFile
                       print msg

            if not os.path.exists(os.path.join(theOutput,iniName[2],"jsns")):
		os.makedirs(os.path.join(theOutput,iniName[2],"data"))
		os.makedirs(os.path.join(theOutput,iniName[2],"jsns"))

            if os.path.exists(inputDataFile):
        	shutil.move(inputDataFile,os.path.join(theOutput,iniName[2],"data",os.path.basename(inputDataFile)))
        	shutil.move(inputJsonFile,os.path.join(theOutput,iniName[2],"jsns",os.path.basename(inputJsonFile)))

"""
Main
"""
valid = ['input=', 'output=', 'help']

usage =  "Usage: moveFiles.py --input=<input_folder>\n"
usage += "                    --output=<output_folders>\n"

try:
    opts, args = getopt.getopt(sys.argv[1:], "", valid)
except getopt.GetoptError, ex:
    print usage
    print str(ex)
    sys.exit(1)

input  = "dummy"
output = "dummy"

for opt, arg in opts:
    if opt == "--help":
        print usage
        sys.exit(1)
    if opt == "--input":
        input = arg
    if opt == "--output":
        output = arg

if not os.path.exists(input):
    msg = "input folder not Found: %s" % input
    raise RuntimeError, msg

if not os.path.exists(output):
    msg = "output folder not Found: %s" % input
    raise RuntimeError, msg

doMove(input,output)
