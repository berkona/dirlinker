# This code is released with no warranty or guarantee as to features or functionality, all rights thrown away, copylefted 2012

import argparse
import logging
import pickle
import json

import logging.config

from os import path, walk, makedirs, rmdir
from sys import argv, exit

VERSION = '%(prog)s v1.1'
STRINGS = {
    'unicodeError': 'Could not write link, invalid character encoding',
    'description': 'This program recursively scans a source directory and places hard links of all files specified by FILTER_FILE (defaults to video files) in the target directory.  A list of previously linked files is maintained by this program so that only files which were not linked previously are linked.',
    'source': 'The root folder to link files from.  This is converted to an absolute path.',
    'target': 'The folder that links will be created in.  This is converted to an absolute path.',
    'logFile': 'Name of the log file.  The log file will be placed in target/LOG_FILE.log.',
    'storeFile': 'Name of the storage file.  The file will be place in target/STORE_FILE.ldir.',
    'filter': 'This will load extensions from the given file (it assumes the file is either comma or new-line delimited.',
    'directory': 'Enable recreating the folder structure of SOURCE in TARGET',
    'prune': 'Delete all empty directories inside of TARGET after linking'
}

# This is a somewhat complete list of extensions for video containers,
# suggestions are welcome
DEFAULT_FILTER_FILE = 'default_filter.txt'

Logger = logging.getLogger()


# Linktastic Module
# - A python2/3 compatible module that can create hardlinks/symlinks on windows-based systems
#
# Linktastic is distributed under the MIT License.  The follow are the terms and conditions of using Linktastic.
#
# The MIT License (MIT)
#  Copyright (c) 2012 Solipsis Development
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
# associated documentation files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial
# portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
# LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import subprocess
from subprocess import CalledProcessError
import os


# Private function to create link on nt-based systems
def _link_windows(src, dest):
    try:
        subprocess.check_output(
            ['cmd', '/C', 'mklink', '/H', dest, src],
            stderr=subprocess.STDOUT)
    except CalledProcessError as err:
        raise IOError(err.output.decode('utf-8'))

    # TODO, find out what kind of messages Windows sends us from mklink
    # print(stdout)
    # assume if they ret-coded 0 we're good


def _symlink_windows(src, dest):
    try:
        subprocess.check_output(
            ['cmd', '/C', 'mklink', dest, src],
            stderr=subprocess.STDOUT)
    except CalledProcessError as err:
        raise IOError(err.output.decode('utf-8'))

    # TODO, find out what kind of messages Windows sends us from mklink
    # print(stdout)
    # assume if they ret-coded 0 we're good


# Create a hard link to src named as dest
# This version of link, unlike os.link, supports nt systems as well
def link(src, dest):
    if os.name == 'nt':
        _link_windows(src, dest)
    else:
        os.link(src, dest)


# Create a symlink to src named as dest, but don't fail if you're on nt
def symlink(src, dest):
    if os.name == 'nt':
        _symlink_windows(src, dest)
    else:
        os.symlink(src, dest)

        
class FileLinker:
    def __init__(self, config):
        for n, v in vars(config).items():
            setattr(self, n, v)

        self.messages = []
        self.links = []
        self.linkFunc = link

        if self.enableDirectoryCreation:
            self.dirFunc = self._linkDirectories
        else:
            self.dirFunc = self._linkFlat

    def run(self):
        prefix = '#' * 10
        Logger.debug('%s FileLinker startup %s', prefix, prefix)

        try:
            self._parseFilter()
        except:
            Logger.exception('Could not load filter:')
            raise

        try:
            self._loadPickle()
        except:
            Logger.exception('Could not load session data:')
            raise

        # Implementations should probably handle exceptions on their own
        self.dirFunc()

        # _pruneDirectories() handles exception
        if (self.pruneDirectories):
            self._pruneDirectories()

        try:
            self._writePickle()
        except:
            Logger.exception('Could not write session data:')
            raise

        Logger.debug('%s FileLinker shutdown %s', prefix, prefix)

    def _linkDirectories(self):
        for root, dirs, files in walk(self.source):
            Logger.info('Processing directory %s',
                self._formatPath(self.source, root))
            newDir = root.replace(self.source, self.target, 1)

            filtered = list(filter(lambda f:
                self._filterFile(path.join(newDir, f)), files))

            # Offset directory creation to here to prevent creating empty
            # directories. I.e., when we don't link any files because of
            # some filtering rule. We use os.makedirs in case we skipped
            # some intermediate folders due to filtering
            if filtered and not path.exists(newDir):
                Logger.info('Created directory %s',
                    self._formatPath(self.target, newDir))
                makedirs(newDir)

            for f in filtered:
                newPath = path.join(newDir, f)
                self._makeLink(path.join(root, f), newPath)

    def _linkFlat(self):
        for root, dirs, files in walk(self.source):
            Logger.info('Processing directory %s',
                self._formatPath(self.source, root))

            filtered = filter(lambda f:
                self._filterFile(path.join(self.target, f)), files)

            for f in filtered:
                newPath = path.join(self.target, f)
                self._makeLink(path.join(root, f), newPath)

    def _pruneDirectories(self):
        for root, dirs, files in walk(self.target, topdown=False):
            if dirs or files:
                continue

            Logger.info('Pruning empty directory %s',
                self._formatPath(self.target, root))
            try:
                rmdir(root)
            except:
                Logger.exception('Could not remove directory %s', root)

    def _parseFilter(self):
        with open(self.filterPath, 'r') as filterFile:
            self.filter = json.load(filterFile)

        Logger.info('Filter loaded from %s.', self.filterPath)
        Logger.info('Enabled extensions: %s', ', '.join(self.filter))

    def _filterFile(self, p):
        return not (path.exists(p) or p in self.links or
            path.splitext(p)[1].lower() not in self.filter)

    def _makeLink(self, src, dst):
        if (self.linkFunc == None):
            raise RuntimeError('No link function has been defined for this implementation or something horrible has happened')
        try:
            self.linkFunc(src, dst)
            self.links.append(dst)
            Logger.info('Created link %s', self._formatPath(self.target, dst))
        except:
            Logger.exception('Could not make link %s => %s', src, dst)

    def _makeLinkWindows(self, source, target):
        subprocess.call(['cmd', '/C', 'mklink', '/H', target, source],
            stdout=subprocess.PIPE)

    def _loadPickle(self):
        if not path.exists(self.storeFile):
            return
        with open(self.storeFile, 'rb') as f:
            data = pickle.load(f)
            if (data['dirCreation'] == self.enableDirectoryCreation
                and set(data['filter']) == set(self.filter)):
                self.links = data['links']

        Logger.info('Loaded link list from %s',
            self._formatPath(self.target, self.storeFile))

    def _writePickle(self):
        data = {
            'links': self.links,
            'dirCreation': self.enableDirectoryCreation,
            'filter': self.filter
        }

        with open(self.storeFile, 'wb') as f:
            pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)

        Logger.info('Wrote session data to %s',
            self._formatPath(self.target, self.storeFile))

    # def _formatMessage(self, msg):
    #     return '%s - %s' % (time.strftime('%c', time.localtime()), msg)

    def _formatPath(self, parent, p):
        if parent == p:
            return '/'
        return p.replace(parent, '').replace('\\', '/')

    # def _log(self, msg):
    #     try:
    #         formattedStr = self._formatMessage(msg)
    #         self.messages.append(formattedStr)
    #         print(formattedStr)
    #     except UnicodeEncodeError:
    #         self.messages.append(self._formatMessage(STRINGS['unicodeError']))

    # def _writeLog(self):
    #     Logger.info`('Wrote log to ' + self._formatPath(self.target, self.logFile))
    #     with open(self.logFile, 'a') as f:
    #         for msg in self.messages:
    #             try:
    #                 f.write(msg + '\n')
    #             except UnicodeEncodeError as u:
    #                 errorText = STRINGS['unicodeError']
    #                 errNo = u.errno
    #                 errMsg = u.strerror
    #                 f.write(self._formatMessage('%s - (%d) %s\n'
    #                     % (errorText, errNo, errMsg)))


def main():
    parser = argparse.ArgumentParser(description=STRINGS['description'])

    # required
    parser.add_argument('source', type=path.abspath, help=STRINGS['source'])
    parser.add_argument('target', type=path.abspath, help=STRINGS['target'])

    # optional flags
    parser.add_argument('-v', '--version', action='version',
        version=VERSION)

    parser.add_argument('-l', '--log-file', dest='logFile', default='dirlinker',
        metavar='LOG_FILE', help=STRINGS['logFile'])

    parser.add_argument('-s', '--store-file', dest='storeFile', default='dirlinker',
        metavar='STORE_FILE', help=STRINGS['storeFile'])

    parser.add_argument('-f', '--filter',  dest='filterPath', type=path.abspath,
        default=path.join(path.dirname(argv[0]), DEFAULT_FILTER_FILE),
        metavar='FILTER_FILE', help=STRINGS['filter'])

    parser.add_argument('-d', '--enable-directory-creation',
        dest='enableDirectoryCreation', action='store_true', default=False, help=STRINGS['directory'])

    parser.add_argument('-p', '--prune-directories', dest='pruneDirectories',
        action='store_const', const=True, default=False, help=STRINGS['prune'])

    config = parser.parse_args()

    # Post-processing for arguments
    config.logFile = path.join(config.target, config.logFile + '.log')
    config.storeFile = path.join(config.target, config.storeFile + '.ldir')

    configPath = path.join(path.dirname(argv[0]), 'log_config.ini')
    logging.config.fileConfig(configPath)

    fileHandler = logging.FileHandler(config.logFile,
        encoding='utf-8', delay=True)
    fileHandler.formatter = logging.Formatter('%(asctime)s|%(levelname)-7.7s %(message)s', '%H:%M:%S')
    fileHandler.level = logging.DEBUG

    Logger.addHandler(fileHandler)

    FileLinker(config).run()

    logging.shutdown()

    return 0


if __name__ == "__main__":
    exit(main())
