# document.py
# A module to handle documents

#    Copyright (C) 2004 Jeremy S. Sanders
#    Email: Jeremy Sanders <jeremy@jeremysanders.net>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
##############################################################################

# $Id$

"""A class to represent Veusz documents, with dataset classes."""

import os
import os.path
import time
import random
import string
import itertools
import re

import qt

import widgets
import utils
import simpleread
import setting
import datasets

class Document( qt.QObject ):
    """Document class for holding the graph data.

    Emits: sigModified when the document has been modified
           sigWiped when document is wiped
    """

    def __init__(self):
        """Initialise the document."""
        qt.QObject.__init__( self )

        self.changeset = 0
        self.historyundo = []
        self.historyredo = []
        self.wipe()

    def applyOperation(self, operation):
        """Apply operation to the document.
        
        Operations represent atomic actions which can be done to the document
        and undone.
        """
        
        retn = operation.do(self)
        self.historyundo.append(operation)
        self.historyredo = []
        self.setModified()
        return retn
        
    def undoOperation(self):
        """Undo the previous operation."""
        
        operation = self.historyundo.pop()
        operation.undo(self)
        self.historyredo.append(operation)
        self.setModified()
        
    def canUndo(self):
        """Returns True if previous operation can be removed."""
        return len(self.historyundo) != 0

    def redoOperation(self):
        """Redo undone operations."""
        
        operation = self.historyredo.pop()
        operation.do(self)
        self.historyundo.append(operation)
        self.setModified()

    def canRedo(self):
        """Returns True if previous operation can be redone."""
        return len(self.historyredo) != 0
        
    def resolveFullWidgetPath(self, path):
        """Translate the widget path given into the widget."""
        
        widget = self.basewidget
        for p in [i for i in path.split('/') if i != '']:
            for child in widget.children:
                if p == child.name:
                    widget = child
                    break
            else:
                # break wasn't called
                assert False
        return widget
        
    def resolveFullSettingPath(self, path):
        """Translate setting path into setting object."""
        
        # find appropriate widget
        widget = self.basewidget
        parts = [i for i in path.split('/') if i != '']
        while len(parts) > 0:
            for child in widget.children:
                if parts[0] == child.name:
                    widget = child
                    del parts[0]
                    break
            else:
                # no child with name
                break
            
        # get Setting object
        s = widget.settings
        while isinstance(s, setting.Settings) and parts[0] in s.setdict:
            s = s.get(parts[0])
            del parts[0]
            
        assert isinstance(s, setting.Setting)
        return s
            
    def wipe(self):
        """Wipe out any stored data."""
        # TODO: remove as this doesn't appear used anymore
        self.data = {}
        self.basewidget = widgets.Root(None, document=self)
        self.setModified(False)
        self.emit( qt.PYSIGNAL("sigWiped"), () )

    def isBlank(self):
        """Does the document contain widgets and no data"""
        return len(self.basewidget.children) == 0 and len(self.data) == 0

    def setData(self, name, dataset):
        """Set data to val, with symmetric or negative and positive errors."""
        self.data[name] = dataset
        dataset.document = self
        self.setModified()

    def reloadLinkedDatasets(self):
        """Reload linked datasets from their files.

        Returns a tuple of
        - List of datasets read
        - Dict of tuples containing dataset names and number of errors
        """

        # build up a list of linked files
        links = {}
        for ds in self.data.itervalues():
            if ds.linked:
                links[ ds.linked ] = True

        read = []
        errors = {}

        # load in the files, merging the vars read and errors
        if links:
            for l in links.iterkeys():
                nread, nerrors = l.reloadLinks(self)
                read += nread
                errors.update(nerrors)
            self.setModified()

        read.sort()
        return (read, errors)

    def deleteDataset(self, name):
        """Remove the selected dataset."""
        del self.data[name]
        self.setModified()

    def renameDataset(self, oldname, newname):
        """Rename the dataset."""
        d = self.data[oldname]
        del self.data[oldname]
        self.data[newname] = d

        self.setModified()

    def duplicateDataset(self, name, newname):
        """Duplicate the dataset to the newname."""

        if newname in self.data:
            raise ValueError, "Dataset %s already exists" % newname

        self.data[newname] = self.data[name].duplicate()
        self.setModified()

##    def unlinkDataset(self, name):
##        """Remove any links to file from the dataset."""
##        self.data[name].linked = None
##        self.setModified()

    def getData(self, name):
        """Get data with name"""
        return self.data[name]

    def hasData(self, name):
        """Whether dataset is defined."""
        return name in self.data

    def setModified(self, ismodified=True):
        """Set the modified flag on the data, and inform views."""

        # useful for tracking back modifications
        # import traceback
        # traceback.print_stack()

        self.modified = ismodified
        self.changeset += 1

        self.emit( qt.PYSIGNAL("sigModified"), ( ismodified, ) )

    def isModified(self):
        """Return whether modified flag set."""
        return self.modified
    
    def printTo(self, printer, pages, scaling = 1.):
        """Print onto printing device."""

        painter = widgets.Painter()
        painter.veusz_scaling = scaling
        painter.begin( printer )

        # work out how many pixels correspond to the given size
        width, height = self.basewidget.getSize(painter)
        children = self.basewidget.children

        # This all assumes that only pages can go into the root widget
        i = 0
        no = len(pages)

        for p in pages:
            c = children[p]
            c.draw( (0, 0, width, height), painter )

            # start new pages between each page
            if i < no-1:
                printer.newPage()
            i += 1

        painter.end()

    def paintTo(self, painter, page):
        """Paint page specified to the painter."""
        
        width, height = self.basewidget.getSize(painter)
        self.basewidget.children[page].draw( (0, 0, width, height), painter)

    def getNumberPages(self):
        """Return the number of pages in the document."""
        return len(self.basewidget.children)

    def saveToFile(self, file):
        """Save the text representing a document to a file."""

        file.write('# Veusz saved document (version %s)\n' % utils.version())
        try:
            file.write('# User: %s\n' % os.environ['LOGNAME'] )
        except KeyError:
            pass
        file.write('# Date: %s\n\n' % time.strftime(
            "%a, %d %b %Y %H:%M:%S +0000", time.gmtime()) )

        # save those datasets which are linked
        # we do this first in case the datasets are overridden below
        savedlinks = {}
        for name, dataset in self.data.items():
            dataset.saveLinksToSavedDoc(file, savedlinks)

        # save the remaining datasets
        for name, dataset in self.data.items():
            dataset.saveToFile(file, name)

        # save the actual tree structure
        file.write(self.basewidget.getSaveText())
        
        self.setModified(False)

    def export(self, filename, pagenumber, color=True):
        """Export the figure to the filename."""

        ext = os.path.splitext(filename)[1]

        if ext == '.eps':
            # write eps file
            p = qt.QPrinter(qt.QPrinter.HighResolution)
            p.setOutputToFile(True)
            p.setOutputFileName(filename)
            p.setColorMode( (qt.QPrinter.GrayScale, qt.QPrinter.Color)[color] )
            p.setCreator('Veusz %s' % utils.version())
            p.newPage()
            self.printTo( p, [pagenumber] )

        elif ext == '.png':
            # write png file
            # unfortunately we need to pass QPrinter the name of an eps
            # file: no secure way we can produce the file. FIXME INSECURE

            # FIXME: doesn't work in Windows

            fdir = os.path.dirname(os.path.abspath(filename))
            if not os.path.exists(fdir):
                raise RuntimeError, 'Directory "%s" does not exist' % fdir

            digits = string.digits + string.ascii_letters
            while True:
                rndstr = ''.join( [random.choice(digits) for i in xrange(20)] )
                tmpfilename = os.path.join(fdir, "tmp_%s.eps" % rndstr)
                try:
                    os.stat(tmpfilename)
                except OSError:
                    break
            
            # write eps file
            p = qt.QPrinter(qt.QPrinter.HighResolution)
            p.setOutputToFile(True)
            p.setOutputFileName(tmpfilename)
            p.setColorMode( (qt.QPrinter.GrayScale, qt.QPrinter.Color)[color] )
            p.newPage()
            self.printTo( p, [pagenumber] )

            # now use ghostscript to convert the file into the relevent type
            cmdline = ( 'gs -sDEVICE=pngalpha -dEPSCrop -dBATCH -dNOPAUSE'
                        ' -sOutputFile="%s" "%s"' % (filename, tmpfilename) )
            stdin, stdout, stderr = os.popen3(cmdline)
            stdin.close()

            # if anything goes to stderr, then report it
            text = stderr.read().strip()
            os.unlink(tmpfilename)
            if len(text) != 0:
                raise RuntimeError, text

        elif ext == '.svg':
            # Use qt's QPicture environment to export the drawing commands
            # as svg (scalable vector graphics)
            p = qt.QPicture()
            self.printTo( p, [pagenumber] )
            p.save(filename, 'svg')

        else:
            raise RuntimeError, "File type '%s' not supported" % ext


    def propagateSettings(self, setting, widgetname=None,
                          root=None, maxlevels=-1):

        """Take the setting given, and propagate it to other widgets,
        according to the parameters here.
        
        If widgetname is given then only propagate it to widgets with
        the name given.

        widgets are located from the widget given (root if not set)
        """

        # locate widget with the setting (building up path)
        path = []
        widget = setting
        while not isinstance(widget, widgets.Widget):
            path.insert(0, widget.name)
            widget = widget.parent

        # remove the name of the main settings of the widget
        path = path[1:]

        # default is root widget
        if root == None:
            root = self.basewidget

        # get a list of matching widgets
        widgetlist = []
        _recursiveGet(root, widgetname, widget.typename, widgetlist,
                      maxlevels)

        val = setting.val
        # set the settings for the widgets
        for w in widgetlist:
            # lookup the setting
            s = w.settings
            for i in path:
                s = s.get(i)

            # set the setting
            s.val = val
            
    def resolve(self, fromwidget, where):
        """Resolve graph relative to the widget fromwidget

        Allows unix-style specifiers, e.g. /graph1/x
        Returns widget
        """

        parts = where.split('/')

        if where[:1] == '/':
            # relative to base directory
            obj = self.basewidget
        else:
            # relative to here
            obj = fromwidget

        # iterate over parts in string
        for p in parts:
            if p == '..':
                # relative to parent object
                p = obj.parent
                if p == None:
                    raise ValueError, "Base graph has no parent"
                obj = p
            elif p == '.' or len(p) == 0:
                # relative to here
                pass
            else:
                # child specified
                obj = obj.getChild( p )
                if obj == None:
                    raise ValueError, "Child '%s' does not exist" % p

        # return widget
        return obj

    def import2D(self, filename, datasets, xrange=None, yrange=None,
                 invertrows=None, invertcols=None, transpose=None,
                 linked=False):
        """Import two-dimensional data from a file.
        filename is the name of the file to read
        datasets is a list of datasets to read from the file, or a single
        dataset name

        xrange is a tuple containing the range of data in x coordinates
        yrange is a tuple containing the range of data in y coordinates
        if invertrows=True, then rows are inverted when read
        if invertcols=True, then cols are inverted when read
        if transpose=True, then rows and columns are swapped

        if linked=True then the dataset is linked to the file
        """
        
        if linked:
            LF = datasets.Linked2DFile(filename, datasets)
            LF.xrange = xrange
            LF.yrange = yrange
            LF.invertrows = invertrows
            LF.invertcols = invertcols
            LF.transpose = transpose
        else:
            LF = None

        f = open(filename, 'r')
        stream = simpleread.FileStream(f)
        for name in datasets:
            sr = simpleread.SimpleRead2D(name)
            if xrange != None:
                sr.xrange = xrange
            if yrange != None:
                sr.yrange = yrange
            if invertrows != None:
                sr.invertrows = invertrows
            if invertcols != None:
                sr.invertcols = invertcols
            if transpose != None:
                sr.transpose = transpose

            sr.readData(stream)
            sr.setInDocument(self, linkedfile=LF)

    def importFITS(self, dsname, filename, hdu,
                   datacol = None, symerrcol = None,
                   poserrcol = None, negerrcol = None,
                   linked = False):
        """Import dataset from FITS file.

        dsname is the name of the dataset
        filename is name of the fits file to open
        hdu is the number/name of the hdu to access

        if the hdu is a table, datacol, symerrcol, poserrcol and negerrcol
        specify the columns containing the data, symmetric error,
        positive and negative errors.

        linked specfies that the dataset is linked to the file
        """

        try:
            import pyfits
        except ImportError:
            raise RuntimeError, ( 'PyFITS is required to import '
                                  'data from FITS files' )

        f = pyfits.open(filename, 'readonly')
        rhdu = f[hdu]
        data = rhdu.data

        try:
            # raise an exception if this isn't a table
            cols = rhdu.get_coldefs()

            datav = None
            symv = None
            posv = None
            negv = None

            # read the columns required
            if datacol != None:
                datav = data.field(datacol)
            if symerrcol != None:
                symv = data.field(symerrcol)
            if poserrcol != None:
                posv = data.field(poserrcol)
            if negerrcol != None:
                negv = data.field(negerrcol)

            # actually create the dataset
            ds = Dataset(data=datav, serr=symv, perr=posv, nerr=negv)

        except AttributeError:
            # Import a 2D image
            if ( datacol != None or symerrcol != None or poserrcol != None
                 or negerrcol != None ):
                print "Warning: ignoring columns as import 2D dataset"

            header = rhdu.header

            try:
                # try to read WCS for image, and work out x/yrange
                wcs = [header[i] for i in ('CRVAL1', 'CRPIX1', 'CDELT1',
                                           'CRVAL2', 'CRPIX2', 'CDELT2')]

                # ximage = (xpix-crpix)*cdelt + crval
                xrange = ( (data.shape[1]-wcs[1])*wcs[2] + wcs[0],
                           (0-wcs[1])*wcs[2] + wcs[0])
                yrange = ( (0-wcs[4])*wcs[5] + wcs[3],
                           (data.shape[0]-wcs[4])*wcs[5] + wcs[3] )

                print "xrange", xrange
                print "yrange", yrange
                xrange = (xrange[1], xrange[0])

            except KeyError:
                # no / broken wcs
                xrange = None
                yrange = None

            ds = Dataset2D(data, xrange=xrange, yrange=yrange)

        if linked:
            ds.linked = datasets.LinkedFITSFile(dsname, filename, hdu,
                                                [datacol, symerrcol,
                                                poserrcol, negerrcol])

        self.setData(dsname, ds)
        f.close()
