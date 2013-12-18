#    Copyright (C) 2013 Jeremy S. Sanders
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
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
##############################################################################

from __future__ import division, print_function

from .. import qtall as qt4
from ..dialogs import importdialog
from ..compat import crange, cstr
from . import defn_hdf5

def _(text, disambiguation=None, context="Import_HDF5"):
    return qt4.QCoreApplication.translate(context, text, disambiguation)

# lazily imported
h5py = None

class Node(object):
    """Generic Node used by tree model."""
    def __init__(self, parent):
        self.parent = parent
        self.children = []

    def data(self, column, role):
        return None

    def flags(self, column, defflags):
        return defflags

    def setData(self, model, index, value, role):
        return False

class GenericTreeModel(qt4.QAbstractItemModel):
    """A generic tree model, operating on Node objects."""

    def __init__(self, parent, root, columnheads):
        qt4.QAbstractItemModel.__init__(self, parent)
        self.rootnode = root
        self.columnheads = columnheads

    def index(self, row, column, parent):
        if not parent.isValid():
            return self.createIndex(row, column, self.rootnode)
        parentnode = parent.internalPointer()
        return self.createIndex(row, column, parentnode.children[row])

    def parent(self, index):
        if not index.isValid():
            return qt4.QModelIndex()
        node = index.internalPointer()
        if node.parent is None:
            return qt4.QModelIndex()
        else:
            parent = node.parent
            if parent.parent is None:
                row = 0
            else:
                # find row of parent's parent for parent
                row = parent.parent.children.index(parent)
            return self.createIndex(row, 0, parent)

    def rowCount(self, parent):
        if not parent.isValid():
            return 1
        return len(parent.internalPointer().children)

    def data(self, index, role):
        if not index.isValid():
            return None
        node = index.internalPointer()
        return node.data(index.column(), role)

    def setData(self, index, value, role):
        if not index.isValid():
            return False
        node = index.internalPointer()
        return node.setData(self, index, value, role)

    def flags(self, index):
        defflags = qt4.QAbstractItemModel.flags(self, index)
        if not index.isValid():
            return defflags
        else:
            node = index.internalPointer()
            return node.flags(index.column(), defflags)

    def columnCount(self, parent):
        return len(self.columnheads)

    def headerData(self, section, orientation, role):
        if ( orientation == qt4.Qt.Horizontal and
             role == qt4.Qt.DisplayRole and
             section < len(self.columnheads) ):
            return self.columnheads[section]
        return None

class ErrorNode(Node):
    def __init__(self, parent, name):
        Node.__init__(self, parent)
        self.name = name

    def data(self, column, role):
        if column == 0 and role == qt4.Qt.DisplayRole:
            return self.name
        return None

# name for the columns
_ColName = 0
_ColDataType = 1
_ColShape = 2
_ColToImport = 3
_ColImportName = 4
_ColSlice = 5

class HDFNode(Node):
    def grpImport(self):
        """Is this disabled because of a group import?"""
        p = self.parent
        while p is not None:
            if p.grpimport:
                return True
            p = p.parent
        return False

    def _updateRow(self, model, index):
        """This is messy - inform view that this row has changed."""
        par = model.parent(index)
        row = index.row()
        idx1 = model.index(row, 0, par)
        idx2 = model.index(row, model.columnCount(index)-1, par)
        model.dataChanged.emit(idx1, idx2)

class HDFGroupNode(HDFNode):
    def __init__(self, parent, grp):
        Node.__init__(self, parent)
        self.name = grp.name.split("/")[-1]
        if self.name == '':
            self.name = '/'
        self.grpimport = False

    def data(self, column, role):
        if column == _ColName and role == qt4.Qt.DisplayRole:
            return self.name
        elif role == qt4.Qt.CheckStateRole and column == _ColToImport:
            return ( qt4.Qt.Checked
                     if self.grpimport or self.grpImport()
                     else qt4.Qt.Unchecked )

        elif role == qt4.Qt.ToolTipRole and column == _ColToImport:
            return _("Check to import all datasets under\n"
                     "this group under their original names")

        return None

    def setData(self, model, index, value, role):
        """Enable selection of group for importing. This prevents
        importing child items individually."""
        column = index.column()
        if column == _ColToImport and role == qt4.Qt.CheckStateRole:
            # import check has changed
            self.grpimport = value == qt4.Qt.Checked

            # disable importing of child nodes
            def recursivedisable(node):
                if isinstance(node, HDFDataNode):
                    node.toimport = False
                else:
                    if node is not self:
                        node.grpimport = False
                    for c in node.children:
                        recursivedisable(c)
            if self.grpimport:
                recursivedisable(self)

            self._updateRow(model, index)
            return True

        return False

    def flags(self, column, defflags):
        if self.grpImport():
            defflags &= ~qt4.Qt.ItemIsEnabled
            return defflags

        if column == _ColToImport:
            defflags |= qt4.Qt.ItemIsUserCheckable
        return defflags

class HDFDataNode(HDFNode):
    """Represent an HDF dataset."""

    def __init__(self, parent, dsname, dsattrs, dsdtype, dsshape):
        Node.__init__(self, parent)
        self.name = dsname.split("/")[-1]
        self.fullname = dsname
        self.rawdatatype = str(dsdtype)
        self.shape = tuple(list(dsshape) + list(dsdtype.shape))
        self.toimport = False
        self.importname = ""
        self.numeric = False
        self.slice = None

        # override import name
        self.defimportname = None
        if "vz_name" in dsattrs:
            self.defimportname = cstr(dsattrs["vz_name"])

        k = dsdtype.kind
        if k in ('b', 'i', 'u', 'f'):
            self.datatype = _('Numeric')
            self.datatypevalid = True
            self.numeric = True
        elif k in ('S', 'a'):
            self.datatype = _('Text')
            self.datatypevalid = True
        elif k == 'O' and h5py.check_dtype(vlen=dsdtype):
            self.datatype = _('Text')
            self.datatypevalid = True
        else:
            self.datatype = _('Unsupported')
            self.datatypevalid = False

    def dimsOkForImport(self):
        """Are dimensions ok to import?
        Need to count dimensions where slice is not fixed
        """
        shape = list(self.shape)
        if self.slice:
            shapei = 0
            for s in self.slice:
                if isinstance(s, int):
                    del shape[shapei]
                else:
                    shapei += 1
        return len(shape) in (1, 2)

    def data(self, column, role):
        """Return data for column"""
        if role in (qt4.Qt.DisplayRole, qt4.Qt.EditRole):
            if column == _ColName:
                return self.name
            elif column == _ColDataType:
                return self.datatype
            elif column == _ColShape:
                return u'\u00d7'.join([str(x) for x in self.shape])

            elif column == _ColImportName:
                if role == qt4.Qt.EditRole and not self.importname:
                    return self.name
                else:
                    if self.defimportname is not None:
                        return self.defimportname
                    return self.importname

            elif column == _ColSlice:
                return defn_hdf5.convertSliceToText(self.slice)

        elif role == qt4.Qt.ToolTipRole:
            if column == _ColName:
                return self.fullname
            elif column == _ColDataType:
                return self.rawdatatype
            elif column == _ColToImport and not self.grpImport():
                return _('Check to import this dataset')
            elif column == _ColImportName and not self.grpImport():
                return _('Name to assign after import.\nSpecial suffixes '
                         '(+), (-), (+-) and (1D) can be used.')
            elif column == _ColSlice:
                return _('Slice data to create a subset to import.\n'
                         'This should be ranges for each dimension\n'
                         'separated by commas.\n'
                         'Ranges can be empty (:), half (:10),\n'
                         ' full (4:10), with steps (1:10:2)\n'
                         ' or negative steps (::-1).\n'
                         'Example syntax: 2:20\n'
                         '   :10,:,2:20\n'
                         '   1:10:5,::5')

        elif role == qt4.Qt.CheckStateRole and column == _ColToImport:
            if ( (self.toimport or self.grpImport()) and
                 self.dimsOkForImport() ):
                return qt4.Qt.Checked
            return qt4.Qt.Unchecked
        return None

    def setData(self, model, index, value, role):
        # enable selection of dataset for importing
        column = index.column()
        if column == _ColToImport and role == qt4.Qt.CheckStateRole:
            # import check has changed
            self.toimport = value == qt4.Qt.Checked
            if not self.toimport:
                self.importname = ''

            self._updateRow(model, index)
            return True

        elif column == _ColImportName and (self.toimport or self.grpImport()):
            # update name if changed
            self.importname = value
            return True

        elif column == _ColSlice:
            slice = defn_hdf5.convertTextToSlice(value, len(self.shape))
            if slice != -1:
                self.slice = slice
                self._updateRow(model, index)
                return True

        return False

    def flags(self, column, defflags):

        if ( column == _ColToImport and self.datatypevalid and
             not self.grpImport() and self.dimsOkForImport() ):
            # allow import column to be clicked
            defflags |= qt4.Qt.ItemIsUserCheckable
        elif ( column == _ColImportName and (self.toimport or self.grpImport())
               and self.dimsOkForImport() ):
            defflags |= qt4.Qt.ItemIsEditable
        elif column == _ColSlice and self.datatypevalid:
            # allow name to be edited
            defflags |= qt4.Qt.ItemIsEditable

        return defflags

class HDFCompoundNode(HDFGroupNode):
    """Node representing a table (Compound data type)."""

    def __init__(self, parent, ds):
        HDFGroupNode.__init__(self, parent, ds)
        self.shape = ds.shape

    def data(self, column, role):
        """Return data for column"""
        if role == qt4.Qt.DisplayRole:
            if column == _ColDataType:
                return _("Table")
            elif column == _ColShape:
                return u'\u00d7'.join([str(x) for x in self.shape])
        return HDFGroupNode.data(self, column, role)

class HDFCompoundSubNode(HDFDataNode):
    """Sub-data of compound table."""

    def __init__(self, parent, ds, name):
        attrs = {}
        for a in ds.attrs:
            # attributes with _dsname suffixes are copied
            if a[:3] == "vz_" and a[-len(name)-1:] == "_"+name:
                attrs[a[:-len(name)-1]] = ds.attrs[a]

        HDFDataNode.__init__(self, parent, ds.name + '/' + name,
                             attrs, ds.dtype[name], ds.shape)

class ImportNameDeligate(qt4.QItemDelegate):
    """This class is for choosing the import name."""

    def __init__(self, parent, datanodes):
        qt4.QItemDelegate.__init__(self, parent)
        self.datanodes = datanodes

    def createEditor(self, parent, option, index):
        """Create combobox for editing type."""
        w = qt4.QComboBox(parent)
        w.setEditable(True)

        node = index.internalPointer()
        out = []
        tooltips = []
        for dn in (n for n in self.datanodes if n.toimport):
            name = dn.name
            out.append( (name, '') )
            if ( len(dn.shape) == 1 and node is not dn and
                 dn.shape == node.shape and
                 node.numeric and dn.numeric and
                 name[-4:] != ' (+)' and name[-4:] != ' (-)' and
                 name[-5:] != ' (+-)' ):
                # add error bars for other datasets
                out.append(
                    ('%s (+-)' % name,
                     _("Import as symmetric error bar for '%s'" % name)) )
                out.append(
                    ('%s (+)' % name,
                     _("Import as positive error bar for '%s'" % name)) )
                out.append(
                    ('%s (-)' % name,
                     _("Import as negative error bar for '%s'" % name)) )
            elif len(dn.shape) == 2 and dn.shape[1] in (2, 3):
                out.append(
                    ('%s (1D)' % name,
                     _("Import at 1D dataset with error bars")) )

        out.sort()

        # remove duplicates
        last = None
        i = 0
        while i < len(out):
            if out[i] == last:
                del out[i]
            else:
                last = out[i]
                i += 1

        w.addItems([i[0] for i in out])
        for i, item in enumerate(out):
            w.setItemData(i, item[1], qt4.Qt.ToolTipRole)
        return w

    def setEditorData(self, editor, index):
        """Update data in editor."""
        text = index.data(qt4.Qt.EditRole)

        i = editor.findText(text)
        if i != -1:
            editor.setCurrentIndex(i)
        else:
            editor.setEditText(text)

    def setModelData(self, editor, model, index):
        """Update data in model."""
        model.setData(index, editor.currentText(),
                      qt4.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        """Update editor geometry."""
        editor.setGeometry(option.rect)

def constructTree(hdf5file):
    """Turn hdf5 file into a tree of nodes.

    Returns root and list of nodes showing datasets
    """

    datanodes = []

    def addsub(parent, grp):
        """To recursively iterate over each parent."""
        for child in sorted(grp.keys()):
            try:
                hchild = grp[child]
            except KeyError:
                continue
            if isinstance(hchild, h5py.Group):
                childnode = HDFGroupNode(parent, hchild)
                addsub(childnode, hchild)
            elif isinstance(hchild, h5py.Dataset):
                if hchild.dtype.kind == 'V':
                    # compound data type - add a special group for
                    # the compound, then its children
                    childnode = HDFCompoundNode(parent, hchild)

                    for field in list(hchild.dtype.fields.keys()):
                        fnode = HDFCompoundSubNode(childnode, hchild, field)
                        childnode.children.append(fnode)
                        datanodes.append(fnode)

                else:
                    childnode = HDFDataNode(parent, hchild.name, hchild.attrs,
                                            hchild.dtype, hchild.shape)
                    datanodes.append(childnode)
            parent.children.append(childnode)

    root = HDFGroupNode(None, hdf5file)
    addsub(root, hdf5file)
    return root, datanodes

class ImportTabHDF5(importdialog.ImportTab):
    """Tab for importing HDF5 file."""

    resource = "import_hdf5.ui"

    def showError(self, err):
        node = ErrorNode(None, err)
        model = GenericTreeModel(self, node, [''])
        self.hdftreeview.setModel(model)

    def loadUi(self):
        importdialog.ImportTab.loadUi(self)
        self.datanodes = []

    def doPreview(self, filename, encoding):
        """Show file as tree."""

        global h5py
        if h5py is None:
            try:
                import h5py
            except ImportError:
                self.showError(_("Cannot load h5py module"))
                return False

        if not filename:
            self.showError(_("Cannot open file"))
            return False

        try:
            with h5py.File(filename, "r") as f:
                self.rootnode, self.datanodes = constructTree(f)
        except IOError as e:
            self.showError(_("Cannot open file"))
            return False

        self.importnamedeligate = ImportNameDeligate(self, self.datanodes)
        self.hdftreeview.setItemDelegateForColumn(
            _ColImportName, self.importnamedeligate)

        mod = GenericTreeModel(
            self, self.rootnode,
            [_('Name'), _('Type'), _('Size'), _('Import'),
             _('Import as'), _('Slice')])
        self.hdftreeview.setModel(mod)
        self.hdftreeview.expandAll()
        for c in _ColName, _ColDataType, _ColShape:
            self.hdftreeview.resizeColumnToContents(c)

        return True

    def doImport(self, doc, filename, linked, encoding, prefix, suffix, tags):
        """Import file."""

        namemap = {}
        slices = {}
        for node in self.datanodes:
            inname = node.importname.strip()
            if inname:
                namemap[node.fullname] = inname
            if node.slice:
                slices[node.fullname] = node.slice

        items = []
        def recursiveitems(node):
            if isinstance(node, HDFGroupNode):
                if node.grpimport:
                    items.append(node.name)
                else:
                    for c in node.children:
                        recursiveitems(c)
            else:
                if node.toimport:
                    items.append(node.fullname)

        recursiveitems(self.rootnode)

        prefix, suffix = self.dialog.getPrefixSuffix(filename)
        params = defn_hdf5.ImportParamsHDF5(
            filename=filename,
            items=items,
            namemap=namemap,
            slices=slices,
            tags=tags,
            prefix=prefix, suffix=suffix,
            linked=linked,
            )

        op = defn_hdf5.OperationDataImportHDF5(params)

        # inform user
        self.hdfimportstatus.setText(_("Import complete"))
        qt4.QTimer.singleShot(2000, self.hdfimportstatus.clear)

        # actually do the import
        doc.applyOperation(op)

importdialog.registerImportTab(_('HDF&5'), ImportTabHDF5)
