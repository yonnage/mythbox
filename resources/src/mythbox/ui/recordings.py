#
#  MythBox for XBMC - http://mythbox.googlecode.com
#  Copyright (C) 2010 analogue@yahoo.com
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
import logging
import odict
import os
import xbmcgui

from mythbox.mythtv.conn import inject_conn
from mythbox.ui.recordingdetails import RecordingDetailsWindow
from mythbox.ui.toolkit import window_busy, BaseWindow, Action
from mythbox.util import catchall_ui, run_async, lirc_hack, timed, catchall, ui_locked, ui_locked2, coalesce
from mythbox.util import CyclingBidiIterator

log = logging.getLogger('mythtv.ui')

ID_PROGRAMS_LISTBOX = 600
ID_REFRESH_BUTTON = 250
ID_SORT_BY_BUTTON = 251
ID_SORT_ASCENDING_TOGGLE = 252
ID_RECORDING_GROUP_BUTTON = 253

SORT_BY = odict.odict([
    ('Date', lambda x: x.starttimeAsTime()), 
    ('Title', lambda x: '%s%s' % (x.title(), x.originalAirDate())), 
    ('Orig. Air Date', lambda x: x.originalAirDate())])

# ==============================================================================
class RecordingsWindow(BaseWindow):
        
    def __init__(self, *args, **kwargs):
        BaseWindow.__init__(self, *args, **kwargs)
        
        self.settings = kwargs['settings']
        self.translator = kwargs['translator']
        self.platform = kwargs['platform']
        self.fanArt = kwargs['fanArt']
        self.mythChannelIconCache = kwargs['cachesByName']['mythChannelIconCache']
        self.mythThumbnailCache = kwargs['cachesByName']['mythThumbnailCache']

        self.programs = []                       # [RecordedProgram]
        self.allPrograms = []                    # [RecordedProgram]
        self.programsByListItem = odict.odict()  # {ListItem:RecordedProgram}
        self.closed = False
        
        self.lastSelected = int(self.settings.get('recordings_last_selected'))
        
        self.sortBy = self.settings.get('recordings_sort_by')
        self.sortAscending = self.settings.getBoolean('recordings_sort_ascending')
        self.group = self.settings.get('recordings_recording_group')
        
    @catchall_ui
    def onInit(self):
        if not self.win:
            self.win = xbmcgui.Window(xbmcgui.getCurrentWindowId())
            self.programsListBox = self.getControl(ID_PROGRAMS_LISTBOX)
            self.refresh()

    def onFocus(self, controlId):
        self.lastFocusId = controlId
        
    @catchall_ui
    @lirc_hack    
    def onClick(self, controlId):
        #source = self.getControl(controlId)
        if controlId == ID_PROGRAMS_LISTBOX: 
            self.goRecordingDetails()
        elif controlId == ID_REFRESH_BUTTON:
            self.refresh()
        elif controlId == ID_SORT_BY_BUTTON:
            keys = SORT_BY.keys()
            self.sortBy = keys[(keys.index(self.sortBy) + 1) % len(keys)] 
            self.applySort()
        elif controlId == ID_SORT_ASCENDING_TOGGLE:
            self.sortAscending = not self.sortAscending
            self.applySort()
                             
    @catchall_ui
    @lirc_hack            
    def onAction(self, action):
        if action.getId() in (Action.PREVIOUS_MENU, Action.PARENT_DIR):
            self.closed = True
            self.settings.put('recordings_last_selected', '%d'%self.programsListBox.getSelectedPosition())
            self.settings.put('recordings_sort_by', self.sortBy)
            self.settings.put('recordings_sort_ascending', '%s' % self.sortAscending)
            self.settings.put('recordings_recording_group', self.group)
            self.close()
        
    @run_async
    @coalesce
    def preCacheThumbnails(self):
        if self.allPrograms:
            log.debug('Precaching thumbnails for %d recordings' % len(self.allPrograms))
            for program in self.allPrograms[:]:  # work on copy since async
                if self.closed: 
                    return
                try:
                    self.mythThumbnailCache.get(program)
                except:
                    log.exception('Thumbnail generation for recording %s failed' % program.title())

    @window_busy
    @inject_conn
    def refresh(self):
        self.allPrograms = self.conn().getAllRecordings()
        self.programs = self.allPrograms[:]
        
        # TODO: Recording group filter
        #self.programs = filter(lambda p: p.getRecordingGroup() == self.group, self.programs)
        
        self.programs.sort(key=SORT_BY[self.sortBy], reverse=self.sortAscending)
        self.preCacheThumbnails()
        self.render()
    
    def applySort(self):
        self.programs.sort(key=SORT_BY[self.sortBy], reverse=self.sortAscending)
        self.render()
        
#    def applyRecordingGroup(self):
#        self.programs = filter(lambda p: p.getRecordingGroup() == self.group, self.allPrograms)
#        self.render()
        
    @ui_locked
    def render(self):
        log.debug('Rendering....')
        self.renderNav()
        self.renderPrograms()
        self.renderPosters()
        
    def renderNav(self):
        self.setWindowProperty('sortBy', self.sortBy)
        self.setWindowProperty('sortAscending', ['false', 'true'][self.sortAscending])

    @timed
    def renderPrograms(self):        
        self.listItems = []
        self.programsByListItem.clear()
        
        @timed 
        def constructorTime(): 
            for i, p in enumerate(self.programs):
                listItem = xbmcgui.ListItem()
                self.listItems.append(listItem)
                self.programsByListItem[listItem] = p

        @timed 
        @ui_locked2
        def propertyTime(): 
            for i, p in enumerate(self.programs):
                listItem = self.listItems[i]
                self.setListItemProperty(listItem, 'title', p.fullTitle())
                self.setListItemProperty(listItem, 'date', p.formattedAirDate())
                self.setListItemProperty(listItem, 'time', p.formattedStartTime())
                self.setListItemProperty(listItem, 'poster', 'loading.gif')

        @timed
        def othertime():
            self.programsListBox.reset()
            self.programsListBox.addItems(self.listItems)
            self.programsListBox.selectItem(self.lastSelected)

        constructorTime()
        propertyTime()
        othertime()

    def renderProgramDeleted(self, deletedProgram, selectionIndex):
        # straight render() takes too long..shortcut for removal
        self.programs.remove(deletedProgram)
        deletedProgramsListItem = self.listItems[selectionIndex]
        del self.listItems[selectionIndex]
        del self.programsByListItem[deletedProgramsListItem]
        self.programsListBox.reset()
        self.programsListBox.addItems(self.listItems)
        self.programsListBox.selectItem(selectionIndex)
        
    @run_async
    @timed
    @catchall
    @coalesce
    def renderPosters(self):
        for i, (listItem, program) in enumerate(self.programsByListItem.items()[:]):
            if self.closed: 
                return
            #log.debug('Poster %d/%d for %s' % (i+1, len(self.programsByListItem), program.title()))
            posterPath = self.fanArt.getRandomPoster(program)
            if posterPath:
                self.setListItemProperty(listItem, 'poster', posterPath)
            else:
                self.setListItemProperty(listItem, 'poster', self.mythThumbnailCache.get(program))

    def goRecordingDetails(self):
        self.lastSelected = self.programsListBox.getSelectedPosition()
        selectedItem = self.programsListBox.getSelectedItem()
        if not selectedItem:
            return
        
        selectedProgram = self.programsByListItem[selectedItem]
        if not selectedProgram:
            return
        
        programIterator = CyclingBidiIterator(self.programs, self.lastSelected)
        
        win = RecordingDetailsWindow(
            'mythbox_recording_details.xml', 
            os.getcwd(), 
            forceFallback=True,
            programIterator=programIterator,
            settings=self.settings,
            translator=self.translator,
            platform=self.platform,
            mythThumbnailCache=self.mythThumbnailCache)
        win.doModal()

        if win.isDeleted:
            self.renderProgramDeleted(programIterator.current(), programIterator.index())
        elif programIterator.index() != self.lastSelected:
            self.programsListBox.selectItem(programIterator.index())
                
        del win
        