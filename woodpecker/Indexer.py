# Woodpecker indexer
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

import email.Utils, mailbox, getopt
import random, md5, sys, socket, string, time
import xapian
import woodpecker.Utils

from woodpecker.Utils import make_temp_file, remove_temp_file, stdout_to_string

hostname = socket.getfqdn()

class Pecker:
    def __init__(self, config):
        self.database = config.get_writeable_index()
        self.indexer = xapian.TermGenerator()
        if config.language!=None:
            self.stemmer = xapian.Stem(config.language)
            self.indexer.set_stemmer(self.stemmer)
        self.VALUE_UTCDATETIME = 0 # as serialised float
        self.VALUE_UTCDATE = 1 # as YYMMDD

    def flush(self):
        self.database.flush()

    def index_part(self, part):
        if part.is_multipart():
            for subpart in part.get_payload():
                self.index_part(subpart)
        else:
            if part.get_content_type=='text/plain':
                self.indexer.index_text(part.get_payload(decode=True))
            if part.get_content_type=='text/html':
                txt = part.get_payload(decode=True)
                tfl = make_temp_file(txt)
                txt = stdout_to_string("elinks --dump %s" % tfl)
                remove_temp_file(tfl)
                self.indexer.index_text(txt)
            # TODO: anything useful for other types?

            self.indexer.increase_termpos()

    def _qterm(self, mess):
        # generate a Q-term
        mid = mess.get("message-id")
        if mid==None:
            # generate our own message id
            local_part = random.randint(0,4*1024*1024*1024*1023)
            mid = "%i@woodpecker.%s" % (local_part, hostname)
        else:
            mid = mid.strip()
            mid = mid.strip("<>")

        qterm = "Q:%s" % mid
        MAX_URL_LENGTH = 240
        HASH_LEN = 32
        if len(qterm) > MAX_URL_LENGTH:
            hash = md5.new(qterm[MAX_URL_LENGTH - HASH_LEN:]).hexdigest()
            qterm = qterm[0:MAX_URL_LENGTH - HASH_LEN] + hash
        return qterm

    def index_message(self, mess, source):
        qterm = self._qterm(mess)
        doc = xapian.Document()
        self.indexer.set_document(doc)

        doc.add_term(qterm)
        source.add_terms(self.indexer)

        # index headers
        self.indexer.index_text_without_positions(mess.get("from", ""), 1, 'A')
        self.indexer.index_text_without_positions(mess.get("to", ""), 1, 'XT')
        self.indexer.index_text_without_positions(mess.get("cc", ""), 1, 'XT')
        self.indexer.index_text_without_positions(mess.get("subject", ""), 1, 'S')

        # G (newsgroup, mailing list or similar)
        # K (keyword?)
        # L (ISO language code)
        # T (mime type -- if we index parts separately, say attachments)

        # index text
        self.index_part(mess)
        self.indexer.increase_termpos()

        self.indexer.index_text(mess.get("from", ""))
        self.indexer.increase_termpos()
        self.indexer.index_text(mess.get("to", ""))
        self.indexer.increase_termpos()
        self.indexer.index_text(mess.get("cc", ""))
        self.indexer.increase_termpos()
        self.indexer.index_text(mess.get("subject", ""))
        self.indexer.increase_termpos()
        self.indexer.index_text(mess.get("date", ""))
        self.indexer.increase_termpos()

        try:
            date = mess["date"]
            pdate = email.Utils.parsedate_tz(date)
            utcdate = email.Utils.mktime_tz(pdate)
            utcdate_st = time.gmtime(utcdate)
            doc.add_term("D" + time.strftime("%Y%m%d", utcdate_st))
            doc.add_term("M" + time.strftime("%Y%m", utcdate_st))
            doc.add_term("Y" + time.strftime("%Y", utcdate_st))
            doc.add_value(self.VALUE_UTCDATETIME,
                          xapian.sortable_serialise(utcdate))
            doc.add_value(self.VALUE_UTCDATE,
                          time.strftime("%Y%m%d", utcdate_st))
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

        data = { 'From': mess.get("from", ""),
                 'To': mess.get("to", ""),
                 'Title': mess.get("subject", ""),
                 'Date': mess.get("date", ""),
                 'Sample': sample }
        if mess.get("cc")!=None:
            data['Cc'] = mess.get("cc")
                    
        data.update(source.get_data())
        doc.set_data(str(data)) # FIXME: JSON

        self.database.replace_document(qterm, doc)
        #self._log(".")

    def _get_last_index_point(self, mbox):
        return (None, None)

    def _is_incremental_indexable(self, mbox):
        return False

    def _update_last_index_point(self, mbox, nmessages):
        pass

    def index_mailbox(self, mbox):
        if type(mbox) is list:
            for one_mbox in mbox:
                self.index_mailbox(one_mbox)
            self._log('Done %i mailboxes.\n' % len(mbox))
            return

        self._log("%s: " % mbox)
        _fp = file(mbox)
        # get index point and num emails in mbox up to index point
        tpl = self._get_last_index_point(mbox)
        if tpl[0]==None:
            num = 0
            fp = _fp
        else:
            num = tpl[1]
            fp = woodpecker.Utils.Subfile(_fp, tpl[0])
        try:
            m = mailbox.PortableUnixMailbox(fp, woodpecker.Utils.msgfactory)
            num = 0
            while True:
                mess = m.next()
                if mess==None:
                    break
                if mess=="":
                    continue

                try:
                    self.index_message(mess, woodpecker.Utils.MBoxSource(mbox, num))
                except KeyboardInterrupt:
                    raise
                except:
                    import traceback
                    traceback.print_exc()
                num+=1
        except KeyboardInterrupt:
            raise
        except:
            import traceback
            traceback.print_exc()
            pass
        _fp.close()
        self._log("done [%i].\n" % num, False)
        self.flush()
        if self._is_incremental_indexable(mbox):
            self._update_last_index_point(mbox, num)

    def _log(self, message, include_timestamp=True):
        if include_timestamp:
            sys.stdout.write(time.strftime('%H:%m:%S '))
        sys.stdout.write(message)
        sys.stdout.flush()

def usage():
    print u"Usage: %s [options] mbox..." % sys.argv[0]
    print u"Options:"
    print u"\t--help\t\tThis message"
    print u"\t--confdir d\tUse ``d'' instead of ~/.woodpecker"

def main():
    """
    Actually run the indexer.
    """
    try:
        try:
            optlist, args = getopt.getopt(sys.argv[1:], 'hc:', ['help', 'confdir='])
        except getopt.GetoptError:
            usage()
            sys.exit(2)

        confdir = None

        for opt, arg in optlist:
            if opt in ('-h', '--help'):
                usage()
                sys.exit()
            if opt in ('-c', '--confdir'):
                confdir = arg

        conf = woodpecker.Config(confdir)
        pecker = Pecker(conf)

        try:
            pecker.index_mailbox(args)
        except:
            import traceback
            traceback.print_exc()
    except woodpecker.WoodpeckerError, e:
        sys.stdout.write(str(e))
        sys.stdout.write("\n")
        print e.aux
