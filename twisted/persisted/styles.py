# -*- test-case-name: twisted.test.test_persisted -*-
# Twisted, the Framework of Your Internet
# Copyright (C) 2001 Matthew W. Lefkowitz
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of version 2.1 of the GNU Lesser General Public
# License as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


"""
Different styles of peristed objects.
"""
# System Imports
import types
import cStringIO
import copy_reg
import copy

# Twisted Imports
from twisted.python import log

try:
    from new import instancemethod
except:
    from org.python.core import PyMethod
    instancemethod = PyMethod

# when do these go away? I suggest at 1.0 we reset to empty
oldModules = {"twisted.python.explorer": "twisted.manhole.explorer"}

# deal with classes that were moved, so old TAPs will work
# this is REALLY ICKY, but can't be helped because of circular imports
from twisted.manhole.telnet import ShellFactory
from twisted.protocols import telnet
telnet.ShellFactory = ShellFactory

## First, let's register support for some stuff that really ought to
## be registerable...

def pickleMethod(method):
    'support function for copy_reg to pickle method refs'
    return unpickleMethod, (method.im_func.__name__,
                             method.im_self,
                             method.im_class)

def unpickleMethod(im_name,
                    im_self,
                    im_class):
    'support function for copy_reg to unpickle method refs'
    try:
        unbound = getattr(im_class,im_name)
        if im_self is None:
            return unbound
        bound=instancemethod(unbound.im_func,
                                 im_self,
                                 im_class)
        return bound
    except AttributeError:
        log.msg("Method",im_name,"not on class",im_class)
        assert im_self is not None,"No recourse: no instance to guess from."
        # Attempt a common fix before bailing -- if classes have
        # changed around since we pickled this method, we may still be
        # able to get it by looking on the instance's current class.
        unbound = getattr(im_self.__class__,im_name)
        log.msg("Attempting fixup with",unbound)
        if im_self is None:
            return unbound
        bound=instancemethod(unbound.im_func,
                                 im_self,
                                 im_self.__class__)
        return bound

copy_reg.pickle(types.MethodType,
                pickleMethod,
                unpickleMethod)

def pickleModule(module):
    'support function for copy_reg to pickle module refs'
    return unpickleModule, (module.__name__,)

def unpickleModule(name):
    'support function for copy_reg to unpickle module refs'
    if oldModules.has_key(name):
        print "Module has moved:",name,
        name = oldModules[name]
        print name
    return __import__(name,{},{},'x')


copy_reg.pickle(types.ModuleType,
                pickleModule,
                unpickleModule)

def pickleStringO(stringo):
    'support function for copy_reg to pickle cStringIO.OutputTypes'
    return unpickleStringO, (stringo.getvalue(), stringo.tell())

def unpickleStringO(val, sek):
    x = cStringIO.StringIO()
    x.write(val)
    x.seek(sek)
    return x

if hasattr(cStringIO, 'OutputType'):
    copy_reg.pickle(cStringIO.OutputType,
                pickleStringO,
                unpickleStringO)

def pickleStringI(stringi):
    return unpickleStringI, (stringi.getvalue(), stringi.tell())

def unpickleStringI(val, sek):
    x = cStringIO.StringIO(val)
    x.seek(sek)
    return x


if hasattr(cStringIO, 'InputType'):
    copy_reg.pickle(cStringIO.InputType,
                pickleStringI,
                unpickleStringI)

class Ephemeral:
    """
    This type of object is never persisted; if possible, even references to it
    are eliminated.
    """

    def __getstate__(self):
        log.msg( "WARNING: serializing ephemeral %s" % self )
        return None

    def __setstate__(self, state):
        log.msg( "WARNING: unserializing ephemeral %s" % self.__class__ )
        self.__class__ = Ephemeral


versionedsToUpgrade = {}
upgraded = {}

def doUpgrade():
    global versionedsToUpgrade, upgraded
    for versioned in versionedsToUpgrade.keys():
        requireUpgrade(versioned)
    versionedsToUpgrade = {}
    upgraded = {}

def requireUpgrade(obj):
    """Require that a Versioned instance be upgraded completely first.
    """
    if versionedsToUpgrade.has_key(obj) and not upgraded.has_key(obj):
        upgraded[obj] = 1
        obj.versionUpgrade()
        return obj

from twisted.python import reflect

def _aybabtu(c):
    l = []
    for b in reflect.allYourBase(c, Versioned):
        if b not in l and b is not Versioned:
            l.append(b)
    return l

class Versioned:
    """
    This type of object is persisted with versioning information.

    I have a single class attribute, the int persistenceVersion.  After I am
    unserialized (and styles.doUpgrade() is called), self.upgradeToVersionX()
    will be called for each version upgrade I must undergo.

    For example, if I serialize an instance of a Foo(Versioned) at version 4
    and then unserialize it when the code is at version 9, the calls::

      self.upgradeToVersion5()
      self.upgradeToVersion6()
      self.upgradeToVersion7()
      self.upgradeToVersion8()
      self.upgradeToVersion9()

    will be made.  If any of these methods are undefined, a warning message
    will be printed.
    """
    persistenceVersion = 1

    def __setstate__(self, state):
        versionedsToUpgrade[self] = 1
        self.__dict__ = state

    def __getstate__(self, dict=None):
        """Get state, adding a version number to it on its way out.
        """
        dct = copy.copy(dict or self.__dict__)
        bases = _aybabtu(self.__class__)
        bases.reverse()
        bases.append(self.__class__) # don't forget me!!
        for base in bases:
            if base.__dict__.has_key('persistenceVersion'):
                dct['%s.persistenceVersion' % str(base)] = base.persistenceVersion
        return dct

    def versionUpgrade(self):
        """(internal) Do a version upgrade.
        """
        bases = _aybabtu(self.__class__)
        # put the bases in order so superclasses' persistenceVersion methods
        # will be called first.
        bases.reverse()
        bases.append(self.__class__) # don't forget me!!
        # first let's look for old-skool versioned's
        if self.__dict__.has_key("persistenceVersion"):
            
            # Hacky heuristic: if more than one class subclasses Versioned,
            # we'll assume that the higher version number wins for the older
            # class, so we'll consider the attribute the version of the older
            # class.  There are obviously possibly times when this will
            # eventually be an incorrect assumption, but hopefully old-school
            # persistenceVersion stuff won't make it that far into multiple
            # classes inheriting from Versioned.
            
            pver = self.__dict__['persistenceVersion']
            del self.__dict__['persistenceVersion']
            highestVersion = 0
            highestBase = None
            for base in bases:
                if not base.__dict__.has_key('persistenceVersion'):
                    continue
                if base.persistenceVersion > highestVersion:
                    highestBase = base
                    highestVersion = base.persistenceVersion
            if highestBase:
                self.__dict__['%s.persistenceVersion' % str(highestBase)] = pver
        for base in bases:
            # ugly hack, but it's what the user expects, really
            if (Versioned not in base.__bases__ and
                not base.__dict__.has_key('persistenceVersion')):
                continue
            currentVers = base.persistenceVersion
            pverName = '%s.persistenceVersion' % str(base)
            persistVers = (self.__dict__.get(pverName) or 0)
            if persistVers:
                del self.__dict__[pverName]
            assert persistVers <=  currentVers, "Sorry, can't go backwards in time."
            while persistVers < currentVers:
                persistVers = persistVers + 1
                method = base.__dict__.get('upgradeToVersion%s' % persistVers, None)
                if method:
                    log.msg( "Upgrading %s to version %s" % (base, persistVers) )
                    method(self)
                else:
                    log.msg( 'Warning: cannot upgrade %s to version %s' % (base, persistVers) )
