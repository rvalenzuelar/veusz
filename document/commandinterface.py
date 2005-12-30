# commandinterface.py
# this module supplies the command line interface for plotting
 
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

"""
Module supplies the command interface used in the program, and for
external programs.
"""

import qt

import widgets
import datasets
import simpleread

class CommandInterface(qt.QObject):
    """Class provides command interface."""

    def __init__(self, document):
        """Initialise the interface."""
        qt.QObject.__init__(self)

        self.document = document
        self.currentwidget = self.document.basewidget
        self.verbose = False

        self.connect( self.document, qt.PYSIGNAL("sigWiped"),
                      self.slotWipedDoc )

    def slotWipedDoc(self):
        """When the document is wiped, we change to the root widget."""
        self.To('/')

    def SetVerbose(self, v=True):
        """Specify whether we want verbose output after operations."""
        self.verbose = v

    def Add(self, type, *args, **args_opt):
        """Add a graph to the plotset."""
        w = widgets.thefactory.makeWidget(type, self.currentwidget,
                                          *args, **args_opt)

        if self.verbose:
            print "Added a graph of type '%s' (%s)" % (type, w.userdescription)

        self.document.setModified()
        return w.name

    def Remove(self, name):
        """Remove a graph from the dataset."""
        w = self.document.resolve(self.currentwidget, name)
        w.parent.removeChild( w.name )
        self.document.setModified()

    def To(self, where):
        """Change to a graph within the current graph."""

        self.currentwidget = self.document.resolve(self.currentwidget,
                                                   where)

        if self.verbose:
            print "Changed to graph '%s'" % self.currentwidget.path

    def List(self, where='.'):
        """List the contents of a graph."""

        widget = self.document.resolve(self.currentwidget, where)
        children = widget.childnames

        if len(children) == 0:
            print '%30s' % 'No children found'
        else:
            # output format name, type
            for name in children:
                w = widget.getChild(name)
                print '%10s %10s %30s' % (name, w.typename, w.userdescription)

    def Get(self, var):
        """Get the value of a setting."""
        return self.currentwidget.prefLookup(var).val

    def GetChildren(self, where='.'):
        """Return a list of widgets which are children of the widget of the
        path given."""
        return list( self.document.resolve(self.currentwidget,
                                           where).childnames )

    def GetDatasets(self):
        """Return a list of names of datasets."""
        ds = self.document.data.keys()
        ds.sort()
        return ds

    def Save(self, filename):
        """Save the state to a file."""
        f = open(filename, 'w')
        self.document.saveToFile(f)

    def Set(self, var, val):
        """Set the value of a setting."""
        pref = self.currentwidget.prefLookup(var)
        pref.val = val

        if self.verbose:
            print ( "Set setting '%s' to %s" %
                    (var, repr(val)) )

    def SetData(self, name, val, symerr=None, negerr=None, poserr=None):
        """Set dataset with name with values (and optionally errors)."""

        data = datasets.Dataset(val, symerr, negerr, poserr)
        self.document.setData(name, data)
 
        if self.verbose:
            print "Set variable '%s':" % name
            print " Values = %s" % str( data.data )
            print " Symmetric errors = %s" % str( data.serr )
            print " Negative errors = %s" % str( data.nerr )
            print " Positive errors = %s" % str( data.perr )

    def SetDataExpression(self, name, val, symerr=None, negerr=None, poserr=None,
                          linked=False):
        """Create a dataset based on text expressions.

        Expressions are functions of existing datasets.
        If evaluating the expression 'y*10' in negerr, then the negerrs of dataset y
        are used, and so on.
        To access a specific part of the dataset y, the suffixes _data, _serr, _perr,
        and _nerr can be appended.
        
        If linked is True then the expressions are reevaluated if the document
        is modified
        """

        data = datasets.DatasetExpression(data=val, serr=symerr, nerr=negerr,
                                          perr=poserr)

        # if not linked, create a dataset based on the linked one
        if not linked:
            data.document = self.document
            data = datasets.Dataset(data=data.data, serr=data.serr,
                                    nerr=data.nerr, perr=data.perr)

        # actually set the dataset
        self.document.setData(name, data)

        if self.verbose:
            print "Set variable '%s' based on expression:" % name
            print " Values = %s" % str( data.data )
            print " Symmetric errors = %s" % str( data.serr )
            print " Negative errors = %s" % str( data.nerr )
            print " Positive errors = %s" % str( data.perr )

    def SetData2D(self, name, data, xrange=None, yrange=None):
        """Create a 2D dataset."""

        data = datasets.Dataset2D(data, xrange=xrange, yrange=yrange)
        self.document.setData(name, data)

        if self.verbose:
            print "Set 2d dataset '%s'" % name

    def GetData(self, name):
        """Return the data with the name.

        Returns a tuple containing:

        (data, serr, nerr, perr)
        Values not defined are set to None

        Return copies, so that the original data can't be indirectly modified
        """

        d = self.document.getData(name)
        data = serr = nerr = perr = None
        if d.data != None:
            data = d.data.copy()
        if d.serr != None:
            serr = d.serr.copy()
        if d.nerr != None:
            nerr = d.nerr.copy()
        if d.perr != None:
            perr = d.perr.copy()

        return (data, serr, nerr, perr)

    def ImportString(self, descriptor, string, useblocks=False):
        """Read data from the string using a descriptor.

        If useblocks is set, then blank lines or the word 'no' are used
        to split the data into blocks. Dataset names are appended with an
        underscore and the block number (starting from 1).

        Returned is a tuple (datasets, errors)
         where datasets is a list of datasets read
         errors is a dict of the datasets with the number of errors while
         converting the data
        """

        stream = simpleread.StringStream(string)
        sr = simpleread.SimpleRead(descriptor)
        sr.readData(stream, useblocks=useblocks)
        datasets = sr.setInDocument(self.document)
        errors = sr.getInvalidConversions()

        if self.verbose:
            print "Imported datasets %s" % (' '.join(datasets),)
            for name, num in errors.iteritems():
                print "%i errors encountered reading dataset %s" % (num, name)

        return (datasets, errors)

    def ImportString2D(self, datasets, string):
        """Read two dimensional data from the string specified.
        datasets is a list of datasets to read from the string or a single
        dataset name
        """

        if type(datasets) in (str, unicode):
            datasets = [datasets]

        stream = simpleread.StringStream(string)
        for name in datasets:
            sr = simpleread.SimpleRead2D(name)
            sr.readData(stream)
            sr.setInDocument(self.document)
            if self.verbose:
                print "Imported dataset %s" % name

    def ImportFile2D(self, filename, datasets, xrange=None, yrange=None,
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

        if type(datasets) in (str, unicode):
            datasets = [datasets]

        self.document.import2D(filename, datasets, xrange=xrange,
                               yrange=yrange, invertrows=invertrows,
                               invertcols=invertcols, transpose=transpose,
                               linked=linked)
        if self.verbose:
            print "Imported datasets %s" % (', '.join(datasets))

    def ImportFile(self, filename, descriptor, useblocks=False, linked=False):
        """Read data from file with filename using descriptor.
        If linked is True, the data won't be saved in a saved document,
        the data will be reread from the file.

        If useblocks is set, then blank lines or the word 'no' are used
        to split the data into blocks. Dataset names are appended with an
        underscore and the block number (starting from 1).

        Returned is a tuple (datasets, errors)
         where datasets is a list of datasets read
         errors is a dict of the datasets with the number of errors while
         converting the data
        """

        # if there's a link, set it up
        if linked:
            LF = datasets.LinkedFile(filename, descriptor, useblocks=useblocks)
        else:
            LF = None

        f = open(filename, 'r')
        stream = simpleread.FileStream(f)
        sr = simpleread.SimpleRead(descriptor)
        sr.readData(stream, useblocks=useblocks)
        datasets = sr.setInDocument(self.document,
                                    linkedfile=LF)
        errors = sr.getInvalidConversions()

        if self.verbose:
            print "Imported datasets %s" % (' '.join(datasets),)
            for name, num in errors.iteritems():
                print "%i errors encountered reading dataset %s" % (num, name)

        return (datasets, errors)

    def ImportFITSFile(self, dsname, filename, hdu,
                       datacol = None, symerrcol = None,
                       poserrcol = None, negerrcol = None,
                       linked = False):
        """Import data from a FITS file

        dsname is the name of the dataset
        filename is name of the fits file to open
        hdu is the number/name of the hdu to access

        if the hdu is a table, datacol, symerrcol, poserrcol and negerrcol
        specify the columns containing the data, symmetric error,
        positive and negative errors.

        linked specfies that the dataset is linked to the file
        """

        self.document.importFITS(dsname, filename, hdu,
                                 datacol=datacol, symerrcol=symerrcol,
                                 poserrcol=poserrcol, negerrcol=negerrcol,
                                 linked=linked)

    def ReloadData(self):
        """Reload any linked datasets.

        Returned is a tuple (datasets, errors)
         where datasets is a list of datasets read
         errors is a dict of the datasets with the number of errors while
         converting the data
        """

        return self.document.reloadLinkedDatasets()

    def Action(self, action, widget='.'):
        """Performs action on current widget."""

        w = self.document.resolve(self.currentwidget, widget)

        # run action
        w.actionfuncs[action]()

    def Print(self):
        """Print document."""
        p = qt.QPrinter()

        if p.setup():
            p.newPage()
            self.document.printTo( p,
                                   range(self.document.getNumberPages()) )
            
    def Export(self, filename, color=True, page=0):
        """Export plot to filename."""
        
        self.document.export(filename, page, color=color)
            
    def Rename(self, widget, newname):
        """Rename the widget with the path given to the new name.

        eg Rename('graph1/xy1', 'scatter')
        This function does not move widgets."""

        w = self.document.resolve(self.currentwidget, widget)
        w.rename(newname)
        
