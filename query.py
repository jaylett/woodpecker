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
import curses, curses.wrapper
import woodpecker

def process_input(scr, qs):
    c = scr.getch()
    if c == curses.KEY_DOWN or c == ord('j'):
        qs.increment_cursor()
    elif c == curses.KEY_UP or c == ord('k'):
        qs.decrement_cursor()
    elif c == curses.KEY_NPAGE:
        qs.next_page_cursor()
    elif c == curses.KEY_PPAGE:
        qs.previous_page_cursor()

def fill_string(scr, y, x, st, attr):
    (height, width) = scr.getmaxyx()
    scr.addstr(y, x, st + " "*(width-len(st)), attr)

def draw_screen(scr, qs):
    scr.clear()
    (height, width) = scr.getmaxyx()
    qs.set_pagesize(height-3) # header, footer, control
    matches = qs.get_matches()

    fill_string(scr, 0, 0, "Woodpecker email browser v0.1", curses.color_pair(1) | curses.A_BOLD)

    for m in matches:
        data = eval(m.document.get_data())
        from_bits = email.Utils.parseaddr(data['From'])
        if from_bits[1] in qs.my_addresses:
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
        if qs.cursor!=m.rank:
            cp = 0
        else:
            cp = 2
        scr.addstr("%4.4s   %-20.20s (%9.9s) %-40.40s" % (str(m.rank+1), address, date_str, subject), curses.color_pair(cp))

    if matches.size()==0:
        fill_string(scr, height-2, 0, "No matches", curses.color_pair(1) | curses.A_BOLD)
    else:
        fill_string(scr, height-2, 0, "Showing %i-%i of about %i matching emails." % (qs.offset+1, qs.offset+matches.size(), matches.get_matches_estimated()), curses.color_pair(1) | curses.A_BOLD)
    # and the bottom line, the command line...
    scr.refresh()

def interface(scr, qs):
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLUE)
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
    while True:
        draw_screen(scr, qs)
        process_input(scr, qs)

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

        curses.wrapper(lambda x: interface(x, qs))
    except woodpecker.WoodpeckerError, e:
        sys.stdout.write(str(e))
        sys.stdout.write("\n")
        print e.aux

if __name__ == '__main__':
    main()
