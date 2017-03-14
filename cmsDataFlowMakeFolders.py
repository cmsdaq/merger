#!/usr/bin/env python
import os

from Logging import getLogger
log = getLogger()

"""
making theOutput folders
"""
def doMakeFolders(theOutputMergedFolderJSNS, theOutputSMMergedFolderJSNS, theOutputDQMMergedFolderJSNS, 
                  theOutputMergedFolderDATA, theOutputSMMergedFolderDATA, theOutputDQMMergedFolderDATA, 
                  theOutputBadFolder, theOutputSMBadFolder, theOutputSMRecoveryFolder):

   if not os.path.exists(theOutputMergedFolderJSNS):
      try:
          os.makedirs(theOutputMergedFolderJSNS)
          msg = "sudo lfs setstripe -c 1 -S 1m {0}".format(theOutputMergedFolderJSNS)
          os.system(msg)
      except Exception, e:
          log.error(
          "Create directory {0} failed: {1}".format(
          theOutputMergedFolderJSNS,e))

   if not os.path.exists(theOutputSMMergedFolderJSNS):
      try:
          os.makedirs(theOutputSMMergedFolderJSNS)
          msg = "sudo lfs setstripe -c 1 -S 1m {0}".format(theOutputSMMergedFolderJSNS)
          os.system(msg)
      except Exception, e:
          log.error(
          "Create directory {0} failed: {1}".format(
          theOutputSMMergedFolderJSNS,e))

   if not os.path.exists(theOutputDQMMergedFolderJSNS):
      try:
          os.makedirs(theOutputDQMMergedFolderJSNS)
          msg = "sudo lfs setstripe -c 1 -S 1m {0}".format(theOutputDQMMergedFolderJSNS)
          os.system(msg)
      except Exception, e:
          log.error(
          "Create directory {0} failed: {1}".format(
          theOutputDQMMergedFolderJSNS,e))

   if not os.path.exists(theOutputMergedFolderDATA):
      try:
          os.makedirs(theOutputMergedFolderDATA)
      except Exception, e:
          log.error(
          "Create directory {0} failed: {1}".format(
          theOutputMergedFolderDATA,e))

   if not os.path.exists(theOutputSMMergedFolderDATA):
      try:
          os.makedirs(theOutputSMMergedFolderDATA)
      except Exception, e:
          log.error(
          "Create directory {0} failed: {1}".format(
          theOutputSMMergedFolderDATA,e))

   if not os.path.exists(theOutputDQMMergedFolderDATA):
      try:
          os.makedirs(theOutputDQMMergedFolderDATA)
      except Exception, e:
          log.error(
          "Create directory {0} failed: {1}".format(
          theOutputDQMMergedFolderDATA,e))

   if not os.path.exists(theOutputBadFolder):
      try:
          os.makedirs(theOutputBadFolder)
      except Exception, e:
          log.error(
          "Create directory {0} failed: {1}".format(
          theOutputBadFolder,e))

   if not os.path.exists(theOutputSMBadFolder):
      try:
          os.makedirs(theOutputSMBadFolder)
      except Exception, e:
          log.error(
          "Create directory {0} failed: {1}".format(
          theOutputSMBadFolder,e))

   if not os.path.exists(theOutputSMRecoveryFolder):
      try:
          os.makedirs(theOutputSMRecoveryFolder)
      except Exception, e:
          log.error(
          "Create directory {0} failed: {1}".format(
          theOutputSMRecoveryFolder,e))
