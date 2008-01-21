#!/usr/bin/env python
#
# woodpecker -- manage omega-style database of mbox emails
#
# ----START-LICENSE----
# Copyright 2006 James Aylett
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
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA
# -----END-LICENCE-----

import email, email.Errors, email.Utils, mailbox
import random, md5, sys, socket, string, time
import xapian

hostname = socket.getfqdn()
MAX_PROB_TERM_LENGTH=64
MAX_URL_LENGTH = 240
HASH_LEN = 32

# taken from standard mailbox, note that standard Python license is
# GPL-compatible
class _Subfile:
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

def hash_string(s):
    return md5.new(s).hexdigest()

def rand():
    return random.randint(0,4*1024*1024*1024*1023)

def get_last_index_point(mbox):
    return (None, None)

def is_incremental_indexable(mbox):
    return False

def update_last_index_point(mbox, nmessages):
    pass

def index_mailbox(db, mbox, stemmer):
    sys.stdout.write("Indexing %s..." % mbox)
    sys.stdout.flush()
    _fp = file(mbox)
    tpl = get_last_index_point(mbox) # and num emails in mbox up to index point
    if tpl[0]==None:
        num = 0
        fp = _fp
    else:
        num = tpl[1]
        fp = _Subfile(_fp, tpl[0])
    try:
        num = do_index(db, fp, mbox, stemmer)
    except KeyboardInterrupt:
        raise
    except:
        import traceback
        traceback.print_exc()
        pass
    _fp.close()
    sys.stdout.write(" done [%i].\n" % num)
    sys.stdout.flush()
    if is_incremental_indexable(mbox):
        update_last_index_point(mbox, num)

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

def do_index(db, fp, mboxfilename, stemmer):
    m = mailbox.PortableUnixMailbox(fp, msgfactory)
    messnum = 0
    while True:
        mess = m.next()
        if mess==None:
            break
        if mess=="":
            continue

        try:
            index_message(db, mess, mboxfilename, messnum, stemmer)
        except KeyboardInterrupt:
            raise
        except:
            import traceback
            traceback.print_exc()
        messnum+=1
    return messnum

def index_subpart(doc, mess, index_start, stemmer=None):
    if mess.is_multipart():
        for mess in mess.get_payload():
            return index_subpart(doc, mess, index_start, stemmer=stemmer)
    else:
        return index_single_part(doc, mess, index_start, stemmer=stemmer)

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

def index_single_part(doc, mess, index_start, stemmer=None):
    if mess.get_content_type=='text/plain':
        return index_text(doc, None, mess.get_payload(decode=True), index_start, stemmer=stemmer)
    if mess.get_content_type=='text/html':
        txt = mess.get_payload(decode=True)
        tfl = make_temp_file(txt)
        txt = stdout_to_string("elinks --dump %s" % tfl)
        remove_temp_file(tfl)
        return index_text(doc, None, txt, index_start, stemmer=stemmer)
    # TODO: anything useful for other types?
    return index_start

def index_message(db, mess, mboxfilename, messnum, stemmer):
    # generate a Q-term
    mid = mess.get("message-id")
    if mid==None:
        # generate our own message id
        mid = "%s@woodpecker.%s" % (rand(), hostname)
    else:
        mid = mid.strip()
        mid = mid.strip("<>")

    qterm = "Q:%s" % mid
    if len(qterm) > MAX_URL_LENGTH:
        qterm = qterm[0:MAX_URL_LENGTH - HASH_LEN] + hash_string(qterm[MAX_URL_LENGTH - HASH_LEN:])

    doc = xapian.Document()
    doc.add_term(qterm)

    # index headers
    index_text(doc, "A", mess.get("from", ""), stemmer=stemmer)
    index_text(doc, "XT", mess.get("to", ""), stemmer=stemmer)
    index_text(doc, "XT", mess.get("cc", ""), stemmer=stemmer)
    index_text(doc, "XS", mess.get("subject", ""), stemmer=stemmer)
    index_text(doc, "XD", mess.get("date", ""), stemmer=stemmer)

    index_text(doc, "XFILENAME", mboxfilename, stemmer=stemmer)

    #for segment in mboxfilename.split('/'):
    #    if len(segment)==0:
    #        continue
    #    if segment[0].isupper():
    #        doc.add_term("XFILENAME:R" + segment.lower())
    #    doc.add_term("XFILENAME" + stemmer(segment.lower()))

    # index text
    index_start = 0
    if mess.is_multipart():
        for messge in mess.get_payload():
            index_start = index_subpart(doc, messge, index_start, stemmer=stemmer)
            index_start += 100
    else:
        index_start = index_single_part(doc, mess, index_start, stemmer=stemmer)
        index_start += 100

    index_start = index_text(doc, "", mess.get("from", ""), index_start, stemmer=stemmer)
    index_start = index_text(doc, "", mess.get("to", ""), index_start + 100, stemmer=stemmer)
    index_start = index_text(doc, "", mess.get("cc", ""), index_start + 100, stemmer=stemmer)
    index_start = index_text(doc, "", mess.get("subject", ""), index_start + 100, stemmer=stemmer)
    index_start = index_text(doc, "", mess.get("date", ""), index_start + 100, stemmer=stemmer)

    try:
        date = mess["date"]
        pdate = email.Utils.parsedate_tz(date)
        utcdate = email.Utils.mktime_tz(pdate)
        doc.add_term("D" + time.strftime("%Y%m%d", utcdate))
        doc.add_term("M" + time.strftime("%Y%m", utcdate))
        doc.add_term("Y" + time.strftime("%Y", utcdate))
        weak = time.strftime("%Y%m%d", utcdate)
        weak = weak[:-1]
        if weak[-1]=='3':
            weak = weak[:-1] + '2'
        doc.add_term("W" + weak)
    except KeyboardInterrupt:
        raise
    except:
        pass

    sample = ""

    MAX_SAMPLE_LENGTH = 300
    for part in mess.walk():
        if part.get_content_type()=="text/plain":
            text = part.get_payload(decode=True)
            if text==None:
                #print "Ignoring a part in %s [%s]" % (qterm, str(mess.is_multipart()))
                continue
            if len(sample)<MAX_SAMPLE_LENGTH and len(sample)>0:
                sample+="..."
            j = MAX_SAMPLE_LENGTH - len(sample)
            if j >= len(text):
                j = len(text)-1
            while j>0 and text[j].isalnum():
                j-=1
            if j==0:
                length = (MAX_SAMPLE_LENGTH-len(sample))/2
                if length>len(text):
                    length = len(text)
                sample += text[0:length] + "..."
            else:
                while j>0 and not text[j].isalnum():
                    j-=1
                sample += text[0:j+1]

    data =  "From=%s\n" % mess.get("from", "").replace("\n", " ")
    data += "To=%s\n" % mess.get("to", "").replace("\n", " ")
    if mess.get("cc")!=None:
        data += "Cc=%s\n" % mess.get("cc").replace("\n", " ")
    data += "Title=%s\n" % mess.get("subject")
    data += "Date=%s\n" % mess.get("date")
    data += "Sample=%s\n" % sample.replace("\n", " ")
    data += "Filename=%s\n" % mboxfilename
    data += "MessageNum=%i\n" % messnum
    doc.set_data(data)

    db.replace_document(qterm, doc)
    #sys.stdout.write(".")
    #sys.stdout.flush()

def index_text(doc, prefix, text, pos=None, stemmer=None, wdfinc=1):
    if text==None or text=="":
        return pos
    rprefix = prefix
    if len(prefix)>1 and prefix[-1]!=':':
        rprefix = "%s:R" % prefix
    else:
        rprefix = "%sR" % prefix

    j = 0
    s_end = len(text)
    while True:
        first = j
        while first!=s_end and not text[first].isalnum():
            first+=1
        if first==s_end:
            break
        term = ""
        
        if text[first].isupper():
            j = first
            term = text[j]
            j+=1
            while j!=s_end and text[j]=='.':
                if j+1!=s_end and text[j+1].isupper():
                    j+=1
                    term += (text[j])
                else:
                    break
            if len(term) < 2 or j!=len(text) and text[j].isalnum():
                term = ""
            last = j

        if len(term)==0:
            j=first
            while text[j].isalnum():
                term += (text[j])
                j+=1
                if j==s_end:
                    break
                if text[j]=='&':
                    next = j
                    next+=1
                    if next==len(text) or not text[next].isalnum():
                        break
                    term += ('&')
                    j = next

            last = j
            if j!=s_end and (text[j]=='#' or p_plusminus(text[j])):
                length = len(term)
                if text[j]=='#':
                    term += ('#')
                    cont = True
                    while cont:
                        j+=1
                        cont = (j!=s_end and text[j]=='#')
                else:
                    while j!=s_end and p_plusminus(text[j]):
                        term += (text[j])
                        j+=1
                if j!=s_end and text[j].isalnum():
                    term = term[0:length]
                else:
                    last = j

        if len(term)<MAX_PROB_TERM_LENGTH:
            term = term.lower()
            if text[first].isupper():
                if pos!=None:
                    doc.add_posting(rprefix + term, pos, wdfinc)
                else:
                    doc.add_term(rprefix + term, wdfinc)

            term = stemmer(term)
            if pos!=None:
                pos+=1
                doc.add_posting(prefix + term, pos, wdfinc)
            else:
                doc.add_term(prefix + term, wdfinc)

    return pos

def p_plusminus(c):
    return c=='+' or c=='-'

class Pecker:
    def __init__(self, database, language=None):
        self.database = database
        self.indexer = xapian.TermGenerator()
        if language!=None:
            self.stemmer = xapian.Stem(language)
            self.indexer.set_stemmer(self.stemmer)

    def index_single_part(self, part):
        pass

    def index_subpart(self, part):
        pass

    def index_message(self, part):
        pass

    def index_mailbox(self, mbox_file):
        pass

    def _log(self, message):
        sys.stdout.write(message)
        sys.stdout.flush()
        pass

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print "Usage: woodpecker <db> <mboxes>"
        sys.exit(0)

    db = xapian.WritableDatabase(sys.argv[1], xapian.DB_CREATE_OR_OPEN)
    stemmer = xapian.Stem("english")

    print "Starting at " + time.ctime()
        
    for mbox in sys.argv[2:]:
        try:
            index_mailbox(db, mbox, stemmer)
        except:
            import traceback
            traceback.print_exc()
            pass
    print "Finishing at " + time.ctime()
