#!/usr/bin/env python
#
# Copyright 2008 James Aylett
#
# woodpecker's query interface
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

import sys, xapian, email.Utils, time, getopt
import curses, curses.wrapper, curses.textpad
import woodpecker

class QueryState:
    def __init__(self, conf, query_string):
        self.conf = conf
        self.offset = 0
        self.pagesize = 10
        self.my_addresses = []
        self.database = self.conf.get_index()
        self.enquire = xapian.Enquire(self.database)
        self.qp = xapian.QueryParser()
        self.qp.add_prefix('author', 'A')
        self.qp.add_prefix('from', 'A')
        self.qp.add_prefix('to', 'XT')
        self.qp.add_prefix('subject', 'S')
        self.qp.add_prefix('title', 'S')
        stemmer = xapian.Stem(self.conf.get_language())
        self.qp.set_stemmer(stemmer)
        self.qp.set_database(self.database)
        self.qp.set_stemming_strategy(xapian.QueryParser.STEM_SOME)
        self.query_string = None
        self.new_query(query_string)

    # States for our state (machine) gun
    INDEX = 0
    MESSAGE = 1

    def interface(self, scr):
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
        state = QueryState.INDEX
        while True:
            if state==QueryState.INDEX:
                self.draw_index_screen(scr)
            else:
                self.draw_message_screen(scr)
            state = self.process_input(scr, state)

    def process_input(self, scr, state):
        c = scr.getch()
        if state==QueryState.MESSAGE:
            if c == ord('i') or c == ord('q'):
                return QueryState.INDEX

        if c == curses.KEY_DOWN or c == ord('j'):
            self.increment_cursor()
        elif c == curses.KEY_UP or c == ord('k'):
            self.decrement_cursor()
        elif c == curses.KEY_NPAGE:
            self.next_page_cursor()
        elif c == curses.KEY_PPAGE:
            self.previous_page_cursor()
        elif c == ord('q') or c == ord('x'):
            sys.exit(0)
        elif c == ord('s') or c == ord('/'):
            (height, width) = scr.getmaxyx()
            scr.addstr(height-1, 0, "/ ")
            scr.refresh()
            win = scr.subwin(1, width-2, height-1, 2)
            textbox = curses.textpad.Textbox(win)
            textbox.edit()
            self.new_query(textbox.gather())
            del textbox
            return QueryState.INDEX
        elif c == 10:
            return QueryState.MESSAGE
        return state

    def fill_string(self, scr, y, x, st, attr):
        (height, width) = scr.getmaxyx()
        scr.addstr(y, x, st + " "*(width-len(st)), attr)

    def draw_message_screen(self, scr):
        scr.clear()
        (height, width) = scr.getmaxyx()
        self._header(scr)
        for m in self.get_matches():
            if m.rank==self.cursor:
                break
        if m.rank==self.cursor:
            doc = m.get_document()
            d = eval(doc.get_data())
            scr.addstr("From: %s\nTo: %s\nDate: %s\nSubject: %s\n\n%s" % (d['From'], d['To'], d['Date'], d['Title'], d['Sample']))
            self.fill_string(scr, height-2, 0, d['Title'], curses.color_pair(1) | curses.A_BOLD)
        else:
            self.fill_string(scr, height-2, 0, "Huh? Not there.", curses.color_pair(1) | curses.A_BOLD)

    def _header(self, scr):
        self.fill_string(scr, 0, 0, "Woodpecker email browser v0.1", curses.color_pair(1) | curses.A_BOLD)

    def draw_index_screen(self, scr):
        scr.clear()
        self._header(scr)
        (height, width) = scr.getmaxyx()
        self.set_pagesize(height-3) # header, footer, control
        matches = self.get_matches()

        for m in matches:
            data = eval(m.document.get_data())
            from_bits = email.Utils.parseaddr(data['From'])
            if from_bits[1] in self.my_addresses:
                to_bits = email.Utils.parseaddr(data['To'])
                if to_bits[0]!='':
                    address = 'To ' + to_bits[0]
                else:
                    address = 'To ' + to_bits[1]
            else:
                if from_bits[0]!='':
                    address = from_bits[0]
                else:
                    address = from_bits[1]
            pdate = email.Utils.parsedate_tz(data['Date'])
            utcdate = email.Utils.mktime_tz(pdate)
            utcdate_st = time.gmtime(utcdate)
            if utcdate < time.time() - 86400 or utcdate > time.time():
                date_str = time.strftime("%d %b %y", utcdate_st)
            else:
                date_str = time.strftime("%a %H:%m", utcdate_st)
            subject = data['Title'] or '(No subject)'
            if self.cursor!=m.rank:
                cp = 0
            else:
                cp = 2
            scr.addstr("%4.4s   %-20.20s (%9.9s) %-40.40s" % (str(m.rank+1), address, date_str, subject), curses.color_pair(cp))

        if matches.size()==0:
            if self.query_string=='':
                text = "Press '/' and type a query to start"
            else:
                text = "Your search '%s' returned nothing" % self.query_string
            mid = height/2 - 1
            left = (width - len(text)) / 2
            scr.addstr(mid, left, text, curses.A_BOLD)
            self.fill_string(scr, height-2, 0, "No matches", curses.color_pair(1) | curses.A_BOLD)
        else:
            self.fill_string(scr, height-2, 0, "Showing %i-%i of about %i matching emails." % (self.offset+1, self.offset+matches.size(), matches.get_matches_estimated()), curses.color_pair(1) | curses.A_BOLD)
        # and the bottom line, the command line is blank unless needed
        scr.refresh()

    def set_pagesize(self, size):
        if size!=self.pagesize:
            self.pagesize = size

    def increment_cursor(self):
        self.cursor += 1
        self.constrain_cursor()
        while self.cursor >= self.offset + self.pagesize:
            self.offset += self.pagesize
            self.clear_matches()
        
    def decrement_cursor(self):
        self.cursor -= 1
        self.constrain_cursor()
        while self.cursor < self.offset:
            self.offset -= self.pagesize
            self.clear_matches()

    def previous_page_cursor(self):
        self.cursor = self.pagesize * (self.cursor / self.pagesize)
        self.decrement_cursor()

    def next_page_cursor(self):
        self.cursor = self.pagesize * (self.cursor / self.pagesize) + self.pagesize - 1
        self.increment_cursor()

    def constrain_cursor(self):
        if self.cursor < 0:
            self.cursor = 0
        # FIXME: overflow
        #if self.cursor >= self.matches.get_matches_upper_bound():
        #    self.cursor = self.matches.get_matches_upper_bound() - 1

    def new_query(self, query_string):
        if self.query_string==query_string:
            return
        self.offset = 0
        self.cursor = 0
        self.query_string = query_string
        query = self.qp.parse_query(self.query_string)
        self.enquire.set_query(query)
        self.matches = None

    def clear_matches(self):
        self.matches = None

    def get_matches(self, offset=None):
        if offset!=None:
            self.offset=offset
        elif self.matches is not None:
            return self.matches
        self.matches = self.enquire.get_mset(self.offset, self.pagesize)
        return self.matches

    def set_my_addresses(self, adrs):
        self.my_addresses = adrs

def usage():
    print u"Usage: %s [options] query" % sys.argv[0]
    print u"Options:"
    print u"\t--help\t\tThis message"
    print u"\t--confdir d\tUse ``d'' instead of ~/.woodpecker"

def main():
    """
    Actually run the search interface.
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
        query_string = ' '.join(args)
        qs = QueryState(conf, query_string)
        qs.set_my_addresses(['james@tartarus.org'])

        curses.wrapper(lambda x: qs.interface(x))
    except woodpecker.WoodpeckerError, e:
        sys.stdout.write(str(e))
        sys.stdout.write("\n")
        print e.aux

if __name__ == '__main__':
    main()
