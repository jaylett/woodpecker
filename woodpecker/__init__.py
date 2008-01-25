# Woodpecker library
#
# (c) Copyright James Aylett 2008
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

"""
Woodpecker is a reasonably lightweight personal email search system.
Throw it at all your mboxes, and you end up with a Xapian database
that you can search quickly. Re-run over mboxes and everything works,
providing you don't delete emails (so it'll cope with emails being
moved from mbox to mbox at low cost).

The search interface is pretty limited. Indexing currently copes with
text/plain and text/html (needs elinks); message processing copes with
multipart.
"""

__all__ = ['Indexer', 'Utils']

VERSION = '0.1'

import os, os.path, pwd, xapian

class WoodpeckerError(RuntimeError):
    def __init__(self, message, aux=None):
        RuntimeError.__init__(self, message)
        self.aux = aux

class Config:
    """Holds Woodpecker configuration at runtime."""
    def __init__(self, configpath):
        if configpath==None:
            try:
                userdir = os.environ['HOME']
            except KeyError:
                pwent = pwd.getpwuid(os.getuid())
                userdir = pwent[5]
            except:
                raise WoodpeckerError("Cannot determine home directory.")
            configpath = os.path.join(userdir, '.woodpecker')
            if not os.path.exists(configpath):
                os.mkdir(configpath)
            if not os.path.isdir(configpath):
                raise WoodpeckerError('~/.woodpecker exists and is not a directory')
        elif not os.path.isdir(configpath):
            raise WoodpeckerError("%s is not a directory" % configpath)

        self.configpath = configpath
        self.dbpath = os.path.join(self.configpath, 'index')
        self.language = 'english' # FIXME: noooo! :-)

    def get_writeable_index(self):
        """Get a xapian.Database that is writable for the email index."""
        return xapian.WritableDatabase(self.dbpath, xapian.DB_CREATE_OR_OPEN)
    get_writable_index = get_writeable_index

    def get_index(self):
        """Get a xapian.Database for the email index."""
        return xapian.Database(self.dbpath)

    def get_language(self):
        """Get the language we're running in (default: English)."""
        return self.language
