.. _mediaplayer:

Mediaplayer
===========

.. image:: ../../../../share/icons/multimedia/mplayer1.png
    :width: 64
    :height: 64

The mediaplayer can play multimedia files (audio or video) stored
in IPFS. The playlists are based on linked-data (:term:`RDF`).

Loading media files
-------------------

From the filemanager
^^^^^^^^^^^^^^^^^^^^

From the filemanager, right-click on an audio or video file, and
from the *Object* menu, select **Queue in mediaplayer**. You can
also do the same thing with a directory, and it will load all
the files inside the directory.

From the clipboard
^^^^^^^^^^^^^^^^^^

First copy the address of a multimedia file in the clipboard.
Then from the mediaplayer, click on the button
**Queue media from clipboard**.

Playlists
---------

The playlists are based on :term:`RDF`. New playlists are
stored in memory, and can be saved in the multimedia graph
using the **Save** button.

The **View all playlists** button shows all the playlists in the
multimedia graph. You can also search playlists by name (the
search field uses regular expressions).

Playlists loaded from the multimedia graph don't need to be
saved, this is done automatically (the save button won't appear).

Metadata
^^^^^^^^

Clicking on the **Scan metadata** button scans the metadata
for each item in the playlist.
