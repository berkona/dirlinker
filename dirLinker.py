import os
import sys
import subprocess
import platform
import pickle
import time
import argparse


UNICODE_ERROR_STR = 'Could not write link, invalid character encoding'
DESCRIPTION_STR = 'This program recursively scans a source directory and attempts to recreate the folder and file structure using \'real\' folders and using hard links for files.\nA list of previously linked files is maintained by this program so that only files which were not linked previously are linked.'
SRC_STR = 'The root folder to link files from.  This is converted to an absolute path.'
TARGET_STR = 'The folder that links will be created in.  This is converted to an absolute path.'
LOG_FILE_STR = 'Name of the log file.  The log file will be placed in target/LOGFILE.log.'
STORE_FILE_STR = 'Name of the storage file.  The file will be place in target/STOREFILE.ldir.'
FILTER_STR = 'List of extensions to use.  If the only argument provided is a file, it will load extensions from the given file (it assumes the file is either comma or new-line delimited.'

DEFAULT_EXTENSIONS = ['3gp', '3g2', 'asf', 'wma', 'wmv', 'avi', 'divx', 'evo', 'f4v', 'flv', 'mkv', 'mk3d', 'mka', 'mks', 'mcf', 'mp4', 'mpg', 'mpeg', 'ps', 'ts', 'm2ts', 'mxf', 'ogg', 'mov', 'qt', 'rmvb', 'vob', 'webm']

class FileLinker:
    def __init__(self, args):
        for n, v in inspect.getmembers(args):
            setattr(self, n, v)

        self.messages = []
        self.links = []
        self.linkFunc = None

        systemStr = platform.system()
        if (systemStr == 'Windows'):
            self.linkFunc = self.makeLinkWindows
        else:
            self.linkFunc = os.link

    def filterFile(self, path):
        ext = os.path.splitext(path)[1]
        return path == self.storeFile or path == self.logFile or os.path.exists(path) or path in self.links or ext in self.extensions

    def makeLink(self, src, dst):
        if (self.linkFunc == None):
            raise RuntimeError()
        self.log('Created link %s' % self.formatPath(self.target, dst))
        self.linkFunc(src, dst)

    def makeLinkWindows(self, source, target):
        subprocess.call(['cmd', '/C', 'mklink', '/H', target, source], stdout=subprocess.PIPE)

    def linkDirectories(self):
        self.loadPickle()
        for root, dirs, files in os.walk(self.source):
            self.log('Processing directory %s' % self.formatPath(self.source, root))
            newDir = root.replace(self.source, self.target, 1)

            for f in files:
                newPath = os.path.join(newDir, f)

                if (self.filterFile(newPath)):
                    continue

                # Offset directory creation to here to prevent creating empty directories.
                # I.e., when we don't link any files because of some filtering rule.
                # We use os.makedirs in case we skipped some intermediate folders due to filtering
                if not os.path.exists(newDir):
                    self.log('Created directory %s' % self.formatPath(self.target, newDir))
                    os.makedirs(newDir)

                self.links.append(str(newPath).encode('utf-8'))
                self.makeLink(os.path.join(root, f), newPath)
        
        self.writePickle()
        self.writeLog()

    def loadPickle(self):
        if not os.path.exists(self.storeFile):
            return
        with open(self.storeFile, 'rb') as f:
            self.links = pickle.load(f)
        self.log('Loaded link list from %s' % self.formatPath(self.target, self.storeFile))

    def writePickle(self):
        with open(self.storeFile, 'wb') as f:
            pickle.dump(self.links, f, pickle.HIGHEST_PROTOCOL)
        self.log('Wrote link list to %s' % self.formatPath(self.target, self.storeFile))

    def formatMessage(self, msg):
        return '%s - %s' % (time.strftime('%c', time.localtime()), msg)

    def formatPath(self, parent, path):
        return path.replace(parent, '').replace('\\', '/')

    def log(self, msg):
        try:
            formattedStr = self.formatMessage(msg)
            self.messages.append(formattedStr)
            print(formattedStr)
        except UnicodeEncodeError:
            self.messages.append(self.formatMessage(UNICODE_ERROR_STR))

    def writeLog(self):
        self.log('Wrote log to %s' % self.formatPath(self.target, self.logFile))
        with open(self.logFile, 'a') as f:
            for msg in self.messages:
                try:
                    f.write('%s\n' % msg)
                except UnicodeEncodeError as u:
                    f.write('%s\n' % self.formatMessage('%s - (%d) %s' % (UNICODE_ERROR_STR, u.errno, u.strerror)))


def main(args):
    parser = argparse.ArgumentParser(description=DESCRIPTION_STR)
    
    # required
    parser.add_argument('source', type=os.path.abspath, help=SRC_STR)
    parser.add_argument('target', type=os.path.abspath, help=TARGET_STR)
    
    # optional/flags
    parser.add_argument('-v --version', action='version', version='%(prog)s 1.0')
    
    parser.add_argument('-l --log-file', metavar='LOGFILE', dest='logFile', default='dir_linker', help=LOG_FILE_STR)
    
    parser.add_argument('-s --store-file', metavar='STOREFILE', dest='storeFile', default='dir_linker', help=STORE_FILE_STR)

    parser.add_argument('-f --filter', nargs='+', metavar='EXT', dest='extensions', default=DEFAULT_EXTENSIONS, help=FILTER_STR)

    args = parser.parse_args()
    
    # Post-processing for arguments
    args.logFile = os.path.join(args.target, '%s.log' % args.logFile)
    args.storeFile = os.path.join(args.target, '%s.ldir' % args.storeFile)

    FileLinker(args).linkDirectories()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
