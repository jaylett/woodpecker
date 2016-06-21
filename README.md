# Woodpecker -- search for email

Woodpecker is a search system for email, using
[Xapian](https://xapian.org/) to index and search/display emails from
Unix mbox files.

## Background

A long, long, long time ago (1984) there was a search system called
Muscat, built out of work by [Dr Martin
Porter](https://tartarus.org/martin/). My understanding was that he
used that to build an email search system he called 'woodpecker'.

Merely a long, long time ago (late 1990s), the successor to Muscat was
a system called OpenMuscat, and later Omsee; if I remember correctly
someone, possibly Martin, wrote a script called 'woodpecker2' using
Omsee.

Omsee was released under GPL, and forked to become
[Xapian](https://xapian.org/), and was separately developed under a
commercial license through a variety of companies and is now possibly
owned by [Smartlogic](http://www.smartlogic.com/) where it may form
the basis for some of their current products.

A bit before the fork (which was only a long time ago, in 2001) I
started work on something called Woodpecker 3, intended to be an email
search system built on the GPL codebase. Laziness resulted in this
ending up being called 'woodpecker' again once I actually got it
vaguely working.

## Notes and warnings

 * written for python2 and, despite the commits being from 2008 is not
   idiomatic python2 (IIRC much of the original code dates from before
   2000, so it's really python1 era)

 * will probably dislike UTF-8 in some cases

 * contains some hardcoded things: my email address, layout of some of
   my files from whatever machine I was using in 2008

That said, it probably wouldn't be much work to update it to py3,
probably rebuild the mail parsing code, and package up for us. Having
said that, many people may find [Recoll](http://www.recoll.org/) more
useful.

James Aylett
