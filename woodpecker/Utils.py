# Woodpecker utilities
#
# (c) Copyright James Aylett 2006, 2008
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301
# USA

import email, email.Errors, os

# Originally taken from standard mailbox; note that the standard
# Python license is GPL-compatible.
class Subfile:
    def __init__(self, fp, start, stop=None):
        self.fp = fp
        self.start = start

        if stop==None:
            mark = self.fp.tell()
            self.fp.seek(0, 2) # end of file
            self.stop = self.fp.tell()
            self.fp.seek(mark)
        else:        
            self.stop = stop
        self.pos = self.start

    def read(self, length = None):
        if self.pos >= self.stop:
            return ''
        remaining = self.stop - self.pos
        if length is None or length < 0:
            length = remaining
        elif length > remaining:
            length = remaining
        self.fp.seek(self.pos)
        data = self.fp.read(length)
        self.pos = self.fp.tell()
        return data

    def readline(self, length = None):
        if self.pos >= self.stop:
            return ''
        if length is None:
            length = self.stop - self.pos
        self.fp.seek(self.pos)
        data = self.fp.readline(length)
        self.pos = self.fp.tell()
        return data

    def readlines(self, sizehint = -1):
        lines = []
        while 1:
            line = self.readline()
            if not line:
                break
            lines.append(line)
            if sizehint >= 0:
                sizehint = sizehint - len(line)
                if sizehint <= 0:
                    break
        return lines

    def tell(self):
        return self.pos - self.start

    def seek(self, pos, whence=0):
        if whence == 0:
            self.pos = self.start + pos
        elif whence == 1:
            self.pos = self.pos + pos
        elif whence == 2:
            self.pos = self.stop + pos

    def close(self):
        del self.fp

def msgfactory(fp):
    try:
        return email.message_from_file(fp)
    except email.Errors.MessageParseError:
        # Don't return None since that will
        # stop the mailbox iterator
        return ''
    except MemoryError:
        # Similarly (happens on HUGE emails)
        return ''

def make_temp_file(string):
    fname = os.tempnam()
    os.unlink(fname)
    fp = file(fname, "wb")
    fp.write(string)
    fp.close()
    return fname

def remove_temp_file(fname):
    os.unlink(fname)

def stdout_to_string(cmd):
    out = ""
    try:
        fh = os.popen(cmd, "rb")
        out = fh.read()
        fh.close()
    except KeyboardInterrupt:
        raise
    except:
        import traceback
        traceback.print_exc()
        pass
    return out

class MBoxSource:
    def __init__(self, filename, message_num):
        self.filename = filename
        self.message_num = message_num

    def add_terms(self, indexer):
        indexer.index_text_without_positions(self.filename, 1, 'XFILENAME')

    def get_data(self):
        return { 'Filename': self.filename, 'MessageNum': self.message_num }
