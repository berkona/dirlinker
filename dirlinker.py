# This code is released with no warranty or guarantee as to features or functionality, all rights thrown away, copylefted 2012

import subprocess
import argparse
import pickle
import time

from os import path, walk, link, makedirs, rmdir
from platform import system
from sys import argv
from sys import exit

VERSION = '%(prog)s v1.1'
STRINGS = {
    'unicodeError': 'Could not write link, invalid character encoding',
    'description': 'This program recursively scans a source directory and places hard links of all files specified by FILTER_FILE (defaults to video files) in the target directory.  A list of previously linked files is maintained by this program so that only files which were not linked previously are linked.',
    'source': 'The root folder to link files from.  This is converted to an absolute path.',
    'target': 'The folder that links will be created in.  This is converted to an absolute path.',
    'logFile': 'Name of the log file.  The log file will be placed in target/LOG_FILE.log.',
    'storeFile': 'Name of the storage file.  The file will be place in target/STORE_FILE.ldir.',
    'filter': 'This will load extensions from the given file (it assumes the file is either comma or new-line delimited.',
    'directory': 'Enable recreating the folder structure of SOURCE in TARGET'
}

# This is a somewhat complete list of extensions for video containers,
# suggestions are welcome
DEFAULT_FILTER_FILE = 'default_filter.txt'


class FileLinker:
    def __init__(self, config):
        for n, v in vars(config).items():
            setattr(self, n, v)

        self.messages = []
        self.links = []
        self.linkFunc = None

        if system() == 'Windows':
            self.linkFunc = self._makeLinkWindows
        else:
            self.linkFunc = link

        if self.enableDirectoryCreation:
            self.dirFunc = self._linkDirectories
        else:
            self.dirFunc = self._linkFlat

    def run(self):
        self._parseFilter()
        self._loadPickle()

        self.dirFunc()

        if (self.pruneDirectories):
            self._pruneDirectories()

        self._writePickle()
        self._writeLog()

    def _linkDirectories(self):
        for root, dirs, files in walk(self.source):
            self._log('Processing directory ' + self._formatPath(self.source, root))
            newDir = root.replace(self.source, self.target, 1)

            filtered = list(filter(lambda f:
                self._filterFile(path.join(newDir, f)), files))

            # Offset directory creation to here to prevent creating empty directories.
            # I.e., when we don't link any files because of some filtering rule.
            # We use os.makedirs in case we skipped some intermediate folders
            # due to filtering
            if not filtered and not path.exists(newDir):
                self._log('Created directory ' + self._formatPath(self.target, newDir))
                makedirs(newDir)

            for f in filtered:
                newPath = path.join(newDir, f)
                self._makeLink(path.join(root, f), newPath)
                self.links.append(newPath)

    def _linkFlat(self):
        for root, dirs, files in walk(self.source):
            self._log('Processing directory ' + self._formatPath(self.source, root))
            filtered = filter(lambda f:
                self._filterFile(path.join(self.target, f)), files)

            for f in filtered:
                newPath = path.join(self.target, f)
                self._makeLink(path.join(root, f), newPath)
                self.links.append(newPath)

    def _pruneDirectories(self):
        for root, dirs, files in walk(self.target, TopDown=False):
            if (len(dirs) == 0 and len(files) == 0):
                self._log('Pruning empty directory ' + self._formatPath(self.target, root))
                rmdir(root)

    def _filterFileItr(self, filterFile):
        for line in filterFile:
            line = line.replace('\t', '').replace('\n', '').replace(' ', '')
            if not line or line.startswith('#'):
                continue

            for token in filter(lambda s: s or s.isspace(), line.split(',')):
                if not token or token.startswith('#'):
                    continue

                yield token

    def _parseFilter(self):
        self.filter = []
        with open(self.filterPath, 'r', encoding='utf-8') as filterFile:
            for ext in self._filterFileItr(filterFile):
                self.filter.append(ext)

        self._log('Filter loaded from %s.' % self.filterPath)
        self._log('Enabled extensions: %s' % ', '.join(self.filter))

    def _filterFile(self, p):
        return not (path.exists(p) or p in self.links or
            path.splitext(p)[1].lower() not in self.filter)

    def _makeLink(self, src, dst):
        if (self.linkFunc == None):
            raise RuntimeError('No link function has been defined for this implementation or something horrible has happened')
        self._log('Created link ' + self._formatPath(self.target, dst))
        self.linkFunc(src, dst)

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

        self._log('Loaded link list from '
            + self._formatPath(self.target, self.storeFile))

    def _writePickle(self):
        data = {
            'links': self.links,
            'dirCreation': self.enableDirectoryCreation,
            'filter': self.filter
        }

        with open(self.storeFile, 'wb') as f:
            pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)

        self._log('Wrote session data to '
            + self._formatPath(self.target, self.storeFile))

    def _formatMessage(self, msg):
        return '%s - %s' % (time.strftime('%c', time.localtime()), msg)

    def _formatPath(self, parent, p):
        if parent == p:
            return '/'
        return p.replace(parent, '').replace('\\', '/')

    def _log(self, msg):
        try:
            formattedStr = self._formatMessage(msg)
            self.messages.append(formattedStr)
            print(formattedStr)
        except UnicodeEncodeError:
            self.messages.append(self._formatMessage(STRINGS['unicodeError']))

    def _writeLog(self):
        self._log('Wrote log to ' + self._formatPath(self.target, self.logFile))
        with open(self.logFile, 'a', encoding='utf-8') as f:
            for msg in self.messages:
                try:
                    f.write(msg + '\n')
                except UnicodeEncodeError as u:
                    errorText = STRINGS['unicodeError']
                    errNo = u.errno
                    errMsg = u.strerror
                    f.write(self._formatMessage('%s - (%d) %s\n'
                        % (errorText, errNo, errMsg)))


def main():
    parser = argparse.ArgumentParser(description=STRINGS['description'])

    # required
    parser.add_argument('source', type=path.abspath, help=STRINGS['source'])
    parser.add_argument('target', type=path.abspath, help=STRINGS['target'])

    # optional flags
    parser.add_argument('-v', '--version', action='version',
        version=VERSION)

    parser.add_argument('-l', '--log-file', dest='logFile', default='dir_linker',
        metavar='LOG_FILE', help=STRINGS['logFile'])

    parser.add_argument('-s', '--store-file', dest='storeFile', default='dir_linker',
        metavar='STORE_FILE', help=STRINGS['storeFile'])

    parser.add_argument('-f', '--filter',  dest='filterPath', type=path.abspath,
        default=path.join(path.dirname(argv[0]), DEFAULT_FILTER_FILE),
        metavar='FILTER_FILE', help=STRINGS['filter'])

    parser.add_argument('-d', '--enable-directory-creation',
        dest='enableDirectoryCreation', action='store_const', const=True,
        default=False, help=STRINGS['directory'])

    parser.add_argument('-p', '--prune-directories', dest='pruneDirectories',
        action='store_const', const=True, default=False)

    config = parser.parse_args()

    # Post-processing for arguments
    config.logFile = path.join(config.target, config.logFile + '.log')
    config.storeFile = path.join(config.target, config.storeFile + '.ldir')

    FileLinker(config).run()

    return 0


if __name__ == "__main__":
    exit(main())
