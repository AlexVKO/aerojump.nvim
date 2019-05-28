# ============================================================================
# FILE: yaj.py
# AUTHOR: Philip Karlsson <philipkarlsson at me.com>
# License: MIT license
# ============================================================================

import neovim
import os
import re

# Create utility function for getting output of a command.
# Use this to set the 'multifiletype' "set filetype={res}.yaj"
# that way syntax highlighting is preserverd even for yaj
# this utility can be borrowed for the fetching of the tabwidth
# too.

# Utility functions
#====================
def python_input(nvim, message = 'input'):
    nvim.command('call inputsave()')
    nvim.command("let user_input = input('" + message + ": ')")
    nvim.command('call inputrestore()')
    return nvim.eval('user_input')

# Utility classes
#====================
class YajLine(object):
    """ Class for a line in a yaj buffer """
    def __init__(self, line, num):
        # Raw text
        self.raw = line
        self.raw_lower = line.lower()
        # Line number
        self.num = num
        # Matches in this line
        self.matches = []

    def __score_matches(self, matches, pat_len):
        sorted_matches = []
        self.scores = []
        for m in matches:
            i = 0
            score = 1
            while i < len(m):
                num = m[i]
                c_match = [m[i]]
                while i < len(m) - 1 and m[i+1] - m[i] == 1:
                    c_match.append(m[i+1])
                    score += 1
                    i += 1
                i += 1
                if c_match not in sorted_matches:
                    sorted_matches.append(c_match)
            self.scores.append(score/pat_len)
        return sorted_matches

    def __find_whole_words(self, matches):
        whole_words = []
        for m in matches:
            i = 0
            while i < len(m) - 1 and m[i+1] - m[i] == 1:
                i += 1
            if i == len(m) - 1:
                whole_words.append(m)
        if whole_words != []:
            matches[:] = whole_words[:]

    def __match_from(self, matches, pattern, pat_index, word_index):
        for i in range(word_index, len(self.raw)):
            if self.raw_lower[i] == pattern[pat_index]:
                matches.append(i+1)
                next_pat_index = pat_index + 1
                next_word_index = i + 1
                # Final match in the pattern
                if next_pat_index == len(pattern):
                    return True
                # More characters to process
                elif next_word_index < len(self.raw_lower):
                    # Recursion :)
                    return self.__match_from(matches, pattern, next_pat_index, next_word_index)
                # No more characters left to process but pattern is complete
                else:
                    return False
        return False

    def filter(self, pattern):
        # Reset the matches
        self.matches = []

        for i in range(0, len(self.raw_lower)):
            # Reset the proposed matches
            proposed_matches = []
            # Start with last pattern c and last char of raw
            if self.raw_lower[i] == pattern[0]:
                if self.__match_from(proposed_matches, pattern, 0, i):
                    self.matches.append(proposed_matches)

        # 1.0 equals full match, thereafter fuzzy partials
        self.__score_matches(self.matches, len(pattern))

        # Sorting example fore future reference, the parent class
        # matches[:] = sorted_matches[:]
        # matches = matches.sort(key=len, reverse=True)



@neovim.plugin
class Yaj(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.logstr = []
        self.logstr.append('== Yaj debug ==')

    def log(self, s):
        self.logstr.append(str(s))

    def open_yaj_buf(self):
        self.nvim.command('split Yaj')
        self.nvim.command('setlocal buftype=nofile')
        self.nvim.command('setlocal filetype=yaj')

    def open_yaj_filter_buf(self):
        self.nvim.command('e YajFilter')
        self.nvim.command('setlocal buftype=nofile')
        self.nvim.command('setlocal filetype=YajFilter')

    def set_original_cursor_position(self):
        old_win = self.nvim.current.window
        self.nvim.current.window = self.main_win
        self.nvim.current.window.cursor = self.top_pos
        self.nvim.command('normal! zt')

        diff = self.current_pos[0] - self.top_pos[0]
        self.nvim.command('normal! %dj' % (diff))
        self.nvim.current.window = old_win

    def apply_filter(self, filter_string):
        for l in self.lines:
            l.filter(filter_string)
            if l.matches != []:
                self.log(l.raw)
            for m in l.matches:
                self.log(str(m))

    def get_lines(self, lines):
        ret = []
        for i, line in enumerate(lines):
            ret.append(YajLine(line, i+1))
        return ret

    def create_highlights(self):
        ret = []
        for l in self.lines:
            for m in l.matches:
                # TODO optimize
                for i in m:
                    # TODO Fix -1 offset bug for l.num
                    # TODO Fix offset error for tabs
                    ret.append(('SearchResult', l.num-1, i-1, i))
        return ret

    def draw_unfiltered(self):
        lines = []
        for l in self.lines:
            lines.append(l.raw)
        self.buf_ref[:] = lines[:]
        # Reset original cursor position
        self.set_original_cursor_position()
        self.buf_ref.clear_highlight(self.hl_source)

    def draw_filtered(self):
        lines = []
        for l in self.lines:
            if l.matches != []:
                lines.append(l.raw)
                for i, m in enumerate(l.matches):
                    continue
                    # Debug
                    lines.append(str(l.scores[i]))
                    lines.append(str(m))
            else:
                # Newlines or commenting text, will start with newlines
                lines.append('')
        self.buf_ref[:] = lines[:]
        hl = self.create_highlights()
        self.log(hl)
        self.buf_ref.update_highlights(self.hl_source, hl, clear=True)
        # TODO cont here: create system for moving around between filter matches
        # move based on score for each line, change highlight depending on if the marker is there
        # yet

    def draw(self):
        """ Draw function of the plugin """
        if self.filter_string == '':
            self.draw_unfiltered()
        else:
            self.draw_filtered()

    @neovim.autocmd("TextChangedI", pattern='YajFilter', sync=True)
    def insert_changed(self):
        """ Process filter input """
        self.filter_string = self.nvim.current.line
        if self.filter_string != '':
            self.apply_filter(self.filter_string)
        self.draw()

    @neovim.command("Yaj", range='', nargs='*', sync=True)
    def yaj(self, args, range):
        self.hl_source = self.nvim.new_highlight_source()
        buf = self.nvim.current.buffer
        window = self.nvim.current.window

        # Height could be used to optimize performance?
        window_height = window.height

        # Sample positions
        self.current_pos = window.cursor
        self.nvim.command('normal! H')
        self.top_pos = window.cursor
        self.nvim.command('normal! L')

        # Spawn the filter buffer
        self.open_yaj_filter_buf()

        # Spawn the yaj buffer
        self.open_yaj_buf()

        new_buf = self.nvim.current.buffer
        # Paste the lines of the old buffer to the new
        new_buf[:] = buf[:]

        # Create lines
        self.lines = self.get_lines(new_buf)

        # Fetch current tabstop
        # needed in order to convert character
        # position to vim position
        self.nvim.command('redir @a')
        self.nvim.command('set tabstop?')
        self.nvim.command('redir END')
        self.tabstop = [int(s) for s in self.nvim.eval('@a').strip('\n').split('=') if s.isdigit()][0]

        # Reference to the text buffer
        self.buf_ref = new_buf

        # Update position
        self.main_win = self.nvim.current.window

        # Go back to the input buffer window
        self.nvim.command('wincmd j')
        self.nvim.current.window.height = 1
        self.nvim.command("startinsert!")

        # Reset the filter string
        self.filter_string = ''
        self.draw()
        self.set_original_cursor_position()

    @neovim.command("YayShowLog", range='', nargs='*', sync=True)
    def YajShowLog(self, args, range):
        self.nvim.command('e Yaj_log')
        self.nvim.command('setlocal buftype=nofile')
        self.nvim.command('setlocal filetype=yaj_log')
        self.nvim.current.buffer.append(self.logstr)
        #self.nvim.current.buffer.append('== Lines Log ==')
        #for i in self.lines:
            # Add log for each line
        #    self.nvim.current.buffer.append(i.logstr)

