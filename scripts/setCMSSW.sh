#!/bin/sh

myDir=$PWD/;

cd /opt/offline/;
source $PWD/cmsset_default.sh;
cd slc7_amd64_gcc630/cms/cmssw/CMSSW_9_2_10/;
eval `scramv1 runtime -sh`;

cd $myDir;
